"""Retrieval semântico via embeddings Ollama (TIER 2 — opcional).

Activado apenas se `RETRIEVER_USE_EMBEDDINGS=true` no .env. Requer o modelo
de embedding instalado no Ollama (ex.: `ollama pull nomic-embed-text`).

O índice é armazenado em ficheiro JSON simples — adequado a bulas (corpus
pequeno). Para escalar (catálogo MedVet completo) trocar por Chroma/FAISS.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from backend.cache import DiskKVStore, KVStore, make_key
from backend.config import get_settings
from backend.llm import OllamaClient
from backend.observability import get_logger
from backend.pdf import PDFSection

log = get_logger(__name__)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


@dataclass
class EmbeddingRetriever:
    """RAG simples sobre as secções do PDF."""

    llm: OllamaClient
    cache: Optional[KVStore] = None
    top_k: int = 6
    _vectors: list[list[float]] = field(default_factory=list)
    _sections: list[PDFSection] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.cache is None:
            self.cache = DiskKVStore(get_settings().cache_dir / "embeddings")

    def index(self, sections: list[PDFSection]) -> None:
        self._sections = sections
        self._vectors = []
        texts_to_embed: list[tuple[int, str]] = []

        for i, sec in enumerate(sections):
            key = make_key("emb", sec.number, sec.title, sec.body[:200])
            cached = self.cache.get(key) if self.cache else None
            if cached:
                self._vectors.append(cached)
            else:
                texts_to_embed.append((i, sec.to_text()))
                self._vectors.append([])  # placeholder

        if not texts_to_embed:
            return

        try:
            vectors = self.llm.embed(t for _, t in texts_to_embed)
        except Exception as exc:  # noqa: BLE001
            log.warning("Embedding falhou (%s) — RAG ficará vazio nesta sessão", exc)
            return

        for (idx, _), vec in zip(texts_to_embed, vectors):
            self._vectors[idx] = vec
            if self.cache:
                sec = sections[idx]
                key = make_key("emb", sec.number, sec.title, sec.body[:200])
                self.cache.set(key, vec)

    def search(self, query: str, *, top_k: int | None = None) -> list[PDFSection]:
        if not self._vectors:
            return []
        try:
            qvec = self.llm.embed([query])[0]
        except Exception as exc:  # noqa: BLE001
            log.warning("Embedding da query falhou: %s", exc)
            return []
        scored = [(_cosine(qvec, v), i) for i, v in enumerate(self._vectors) if v]
        scored.sort(reverse=True)
        keep = top_k or self.top_k
        return [self._sections[i] for _, i in scored[:keep]]


def save_index(path: Path, vectors: list[list[float]], sections: list[PDFSection]) -> None:
    payload = {
        "vectors": vectors,
        "sections": [
            {"number": s.number, "title": s.title, "body": s.body, "has_table": s.has_table}
            for s in sections
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def load_index(path: Path) -> tuple[list[list[float]], list[PDFSection]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    secs = [PDFSection(**s) for s in payload["sections"]]
    return payload["vectors"], secs
