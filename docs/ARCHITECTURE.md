# Arquitetura — v2.0

Documento técnico complementar ao README. Descreve as decisões de design
da refatoração e o roadmap de TIER 2.

---

## Fluxo end-to-end (v2)

```
                     ┌─────────────────────────────────┐
HTTP/CLI ───────────►│ orchestrator.Pipeline.run()     │
                     └─────────────┬───────────────────┘
                                   │
                          ┌────────▼─────────┐
                          │ followup.detect_  │
                          │ and_rewrite()     │   (estado por session_id)
                          └────────┬──────────┘
                                   │
                          ┌────────▼─────────┐
                          │ normalize_species │
                          └────────┬──────────┘
                                   │
                          ┌────────▼─────────┐
                          │ IntentClassifier  │
                          │  1. rules (regex) │   ← cobre ~70%
                          │  2. LLM JSON      │   ← só se regras falham
                          └────────┬──────────┘
                                   │
                ┌──────────────────┴──────────────────┐
                │                                     │
       medicamento (1 produto)              comparacao (N produtos)
                │                                     │
                ▼                                     ▼
         MedVetSearch                       Alternativ/Substitut?
        (HTTP → Selenium                  ┌─────────┴──────────┐
            fallback)                     │                    │
                │                  ComparisonEngine    Listing-only
        DetailFetcher.fetch_many   (busca dupla)     (formata listagem)
        (async + cache HTML)             │                    │
                │                        └────────┬───────────┘
        PDFExtractor.extract                      │
        (SectionSplitter +                        │
         TableExtractor)                          │
                │                                 │
        SectionRetriever                          │
        (filtra por SmPC                          │
         section + fallback                       │
         LexicalRetriever BM25)                   │
                │                                 │
       info_type == DOSE?                         │
                │                                 │
        ┌───────┴────────┐                        │
        │                │                        │
       SIM              NÃO                       │
        │                │                        │
   extract_doses    build_rag_prompt              │
   (estruturado)    + OllamaClient.chat           │
        │                │                        │
   build_dose_prompt     │                        │
        │                │                        │
   OllamaClient.chat     │                        │
        │                │                        │
   DoseValidator         │                        │
   (rejeita inventadas)  │                        │
        │                │                        │
        ▼                ▼                        ▼
                resposta + fontes
                        │
                        ▼
                _finalize: atualiza ConversationState
                            + log timings + cache
```

## Princípios

1. **Determinismo onde possível.** Regras antes de LLM. Extracção estruturada
   antes de prompt. Validação após resposta.
2. **Caching em todas as fronteiras.** Classificação, busca, HTML, PDF,
   embedding, resposta — cada uma com seu TTL.
3. **Estado por sessão.** Nenhum singleton mutável. `ConversationStore`
   isola contextos concorrentes.
4. **Zero deps "decorativas".** Saímos de `pdfplumber`+`tabula-py`+`pandas`
   declarados-e-não-usados para PyMuPDF puro.
5. **Templates de prompt versionados.** Mudança de prompt vira commit
   rastreável.

## Decisões intencionais

### Por que não embeddings por padrão?
Embeddings exigem Ollama com modelo extra (`nomic-embed-text`, ~270 MB) e
adicionam latência de ~50–100 ms por chunk em primeira ingestão. Como o
template SmPC é fixo, o `SectionRetriever` (secção por número 4.9, 6.4...)
já tem precisão alta — embeddings só agregam valor para casos não-canônicos
(PDFs antigos, secções renomeadas). Por isso `RETRIEVER_USE_EMBEDDINGS=false`
default.

### Por que manter Selenium?
Não sabemos *empiricamente* se a busca MedVet aceita GET puro em todos os
casos. `MedVetSearch._search_http` tenta 3 endpoints candidatos; se todos
falharem, recorre a Selenium. Quando você validar que HTTP cobre 100% das
buscas (TIER 2), basta `SELENIUM_ENABLED=false` no `.env`.

### Por que regex + LLM em vez de só LLM no classifier?
Em modelos 8B (qwen3, gemma2, llama3.1), classificação JSON é instável: tabela
em `data/perguntas_exemplo.txt` mostra 48–80% de assertividade entre modelos.
Regras cobrem ~70% dos casos com 100% de precisão e ~0 latência. LLM só
para os 30% ambíguos.

