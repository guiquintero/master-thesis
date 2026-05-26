from backend.llm.language_guard import LanguageGuard, detect_language


def test_portuguese_text():
    assert detect_language("Esta é uma resposta em português sobre o medicamento.") == "portugues"


def test_english_text():
    assert detect_language("According to the document, the dose is 1 mg/kg for cats.") == "ingles"


def test_spanish_text():
    assert detect_language("Según el documento, la dosis es de 1 mg/kg para gatos.") == "espanhol"


def test_chinese_text():
    assert detect_language("根据文件，剂量为每公斤1毫克。") == "cjk"


def test_short_text_is_undetermined_or_pt():
    assert detect_language("1 mg/kg") in ("portugues", "indefinido")


def test_guard_check():
    g = LanguageGuard()
    ok, _ = g.check("Resposta em português sobre o medicamento e a dose.")
    assert ok
    ok, reason = g.check("According to the document, this is the answer.")
    assert not ok and "ingles" in reason
