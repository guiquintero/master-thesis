"""Desambiguação entidade → PDF (P3 — Sprint v2.1).

ANTES (v2.0): ``primary = details[0]`` — pegava sempre o primeiro listing
devolvido pelo MedVet. Para "Senvelgo" podia escolher "Senvelgo Plus" em vez
do "Senvelgo 15 mg/ml" real.

DEPOIS (v2.1): score por similaridade de nome + bónus por espécie alvo +
bónus por substância activa. Devolve a lista ordenada com o melhor primeiro
e expõe a confiança (gap top1 vs top2).
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional

from backend.medvet.parser_listing import ListingResult
from backend.observability import get_logger

log = get_logger(__name__)


def _similarity(a: str, b: str) -> float:
    """Razão de similaridade [0,1], case-insensitive."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _token_overlap(query: str, target: str) -> float:
    """Fracção de tokens da query presentes no target."""
    q = {t for t in query.lower().split() if len(t) > 2}
    t = target.lower()
    if not q:
        return 0.0
    return sum(1 for tok in q if tok in t) / len(q)


@dataclass
class RankedListing:
    listing: ListingResult
    score: float
    breakdown: dict  # explicação: name_sim=0.8, species_bonus=0.1, ...


def rank_listings(
    listings: list[ListingResult],
    *,
    termo_busca: str,
    especie_alvo: Optional[str] = None,
    substancia_ativa: Optional[str] = None,
) -> list[RankedListing]:
    """Ordena listings por relevância para a query.

    Score = 0.55 * name_sim + 0.25 * token_overlap +
            0.10 * species_match + 0.10 * substancia_match
    """
    ranked: list[RankedListing] = []
    for l in listings:
        name_sim = _similarity(termo_busca, l.nome)
        tok = _token_overlap(termo_busca, l.nome)

        species_bonus = 0.0
        if especie_alvo and l.especies:
            if especie_alvo.lower() in l.especies.lower():
                species_bonus = 1.0

        subst_bonus = 0.0
        if substancia_ativa and l.substancias_ativas:
            subst_low = substancia_ativa.lower()
            for s in l.substancias_ativas:
                if subst_low in s.lower() or s.lower() in subst_low:
                    subst_bonus = 1.0
                    break

        score = 0.55 * name_sim + 0.25 * tok + 0.10 * species_bonus + 0.10 * subst_bonus
        ranked.append(RankedListing(
            listing=l,
            score=score,
            breakdown={
                "name_sim": round(name_sim, 3),
                "token_overlap": round(tok, 3),
                "species_bonus": species_bonus,
                "substancia_bonus": subst_bonus,
            },
        ))
    ranked.sort(key=lambda r: r.score, reverse=True)
    return ranked


def confidence_gap(ranked: list[RankedListing]) -> float:
    """Diferença entre top-1 e top-2 — sinal de ambiguidade.

    > 0.15: top-1 claramente melhor (confiança alta).
    ≤ 0.05: muito empate — provavelmente precisa LLM/utilizador desambiguar.
    """
    if len(ranked) < 2:
        return 1.0
    return ranked[0].score - ranked[1].score


def pick_best(
    listings: list[ListingResult],
    *,
    termo_busca: str,
    especie_alvo: Optional[str] = None,
    substancia_ativa: Optional[str] = None,
) -> tuple[Optional[ListingResult], list[RankedListing]]:
    """Escolha conveniente. Retorna ``(best, ranked_all)``."""
    if not listings:
        return None, []
    ranked = rank_listings(
        listings,
        termo_busca=termo_busca,
        especie_alvo=especie_alvo,
        substancia_ativa=substancia_ativa,
    )
    best = ranked[0].listing
    gap = confidence_gap(ranked)
    log.info(
        "Disambiguator: best=%r score=%.3f gap=%.3f breakdown=%s",
        best.nome, ranked[0].score, gap, ranked[0].breakdown,
    )
    return best, ranked
