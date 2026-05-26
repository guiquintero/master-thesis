"""Orchestrador principal do pipeline de consulta.

v2.1 — Sprint RAG:
  P1 chunking semântico (já no DetailFetcher → extract_chunks)
  P2 retriever híbrido (BM25 + denso/embeddings com RRF)
  P3 desambiguação entidade → PDF (rank por similaridade + score)
  P4 re-prompting com contexto expandido em vez de fallback fixo
  P5 output estruturado JSON do LLM (LLMResponse tipado)
  P6 janela de contexto útil maior (30 000 chars) + threshold de relevância
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional

from backend.cache import DiskKVStore, KVStore, make_key
from backend.comparison import ComparisonEngine
from backend.config import get_settings
from backend.entities import EntityExtractor, Entities, InfoType
from backend.entities.species_map import normalize_species
from backend.intent import Category, IntentClassifier
from backend.llm import OllamaClient
from backend.medvet import DetailFetcher, MedicamentoDetail, MedVetSearch, pick_best
from backend.observability import StepTimer, TimingReport, get_logger
from backend.orchestrator.conversation import ConversationState, ConversationStore
from backend.orchestrator.dose_extractor import extract_doses
from backend.orchestrator.followup import detect_and_rewrite
from backend.pdf import Chunk
from backend.prompts import (
    DoseValidator,
    LLMResponse,
    build_dose_prompt,
    build_rag_prompt,
    parse_llm_response,
    render_for_user,
)
from backend.retriever import (
    DenseRetriever,
    HybridRetriever,
    LexicalRetriever,
    SectionRetriever,
)

log = get_logger(__name__)


@dataclass
class PipelineResult:
    response: str
    category: str
    entities: dict
    via: str
    timings: dict[str, float]
    session_id: str
    confidence: float = 1.0
    sources: list[dict] = field(default_factory=list)


@dataclass
class Pipeline:
    """Pipeline determinístico: classify → fetch → chunk → retrieve → answer → (re-prompt?)."""

    llm: Optional[OllamaClient] = None
    classifier: Optional[IntentClassifier] = None
    search: Optional[MedVetSearch] = None
    detail_fetcher: Optional[DetailFetcher] = None
    comparison: Optional[ComparisonEngine] = None
    section_retriever: SectionRetriever = field(default_factory=SectionRetriever)
    response_cache: Optional[KVStore] = None
    conversations: ConversationStore = field(default_factory=ConversationStore)
    # v2.1: retriever híbrido construído por-pergunta (índice in-memory dos
    # chunks do PDF actual). Para corpus pré-indexado global usar DenseRetriever
    # apontando para ChromaVectorStore persistente.
    enable_dense_retrieval: Optional[bool] = None

    def __post_init__(self) -> None:
        s = get_settings()
        self.llm = self.llm or OllamaClient()
        self.classifier = self.classifier or IntentClassifier(
            extractor=EntityExtractor(), llm=self.llm
        )
        self.search = self.search or MedVetSearch()
        self.detail_fetcher = self.detail_fetcher or DetailFetcher()
        self.comparison = self.comparison or ComparisonEngine(search=self.search)
        if self.response_cache is None:
            self.response_cache = DiskKVStore(s.cache_dir / "responses")
        if self.enable_dense_retrieval is None:
            self.enable_dense_retrieval = s.retriever_use_embeddings

    # ----------------------------------------------------------------- entrypoint

    def run(self, query: str, session_id: str = "default") -> PipelineResult:
        report = TimingReport()
        state = self.conversations.get(session_id)

        with StepTimer(report, "followup"):
            fu = detect_and_rewrite(query, state)
            if fu.is_followup and fu.rewritten_query:
                log.info("Follow-up reescrito: %s → %s", query, fu.rewritten_query)
                query = fu.rewritten_query

        query_norm = normalize_species(query)

        with StepTimer(report, "classification"):
            classification = self.classifier.classify(query_norm)

        log.info("Categoria: %s (via=%s)", classification.category.value, classification.via)
        entities = classification.entities

        if classification.category == Category.COMPARACAO and self._is_alternative_question(query_norm):
            with StepTimer(report, "comparison"):
                response = self.comparison.find_alternatives(
                    entities, tipo_pergunta=self._alternative_type(query_norm)
                )
            return self._finalize(report, state, query, response,
                                  classification.category.value, entities,
                                  classification.via, session_id)

        if classification.category == Category.COMPARACAO:
            return self._handle_listing(query_norm, entities, classification.via,
                                        state, session_id, report)

        return self._handle_medicamento(query_norm, entities, classification.via,
                                        state, session_id, report)

    # ----------------------------------------------------------------- medicamento

    def _handle_medicamento(
        self,
        query: str,
        entities: Entities,
        via: str,
        state: ConversationState,
        session_id: str,
        report: TimingReport,
    ) -> PipelineResult:
        cache_key = make_key(
            "response", entities.termo_busca, entities.info_type.value,
            entities.especie_alvo or "", self.llm.model,
        )
        cached = self.response_cache.get(cache_key) if self.response_cache else None
        if cached:
            log.info("Resposta servida do cache")
            return self._finalize(report, state, query, cached, "medicamento",
                                  entities, "cache", session_id)

        # 1. Busca MedVet
        with StepTimer(report, "scraping"):
            listings = self.search.search(entities.termo_busca)
            if not listings:
                return self._finalize_with_fallback(
                    report, state, query, entities, via, session_id,
                    "Não foram encontrados resultados para a tua pergunta no portal MedVet.",
                )
            details = asyncio.run(self.detail_fetcher.fetch_many(
                listings[: get_settings().medvet_max_results]
            ))

        if not details:
            return self._finalize_with_fallback(
                report, state, query, entities, via, session_id,
                "Foi encontrada uma entrada no MedVet mas não foi possível extrair o conteúdo.",
            )

        # 2. P3 — desambiguação: escolhe o melhor match em vez de details[0]
        with StepTimer(report, "disambiguation"):
            ranked_listings = [d.listing for d in details]
            best_listing, ranked = pick_best(
                ranked_listings,
                termo_busca=entities.termo_busca,
                especie_alvo=entities.especie_alvo,
                substancia_ativa=entities.substancia_ativa,
            )
            primary = next((d for d in details if d.listing.link == best_listing.link), details[0])
            log.info("Disambiguator escolheu: %s", primary.listing.nome)

        # 3. Retrieval: hybrid sobre chunks (P1 + P2) + filtro estrutural (SectionRetriever)
        with StepTimer(report, "retrieval"):
            chunks = primary.pdf_chunks or self._chunks_fallback(primary)
            if not chunks:
                return self._finalize_with_fallback(
                    report, state, query, entities, via, session_id,
                    "O PDF deste medicamento não pôde ser interpretado.",
                )

            relevant = self._retrieve(query, chunks, entities.info_type)

        # 4. Resposta + (P4) re-prompting se confiança baixa
        with StepTimer(report, "answer"):
            llm_resp = self._answer(query, entities, primary, relevant)

            if llm_resp.needs_reprompt(min_confidence=get_settings().answer_min_confidence):
                log.info("Resposta com baixa confiança (%.2f, found=%s) — re-promptando",
                         llm_resp.confianca, llm_resp.encontrada_no_documento)
                with StepTimer(report, "reprompt"):
                    expanded = self._expand_context(query, chunks, relevant)
                    llm_resp2 = self._answer(query, entities, primary, expanded, is_reprompt=True)
                    # Fica com o melhor dos dois
                    if llm_resp2.confianca >= llm_resp.confianca and llm_resp2.encontrada_no_documento:
                        llm_resp = llm_resp2

        response_text = render_for_user(llm_resp)
        response_text = self._format_provenance(response_text, primary, ranked)

        if response_text and self.response_cache and llm_resp.encontrada_no_documento:
            self.response_cache.set(cache_key, response_text,
                                    ttl_s=get_settings().cache_ttl_response)

        return self._finalize(
            report, state, query, response_text, "medicamento", entities, via,
            session_id, confidence=llm_resp.confianca,
            sources=[{"secao": f.secao, "trecho": f.trecho} for f in llm_resp.fontes],
        )

    # ----------------------------------------------------------------- comparação (listing)

    def _handle_listing(
        self,
        query: str,
        entities: Entities,
        via: str,
        state: ConversationState,
        session_id: str,
        report: TimingReport,
    ) -> PipelineResult:
        with StepTimer(report, "scraping"):
            term = " ".join(
                t for t in (entities.substancia_ativa, entities.especie_alvo, entities.forma_farmaceutica) if t
            ).strip() or entities.termo_busca
            results = self.search.search(term)

        if not results:
            return self._finalize_with_fallback(
                report, state, query, entities, via, session_id,
                "Não foram encontrados resultados para esta consulta no portal MedVet.",
            )

        lines = [f"Resultados para '{term}' ({len(results)}):\n"]
        for i, item in enumerate(results, 1):
            lines.append(f"{i}. **{item.nome}**")
            if item.especies:
                lines.append(f"   - Espécies: {item.especies}")
            if item.forma_farmaceutica:
                lines.append(f"   - Forma: {item.forma_farmaceutica}")
            if item.principio_ativo:
                lines.append(f"   - Princípio activo: {item.principio_ativo}")
            if item.link:
                lines.append(f"   - Link: {item.link}")

        return self._finalize(report, state, query, "\n".join(lines), "comparacao",
                              entities, via, session_id)

    # ----------------------------------------------------------------- retrieval

    def _retrieve(self, query: str, chunks: list[Chunk], info_type: InfoType) -> list[Chunk]:
        """Section filter (P3 antigo) → hybrid retriever (P2) → top-k."""
        s = get_settings()

        # Filtro estrutural por secção SmPC. Se for None, usa universo todo.
        filtered = self.section_retriever.retrieve(chunks, info_type) or chunks

        # Hybrid retriever (BM25 + denso opcional)
        dense = None
        if self.enable_dense_retrieval:
            try:
                dense = DenseRetriever(llm=self.llm, top_k=s.retriever_top_k)
            except Exception as exc:  # noqa: BLE001
                log.warning("DenseRetriever indisponível (%s) — usando só BM25", exc)
                dense = None

        hybrid = HybridRetriever(
            lexical=LexicalRetriever(top_k=s.retriever_top_k),
            dense=dense,
            top_k=s.retriever_top_k,
            dense_min_similarity=s.retriever_dense_min_sim,
        )
        hybrid.index(filtered)
        return hybrid.search(query, top_k=s.retriever_top_k)

    def _expand_context(self, query: str, all_chunks: list[Chunk],
                        already: list[Chunk]) -> list[Chunk]:
        """P4: ao re-promptar, alarga top-k para incluir chunks vizinhos."""
        s = get_settings()
        bigger = LexicalRetriever(top_k=s.retriever_top_k * s.reprompt_expand_factor)
        bigger.index(all_chunks)
        results = bigger.search(query, top_k=s.retriever_top_k * s.reprompt_expand_factor)
        # Garante que mantemos os iniciais + adiciona novos
        seen = set()
        merged: list[Chunk] = []
        for c in already + results:
            key = (c.section_num, c.paragraph_idx, c.text[:80])
            if key not in seen:
                seen.add(key)
                merged.append(c)
        return merged

    def _chunks_fallback(self, detail: MedicamentoDetail) -> list[Chunk]:
        """Se por algum motivo pdf_chunks vier vazio (PDF antigo), constrói
        chunks ad-hoc a partir das pdf_sections."""
        from backend.pdf import SemanticChunker

        if not detail.pdf_sections:
            return []
        chunker = SemanticChunker()
        joined = "\n\n".join(
            (f"{s.number}. {s.title}\n{s.body}".strip())
            for s in detail.pdf_sections
        )
        return chunker.chunk(joined, source_pdf=detail.pdf_url,
                             medicamento=detail.listing.nome)

    # ----------------------------------------------------------------- answer

    def _answer(
        self,
        query: str,
        entities: Entities,
        detail: MedicamentoDetail,
        chunks: list[Chunk],
        *,
        is_reprompt: bool = False,
    ) -> LLMResponse:
        s = get_settings()
        texts = [c.to_text() for c in chunks]
        texts = self._truncate_to_budget(texts, s.context_chars_limit)

        # Caminho especializado para perguntas de dose: extracção determinística
        # seguida de validação rigorosa.
        if entities.info_type == InfoType.DOSE:
            doses = extract_doses(self._chunks_as_sections(chunks),
                                  species=entities.especie_alvo)
            if doses:
                prompt = build_dose_prompt(
                    query,
                    medicamento=detail.listing.nome,
                    secoes=texts,
                    doses_extraidas=[d.display() for d in doses],
                    especie=entities.especie_alvo,
                )
                raw = self.llm.chat(
                    [{"role": "user", "content": prompt}],
                    temperature=0.0, num_predict=700, json_mode=True,
                )
                llm_resp = parse_llm_response(raw)
                # Validação rigorosa (P5 + dose validator)
                validator = DoseValidator(allowed=[d.display() for d in doses])
                ok, invalid = validator.validate(llm_resp.resposta)
                if not ok:
                    log.warning("Doses inválidas %s — substituindo por extracção determinística", invalid)
                    llm_resp.resposta = self._deterministic_dose_answer(
                        detail.listing.nome, entities.especie_alvo, doses,
                    )
                    llm_resp.encontrada_no_documento = True
                    llm_resp.confianca = 0.85
                return llm_resp

        # Caminho geral
        prompt = build_rag_prompt(
            query,
            medicamento=detail.listing.nome,
            secoes=texts,
            especie=entities.especie_alvo,
            tipo_info=entities.info_type.value if entities.info_type != InfoType.GERAL else None,
        )
        raw = self.llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.0, num_predict=900, json_mode=True,
        )
        return parse_llm_response(raw)

    @staticmethod
    def _chunks_as_sections(chunks: list[Chunk]):
        """Adaptador para extract_doses (que aceita PDFSection)."""
        from backend.pdf import PDFSection
        return [
            PDFSection(
                number=c.section_num, title=c.section_title,
                body=c.text, has_table=c.is_table,
            )
            for c in chunks
        ]

    @staticmethod
    def _truncate_to_budget(texts: list[str], char_budget: int) -> list[str]:
        """Mantém top-N até esgotar o budget de chars (P6)."""
        out = []
        used = 0
        for t in texts:
            if used + len(t) > char_budget:
                # corta o último chunk para encaixar
                remaining = char_budget - used
                if remaining > 200:
                    out.append(t[:remaining])
                break
            out.append(t)
            used += len(t)
        return out

    @staticmethod
    def _deterministic_dose_answer(medicamento: str, especie: Optional[str], doses) -> str:
        head = f"Segundo o documento de {medicamento}"
        if especie:
            head += f", para {especie}"
        if len(doses) == 1:
            return f"{head}, a dose indicada é {doses[0].display()}."
        body = "\n".join(f"- {d.display()}" for d in doses)
        return f"{head}, as doses indicadas são:\n{body}"

    @staticmethod
    def _format_provenance(response: str, primary: MedicamentoDetail, ranked) -> str:
        """Adiciona linha de proveniência (qual PDF foi consultado)."""
        if not primary:
            return response
        prov = f"\n\n---\nMedicamento consultado: **{primary.listing.nome}**"
        if primary.listing.link:
            prov += f"\n{primary.listing.link}"
        # Se houve ambiguidade significativa, regista outros candidatos
        if len(ranked) > 1 and (ranked[0].score - ranked[1].score) < 0.10:
            prov += f"\n\n_(também encontrados: " + ", ".join(
                r.listing.nome for r in ranked[1:3]
            ) + ")_"
        return response + prov

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _is_alternative_question(query: str) -> bool:
        low = query.lower()
        return any(k in low for k in ("alternativ", "substitut", "equivalente", "mesmo princípio ativo"))

    @staticmethod
    def _alternative_type(query: str) -> str:
        low = query.lower()
        if "alternativ" in low:
            return "alternativo"
        if "substitut" in low:
            return "substituto"
        if "equivalente" in low:
            return "equivalente"
        return "mesmo princípio ativo"

    def _finalize_with_fallback(
        self, report, state, query, entities, via, session_id, message: str,
    ) -> PipelineResult:
        return self._finalize(report, state, query, message, "medicamento",
                              entities, via, session_id, confidence=0.1)

    def _finalize(
        self,
        report: TimingReport,
        state: ConversationState,
        query: str,
        response: str,
        category: str,
        entities: Entities,
        via: str,
        session_id: str,
        *,
        confidence: float = 1.0,
        sources: Optional[list[dict]] = None,
    ) -> PipelineResult:
        state.last_query = query
        state.last_category = category
        state.last_medicamento = entities.medicamento
        state.last_termo_busca = entities.termo_busca
        state.last_response = response
        state.last_info_type = entities.info_type
        state.add_turn(query, response, category)
        report.log_summary()
        return PipelineResult(
            response=response,
            category=category,
            entities=entities.as_dict(),
            via=via,
            timings=report.to_dict(),
            session_id=session_id,
            confidence=confidence,
            sources=sources or [],
        )
