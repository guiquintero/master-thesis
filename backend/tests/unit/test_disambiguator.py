"""Testes do disambiguador entidade → PDF (P3 — v2.1)."""

from backend.medvet import ListingResult, confidence_gap, pick_best, rank_listings


def _listings():
    return [
        ListingResult(nome="Senvelgo Plus 30 mg/ml", link="a",
                      especies="cães", substancias_ativas=["Carprofeno"]),
        ListingResult(nome="Senvelgo 15 mg/ml", link="b",
                      especies="gatos", substancias_ativas=["Velagliflozina"]),
        ListingResult(nome="Outro medicamento", link="c"),
    ]


def test_best_match_by_name_similarity():
    best, ranked = pick_best(_listings(), termo_busca="Senvelgo 15 mg/ml")
    assert best.link == "b"
    assert ranked[0].score > ranked[1].score


def test_species_bonus_breaks_tie():
    listings = [
        ListingResult(nome="Foo 10 mg", link="x", especies="cães"),
        ListingResult(nome="Foo 10 mg", link="y", especies="gatos"),
    ]
    best, _ = pick_best(listings, termo_busca="Foo 10 mg", especie_alvo="gatos")
    assert best.link == "y"


def test_substancia_bonus():
    listings = [
        ListingResult(nome="X", link="x", substancias_ativas=["Outro"]),
        ListingResult(nome="X", link="y", substancias_ativas=["Meloxicam"]),
    ]
    best, _ = pick_best(listings, termo_busca="X", substancia_ativa="Meloxicam")
    assert best.link == "y"


def test_confidence_gap():
    listings = _listings()
    ranked = rank_listings(listings, termo_busca="Senvelgo 15 mg/ml")
    gap = confidence_gap(ranked)
    assert 0.0 <= gap <= 1.0


def test_empty_listings_returns_none():
    best, ranked = pick_best([], termo_busca="x")
    assert best is None and ranked == []
