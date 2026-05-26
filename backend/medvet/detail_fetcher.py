"""Fetcher async dos detalhes (HTML + PDF) de páginas de medicamento."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional

import aiohttp
from bs4 import BeautifulSoup

from backend.cache import DiskKVStore, KVStore, make_key
from backend.config import get_settings
from backend.medvet.parser_listing import ListingResult
from backend.medvet.pdf_fetcher import PDFFetcher
from backend.observability import get_logger
from backend.pdf import Chunk, PDFExtractor, PDFSection

log = get_logger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    )
}
_TAGS_KEEP = {"h1", "h2", "h3", "h4", "h5", "p", "a"}


@dataclass
class MedicamentoDetail:
    listing: ListingResult
    conteudo_html: str = ""
    pdf_url: Optional[str] = None
    pdf_sections: list[PDFSection] = field(default_factory=list)
    # v2.1: chunks atómicos (P1). Preenchidos pelo DetailFetcher quando o
    # extractor for chamado com `extract_chunks`. Vazio se ainda não calculados.
    pdf_chunks: list[Chunk] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = self.listing.to_dict()
        d["conteudo_html"] = self.conteudo_html
        d["pdf_url"] = self.pdf_url
        d["conteudo_pdf"] = [s.to_text() for s in self.pdf_sections]
        d["pdf_chunks_count"] = len(self.pdf_chunks)
        return d


class DetailFetcher:
    def __init__(
        self,
        pdf_fetcher: Optional[PDFFetcher] = None,
        pdf_extractor: Optional[PDFExtractor] = None,
        cache: Optional[KVStore] = None,
    ) -> None:
        s = get_settings()
        self.settings = s
        self.pdf_fetcher = pdf_fetcher or PDFFetcher()
        self.pdf_extractor = pdf_extractor or PDFExtractor(max_pages=s.max_pdf_pages)
        self.cache = cache or DiskKVStore(s.cache_dir / "html")

    async def fetch_many(self, listings: list[ListingResult]) -> list[MedicamentoDetail]:
        connector = aiohttp.TCPConnector(limit=self.settings.medvet_concurrent, ssl=False)
        async with aiohttp.ClientSession(connector=connector, headers=_HEADERS) as session:
            tasks = [self._fetch_one(session, l) for l in listings]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        out: list[MedicamentoDetail] = []
        for r in results:
            if isinstance(r, MedicamentoDetail):
                out.append(r)
            elif isinstance(r, Exception):
                log.warning("Falha em fetch_one: %s", r)
        return out

    async def _fetch_one(self, session: aiohttp.ClientSession, listing: ListingResult) -> MedicamentoDetail:
        cache_key = make_key("html", listing.link)
        html = self.cache.get(cache_key)
        if html is None:
            try:
                async with session.get(listing.link, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status != 200:
                        return MedicamentoDetail(listing=listing)
                    html = await resp.text()
                self.cache.set(cache_key, html, ttl_s=self.settings.cache_ttl_html)
            except Exception as exc:  # noqa: BLE001
                log.warning("Erro a baixar página %s: %s", listing.link, exc)
                return MedicamentoDetail(listing=listing)

        detail = MedicamentoDetail(listing=listing, conteudo_html=self._extract_text(html))

        pdf_url = self.pdf_fetcher.find_pdf_link(html, listing.link)
        if pdf_url:
            detail.pdf_url = pdf_url
            pdf_path = await self.pdf_fetcher.fetch_async(session, pdf_url)
            if pdf_path:
                # v2.1: extrai secções (compat) E chunks atómicos (P1).
                detail.pdf_sections = self.pdf_extractor.extract(pdf_path)
                detail.pdf_chunks = self.pdf_extractor.extract_chunks(
                    pdf_path, medicamento=listing.nome,
                )

        return detail

    @staticmethod
    def _extract_text(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        main = soup.find("article") or soup.find("main") or soup.body
        if not main:
            return ""
        parts: list[str] = []
        for el in main.find_all(_TAGS_KEEP, recursive=True):
            text = el.get_text(strip=True)
            if not text:
                continue
            if el.name in {"h1", "h2", "h3", "h4", "h5"}:
                parts.append(f"\n## {text}")
            else:
                parts.append(text)
        return " ".join(parts).strip()
