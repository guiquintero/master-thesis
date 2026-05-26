from backend.entities import InfoType
from backend.pdf import PDFSection
from backend.retriever import SectionRetriever
from backend.retriever.lexical import LexicalRetriever


def _sections():
    return [
        PDFSection(number="4.1", title="Espécies-alvo", body="Cães e gatos."),
        PDFSection(number="4.2", title="Indicações", body="Tratamento da dor."),
        PDFSection(number="4.9", title="Posologia e via de administração",
                   body="Dose: 1 mg/kg uma vez ao dia."),
        PDFSection(number="6.4", title="Conservação", body="Armazenar abaixo de 25 °C."),
    ]


def test_section_retriever_dose():
    r = SectionRetriever()
    out = r.retrieve(_sections(), InfoType.DOSE)
    # v2.1: pode devolver None se nada bater; aqui 4.9 bate
    assert out is not None
    assert any(s.number == "4.9" for s in out)


def test_section_retriever_armazenamento():
    r = SectionRetriever()
    out = r.retrieve(_sections(), InfoType.ARMAZENAMENTO)
    assert out is not None
    assert any(s.number == "6.4" for s in out)


def test_section_retriever_returns_none_when_nothing_matches():
    """v2.1: deixou de devolver top-N arbitrário quando não bate; devolve None."""
    sections = [PDFSection(number="99.9", title="Algo inexistente", body="Nada")]
    r = SectionRetriever()
    out = r.retrieve(sections, InfoType.DOSE)
    assert out is None


def test_lexical_retriever_finds_dose_section():
    lex = LexicalRetriever(top_k=2)
    lex.index(_sections())
    results = lex.search("qual a dose")
    assert results
    assert results[0].number == "4.9"


def test_lexical_retriever_armazenamento():
    lex = LexicalRetriever(top_k=2)
    lex.index(_sections())
    results = lex.search("como armazenar conservação")
    assert results[0].number == "6.4"
