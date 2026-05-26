"""Retrieval híbrido — BM25 (lexical) + denso (embeddings), fundidos por RRF.

v2.1 (P2). Combina o melhor dos dois mundos:
  - Lexical: ganha quando a query usa o vocabulário exacto do documento
    (ex.: "Senvelgo 15 mg/ml" — match literal).
  - Denso: ganha quando a query é semanticamente próxima mas não-literal
    (ex.: "dose para felinos" ↔ "posologia em gatos").

# Reciprocal Rank Fusion (RRF)

  score_rrf(d) = Σ_r 1 / (k + rank_r(d))

onde r é cada retriever (lexical, denso) e ``k`` é uma constante
(60 é o valor canónico do paper Cormack 2009).

Vantagens vs. soma ponderada de scores:
  - Não exige normalização de scores (BM25 e cosseno têm escalas diferentes)
  - Robusto a outliers
  - Trivial de implementar
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from backend.observability import get_logger
from backend.pdf import Chunk, PDFSection
from backend.retriever.dense import DenseRetriever
from backend.retriever.lexical import LexicalRetriever, ScoredDoc

log = get_logger(__name__)


@dataclass
class HybridRetriever:
    """Combina lexical (BM25) + denso (embeddings) via RRF.

    O denso é opcional: se ``dense`` for None, comporta-se como o lexical puro.
    Isso permite degradação graciosa quando Ollama embed model não está
    disponível.
    """

    lexical: LexicalRetriever = field(default_factory=LexicalRetriever)
    dense: Optional[DenseRetriever] = None
    rrf_k: int = 60
    top_k: int = 6
    # Threshold de similaridade no retriever denso (0..1). Chunks abaixo são
    # descartados (não entram na fusão). Default permissivo.
    dense_min_similarity: float = 0.30

    # ----------------------------------------------------------------- index

    def index(self, chunks: list[Chunk]) -> None:
        self.lexical.index(chunks)
        if self.dense is not None:
            self.dense.index(chunks)

    # ----------------------------------------------------------------- search

    def search(
        self,
        query: str,
        *,
        top_k: Optional[int] = None,
        where: Optional[dict] = None,
    ) -> list[Chunk]:
        return [s.doc for s in self.search_scored(query, top_k=top_k, where=where)]

    def search_scored(
        self,
        query: str,
        *,
        top_k: Optional[int] = None,
        where: Optional[dict] = None,
    ) -> list[ScoredDoc]:
        k = top_k or self.top_k

        lex_results = self.lexical.search_scored(query, top_k=k * 3)
        dense_results: list[tuple[Chunk, float]] = []
        if self.dense is not None:
            dense_results = self.dense.search(query, top_k=k * 3, where=where)
            dense_results = [
                (c, sim) for c, sim in dense_results
                if sim >= self.dense_min_similarity
            ]

        if not dense_results:
            log.debug("Hybrid: denso vazio/desligado, devolvendo só lexical")
            return lex_results[:k]
        if not lex_results:
            log.debug("Hybrid: lexical vazio, devolvendo só denso")
            return [ScoredDoc(c, s) for c, s in dense_results[:k]]

        # RRF
        rrf_scores: dict[int, float] = defaultdict(float)
        chunk_by_id: dict[int, Chunk] = {}

        for rank, sd in enumerate(lex_results):
            cid = self._id(sd.doc)
            rrf_scores[cid] += 1.0 / (self.rrf_k + rank + 1)
            chunk_by_id[cid] = sd.doc  # type: ignore[assignment]

        for rank, (c, _sim) in enumerate(dense_results):
            cid = self._id(c)
            rrf_scores[cid] += 1.0 / (self.rrf_k + rank + 1)
            chunk_by_id.setdefault(cid, c)

        ranked = sorted(rrf_scores.items(), key=lambda kv: kv[1], reverse=True)
        return [ScoredDoc(chunk_by_id[cid], score) for cid, score in ranked[:k]]

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _id(doc) -> int:
        """ID único para fusão — funciona tanto para Chunk como PDFSection."""
        if isinstance(doc, Chunk):
            return hash((doc.source_pdf, doc.section_num, doc.paragraph_idx, doc.text[:100]))
        # PDFSection
        if isinstance(doc, PDFSection):
            return hash((doc.number, doc.title, doc.body[:100]))
        return hash(str(doc))
