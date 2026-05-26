"""Testes do parser de output estruturado (P5 — v2.1)."""

from backend.prompts import LLMResponse, parse_llm_response, render_for_user


def test_parses_clean_json():
    raw = '{"resposta": "Dose é 1 mg/kg.", "encontrada_no_documento": true, "fontes": [{"secao": "4.9", "trecho": "1 mg/kg"}], "confianca": 0.9}'
    r = parse_llm_response(raw)
    assert r.parse_ok
    assert r.encontrada_no_documento is True
    assert r.confianca == 0.9
    assert len(r.fontes) == 1
    assert r.fontes[0].secao == "4.9"


def test_strips_code_fences():
    raw = '```json\n{"resposta": "X", "encontrada_no_documento": true, "fontes": [], "confianca": 0.7}\n```'
    r = parse_llm_response(raw)
    assert r.parse_ok and r.resposta == "X"


def test_handles_curly_quotes():
    raw = '{“resposta”: “Y”, “encontrada_no_documento”: true, “fontes”: [], “confianca”: 0.5}'
    r = parse_llm_response(raw)
    assert r.parse_ok and r.resposta == "Y"


def test_handles_trailing_comma():
    raw = '{"resposta": "Z", "encontrada_no_documento": false, "fontes": [], "confianca": 0.1,}'
    r = parse_llm_response(raw)
    assert r.parse_ok and r.confianca == 0.1


def test_falls_back_when_not_json():
    raw = "Apenas texto livre sem JSON."
    r = parse_llm_response(raw)
    assert not r.parse_ok
    assert "texto livre" in r.resposta
    assert r.encontrada_no_documento is False


def test_needs_reprompt_when_low_confidence():
    r = LLMResponse(resposta="X", encontrada_no_documento=True, confianca=0.3)
    assert r.needs_reprompt(min_confidence=0.55)
    r2 = LLMResponse(resposta="X", encontrada_no_documento=True, confianca=0.8)
    assert not r2.needs_reprompt(min_confidence=0.55)


def test_needs_reprompt_when_not_found():
    r = LLMResponse(resposta="X", encontrada_no_documento=False, confianca=0.9)
    assert r.needs_reprompt()


def test_render_for_user_includes_sources():
    r = LLMResponse(
        resposta="Dose é 1 mg/kg",
        encontrada_no_documento=True,
        confianca=0.9,
    )
    out = render_for_user(r)
    assert "1 mg/kg" in out


def test_empty_resposta_triggers_reprompt():
    """v2.1.1: bug 2026-05 — LLM preenchia fontes mas deixava resposta vazia."""
    from backend.prompts import Source
    r = LLMResponse(
        resposta="",
        encontrada_no_documento=True,
        confianca=0.9,
        fontes=[Source(secao="4.1", trecho="cães")],
    )
    assert r.needs_reprompt()


def test_render_for_user_synthesizes_from_sources_when_resposta_empty():
    """v2.1.1: se resposta vazia mas há fontes, sintetiza algo útil."""
    from backend.prompts import Source
    r = LLMResponse(
        resposta="",
        encontrada_no_documento=True,
        confianca=0.9,
        fontes=[
            Source(secao="4.1", trecho="O medicamento é indicado para cães adultos."),
            Source(secao="4.2", trecho="Tratamento de infestações por pulgas e carraças."),
        ],
    )
    out = render_for_user(r)
    assert "Não foi possível gerar resposta." not in out
    assert "cães adultos" in out
    assert "pulgas" in out
