"""Detecção e reconstrução de perguntas follow-up.

Substitui `_detectar_pergunta_followup` + `_extrair_entidade_followup` +
`_construir_pergunta_completa` da god-class antiga. Tudo determinístico.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from backend.entities import InfoType, identify_info_type
from backend.entities.species_map import find_species_in
from backend.orchestrator.conversation import ConversationState

_SPECIES_PATTERN = re.compile(
    r"\b(?:em|para)\s+(?:suínos|bovinos|equinos|cães|gatos|aves|perus?|coelhos|ovinos|caprinos)\b",
    re.IGNORECASE,
)
_SHORT_INDICATORS = (
    "e", "para", "em", "gatos", "cães", "suínos", "bovinos", "equinos",
    "peru", "perus", "aves", "coelhos", "dose", "dosagem", "armazenamento",
    "composição", "indicação", "efeitos",
)


@dataclass
class FollowupResult:
    is_followup: bool
    rewritten_query: Optional[str] = None
    detected_species: Optional[str] = None
    detected_info_type: Optional[InfoType] = None


def detect_and_rewrite(query: str, state: ConversationState) -> FollowupResult:
    """Detecta follow-up curto e reescreve em pergunta completa."""
    if not state.last_query or not state.last_medicamento:
        return FollowupResult(is_followup=False)

    words = query.lower().split()
    if len(words) > 5:
        return FollowupResult(is_followup=False)

    species = find_species_in(query)
    info_type = identify_info_type(query)
    info_changed = info_type != InfoType.GERAL and info_type != state.last_info_type

    has_indicator = species or info_changed or any(w in _SHORT_INDICATORS for w in words)
    if not has_indicator:
        return FollowupResult(is_followup=False)

    rewritten = _rewrite(query, state, species, info_type)
    return FollowupResult(
        is_followup=True,
        rewritten_query=rewritten,
        detected_species=species,
        detected_info_type=info_type if info_type != InfoType.GERAL else None,
    )


def _rewrite(
    query: str,
    state: ConversationState,
    species: Optional[str],
    info_type: InfoType,
) -> str:
    med = state.last_medicamento or ""
    if info_type != InfoType.GERAL:
        templates = {
            InfoType.DOSE: f"Qual a dose do {med}",
            InfoType.ARMAZENAMENTO: f"Como armazenar o {med}",
            InfoType.COMPOSICAO: f"Qual a composição do {med}",
            InfoType.INDICACAO: f"Para que serve o {med}",
            InfoType.REACOES: f"Quais os efeitos adversos do {med}",
            InfoType.ESPECIES: f"Para que espécies está indicado o {med}",
            InfoType.CONTRAINDICACOES: f"Quais as contra-indicações do {med}",
            InfoType.INTERVALOS: f"Quais os intervalos de segurança do {med}",
        }
        base = templates.get(info_type, f"Informação sobre {med}")
        if species:
            base += f" para {species}"
        return base + "?"

    # Sem mudança de info_type: provavelmente mudou de espécie.
    if species and state.last_query:
        m = _SPECIES_PATTERN.search(state.last_query)
        if m:
            return _SPECIES_PATTERN.sub(f"para {species}", state.last_query, count=1)
        return f"{state.last_query.rstrip('?')} para {species}?"

    return state.last_query or query
