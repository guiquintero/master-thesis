"""Validadores pós-resposta.

Substituem `_validar_resposta_dose`, `_validar_qualidade_resposta`,
`_resposta_muito_vaga` espalhados pelo código antigo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.observability import get_logger

log = get_logger(__name__)


_DOSE_PATTERN = re.compile(
    r"(\d+[\.,]?\d*)\s*(mg|mcg|µg|ug|ml|g)\s*/\s*(kg|quilograma)",
    re.IGNORECASE,
)
_VAGUE_INDICATORS = [
    "não encontrei",
    "não foi possível encontrar",
    "não há informação",
    "não consta",
    "não está especificado",
    "consulte o veterinário",
    "consulte a bula",
    "informação não encontrada",
]


@dataclass
class DoseValidator:
    """Garante que doses na resposta existem no documento."""

    allowed: list[str]

    def _normalize(self, value: str, unit: str, denom: str) -> str:
        unit = unit.lower().replace("µg", "mcg").replace("ug", "mcg")
        denom = denom.lower()
        return f"{value.replace(',', '.')} {unit}/{denom}"

    def _extract_pairs(self, text: str) -> list[str]:
        out = []
        for m in _DOSE_PATTERN.finditer(text):
            out.append(self._normalize(m.group(1), m.group(2), m.group(3)))
        return out

    def validate(self, response: str) -> tuple[bool, list[str]]:
        """Retorna (ok, doses_invalidas)."""
        if not self.allowed:
            return True, []

        allowed_norm = {self._extract_pairs(d)[0] if self._extract_pairs(d) else d.lower() for d in self.allowed}
        # Para cada dose mencionada na resposta, exige correspondência exata (valor+unidade+denom)
        invalid = []
        for dose in self._extract_pairs(response):
            if dose not in allowed_norm:
                # Comparação relaxada por valor numérico (caso unidade case ligeiramente)
                num = dose.split()[0]
                if not any(d.startswith(num + " ") for d in allowed_norm):
                    invalid.append(dose)
        return len(invalid) == 0, invalid


@dataclass
class ResponseValidator:
    """Verifica se a resposta é específica o suficiente."""

    min_length: int = 80
    max_vague_indicators: int = 1

    def is_vague(self, response: str) -> bool:
        low = response.lower()
        vague = sum(1 for ind in _VAGUE_INDICATORS if ind in low)
        if vague >= 2:
            return True
        if vague >= 1 and len(response) < self.min_length:
            return True
        return False

    def has_specifics(self, response: str) -> bool:
        return bool(re.search(r"\d", response)) or any(
            u in response.lower() for u in ("mg", "ml", "kg", "°c", "graus", "dias", "horas")
        )
