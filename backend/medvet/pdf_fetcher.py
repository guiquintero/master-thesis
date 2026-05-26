"""Download de PDFs com cache em disco.

Mantém compatibilidade com o cache antigo (`pdf_cache_otimizado/`):
o nome do ficheiro continua sendo `md5(pdf_url).pdf`, então os PDFs já
baixados são reaproveitados após o refactor.
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import aiohttp
import requests
from bs4 import BeautifulSoup

from backend.config import get_settings
from backend.observability import get_logger

log = get_logger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    )
}


class PDFFetcher:
    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        s = get_settings()
        self.cache_dir = Path(cache_dir or s.pdf_cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ----------------------------------------------------------------- find pdf in page

    @staticmethod
    def find_pdf_link(html: str, page_url: str) -> Optional[str]:
        soup = BeautifulSoup(html, "html.parser")
        tag = soup.find("a", href=True, target="_blank")
        if tag and tag.find("span", class_="fa-file-pdf-o"):
            return urljoin(page_url, tag["href"])
        # Fallback: qualquer <a href="...pdf">
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.lower().endswith(".pdf"):
                return urljoin(page_url, href)
        return None

    # ----------------------------------------------------------------- sync

    def fetch_sync(self, pdf_url: str) -> Optional[Path]:
        path = self._path_for(pdf_url)
        if path.exists():
            return path
        try:
            resp = requests.get(pdf_url, headers=_HEADERS, timeout=30, verify=False)
            resp.raise_for_status()
            path.write_bytes(resp.content)
            log.info("PDF salvo: %s", path.name)
            return path
        except Exception as exc:  # noqa: BLE001
            log.error("Erro a baixar PDF %s: %s", pdf_url, exc)
            return None

    # ----------------------------------------------------------------- async

    async def fetch_async(self, session: aiohttp.ClientSession, pdf_url: str) -> Optional[Path]:
        path = self._path_for(pdf_url)
        if path.exists():
            return path
        try:
            async with session.get(pdf_url, ssl=False, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    log.warning("PDF status %d: %s", resp.status, pdf_url)
                    return None
                data = await resp.read()
                path.write_bytes(data)
                log.info("PDF salvo (async): %s", path.name)
                return path
        except Exception as exc:  # noqa: BLE001
            log.error("Erro async a baixar PDF %s: %s", pdf_url, exc)
            return None

    # ----------------------------------------------------------------- helpers

    def _path_for(self, url: str) -> Path:
        return self.cache_dir / (hashlib.md5(url.encode("utf-8")).hexdigest() + ".pdf")
