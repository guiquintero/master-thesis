"""Extração determinística de doses do PDF.

Substitui `_buscar_informacao_direta_pdf` da god-class. Output estruturado
(`(valor, unidade, especie?)`) em vez de strings soltas. Isso permite a
validação rigorosa (`backend/prompts/validators.DoseValidator`) sem perder
informação.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

from backend.pdf import PDFSection

_DOSE_RE = re.compile(
    r"(?P<valor>\d+[\.,]?\d*)\s*(?P<unidade>mg|mcg|µg|ml)\s*/\s*(?P<denom>kg)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ExtractedDose:
    valor: str
    unidade: str
    contexto: str

    def display(self) -> str:
        return f"{self.valor.replace(',', '.')} {self.unidade.lower()}/kg"


def extract_doses(sections: Iterable[PDFSection], species: Optional[str] = None) -> list[ExtractedDose]:
    species_low = species.lower() if species else None
    out: list[ExtractedDose] = []
    seen = set()

    for sec in sections:
        body = sec.body
        for m in _DOSE_RE.finditer(body):
            # Pega um contexto curto ao redor (60 chars antes/depois)
            start = max(0, m.start() - 80)
            end = min(len(body), m.end() + 80)
            ctx = body[start:end].replace("\n", " ")
            if species_low and species_low not in ctx.lower() and species_low not in sec.body.lower():
                # Se há espécie alvo e ela não aparece nas redondezas, ignora
                continue
            dose = ExtractedDose(
                valor=m.group("valor"),
                unidade=m.group("unidade").lower().replace("µg", "mcg"),
                contexto=ctx,
            )
            key = dose.display()
            if key not in seen:
                seen.add(key)
                out.append(dose)

    return out
