"""Detecção e enforcement de idioma português.

Unifica as três implementações divergentes do código legado
(`_detectar_idioma_errado`, `OllamaWrapperSeguro._detectar_idioma` e checagens
inline). Uma única fonte de verdade, com thresholds e listas calibradas.

A heurística é leve (sem deps externas). Para casos de borda, pode-se trocar
por `langdetect` no futuro — a interface não muda.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

Language = Literal["portugues", "ingles", "espanhol", "frances", "alemao", "cjk", "outro", "indefinido"]

# Listas compactas — palavras MUITO frequentes que praticamente não aparecem em PT.
_STOPWORDS = {
    "ingles": {
        "the", "this", "that", "these", "those", "and", "with", "for",
        "according", "document", "information", "dose", "administration",
        "storage", "species", "indicated", "should", "must", "following",
        "please", "refer", "consult",
    },
    "espanhol": {
        "el", "la", "los", "las", "según", "información", "está",
        "debe", "puede", "siguiente",
    },
    "frances": {
        "le", "les", "selon", "avec", "dans", "pour", "sur",
        "doit", "peut",
    },
    "alemao": {
        "der", "die", "das", "und", "mit", "nach", "für", "von",
        "auf", "sind",
    },
}

_PORTUGUES_HINTS = {
    "o", "a", "os", "as", "de", "do", "da", "dos", "das",
    "em", "para", "com", "por", "que", "não", "é", "são",
    "está", "segundo", "medicamento", "dose", "espécie", "espécies",
    "armazenamento", "indicação", "deve",
}

# Threshold (proporção de palavras estrangeiras) para classificar como não-PT.
_FOREIGN_THRESHOLD = 0.12

_NON_LATIN = re.compile(r"[Ѐ-ӿ؀-ۿऀ-ॿ一-鿿぀-ゟ゠-ヿ가-힯]")


def _tokens(text: str) -> list[str]:
    nfkd = unicodedata.normalize("NFKD", text.lower())
    text_normalized = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.findall(r"[a-záàâãéêíóôõúüç']+", text.lower()) + re.findall(r"[a-z']+", text_normalized)


def detect_language(text: str) -> Language:
    if not text or not text.strip():
        return "indefinido"

    if _NON_LATIN.search(text):
        return "cjk"  # qualquer alfabeto não-latino agrupado

    words = set(_tokens(text))
    total = max(len(words), 1)

    scores = {
        lang: sum(1 for w in stopwords if w in words) / total
        for lang, stopwords in _STOPWORDS.items()
    }
    pt_score = sum(1 for w in _PORTUGUES_HINTS if w in words) / total

    best_foreign = max(scores, key=scores.get)  # type: ignore[arg-type]
    best_foreign_score = scores[best_foreign]

    if best_foreign_score > _FOREIGN_THRESHOLD and best_foreign_score > pt_score:
        return best_foreign  # type: ignore[return-value]
    if pt_score >= 0.05 or len(text.split()) <= 4:
        return "portugues"
    return "outro"


@dataclass
class LanguageGuard:
    """Política de enforcement: retorna (ok, motivo)."""

    target: Language = "portugues"

    def check(self, text: str) -> tuple[bool, str]:
        detected = detect_language(text)
        if detected == self.target:
            return True, "ok"
        if detected == "indefinido":
            return True, "indefinido (texto curto)"
        return False, f"detectado={detected}"
