"""Retrieval determinístico baseado em secções SmPC.

v2.1: agora trabalha com ``Chunk`` (preferido) ou ``PDFSection`` (compat).
Usado como **pré-filtro** antes do retrieval híbrido — restringe o universo
aos chunks que vivem na(s) secção(ões) relevantes ao info_type.

ANTES (v2.0):
    Devolvia secções SmPC inteiras (4 000–8 000 chars), mas retornava lista
    vazia se a secção não existisse → caía no fallback lexical sobre tudo.

DEPOIS (v2.1):
    Devolve chunks pequenos da(s) secção(ões) alvo. Se nada bate, devolve
    None para o caller decidir (em vez de "top-N aleatório").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Union

from backend.entities import InfoType
from backend.entities.info_type import smpc_sections_for
from backend.pdf import Chunk, PDFSection

Doc = Union[Chunk, PDFSection]


def _doc_number(doc: Doc) -> str:
    if isinstance(doc, Chunk):
        return doc.section_num
    return doc.number


def _doc_text_for_kw(doc: Doc) -> str:
    if isinstance(doc, Chunk):
        return (doc.section_title + " " + doc.text).lower()
    return (doc.title + " " + doc.body).lower()


@dataclass
class SectionRetriever:
    """Restringe chunks/secções ao info_type. Devolve None se nada bate."""

    fallback_top_n: int = 6

    def retrieve(
        self,
        docs: Iterable[Doc],
        info_type: InfoType,
    ) -> Optional[list[Doc]]:
        docs = list(docs)
        if not docs:
            return None

        targets = smpc_sections_for(info_type)

        # Caminho 1: filtro estrutural por nº de secção SmPC.
        if targets:
            primary = [
                d for d in docs
                if any(_doc_number(d).startswith(t.rstrip(".")) for t in targets)
            ]
            if primary:
                return primary

        # Caminho 2: fallback por keyword no título/body.
        kw_map = {
            InfoType.DOSE: ("posologia", "dose", "administração"),
            InfoType.ARMAZENAMENTO: ("conservação", "armazenamento", "validade"),
            InfoType.ESPECIES: ("espécies", "alvo"),
            InfoType.COMPOSICAO: ("composição",),
            InfoType.INDICACAO: ("indicação", "indicações"),
            InfoType.CONTRAINDICACOES: ("contra-indicação", "contraindicação"),
            InfoType.REACOES: ("reações", "efeitos"),
            InfoType.INTERVALOS: ("intervalo", "espera", "carência"),
        }
        kws = kw_map.get(info_type, ())
        if kws:
            matches = [d for d in docs if any(k in _doc_text_for_kw(d) for k in kws)]
            if matches:
                return matches[: self.fallback_top_n]

        # Caminho 3: não há filtro estrutural confiável → devolve None
        # (em v2.0 devolvia top-N arbitrário; em v2.1 deixamos o caller decidir).
        return None
