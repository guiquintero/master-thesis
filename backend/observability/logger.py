"""Logger central baseado em `logging` stdlib.

Substitui o `print(colored(...))` espalhado pelo código antigo e o rebind
global de `print()`. Tem dois handlers:
- stderr (sempre)
- callback opcional por requisição (usado pelo SSE para streaming de logs)

Não usamos `loguru`/`structlog` para manter zero deps extras.
"""

from __future__ import annotations

import logging
import sys
import threading
from contextvars import ContextVar
from typing import Callable, Optional

_configured = False
_lock = threading.Lock()

# Callback por contexto (por requisição) — permite SSE capturar logs do
# pipeline sem hijack global de stdout.
_log_callback: ContextVar[Optional[Callable[[str, str], None]]] = ContextVar(
    "_log_callback", default=None
)


class _CallbackHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        cb = _log_callback.get()
        if cb is None:
            return
        try:
            cb(record.levelname, self.format(record))
        except Exception:  # noqa: BLE001
            # Logger nunca deve quebrar a aplicação.
            pass


def configure_logging(level: str = "INFO") -> None:
    """Configura handlers uma única vez por processo."""
    global _configured
    with _lock:
        if _configured:
            return
        root = logging.getLogger()
        root.setLevel(level.upper())
        # Limpar handlers herdados (ex.: Flask/Werkzeug)
        for h in list(root.handlers):
            root.removeHandler(h)

        stderr = logging.StreamHandler(stream=sys.stderr)
        stderr.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-7s %(name)s | %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        root.addHandler(stderr)

        cb = _CallbackHandler()
        cb.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(cb)

        # Silenciar libs ruidosas
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("selenium").setLevel(logging.WARNING)
        logging.getLogger("werkzeug").setLevel(logging.WARNING)

        _configured = True


def get_logger(name: str) -> logging.Logger:
    if not _configured:
        configure_logging()
    return logging.getLogger(name)


class capture_logs:
    """Context manager que captura logs do pipeline para um callback.

    Uso típico no endpoint SSE::

        def cb(level, msg):
            queue.put({"type": "log", "level": level, "message": msg})

        with capture_logs(cb):
            resposta = pipeline.run(pergunta)
    """

    def __init__(self, callback: Callable[[str, str], None]) -> None:
        self._cb = callback
        self._token = None

    def __enter__(self) -> "capture_logs":
        self._token = _log_callback.set(self._cb)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._token is not None:
            _log_callback.reset(self._token)
