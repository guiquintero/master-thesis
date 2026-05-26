"""Geração canônica de chaves de cache.

Tudo que entra numa chave passa por normalização para garantir que pequenas
variações irrelevantes (espaços extras, capitalização, acentos opcionais)
não produzam chaves diferentes.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Any


def _normalize_text(value: str) -> str:
    value = value.strip().lower()
    # NFKD remove acentos preservando a letra base
    nfkd = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(value.split())


def _canon(value: Any) -> Any:
    if isinstance(value, str):
        return _normalize_text(value)
    if isinstance(value, dict):
        return {k: _canon(value[k]) for k in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canon(v) for v in value]
    return value


def make_key(namespace: str, *parts: Any) -> str:
    """Gera chave estável a partir de uma tupla de componentes."""
    canonical = json.dumps([_canon(p) for p in parts], ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha1(canonical.encode("utf-8")).hexdigest()
    return f"{namespace}:{digest}"
