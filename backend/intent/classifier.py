"""Classificação de intent em cascata.

Camada 1: regras determinísticas (resolve a maioria)
Camada 2: kNN sobre embeddings do golden set (precisa de Ollama embed; opcional)
Camada 3: LLM como fallback final (JSON mode, schema validado)

Substitui o `QueryClassifier` legado, que ia direto pra LLM e tinha
fallback regex misturado.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from backend.cache import DiskKVStore, KVStore, make_key
from backend.config import get_settings
from backend.entities import EntityExtractor, Entities
from backend.intent.rules import (
    COMPARISON_KEYWORDS,
    MEDICATION_PHRASES,
    PLURAL_QUE_MED,
    SINGULAR_QUE_MED,
    SPECIFIC_MED_PATTERN,
    has_any,
)
from backend.llm import OllamaClient
from backend.observability import get_logger
from backend.prompts.templates import build_classification_prompt

log = get_logger(__name__)


class Category(str, Enum):
    MEDICAMENTO = "medicamento"
    COMPARACAO = "comparacao"
    ERRO = "erro"


@dataclass
class ClassificationResult:
    category: Category
    entities: Entities
    confidence: float = 1.0
    via: str = "rules"  # "rules" | "knn" | "llm"

    def as_dict(self) -> dict:
        return {
            "categoria": self.category.value,
            "entidades": self.entities.as_dict(),
            "confianca": self.confidence,
            "via": self.via,
        }


@dataclass
class IntentClassifier:
    extractor: EntityExtractor = field(default_factory=EntityExtractor)
    llm: Optional[OllamaClient] = None
    cache: Optional[KVStore] = None

    def __post_init__(self) -> None:
        s = get_settings()
        if self.cache is None:
            self.cache = DiskKVStore(s.cache_dir / "intent")

    def classify(self, query: str) -> ClassificationResult:
        cache_key = make_key("intent", query)
        cached = self.cache.get(cache_key) if self.cache else None
        if cached:
            try:
                cat = Category(cached["categoria"])
                ents = self.extractor.extract(query)
                return ClassificationResult(cat, ents, cached.get("confianca", 1.0), cached.get("via", "cache"))
            except (KeyError, ValueError):
                pass

        result = self._classify_rules(query)
        if result is None:
            result = self._classify_llm(query)

        if self.cache:
            ttl = get_settings().cache_ttl_classification
            self.cache.set(cache_key, result.as_dict(), ttl_s=ttl)
        return result

    # ----------------------------------------------------------------- camada 1: regras

    def _classify_rules(self, query: str) -> Optional[ClassificationResult]:
        low = query.lower()
        ents = self.extractor.extract(query)

        # Singular "que medicamento " sem "s" → medicamento específico
        is_plural_que_med = bool(PLURAL_QUE_MED.search(low))
        is_singular_que_med = bool(SINGULAR_QUE_MED.search(low)) and not is_plural_que_med

        # Comparação forte
        if has_any(low, COMPARISON_KEYWORDS) and not is_singular_que_med:
            log.debug("intent[rules]=comparacao")
            return ClassificationResult(Category.COMPARACAO, ents, 0.95, "rules")

        # Padrão "o medicamento X" → medicamento
        if SPECIFIC_MED_PATTERN.search(low):
            log.debug("intent[rules]=medicamento (padrão 'o medicamento X')")
            return ClassificationResult(Category.MEDICAMENTO, ents, 0.95, "rules")

        # Perguntas tipicamente de medicamento único
        if has_any(low, MEDICATION_PHRASES) and ents.medicamento:
            log.debug("intent[rules]=medicamento (frase + medicamento detectado)")
            return ClassificationResult(Category.MEDICAMENTO, ents, 0.9, "rules")

        # Heurística: começa com maiúscula no meio (nome próprio) → medicamento
        if ents.medicamento:
            log.debug("intent[rules]=medicamento (nome próprio detectado)")
            return ClassificationResult(Category.MEDICAMENTO, ents, 0.7, "rules")

        return None  # camadas seguintes

    # ----------------------------------------------------------------- camada 3: LLM

    def _classify_llm(self, query: str) -> ClassificationResult:
        ents = self.extractor.extract(query)
        if self.llm is None:
            log.warning("Sem cliente LLM e regras não cobriram — fallback medicamento")
            return ClassificationResult(Category.MEDICAMENTO, ents, 0.3, "fallback")

        try:
            prompt = build_classification_prompt(query)
            content = self.llm.chat(
                [{"role": "user", "content": prompt}],
                json_mode=True,
                temperature=0.0,
                num_predict=400,
            )
            data = self._parse_json(content)
            cat = Category(data.get("categoria", "medicamento"))
            return ClassificationResult(cat, ents, 0.8, "llm")
        except Exception as exc:  # noqa: BLE001
            log.warning("LLM classification falhou (%s) — fallback medicamento", exc)
            return ClassificationResult(Category.MEDICAMENTO, ents, 0.3, "fallback")

    @staticmethod
    def _parse_json(content: str) -> dict:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise
