"""Retrieval lexical (BM25-like) sobre chunks de PDF.

v2.1: aceita ``Chunk`` (preferido) ou ``PDFSection`` (compat). Internamente
indexa qualquer objecto com atributos ``body`` e ``title`` (duck-typed) OU
``text`` e ``section_title``.

A implementação BM25 é minimalista (sem `rank_bm25`) para manter zero deps
extras. Para corpus >1000 documentos, considerar trocar por `rank_bm25`.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Union

from backend.pdf import Chunk, PDFSection

Doc = Union[Chunk, PDFSection]

_TOKEN = re.compile(r"[a-zà-ÿ0-9]+", re.IGNORECASE)
_STOPWORDS = {
    "a", "o", "as", "os", "de", "da", "do", "das", "dos", "em", "para",
    "com", "por", "que", "é", "são", "no", "na", "nos", "nas", "um",
    "uma", "se", "ao", "à", "às", "aos", "ou", "e", "mas", "como",
}


def _tokenize(text: str) -> list[str]:
    nfkd = unicodedata.normalize("NFKD", text.lower())
    flat = "".join(c for c in nfkd if not unicodedata.combining(c))
    return [t for t in _TOKEN.findall(flat) if t not in _STOPWORDS and len(t) > 2]


def _doc_text(doc: Doc) -> str:
    """Extrai texto+título de Chunk ou PDFSection de forma uniforme."""
    if isinstance(doc, Chunk):
        return f"{doc.section_title} {doc.text}"
    # PDFSection
    return f"{doc.title} {doc.body}"


@dataclass
class ScoredDoc:
    doc: Doc
    score: float


@dataclass
class LexicalRetriever:
    k1: float = 1.5
    b: float = 0.75
    top_k: int = 6

    _tokens: list[list[str]] = field(default_factory=list)
    _docs: list[Doc] = field(default_factory=list)
    _avgdl: float = 0.0
    _df: Counter = field(default_factory=Counter)

    def index(self, docs: Iterable[Doc]) -> None:
        self._docs = list(docs)
        self._tokens = [_tokenize(_doc_text(d)) for d in self._docs]
        self._avgdl = sum(len(t) for t in self._tokens) / max(len(self._tokens), 1)
        self._df = Counter()
        for toks in self._tokens:
            for term in set(toks):
                self._df[term] += 1

    def search(self, query: str, *, top_k: int | None = None) -> list[Doc]:
        return [s.doc for s in self.search_scored(query, top_k=top_k)]

    def search_scored(self, query: str, *, top_k: int | None = None) -> list[ScoredDoc]:
        if not self._docs:
            return []
        q_tokens = _tokenize(query)
        if not q_tokens:
            return [ScoredDoc(d, 0.0) for d in self._docs[: top_k or self.top_k]]

        N = len(self._docs)
        results: list[ScoredDoc] = []
        for i, doc_tokens in enumerate(self._tokens):
            doc_len = len(doc_tokens) or 1
            counter = Counter(doc_tokens)
            score = 0.0
            for term in q_tokens:
                f = counter.get(term, 0)
                if f == 0:
                    continue
                idf = math.log(
                    (N - self._df[term] + 0.5) / (self._df[term] + 0.5) + 1.0
                )
                tf = f * (self.k1 + 1) / (
                    f + self.k1 * (1 - self.b + self.b * doc_len / max(self._avgdl, 1))
                )
                score += idf * tf
            if score > 0:
                results.append(ScoredDoc(self._docs[i], score))

        results.sort(key=lambda s: s.score, reverse=True)
        return results[: top_k or self.top_k]
