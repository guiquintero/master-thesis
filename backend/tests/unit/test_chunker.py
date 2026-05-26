"""Testes do SemanticChunker (P1 — v2.1)."""

from backend.pdf import Chunk, SemanticChunker


def test_chunker_splits_by_smpc_section():
    text = """
4.1. Espécies-alvo
Cães e gatos.

4.9. Posologia e via de administração
Para cães: 1 mg/kg. Para gatos: 0,5 mg/kg.

6.4. Conservação
Conservar a temperatura inferior a 25°C.
""".strip()
    chunks = SemanticChunker().chunk(text, source_pdf="bula.pdf", medicamento="Foo")
    sections = {c.section_num for c in chunks}
    assert "4.1" in sections
    assert "4.9" in sections
    assert "6.4" in sections
    assert all(c.medicamento == "Foo" for c in chunks)


def test_chunker_tolerates_uppercase_headers():
    text = "4.9 POSOLOGIA\nDose: 1 mg/kg.\n\n6.4 CONSERVAÇÃO\nAbaixo de 25°C."
    chunks = SemanticChunker().chunk(text)
    nums = {c.section_num for c in chunks}
    assert "4.9" in nums and "6.4" in nums


def test_chunker_handles_no_smpc_header():
    text = "Texto livre sem secção numerada. Apenas parágrafos."
    chunks = SemanticChunker().chunk(text)
    assert len(chunks) >= 1
    assert all(c.section_num == "" for c in chunks)


def test_chunker_extracts_tables_separately():
    text = """
4.9. Posologia
Ver tabela abaixo.

[Tabela página 3]
Espécie | Dose
Cão | 1 mg/kg
Gato | 0,5 mg/kg
[/Tabela]

Texto após tabela.
""".strip()
    chunks = SemanticChunker().chunk(text)
    tables = [c for c in chunks if c.is_table]
    assert len(tables) == 1
    assert "Cão" in tables[0].text
    assert tables[0].section_num == "4.9"
    assert tables[0].page == 3


def test_chunker_target_size_with_overlap():
    long_text = "4.9. Posologia\n" + (("Parágrafo de exemplo. " * 30 + "\n\n") * 8)
    chunker = SemanticChunker(target_tokens=200, overlap_tokens=40)
    chunks = chunker.chunk(long_text)
    # tem que produzir vários chunks (sem o overlap, seria 1 enorme)
    paras = [c for c in chunks if not c.is_table]
    assert len(paras) >= 2
    # cada chunk não deve estourar muito o target
    assert all(c.char_count <= chunker.target_chars * 1.5 for c in paras)


def test_chunk_serialization_roundtrip():
    c = Chunk(
        text="dose 1 mg/kg",
        section_num="4.9", section_title="Posologia",
        paragraph_idx=2, is_table=False, page=5,
        source_pdf="x.pdf", medicamento="Foo",
    )
    d = c.to_dict()
    c2 = Chunk.from_dict(d)
    assert c == c2