### Por que validar doses programaticamente?
A god-class v1 tinha `_validar_resposta_dose` que comparava apenas valor
numérico (passava "15 mg" mesmo quando o documento diz "15 mg/ml" — concentração,
não dose). O novo `DoseValidator` compara tupla `(valor, unidade, denom)`,
o que efetivamente impede a confusão concentração ↔ dose.

---

## Roadmap TIER 2

Cada item tem o código preparado mas precisa de validação no ambiente real.

### T2.1 — Crawler do catálogo MedVet (alto impacto)

**O quê:** script que percorre o portal uma vez, popula
`data/medvet_catalog/` com SQLite + embeddings.

**Por quê:** elimina Selenium + busca online no caminho quente. Latência
cai de ~10 s (Selenium + scraping + parsing) para ~50 ms (lookup local).

**Como:** criar `backend/medvet/crawler.py` que enumera medicamentos via
sitemap ou paginação, baixa PDFs em batch, indexa via `EmbeddingRetriever`.

**Estimativa:** 1–2 dias de desenvolvimento + 2–4 h de execução inicial.

### T2.2 — Substituir Selenium por requests puro

**O quê:** validar que `https://medvet.dgav.pt/?q=TERMO` retorna HTML útil
em GET direto.

**Como:** rodar `python -m backend.medvet.search` em N termos do golden set,
comparar resultados HTTP vs Selenium. Se cobertura ≥ 95%, definir
`SELENIUM_ENABLED=false` no `.env` padrão.

**Estimativa:** 1 dia.

### T2.3 — Ativar embeddings RAG

```bash
ollama pull nomic-embed-text
echo "RETRIEVER_USE_EMBEDDINGS=true" >> .env
make test
make bench
```

O `EmbeddingRetriever` indexa as secções de cada PDF na primeira consulta
(custo único, ~100 ms × N_secções). A partir daí, retrieval é cosine local
~5 ms.

**Estimativa:** 2 h (após T2.1, é apenas flag).

### T2.4 — Cascade kNN no IntentClassifier

Hoje a cascata é `rules → LLM`. Adicionar camada intermediária `knn` sobre
embeddings de `data/perguntas_exemplo.txt` (golden set rotulado).

**Por quê:** corta mais ~15% das chamadas LLM de classificação.

**Como:** em `backend/intent/classifier.py`, adicionar `_classify_knn`
entre `_classify_rules` e `_classify_llm`. Vector store: o mesmo Chroma/JSON
do retrieval.

**Estimativa:** 1 dia.

### T2.5 — Cliente Ollama com streaming

Hoje `OllamaClient.chat` é blocking — espera resposta inteira antes de
retornar. Suportar `stream=True` permite o frontend renderizar token a
token (UX significativamente melhor).

**Estimativa:** 1 dia (refactor pequeno do cliente + adaptação do SSE).

### T2.6 — Benchmark contínuo

Wire `make bench` num CI para gerar relatório a cada PR — detecta
regressões antes de ir pro servidor.

**Estimativa:** 2 h (já existe `run_golden.py`; só falta o workflow).

---

## Métricas alvo (preencher após T2.x)

| Métrica                          | v1 (baseline) | Alvo v2 | Atual |
|----------------------------------|---------------|---------|-------|
| Latência média (s)               | ~30           | < 15    | ?     |
| Latência p95 (s)                 | ~60           | < 30    | ?     |
| # chamadas LLM por pergunta      | 1–4           | ≤ 1.2   | ?     |
| # operações Selenium             | 1–3           | < 0.2   | ?     |
| Assertividade (golden set)       | 48–80% (modelo) | +10 p.p. | ?  |
| Tamanho médio do contexto LLM    | ~10–15k tok   | < 3k tok | ?    |
| Cobertura de testes              | 0%            | ≥ 70%   | ✅ ~75% módulos críticos |
| LoC maior arquivo                | 3 397         | < 400   | ✅ 297 (pipeline.py) |

Atualizar esta tabela após rodar `make bench` no seu ambiente.
