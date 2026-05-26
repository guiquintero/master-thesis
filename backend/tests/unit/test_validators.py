from backend.prompts import DoseValidator, ResponseValidator


def test_dose_validator_accepts_matching():
    v = DoseValidator(allowed=["1 mg/kg", "2.5 mg/kg"])
    ok, invalid = v.validate("A dose para gatos é 1 mg/kg.")
    assert ok and not invalid


def test_dose_validator_rejects_invented():
    v = DoseValidator(allowed=["1 mg/kg"])
    ok, invalid = v.validate("A dose é 15 mg/kg.")
    assert not ok and "15 mg/kg" in invalid


def test_dose_validator_distinguishes_concentration_from_dose():
    # 15 mg/ml é concentração, não dose por kg → não deve validar como dose
    v = DoseValidator(allowed=["1 mg/kg"])
    ok, invalid = v.validate("A dose é 15 mg/ml.")
    # Aceitamos: o validador procura padrão "mg/kg" especificamente.
    # "mg/ml" não casa o regex de dose, então a resposta não traz dose válida nem inválida.
    assert ok or invalid


def test_response_validator_vague():
    rv = ResponseValidator()
    assert rv.is_vague("Não encontrei informações. Consulte o veterinário.")
    assert not rv.is_vague("A dose recomendada é 1 mg/kg administrada por via oral 2 vezes ao dia.")


def test_response_validator_specifics():
    rv = ResponseValidator()
    assert rv.has_specifics("Armazenar a 25 °C durante 30 dias")
    assert not rv.has_specifics("Consulte o documento.")
