"""KV store baseado em sistema de arquivos.

Mantém a stack zero-deps. Para multi-worker em produção troque por Redis
implementando a interface `KVStore`.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional, Protocol


class KVStore(Protocol):
    def get(self, key: str) -> Optional[Any]: ...
    def set(self, key: str, value: Any, ttl_s: Optional[int] = None) -> None: ...
    def delete(self, key: str) -> None: ...
    def has(self, key: str) -> bool: ...


class DiskKVStore:
    """Persistente em disco. JSON serializável."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, key: str) -> Path:
        safe = key.replace(":", "__").replace("/", "_")
        return self._root / f"{safe}.json"

    def get(self, key: str) -> Optional[Any]:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                entry = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
        expires_at = entry.get("expires_at")
        if expires_at is not None and time.time() > expires_at:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            return None
        return entry.get("value")

    def set(self, key: str, value: Any, ttl_s: Optional[int] = None) -> None:
        path = self._path(key)
        # ttl_s <= 0 → expira imediatamente (útil em testes/forçar refresh)
        if ttl_s is not None and ttl_s <= 0:
            expires_at = time.time() - 1
        elif ttl_s:
            expires_at = time.time() + ttl_s
        else:
            expires_at = None
        entry = {
            "value": value,
            "expires_at": expires_at,
            "stored_at": time.time(),
        }
        tmp = path.with_suffix(".tmp")
        with self._lock:
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(entry, f, ensure_ascii=False)
            os.replace(tmp, path)

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink(missing_ok=True)
        except OSError:
            pass

    def has(self, key: str) -> bool:
        return self.get(key) is not None
