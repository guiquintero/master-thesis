"""Cliente Ollama com timeout, retry e suporte a JSON-mode.

Características:
- Configurado por `Settings`
- Suporta `format="json"` para extrações estruturadas
- Implementa `embed()` para retrieval semântico
- Política de retry exponencial em falhas de rede
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Protocol

import ollama

from backend.config import get_settings
from backend.llm.language_guard import LanguageGuard
from backend.observability import get_logger

log = get_logger(__name__)


class LLMClient(Protocol):
    def chat(self, messages: list[dict], **opts: Any) -> str: ...
    def embed(self, texts: Iterable[str]) -> list[list[float]]: ...


@dataclass
class OllamaClient:
    """Wrapper único (substitui o `OllamaWrapperSeguro` antigo).

    Diferenças vs. wrapper antigo:
    - System prompt curto e claro em pt-PT (sem CAPS/emojis).
    - Detecção de idioma desacoplada (módulo `language_guard`).
    - JSON mode opcional.
    - Sem `3 tentativas de prompts cada vez mais agressivos` — em vez disso,
      uma única retentativa com sinalização explícita e fallback do chamador.
    """

    model: Optional[str] = None
    embed_model: Optional[str] = None
    temperature: Optional[float] = None
    timeout_s: Optional[int] = None
    num_predict: Optional[int] = None
    enforce_portuguese: bool = True

    def __post_init__(self) -> None:
        s = get_settings()
        self.model = self.model or s.ollama_model
        self.embed_model = self.embed_model or s.ollama_embed_model
        self.temperature = self.temperature if self.temperature is not None else s.ollama_temperature
        self.timeout_s = self.timeout_s or s.ollama_timeout_s
        self.num_predict = self.num_predict or s.ollama_num_predict
        self._guard = LanguageGuard()
        # Cliente nativo do pacote `ollama` lê OLLAMA_HOST do env

    # ----------------------------------------------------------------- chat

    def chat(
        self,
        messages: list[dict],
        *,
        json_mode: bool = False,
        temperature: Optional[float] = None,
        num_predict: Optional[int] = None,
        retries: int = 1,
    ) -> str:
        msgs = self._ensure_system(messages)
        options = {
            "temperature": float(temperature if temperature is not None else self.temperature),
            "num_predict": int(num_predict or self.num_predict),
        }

        last_exc: Optional[BaseException] = None
        for attempt in range(retries + 1):
            try:
                kwargs: dict[str, Any] = {
                    "model": self.model,
                    "messages": msgs,
                    "options": options,
                }
                if json_mode:
                    kwargs["format"] = "json"
                resp = ollama.chat(**kwargs)
                content = self._extract(resp)
                if not content:
                    raise RuntimeError("Resposta vazia do Ollama")

                if self.enforce_portuguese and not json_mode:
                    ok, reason = self._guard.check(content)
                    if not ok:
                        log.warning("Idioma fora do esperado (%s) — retentando", reason)
                        if attempt < retries:
                            # Reforça pedido em PT na próxima tentativa, sem CAPS.
                            msgs = self._reinforce_portuguese(msgs)
                            continue
                        # Última tentativa: tenta tradução determinística como fallback.
                        return self._translate_to_portuguese(content)
                return content

            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                wait = 0.5 * (2**attempt)
                log.warning("Falha chat Ollama (tentativa %d): %s — aguardando %.1fs",
                            attempt + 1, exc, wait)
                time.sleep(wait)

        raise RuntimeError(f"Falha persistente no chat Ollama: {last_exc!r}")

    # ----------------------------------------------------------------- embed

    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for t in texts:
            resp = ollama.embeddings(model=self.embed_model, prompt=t)
            vec = resp.get("embedding") if isinstance(resp, dict) else None
            if not vec:
                raise RuntimeError(f"Embedding vazio para texto: {t[:60]!r}")
            out.append(vec)
        return out

    # ----------------------------------------------------------------- utils

    @staticmethod
    def _extract(resp: Any) -> Optional[str]:
        if isinstance(resp, str):
            return resp
        if isinstance(resp, dict):
            msg = resp.get("message")
            if isinstance(msg, dict):
                return msg.get("content")
            if "content" in resp:
                return resp["content"]
        # Pacote `ollama` >=0.3 retorna objetos com atributo .message
        msg = getattr(resp, "message", None)
        if msg is not None:
            content = getattr(msg, "content", None)
            if content:
                return content
        return None

    @staticmethod
    def _ensure_system(messages: list[dict]) -> list[dict]:
        from backend.prompts.system import SYSTEM_PROMPT_PT

        has_system = any(m.get("role") == "system" for m in messages)
        if has_system:
            return messages
        return [{"role": "system", "content": SYSTEM_PROMPT_PT}] + messages

    @staticmethod
    def _reinforce_portuguese(messages: list[dict]) -> list[dict]:
        reinforced = []
        for m in messages:
            if m.get("role") == "system":
                m = dict(m)
                m["content"] = (
                    m.get("content", "")
                    + "\n\nNota: a resposta anterior estava em outro idioma. "
                    "Responda obrigatoriamente em português europeu (pt-PT)."
                )
            reinforced.append(m)
        return reinforced

    def _translate_to_portuguese(self, text: str) -> str:
        try:
            resp = ollama.chat(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Traduza o texto a seguir para português europeu. Não adicione comentários.",
                    },
                    {"role": "user", "content": text},
                ],
                options={"temperature": 0.0, "num_predict": int(self.num_predict)},
            )
            return self._extract(resp) or text
        except Exception:  # noqa: BLE001
            log.warning("Tradução de fallback falhou; devolvendo texto original")
            return text
