"""Busca de medicamentos no portal MedVet.

Estratégia:
1. Tenta `requests` direto na URL de busca (pode funcionar dependendo do site).
2. Se o resultado vier vazio, recorre a Selenium como fallback.

Isto reduz drasticamente o overhead em condições normais (~3s de boot do Chrome
eliminados por consulta) e preserva o caminho original como rede de segurança.

TIER 2 (TODO): validar empiricamente se o endpoint da MedVet aceita GET direto;
em caso afirmativo, remover Selenium completamente.
"""

from __future__ import annotations

import time
from typing import Optional
from urllib.parse import quote, urljoin

import requests
import urllib3

from backend.cache import DiskKVStore, KVStore, make_key
from backend.config import get_settings
from backend.medvet.parser_listing import ListingParser, ListingResult
from backend.observability import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

log = get_logger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    )
}


class MedVetSearch:
    def __init__(self, cache: Optional[KVStore] = None) -> None:
        self.settings = get_settings()
        self.cache = cache or DiskKVStore(self.settings.cache_dir / "search")
        self.parser = ListingParser()

    # ----------------------------------------------------------------- API

    def search(self, term: str, use_cache: bool = True) -> list[ListingResult]:
        key = make_key("search", term)
        if use_cache:
            cached = self.cache.get(key)
            if cached is not None:
                log.info("Cache HIT search: %s", term)
                return [ListingResult.from_dict(c) for c in cached]

        results = self._search_http(term)
        if not results and self.settings.selenium_enabled:
            log.info("HTTP retornou vazio, tentando Selenium para: %s", term)
            results = self._search_selenium(term)

        if use_cache and results:
            self.cache.set(
                key,
                [r.to_dict() for r in results],
                ttl_s=self.settings.cache_ttl_search,
            )
        return results

    # ----------------------------------------------------------------- HTTP path

    def _search_http(self, term: str) -> list[ListingResult]:
        candidates = [
            f"{self.settings.medvet_base_url}/?q={quote(term)}",
            f"{self.settings.medvet_base_url}/medvet/search?q={quote(term)}",
            f"{self.settings.medvet_base_url}/?search={quote(term)}",
        ]
        for url in candidates:
            try:
                resp = requests.get(url, headers=_HEADERS, timeout=20, verify=False, allow_redirects=True)
                resp.raise_for_status()
                results = self.parser.parse(resp.text, str(resp.url))
                if results:
                    log.info("Search HTTP OK (%s): %d resultados", resp.url, len(results))
                    return results
            except requests.RequestException as exc:
                log.debug("Search HTTP falhou em %s: %s", url, exc)
        return []

    # ----------------------------------------------------------------- Selenium fallback

    def _search_selenium(self, term: str) -> list[ListingResult]:
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.keys import Keys
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.support.ui import WebDriverWait
        except ImportError:
            log.error("Selenium não instalado e HTTP falhou — instale selenium")
            return []

        opts = Options()
        if self.settings.selenium_headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--no-sandbox")
        opts.add_argument(f"user-agent={_HEADERS['User-Agent']}")

        driver = None
        try:
            driver = webdriver.Chrome(options=opts)
            driver.get(self.settings.medvet_base_url)
            wait = WebDriverWait(driver, 20)
            box = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text'], input[type='search']"))
            )
            box.send_keys(term)
            box.send_keys(Keys.RETURN)
            time.sleep(2)
            url = driver.current_url
            if not url or url == self.settings.medvet_base_url + "/":
                return []
            return self._fetch_and_parse(url)
        except Exception as exc:  # noqa: BLE001
            log.error("Selenium falhou: %s", exc)
            return []
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:  # noqa: BLE001
                    pass

    def _fetch_and_parse(self, url: str) -> list[ListingResult]:
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=20, verify=False)
            resp.raise_for_status()
            return self.parser.parse(resp.text, str(resp.url))
        except requests.RequestException as exc:
            log.error("Falha ao buscar URL %s: %s", url, exc)
            return []
