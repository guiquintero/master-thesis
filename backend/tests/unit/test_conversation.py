import time

from backend.entities import InfoType
from backend.orchestrator.conversation import ConversationStore
from backend.orchestrator.followup import detect_and_rewrite


def test_session_isolation():
    store = ConversationStore()
    a = store.get("a")
    b = store.get("b")
    a.last_medicamento = "Senvelgo"
    assert b.last_medicamento is None


def test_session_lru():
    store = ConversationStore(max_sessions=2)
    store.get("a")
    store.get("b")
    store.get("c")  # deve expulsar "a"
    assert "a" not in store._sessions  # noqa: SLF001


def test_followup_detects_species_change():
    store = ConversationStore()
    state = store.get("s")
    state.last_query = "Qual a dose do Senvelgo para gatos?"
    state.last_medicamento = "Senvelgo"
    state.last_info_type = InfoType.DOSE

    res = detect_and_rewrite("E para cães?", state)
    assert res.is_followup
    assert res.rewritten_query
    assert "cães" in res.rewritten_query.lower()


def test_followup_detects_info_type_change():
    store = ConversationStore()
    state = store.get("s")
    state.last_query = "Para que serve o Senvelgo?"
    state.last_medicamento = "Senvelgo"
    state.last_info_type = InfoType.INDICACAO

    res = detect_and_rewrite("E o armazenamento?", state)
    assert res.is_followup
    assert res.detected_info_type == InfoType.ARMAZENAMENTO


def test_no_followup_without_history():
    store = ConversationStore()
    state = store.get("s")
    res = detect_and_rewrite("Qual a dose?", state)
    assert not res.is_followup
