"""Retrieval semântico via embeddings (Ollama) + vector store.

v2.1 (P2). Substitui o `EmbeddingRetriever` JSON-baseado da v2.0.

Modelo de embedding configurável via ``OLLAMA_EMBED_MODEL``.
Recomendado: ``bge-m3`` (multilíngue forte, 8k contexto) ou ``nomic-embed-text``.

ANTES vs DEPOIS:

  Antes (v2.0):
    EmbeddingRetriever in-memory, índice JSON, sem filtros metadata, sem
    persistência entre sessões. Indexava por sessão de utilizador.

  Depois (v2.1):
    DenseRetriever encapsula vector store (Chroma persistente) + cache de
    embeddings. Filtros metadata pré-retrieval (medicamento, secção).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from backend.cache import DiskKVStore, KVStore, make_key
from backend.config import get_settings
from backend.llm import OllamaClient
from backend.observability import get_logger
from backend.pdf import Chunk
from backend.retriever.vector_store import (
    InMemoryVectorStore,
    VectorStore,
    get_vector_store,
)

log = get_logger(__name__)


@dataclass
class DenseRetriever:
    """RAG denso com vector store + cache de embeddings."""

    llm: OllamaClient
    store: VectorStore = None  # type: ignore[assignment]
    embed_cache: Optional[KVStore] = None
    top_k: int = 6

    def __post_init__(self) -> None:
        s = get_settings()
        if self.store is None:
            self.store = get_vector_store(s.index_dir / "chroma")
        if self.embed_cache is None:
            self.embed_cache = DiskKVStore(s.cache_dir / "embeddings")

    # ----------------------------------------------------------------- index

    def index(self, chunks: list[Chunk]) -> int:
        """Indexa chunks no vector store. Embeddings vêm do cache se já existirem.

        Retorna nº de chunks novos efectivamente embeddados (não vindos do cache).
        """
        if not chunks:
            return 0

        # Decide o que precisa ser embeddado.
        cached_vecs: dict[int, list[float]] = {}
        to_embed_idx: list[int] = []
        for i, c in enumerate(chunks):
            key = self._embed_key(c)
            cached = self.embed_cache.get(key) if self.embed_cache else None
            if cached:
                cached_vecs[i] = cached
            else:
                to_embed_idx.append(i)

        # Embedda os faltantes.
        if to_embed_idx:
            log.info("Embed: %d novos chunks (modelo=%s)",
                     len(to_embed_idx), self.llm.embed_model)
            try:
                new_vecs = self.llm.embed([chunks[i].text for i in to_embed_idx])
            except Exception as exc:  # noqa: BLE001
                log.error("Falha a embeddar: %s", exc)
                return 0
            for i, v in zip(to_embed_idx, new_vecs):
                cached_vecs[i] = v
                if self.embed_cache:
                    self.embed_cache.set(self._embed_key(chunks[i]), v)

        # Reagrupa na ordem original.
        all_vecs = [cached_vecs[i] for i in range(len(chunks))]
        self.store.upsert(chunks, all_vecs)
        return len(to_embed_idx)

    # ----------------------------------------------------------------- query

    def search(
        self,
        query: str,
        *,
        top_k: Optional[int] = None,
        where: Optional[dict] = None,
    ) -> list[tuple[Chunk, float]]:
        try:
            qvec = self.llm.embed([query])[0]
        except Exception as exc:  # noqa: BLE001
            log.warning("Embedding da query falhou: %s", exc)
            return []
        return self.store.query(qvec, top_k or self.top_k, where=where)

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _embed_key(c: Chunk) -> str:
        return make_key("emb", c.source_pdf or "", c.section_num, c.paragraph_idx, c.text[:200])
