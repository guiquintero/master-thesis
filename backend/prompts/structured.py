"""Parsing tolerante do output JSON estruturado do LLM (P5 — Sprint v2.1).

LLMs locais frequentemente devolvem JSON com pequenos defeitos:
- texto antes/depois do `{...}`
- aspas curvas em vez de ASCII
- vírgula final
- chaves não escapadas dentro de strings

Este módulo absorve todos esses problemas e devolve um ``LLMResponse``
tipado. Se nada salvável vier do LLM, devolve fallback consistente.

ANTES (v2.0):
    LLM devolvia texto livre; código procurava \"não encontrei\" com regex
    para decidir se a resposta era vaga. Sem confiança quantitativa.

DEPOIS (v2.1):
    LLM devolve JSON tipado com ``encontrada_no_documento``, ``confianca`` e
    lista de ``fontes``. Pipeline pode decidir re-promptar (P4) com base em
    sinais explícitos.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from backend.observability import get_logger

log = get_logger(__name__)


@dataclass
class Source:
    secao: str = ""
    trecho: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Source":
        return cls(secao=str(d.get("secao", "")), trecho=str(d.get("trecho", "")))


@dataclass
class LLMResponse:
    resposta: str = ""
    encontrada_no_documento: bool = False
    confianca: float = 0.0
    fontes: list[Source] = field(default_factory=list)
    raw: str = ""               # texto bruto recebido do LLM
    parse_ok: bool = True       # False se houve fallback

    def needs_reprompt(self, *, min_confidence: float = 0.55) -> bool:
        """Sinaliza ao pipeline que vale a pena tentar com mais contexto."""
        if not self.parse_ok:
            return True
        # v2.1.1: resposta vazia (LLM preencheu só fontes e esqueceu o campo
        # principal) também pede re-prompt.
        if not (self.resposta or "").strip():
            return True
        if not self.encontrada_no_documento:
            return True
        return self.confianca < min_confidence


# Regex para extrair o primeiro objecto JSON balanceado da string.
_JSON_BLOB = re.compile(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", re.DOTALL)
_CURLY_QUOTE_MAP = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"})


def _strip_code_fences(text: str) -> str:
    return re.sub(r"```(?:json)?\s*|\s*```", "", text, flags=re.IGNORECASE)


def _try_parse(text: str) -> Any:
    return json.loads(text)


def parse_llm_response(raw: str) -> LLMResponse:
    """Devolve um ``LLMResponse``. Nunca levanta excepção."""
    text = (raw or "").strip()
    if not text:
        return LLMResponse(raw=raw, parse_ok=False,
                           resposta="Informação não encontrada no documento.")

    text = _strip_code_fences(text).translate(_CURLY_QUOTE_MAP)

    # Tentativa 1: parse directo
    candidates = []
    try:
        candidates.append(_try_parse(text))
    except json.JSONDecodeError:
        pass

    # Tentativa 2: primeiro {...} encontrado
    if not candidates:
        m = _JSON_BLOB.search(text)
        if m:
            try:
                candidates.append(_try_parse(m.group(0)))
            except json.JSONDecodeError:
                # Limpa vírgulas finais e re-tenta
                cleaned = re.sub(r",\s*([}\]])", r"\1", m.group(0))
                try:
                    candidates.append(_try_parse(cleaned))
                except json.JSONDecodeError:
                    pass

    if not candidates or not isinstance(candidates[0], dict):
        log.warning("LLM output não-JSON, usando como texto bruto. raw=%r", raw[:200])
        return LLMResponse(
            raw=raw,
            parse_ok=False,
            resposta=text[:2000],
            encontrada_no_documento=False,
            confianca=0.2,
        )

    data = candidates[0]
    fontes_raw = data.get("fontes") or []
    if not isinstance(fontes_raw, list):
        fontes_raw = []

    try:
        confianca = float(data.get("confianca", 0.5))
    except (TypeError, ValueError):
        confianca = 0.5
    confianca = max(0.0, min(1.0, confianca))

    return LLMResponse(
        resposta=str(data.get("resposta", "")).strip(),
        encontrada_no_documento=bool(data.get("encontrada_no_documento", True)),
        confianca=confianca,
        fontes=[Source.from_dict(f) for f in fontes_raw if isinstance(f, dict)],
        raw=raw,
        parse_ok=True,
    )


def render_for_user(response: LLMResponse, *, include_sources: bool = True) -> str:
    """Renderiza um LLMResponse como texto markdown para o utilizador final.

    v2.1.1: se ``resposta`` veio vazia mas há fontes, sintetiza uma resposta a
    partir dos trechos disponíveis (em vez de devolver "Não foi possível…").
    """
    main = (response.resposta or "").strip()
    if not main and response.fontes:
        # Síntese mínima a partir das fontes (último recurso útil)
        trechos = [
            (f.trecho or "").strip()
            for f in response.fontes
            if (f.trecho or "").strip()
        ]
        if trechos:
            main = "Segundo o documento:\n\n" + "\n\n".join(
                t if len(t) <= 600 else t[:600] + "…" for t in trechos
            )
    if not main:
        main = "Não foi possível gerar resposta."

    out = main
    if include_sources and response.fontes:
        out += "\n\nFontes (excertos):"
        for f in response.fontes:
            label = f.secao or "(secção)"
            trecho = (f.trecho or "").strip()
            if trecho:
                trecho_short = trecho if len(trecho) <= 250 else trecho[:250] + "…"
                out += f"\n- **{label}**: {trecho_short}"
            else:
                out += f"\n- **{label}**"
    return out
