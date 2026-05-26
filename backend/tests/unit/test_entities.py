"""Testes unitários para extração de entidades. NÃO requer Ollama."""

from backend.entities import EntityExtractor, InfoType
from backend.entities.species_map import find_species_in, normalize_species


def test_species_normalization_basic():
    assert normalize_species("para cães") == "para cães"
    assert "suínos" in normalize_species("dose para porcos")
    assert "bovinos" in normalize_species("indicado para vacas")


def test_species_detection():
    assert find_species_in("dose para gatinhos") == "gatos"
    assert find_species_in("administrar em coelhos") == "coelhos"
    assert find_species_in("uso geral") is None


def test_extractor_dose_question():
    e = EntityExtractor().extract("Qual a dose do Senvelgo 15 mg/ml em gatos?")
    assert e.info_type == InfoType.DOSE
    assert e.especie_alvo == "gatos"
    assert e.medicamento is not None
    assert "Senvelgo" in (e.medicamento or "")


def test_extractor_alternative_question():
    e = EntityExtractor().extract("Qual o medicamento alternativo para Trocoxil 75 para cães?")
    assert "Trocoxil" in (e.medicamento or "")
    assert e.especie_alvo == "cães"


def test_extractor_armazenamento():
    e = EntityExtractor().extract("Como deve ser armazenado o medicamento Acuimix?")
    assert e.info_type == InfoType.ARMAZENAMENTO
    assert e.medicamento is not None


def test_extractor_indicacao():
    e = EntityExtractor().extract("Para que serve o medicamento Dolpac?")
    assert e.info_type == InfoType.INDICACAO


def test_extractor_strips_species_suffix_from_termo_busca():
    """Bug 2026-05: termo_busca virava 'Hidrocol em suínos' → MedVet 404."""
    e = EntityExtractor().extract("Qual a forma de administração do medicamento Hidrocol em suínos?")
    assert e.medicamento == "Hidrocol"
    assert e.termo_busca == "Hidrocol"
    assert e.especie_alvo == "suínos"


def test_extractor_strips_species_without_medicamento_prefix():
    """Variantes sem 'do medicamento'."""
    e = EntityExtractor().extract("Hidrocol em suínos?")
    assert e.medicamento == "Hidrocol"
    assert e.termo_busca == "Hidrocol"


def test_extractor_keeps_composite_drug_name():
    """Nomes compostos legítimos não devem ser cortados."""
    e = EntityExtractor().extract("Qual a dose do medicamento Simparica Trio para cães?")
    # "Trio" começa com maiúscula, é parte do nome
    assert e.medicamento is not None
    assert "Simparica" in e.medicamento
    # Não deve ter "para cães" no termo_busca
    assert "para" not in e.termo_busca.lower()
    assert "cães" not in e.termo_busca.lower()
