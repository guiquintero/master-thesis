"""Configuração central por variáveis de ambiente.

Funciona em três modos:
- `local`    → roda diretamente na máquina do desenvolvedor
- `docker`   → roda em container, Ollama é outro container/host
- `server`   → faculdade/produção, normalmente Ollama em host dedicado

Cada flag tem default seguro; só é necessário sobrescrever o que muda.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Literal

Mode = Literal["local", "docker", "server"]


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # ---- Modo / ambiente
    mode: Mode = field(default_factory=lambda: _env("APP_MODE", "local"))  # type: ignore[arg-type]
    debug: bool = field(default_factory=lambda: _env_bool("APP_DEBUG", False))

    # ---- Caminhos
    project_root: Path = field(default_factory=lambda: Path(_env("PROJECT_ROOT", str(Path(__file__).resolve().parents[2]))))
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", str(Path(__file__).resolve().parents[2] / "data"))))
    cache_dir: Path = field(default_factory=lambda: Path(_env("CACHE_DIR", str(Path(__file__).resolve().parents[2] / "data" / "cache"))))
    pdf_cache_dir: Path = field(default_factory=lambda: Path(_env("PDF_CACHE_DIR", str(Path(__file__).resolve().parents[2] / "pdf_cache_otimizado"))))
    index_dir: Path = field(default_factory=lambda: Path(_env("INDEX_DIR", str(Path(__file__).resolve().parents[2] / "data" / "index"))))
    catalog_dir: Path = field(default_factory=lambda: Path(_env("CATALOG_DIR", str(Path(__file__).resolve().parents[2] / "data" / "medvet_catalog"))))

    # ---- Ollama
    ollama_host: str = field(default_factory=lambda: _env("OLLAMA_HOST", "http://127.0.0.1:11434"))
    ollama_model: str = field(default_factory=lambda: _env("OLLAMA_MODEL", "qwen3:8b"))
    ollama_embed_model: str = field(default_factory=lambda: _env("OLLAMA_EMBED_MODEL", "nomic-embed-text"))
    ollama_temperature: float = field(default_factory=lambda: float(_env("OLLAMA_TEMPERATURE", "0.0")))
    ollama_timeout_s: int = field(default_factory=lambda: _env_int("OLLAMA_TIMEOUT", 120))
    ollama_num_predict: int = field(default_factory=lambda: _env_int("OLLAMA_NUM_PREDICT", 1000))

    # ---- MedVet
    medvet_base_url: str = field(default_factory=lambda: _env("MEDVET_BASE_URL", "https://medvet.dgav.pt"))
    medvet_max_results: int = field(default_factory=lambda: _env_int("MEDVET_MAX_RESULTS", 10))
    medvet_concurrent: int = field(default_factory=lambda: _env_int("MEDVET_CONCURRENT", 5))
    selenium_enabled: bool = field(default_factory=lambda: _env_bool("SELENIUM_ENABLED", True))
    selenium_headless: bool = field(default_factory=lambda: _env_bool("SELENIUM_HEADLESS", True))

    # ---- Cache TTLs (segundos)
    cache_ttl_classification: int = field(default_factory=lambda: _env_int("CACHE_TTL_CLASSIFICATION", 7 * 86400))
    cache_ttl_search: int = field(default_factory=lambda: _env_int("CACHE_TTL_SEARCH", 86400))
    cache_ttl_html: int = field(default_factory=lambda: _env_int("CACHE_TTL_HTML", 7 * 86400))
    cache_ttl_response: int = field(default_factory=lambda: _env_int("CACHE_TTL_RESPONSE", 86400))

    # ---- API
    api_host: str = field(default_factory=lambda: _env("API_HOST", "0.0.0.0"))
    api_port: int = field(default_factory=lambda: _env_int("API_PORT", 5000))
    cors_origins: str = field(default_factory=lambda: _env("CORS_ORIGINS", "*"))
    api_workers: int = field(default_factory=lambda: _env_int("API_WORKERS", 1))

    # ---- Limites
    # v2.1: subiu de 12000 → 30000 (com 24 GB VRAM e modelos 32k contexto
    # nativo há margem confortável; o retriever híbrido garante que apenas
    # chunks relevantes entram).
    context_chars_limit: int = field(default_factory=lambda: _env_int("CONTEXT_CHARS_LIMIT", 30000))
    max_pdf_pages: int = field(default_factory=lambda: _env_int("MAX_PDF_PAGES", 20))

    # ---- Retrieval
    retriever_top_k: int = field(default_factory=lambda: _env_int("RETRIEVER_TOP_K", 8))
    # v2.1: ON por default — usa Ollama embed model. Cai para BM25 puro se
    # o modelo embed não estiver instalado.
    retriever_use_embeddings: bool = field(default_factory=lambda: _env_bool("RETRIEVER_USE_EMBEDDINGS", True))
    # Threshold mínimo (cosine sim) abaixo do qual chunks denso são ignorados
    retriever_dense_min_sim: float = field(default_factory=lambda: float(_env("RETRIEVER_DENSE_MIN_SIM", "0.30")))
    # Confiança mínima da resposta LLM (P5) abaixo da qual o pipeline re-prompta (P4)
    answer_min_confidence: float = field(default_factory=lambda: float(_env("ANSWER_MIN_CONFIDENCE", "0.55")))
    # Tamanho da janela ao expandir contexto no re-prompting
    reprompt_expand_factor: int = field(default_factory=lambda: _env_int("REPROMPT_EXPAND_FACTOR", 2))

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.cache_dir, self.pdf_cache_dir, self.index_dir, self.catalog_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
