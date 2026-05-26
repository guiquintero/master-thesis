"""Testes do HybridRetriever + InMemoryVectorStore (P2 — v2.1).

Não precisa de Ollama: usa fake LLM que devolve embeddings determinísticos.
"""

from typing import Iterable

from backend.pdf import Chunk
from backend.retriever import (
    DenseRetriever,
    HybridRetriever,
    InMemoryVectorStore,
    LexicalRetriever,
)


class _FakeLLM:
    """Embedding fake: vector = bag-of-words sobre vocabulário fixo."""

    model = "fake"
    embed_model = "fake-embed"

    _VOCAB = [
        "dose", "gatos", "cães", "mg", "kg", "armazenamento",
        "temperatura", "posologia", "indicação", "espécies",
    ]

    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        out = []
        for t in texts:
            tl = t.lower()
            out.append([1.0 if w in tl else 0.0 for w in self._VOCAB])
        return out


def _chunks():
    return [
        Chunk(text="Dose: 1 mg/kg para gatos.", section_num="4.9",
              section_title="Posologia", paragraph_idx=0),
        Chunk(text="Conservar a 25°C, armazenamento ao abrigo da luz.",
              section_num="6.4", section_title="Conservação", paragraph_idx=0),
        Chunk(text="Indicação: tratamento de cães adultos.",
              section_num="4.2", section_title="Indicações", paragraph_idx=0),
    ]


def test_hybrid_finds_dose_with_lexical_only():
    h = HybridRetriever(lexical=LexicalRetriever(top_k=2), dense=None)
    h.index(_chunks())
    results = h.search("qual a dose para gatos")
    assert results
    assert "1 mg/kg" in results[0].text


def test_hybrid_finds_dose_with_dense():
    fake_llm = _FakeLLM()
    dense = DenseRetriever(
        llm=fake_llm,                       # type: ignore[arg-type]
        store=InMemoryVectorStore(),
        embed_cache=None,
        top_k=3,
    )
    h = HybridRetriever(
        lexical=LexicalRetriever(top_k=3),
        dense=dense,
        top_k=2,
        dense_min_similarity=0.0,
    )
    chunks = _chunks()
    h.index(chunks)
    results = h.search("dose gatos")
    assert results
    assert "1 mg/kg" in results[0].text


def test_in_memory_vector_store_metadata_filter():
    store = InMemoryVectorStore()
    chunks = _chunks()
    fake = _FakeLLM()
    vecs = fake.embed([c.text for c in chunks])
    store.upsert(chunks, vecs)

    qvec = fake.embed(["armazenamento"])[0]
    res = store.query(qvec, top_k=10, where={"section_num": "6.4"})
    assert len(res) == 1
    assert res[0][0].section_num == "6.4"


def test_rrf_combines_when_both_have_results():
    fake_llm = _FakeLLM()
    dense = DenseRetriever(
        llm=fake_llm,                       # type: ignore[arg-type]
        store=InMemoryVectorStore(),
        embed_cache=None,
        top_k=3,
    )
    h = HybridRetriever(
        lexical=LexicalRetriever(top_k=3),
        dense=dense,
        top_k=3,
        dense_min_similarity=0.0,
    )
    h.index(_chunks())
    # Pergunta semanticamente próxima de "armazenamento"
    results = h.search("temperatura armazenamento")
    assert results
    assert "Conservar" in results[0].text or "armazen" in results[0].text.lower()
