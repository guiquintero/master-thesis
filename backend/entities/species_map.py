"""Mapa canônico de espécies. ÚNICA fonte de verdade.

O código antigo replicava esse mapa em 4 lugares (cada um ligeiramente
diferente). Aqui é definido uma única vez e importado por todos os módulos.
"""

from __future__ import annotations

import re

# canônica -> sinônimos
SPECIES_SYNONYMS: dict[str, list[str]] = {
    "suínos": ["suíno", "suino", "suínos", "suinos", "porco", "porcos", "leitão", "leitões", "porcino"],
    "bovinos": ["bovino", "bovinos", "vaca", "vacas", "novilho", "novilhos", "touro", "touros", "bezerro", "bezerros", "gado"],
    "equinos": ["cavalo", "cavalos", "égua", "éguas", "egua", "eguas", "potro", "potros", "equino", "equinos"],
    "cães": ["cão", "cao", "cães", "caes", "cachorro", "cachorros", "cadela", "cadelas", "canino", "caninos"],
    "gatos": ["gato", "gatos", "gata", "gatas", "felino", "felinos", "gatinho", "gatinhos"],
    "ovinos": ["ovino", "ovinos", "ovelha", "ovelhas", "carneiro", "carneiros", "borrego", "borregos", "cordeiro", "cordeiros"],
    "caprinos": ["caprino", "caprinos", "cabra", "cabras", "bode", "bodes"],
    "aves": ["ave", "aves", "galinha", "galinhas", "frango", "frangos"],
    "perus": ["peru", "perus"],
    "coelhos": ["coelho", "coelhos", "coelha", "coelhas", "leporídeo", "leporídeos", "leporideo", "leporideos"],
}

# sinônimo -> canônica
_SYN_TO_CANON: dict[str, str] = {
    syn.lower(): canon
    for canon, syns in SPECIES_SYNONYMS.items()
    for syn in syns
}

SPECIES_CANONICAL = list(SPECIES_SYNONYMS.keys())


def normalize_species(text: str) -> str:
    """Substitui qualquer sinônimo de espécie pela forma canônica no texto."""
    result = text
    for syn, canon in _SYN_TO_CANON.items():
        pattern = r"\b" + re.escape(syn) + r"\b"
        result = re.sub(pattern, canon, result, flags=re.IGNORECASE)
    return result


def find_species_in(text: str) -> str | None:
    """Retorna a primeira espécie canônica encontrada no texto, ou None."""
    low = text.lower()
    for syn, canon in _SYN_TO_CANON.items():
        if re.search(r"\b" + re.escape(syn) + r"\b", low):
            return canon
    return None
