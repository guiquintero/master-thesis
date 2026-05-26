"""Regras determinísticas de classificação.

Cobrem ~60–70% das perguntas reais do golden set sem precisar tocar a LLM.
"""

from __future__ import annotations

import re

# Indicadores fortes de COMPARAÇÃO (busca de múltiplos medicamentos)
COMPARISON_KEYWORDS = (
    "alternativ",
    "substitut",
    "equivalente",
    "similar",
    "mesmo princípio ativo",
    "mesma substância",
    "que medicamentos",
    "quais medicamentos",
    "liste medicamentos",
    "medicamentos com",
    "medicamentos contendo",
    "medicamentos que",
    "marcas",
)

# Indicadores de MEDICAMENTO ÚNICO
MEDICATION_PHRASES = (
    "qual a dose",
    "dose indicada",
    "como armazenar",
    "como deve ser armazenado",
    "armazenamento",
    "qual a forma de administração",
    "forma de administração",
    "quais os intervalos",
    "intervalos de segurança",
    "qual é a composição",
    "qual a composição",
    "composição do",
    "para que é usado",
    "para que serve",
    "que reações adversas",
    "reações adversas",
    "em que espécies pode ser usado",
    "para que espécies",
    "como deve ser administrado",
)

# Padrão "o medicamento X" / "do medicamento X" — sinal forte de pergunta sobre UM medicamento
SPECIFIC_MED_PATTERN = re.compile(
    r"\b(?:o|do|no|ao|de|para|com)\s+medicamento\s+\w+",
    re.IGNORECASE,
)

# Captura "que medicamento " no singular (que é "medicamento" e não "comparacao")
SINGULAR_QUE_MED = re.compile(r"\bque\s+medicamento\s+", re.IGNORECASE)
PLURAL_QUE_MED = re.compile(r"\bque\s+medicamentos\b", re.IGNORECASE)


def has_any(text: str, terms) -> bool:
    return any(t in text for t in terms)
