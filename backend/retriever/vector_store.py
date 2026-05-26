"""Vector store baseado em ChromaDB (v2.1 — P2).

ChromaDB é lazy-imported: se não estiver instalado, cai num backend JSON
simples (cosine puro) — útil para testes unitários sem deps pesadas.

A interface é minimalista e desacoplada do Chroma para poder trocar por
FAISS ou Qdrant no futuro sem mexer no resto do código.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol

from backend.observability import get_logger
from backend.pdf import Chunk

log = get_logger(__name__)


class VectorStore(Protocol):
    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None: ...
    def query(self, embedding: list[float], top_k: int,
              where: Optional[dict] = None) -> list[tuple[Chunk, float]]: ...
    def count(self) -> int: ...
    def reset(self) -> None: ...


# ==========================================================================
# Backend 1: ChromaDB (preferido — persistente, com filtros metadata)
# ==========================================================================

class ChromaVectorStore:
    """Persistente em disco. Cada chunk vira 1 documento Chroma."""

    def __init__(self, persist_dir: Path, collection: str = "medvet_chunks") -> None:
        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError(
                "chromadb não instalado. Execute: pip install chromadb"
            ) from exc

        persist_dir = Path(persist_dir)
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        # cosine + hnsw (default Chroma) é o que queremos
        self._collection = self._client.get_or_create_collection(
            name=collection,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        if not chunks:
            return
        if len(chunks) != len(embeddings):
            raise ValueError("chunks e embeddings devem ter o mesmo tamanho")

        ids = [self._chunk_id(c) for c in chunks]
        metadatas = [self._chunk_metadata(c) for c in chunks]
        documents = [c.text for c in chunks]
        self._collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )
        log.debug("Chroma upsert: +%d chunks (total=%d)", len(chunks), self.count())

    def query(self, embedding: list[float], top_k: int,
              where: Optional[dict] = None) -> list[tuple[Chunk, float]]:
        # Chroma aceita where={"medicamento": "Senvelgo"} — filtro pré-retrieval
        kwargs = {
            "query_embeddings": [embedding],
            "n_results": top_k,
        }
        if where:
            kwargs["where"] = where
        res = self._collection.query(**kwargs)
        ids = res["ids"][0] if res["ids"] else []
        docs = res["documents"][0] if res["documents"] else []
        metas = res["metadatas"][0] if res["metadatas"] else []
        dists = res["distances"][0] if res["distances"] else []

        out: list[tuple[Chunk, float]] = []
        for _id, doc, meta, dist in zip(ids, docs, metas, dists):
            chunk = self._chunk_from_meta(text=doc, meta=meta)
            # Chroma devolve "distance"; convertemos em similaridade [0,1]
            similarity = max(0.0, 1.0 - dist)
            out.append((chunk, similarity))
        return out

    def count(self) -> int:
        return self._collection.count()

    def reset(self) -> None:
        self._client.delete_collection(self._collection.name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection.name,
            metadata={"hnsw:space": "cosine"},
        )

    @staticmethod
    def _chunk_id(c: Chunk) -> str:
        return f"{c.source_pdf}::{c.section_num}::{c.paragraph_idx}::{hash(c.text)}"

    @staticmethod
    def _chunk_metadata(c: Chunk) -> dict:
        return {
            "section_num": c.section_num or "",
            "section_title": c.section_title or "",
            "paragraph_idx": int(c.paragraph_idx),
            "is_table": bool(c.is_table),
            "page": c.page if c.page is not None else -1,
            "source_pdf": c.source_pdf or "",
            "medicamento": c.medicamento or "",
            "char_count": int(c.char_count),
        }

    @staticmethod
    def _chunk_from_meta(text: str, meta: dict) -> Chunk:
        return Chunk(
            text=text,
            section_num=meta.get("section_num", ""),
            section_title=meta.get("section_title", ""),
            paragraph_idx=int(meta.get("paragraph_idx", 0)),
            is_table=bool(meta.get("is_table", False)),
            page=None if meta.get("page", -1) == -1 else int(meta["page"]),
            source_pdf=meta.get("source_pdf") or None,
            medicamento=meta.get("medicamento") or None,
            char_count=int(meta.get("char_count", len(text))),
        )


# ==========================================================================
# Backend 2: In-memory cosine (fallback sem deps — usado em testes)
# ==========================================================================

def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


@dataclass
class InMemoryVectorStore:
    _chunks: list[Chunk] = field(default_factory=list)
    _vectors: list[list[float]] = field(default_factory=list)

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks e embeddings devem ter o mesmo tamanho")
        self._chunks.extend(chunks)
        self._vectors.extend(embeddings)

    def query(self, embedding: list[float], top_k: int,
              where: Optional[dict] = None) -> list[tuple[Chunk, float]]:
        scored = []
        for c, v in zip(self._chunks, self._vectors):
            if where and not self._match(c, where):
                continue
            scored.append((c, _cosine(embedding, v)))
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[:top_k]

    def count(self) -> int:
        return len(self._chunks)

    def reset(self) -> None:
        self._chunks.clear()
        self._vectors.clear()

    @staticmethod
    def _match(c: Chunk, where: dict) -> bool:
        for k, v in where.items():
            if getattr(c, k, None) != v:
                return False
        return True


# ==========================================================================
# Factory
# ==========================================================================

def get_vector_store(persist_dir: Optional[Path] = None,
                     collection: str = "medvet_chunks") -> VectorStore:
    """Retorna ChromaVectorStore se chromadb estiver instalado; senão InMemory."""
    if persist_dir is None:
        return InMemoryVectorStore()
    try:
        return ChromaVectorStore(persist_dir, collection=collection)
    except RuntimeError as exc:
        log.warning("Chroma indisponível (%s) — usando InMemoryVectorStore", exc)
        return InMemoryVectorStore()


__all__ = ["VectorStore", "ChromaVectorStore", "InMemoryVectorStore", "get_vector_store"]
