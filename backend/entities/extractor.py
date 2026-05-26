"""Extração de entidades determinística (sem LLM).

Substitui a salada de regex espalhada em `QueryClassifier` legado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from backend.entities.info_type import InfoType, identify_info_type
from backend.entities.species_map import find_species_in

# Padrão amplo para nomes comerciais de medicamento.
# Começa com maiúscula, aceita hifens, números, %, sufixos farmacêuticos.
_MEDICAMENTO_PATTERN = re.compile(
    r"\b([A-ZÀ-Ú][A-ZÀ-Úa-zà-ú\-]{2,}"
    r"(?:\s+[A-ZÀ-Ú][A-ZÀ-Úa-zà-ú\-]+)*"
    r"(?:\s+(?:PÓ|Pó|SOLUÇÃO|Solução|COMPRIMIDO|Comprimido|INJETÁVEL|Injetável))?"
    r"(?:\s+\d+(?:[.,]\d+)?%?(?:\s*(?:mg|ml|g|mcg)(?:/(?:ml|kg|g))?)?)*"
    r")"
)

# Lista de stopwords (não são nomes de medicamento)
_STOPWORDS = {
    "para", "com", "que", "qual", "como", "quais", "onde", "quando",
    "espécie", "espécies", "animal", "animais", "medicamento", "medicamentos",
    "dose", "dosagem", "porque", "porquê",
}

_FORMS = (
    "comprimidos", "comprimido", "injetável", "injetavel",
    "solução", "solucao", "pó", "po", "pomada", "creme", "spray", "gotas",
)


@dataclass(frozen=True)
class Entities:
    """Entidades extraídas de uma pergunta."""

    termo_busca: str = ""
    medicamento: Optional[str] = None
    substancia_ativa: Optional[str] = None
    especie_alvo: Optional[str] = None
    forma_farmaceutica: Optional[str] = None
    info_type: InfoType = InfoType.GERAL

    def as_dict(self) -> dict:
        return {
            "termo_busca": self.termo_busca,
            "medicamento": self.medicamento,
            "substancia_ativa": self.substancia_ativa,
            "especie_alvo": self.especie_alvo,
            "forma_farmaceutica": self.forma_farmaceutica,
            "info_type": self.info_type.value,
        }


class EntityExtractor:
    """Extrai entidades determinísticas. Sem LLM."""

    # Padrões para perguntas de alternativa
    _ALT_PATTERNS = (
        re.compile(r"alternativ[oa]s?\s+(?:ao|para|do)\s+(.+?)(?:\s+para|\s+em|$)", re.IGNORECASE),
        re.compile(r"substitut[oa]s?\s+(?:ao|para|do)\s+(.+?)(?:\s+para|\s+em|$)", re.IGNORECASE),
        re.compile(r"equivalente\s+(?:ao|para|do)\s+(.+?)(?:\s+para|\s+em|$)", re.IGNORECASE),
        re.compile(r"similar\s+(?:ao|para|do)\s+(.+?)(?:\s+para|\s+em|$)", re.IGNORECASE),
        re.compile(r"mesmo\s+princípio\s+ativo\s+que\s+(?:o\s+medicamento\s+)?(.+?)(?:\s+para|\s+em|$)", re.IGNORECASE),
    )

    # Padrão "o medicamento NOME". Em 2 partes para distinguir case:
    # - prefixo "(o|do|...)\s+medicamento\s+" tolera maiúsculas/minúsculas
    # - nome do medicamento exige começar por maiúscula (nome próprio)
    #   e cada palavra adicional também deve começar por maiúscula/número,
    #   senão pára (evita capturar "Hidrocol em suínos").
    _MED_INLINE_PREFIX = re.compile(
        r"\b(?:o|do|no|ao|de|para|com)\s+medicamento\s+",
        re.IGNORECASE,
    )
    _MED_INLINE_NAME = re.compile(
        r"([A-ZÀ-Ú][A-Za-zÀ-Úà-ú\-]{1,}"
        r"(?:[\-/]\d+(?:[.,]\d+)?(?:\s*(?:mg|ml|g|mcg|%)(?:/(?:ml|kg|g))?)?)*"
        r"(?:\s+[A-ZÀ-Ú0-9][A-Za-zÀ-Úà-ú0-9\-]*"
        r"(?:[\-/]\d+(?:[.,]\d+)?(?:\s*(?:mg|ml|g|mcg|%)(?:/(?:ml|kg|g))?)?)*"
        r"){0,5})"
    )

    def extract(self, query: str) -> Entities:
        especie = find_species_in(query) or ""
        forma = self._extract_form(query)
        info = identify_info_type(query)

        medicamento_ref = self._extract_alternative_reference(query)
        if medicamento_ref:
            termo = medicamento_ref
            return Entities(
                termo_busca=termo,
                medicamento=medicamento_ref,
                substancia_ativa=medicamento_ref,
                especie_alvo=especie or None,
                forma_farmaceutica=forma or None,
                info_type=info,
            )

        medicamento = self._extract_medicamento(query)
        # Limpa cauda "em X" / "para Y" do termo de busca para não envenenar
        # a query MedVet (que falha 404 se a string tiver preposições).
        termo = medicamento or query.strip()
        termo = re.sub(
            r"\s+(?:em|para|de|do|da|com|a|o)\s+\w+.*$",
            "",
            termo,
            flags=re.IGNORECASE,
        ).strip()

        return Entities(
            termo_busca=termo,
            medicamento=medicamento,
            substancia_ativa=medicamento,
            especie_alvo=especie or None,
            forma_farmaceutica=forma or None,
            info_type=info,
        )

    @staticmethod
    def _extract_form(query: str) -> Optional[str]:
        low = query.lower()
        for f in _FORMS:
            if f in low:
                return f.capitalize()
        return None

    def _extract_alternative_reference(self, query: str) -> Optional[str]:
        for pat in self._ALT_PATTERNS:
            m = pat.search(query)
            if not m:
                continue
            candidate = m.group(1).strip()
            # Limpar palavras finais comuns
            candidate = re.sub(r"\s+(para|em|indicado)\b.*$", "", candidate, flags=re.IGNORECASE)
            candidate = candidate.strip(" ?.,;:")
            if candidate:
                return candidate
        return None

    def _extract_medicamento(self, query: str) -> Optional[str]:
        # 1) "do medicamento NOME" — prefixo case-insensitive, nome case-sensitive
        m_prefix = self._MED_INLINE_PREFIX.search(query)
        if m_prefix:
            after = query[m_prefix.end():]
            m_name = self._MED_INLINE_NAME.match(after)
            if m_name:
                cand = m_name.group(1).strip(" ?.,;:")
                # Remove cauda de preposições/conectores se restaram
                cand = re.sub(
                    r"\s+(?:em|para|de|do|da|com|a|o)\s+\w+.*$",
                    "",
                    cand,
                    flags=re.IGNORECASE,
                )
                cand = cand.strip(" ?.,;:")
                if cand:
                    return cand

        # 2) Heurística por capitalização (sem precisar de "medicamento ...")
        for match in _MEDICAMENTO_PATTERN.finditer(query):
            cand = match.group(1).strip()
            if cand.lower() in _STOPWORDS:
                continue
            if len(cand) < 3:
                continue
            return cand
        return None
