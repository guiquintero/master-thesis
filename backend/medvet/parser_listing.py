"""Parsing das páginas de listagem da MedVet."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from backend.observability import get_logger

log = get_logger(__name__)


@dataclass
class ListingResult:
    nome: str
    link: str
    informacoes_visiveis: str = ""
    substancias_ativas: list[str] = field(default_factory=list)
    especies: Optional[str] = None
    forma_farmaceutica: Optional[str] = None
    principio_ativo: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "nome": self.nome,
            "link": self.link,
            "url": self.link,  # compat com formato antigo
            "informacoes_visiveis": self.informacoes_visiveis,
            "substancias_ativas": self.substancias_ativas,
            "especies": self.especies,
            "forma_farmaceutica": self.forma_farmaceutica,
            "principio_ativo": self.principio_ativo,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ListingResult":
        """Reconstrói a partir de dict, ignorando chaves extras (ex.: ``url`` compat)."""
        valid = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in valid})


_SUBST_PATTERN = re.compile(
    r"Substância(?:s)?\s*(?:\(s\))?\s*Ativa(?:s)?\s*(?:\(s\))?[:]\s*(.+?)(?:\s*\|\s*Espécie|\s*$)",
    re.IGNORECASE,
)
_CONC_PATTERN = re.compile(r"\d+[.,]?\d*\s*(?:mg|ml|g|mcg|µg)(?:/(?:ml|kg|g))?", re.IGNORECASE)


def parse_substancias_ativas(informacoes_visiveis: str) -> list[str]:
    """Extrai substâncias activas de uma string "Substância Ativa: X 50 mg | Y 10 mg"."""
    if not informacoes_visiveis:
        return []
    m = _SUBST_PATTERN.search(informacoes_visiveis)
    if not m:
        return []
    raw = m.group(1).strip()
    out: list[str] = []
    for part in raw.split("|"):
        cleaned = _CONC_PATTERN.sub("", part).strip(" ,;.")
        if cleaned:
            out.append(cleaned)
    return out


class ListingParser:
    """Faz parsing das páginas de busca."""

    def parse(self, html: str, base_url: str) -> list[ListingResult]:
        soup = BeautifulSoup(html, "html.parser")
        items = soup.find_all("div", class_="search-result")
        if items:
            return self._parse_search_results(items, base_url)
        return self._parse_link_list(soup, base_url)

    def _parse_search_results(self, items, base_url: str) -> list[ListingResult]:
        out: list[ListingResult] = []
        for div in items:
            h5 = div.find("h5")
            nome = h5.get_text(strip=True) if h5 else ""
            link_tag = div.find("a", href=True)
            link = urljoin(base_url, link_tag["href"]) if link_tag else ""
            if not nome or not link:
                continue

            texto = div.get_text(separator=" ", strip=True)
            substancias = parse_substancias_ativas(texto)

            result = ListingResult(
                nome=nome,
                link=link,
                informacoes_visiveis=texto,
                substancias_ativas=substancias,
            )

            for linha in texto.split("\n"):
                ll = linha.strip().lower()
                if not ll:
                    continue
                if any(kw in ll for kw in ("espécie", "especie", "animal")):
                    result.especies = linha.strip()
                elif any(kw in ll for kw in ("forma", "apresentação", "apresentacao")):
                    result.forma_farmaceutica = linha.strip()
                elif any(kw in ll for kw in ("princípio", "principio", "substância", "substancia", "ativo")):
                    result.principio_ativo = linha.strip()

            out.append(result)
        return out

    def _parse_link_list(self, soup, base_url: str) -> list[ListingResult]:
        results: list[ListingResult] = []
        seen = set()
        for a in soup.find_all("a", href=True):
            url = urljoin(base_url, a["href"])
            if "medvet.dgav.pt/medvet/med" not in url:
                continue
            nome = a.get_text(strip=True) or "Sem nome"
            if nome in seen:
                continue
            seen.add(nome)
            results.append(ListingResult(nome=nome, link=url, informacoes_visiveis=nome))
        return results
