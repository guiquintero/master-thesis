"""Estado de conversa POR SESSÃO.

Substitui `self.contexto_conversacao` (singleton mutável compartilhado entre
threads) da god-class antiga, que tinha race condition na API threaded.

Cada chamada à API passa um `session_id`; o `ConversationStore` mantém um
state isolado por sessão e expira sessões inativas.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Optional

from backend.entities import InfoType


@dataclass
class ConversationState:
    session_id: str
    last_query: Optional[str] = None
    last_category: Optional[str] = None
    last_medicamento: Optional[str] = None
    last_termo_busca: Optional[str] = None
    last_response: Optional[str] = None
    last_info_type: InfoType = InfoType.GERAL
    last_scraping_results: list = field(default_factory=list)
    last_interaction: float = field(default_factory=time.time)
    history: list[dict] = field(default_factory=list)
    max_history: int = 8

    def add_turn(self, query: str, response: str, category: str) -> None:
        self.history.append({
            "ts": time.time(),
            "query": query,
            "response": response[:200] + "..." if len(response) > 200 else response,
            "category": category,
        })
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
        self.last_interaction = time.time()


class ConversationStore:
    """LRU thread-safe de sessões."""

    def __init__(self, max_sessions: int = 100, ttl_s: int = 3600) -> None:
        self._sessions: OrderedDict[str, ConversationState] = OrderedDict()
        self._lock = threading.RLock()
        self.max_sessions = max_sessions
        self.ttl_s = ttl_s

    def get(self, session_id: str) -> ConversationState:
        with self._lock:
            self._evict_stale()
            if session_id in self._sessions:
                state = self._sessions.pop(session_id)
                self._sessions[session_id] = state
                return state
            state = ConversationState(session_id=session_id)
            self._sessions[session_id] = state
            if len(self._sessions) > self.max_sessions:
                self._sessions.popitem(last=False)
            return state

    def reset(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def _evict_stale(self) -> None:
        now = time.time()
        expired = [
            sid for sid, st in self._sessions.items()
            if now - st.last_interaction > self.ttl_s
        ]
        for sid in expired:
            self._sessions.pop(sid, None)
