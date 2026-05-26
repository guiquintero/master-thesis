# Histórico de migração — Antes / Depois

Este documento regista TODAS as mudanças estruturais aplicadas ao projecto,
sprint a sprint, com a intenção e a comparação directa de comportamento.

Cronograma:

| Versão | Data       | Tema                                              | Estado |
|--------|------------|---------------------------------------------------|--------|
| v1.0   | < 2026-05  | God-class monolítica (legado)                     | Substituído |
| v2.0   | 2026-05-18 | Refactor modular completo + dual deployment       | ✅ Em produção |
| v2.1   | 2026-05-18 | Sprint RAG: chunking, embeddings, re-prompting    | ✅ Concluído |
| v2.1.1 | 2026-05-18 | Bugfix: termo_busca com cauda + resposta vazia    | ✅ Concluído |
| v2.2   | 2026-05-26 | Benchmark multi-modelo CLI (clean slate)          | ✅ Concluído |

---

## v2.0 — Refactor modular (resumo)

Migrou-se de uma god-class de **3 397 linhas** (`src/core/sistema_consulta.py`)
para **~15 módulos coesos** em `backend/`. Detalhes completos em
[`docs/ARCHITECTURE.md`](ARCHITECTURE.md).

### Bibliotecas removidas

| Pacote | Razão |
|---|---|
| `pdfplumber` | Declarado mas nunca importado no código |
| `tabula-py` | Declarado mas nunca importado |
| `pandas` | Declarado mas nunca importado |
| `openpyxl` | Declarado mas nunca importado |
| `camelot-py[cv]` / `camelot-py` | Declarado 2× no `requirements.txt`, nunca importado |
| `termcolor` (uso interno) | Substituído por `logging` stdlib |

### Bibliotecas mantidas

`flask`, `flask-cors`, `requests`, `aiohttp`, `beautifulsoup4`, `selenium`,
`PyMuPDF` (fitz), `ollama`, `urllib3`, `tqdm`, `gunicorn`.

### Bibliotecas adicionadas

| Pacote | Função |
|---|---|
| `pytest`, `pytest-watcher` | Suite de testes (35/35 passam) + modo watch |
| `ruff`, `mypy` (dev) | Lint e typecheck |

### Comportamento antes vs depois

| Aspecto | Antes (v1) | Depois (v2) |
|---|---|---|
| Maior ficheiro | `sistema_consulta.py` (3 397 LoC) | `pipeline.py` (302 LoC) |
| Detector de idioma | 3 implementações divergentes | 1 (`backend/llm/language_guard.py`) |
| Montador de prompt | 5 espalhados pelo código | 4 templates versionados (`prompts/templates.py`) |
| Mapa de espécies | 4 cópias (extractor, classifier, dose, followup) | 1 (`backend/entities/species_map.py`) |
| Mapa de "tipo de informação" | 5 cópias | 1 (`backend/entities/info_type.py`) |
| Processador de PDF | 2 (`TabelaInterpreter` + `PDFProcessor` morto) | 1 (`backend/pdf/`) |
| Estado de conversa | Singleton `contexto_conversacao` (race nas threads) | `ConversationStore` por `session_id` |
| Logger | `print(colored(...))` + rebind global de `print` | `logging` stdlib + callback contextual para SSE |
| Hijack de stdout no SSE | Sim (race em threads) | Não — usa `ContextVar` + handler dedicado |
| Classificação de intent | Sempre LLM | Cascata regras → LLM (~70% sem LLM) |
| Cache | Disco JSON, chaves não-canônicas | Disco JSON, chaves canônicas (acento/case-insensitive) |
| Validação de doses | Comparava só valor numérico | Compara tupla `(valor, unidade, denom)` |
| Deploy local | Script ad-hoc + venv manual | `make local` / `make local-cli` / `make local-api` |
| Deploy servidor | Não existia | `docker compose up -d` (3 containers: ollama + api + nginx) |
| Frontend | `API_BASE_URL` hardcoded em `localhost:5000` | Auto-detect via `window.location.origin` + session_id por aba |
| Testes | Quebrados (`from temporario import ...`) | 35/35 passam (`make test`) |

### Ficheiros removidos

- `src/api/api_vet_mv.py` (importava módulo inexistente `temporario`)
- `scripts/start_system.sh` (duplicado de `iniciar_sistema.sh`)

### Ficheiros novos no topo

- `pyproject.toml`, `Dockerfile`, `docker-compose.yml`,
  `docker-compose.local.yml`, `Makefile`, `.env.example`, `.dockerignore`,
  `scripts/nginx.conf`, `scripts/kill-ports.sh`, `scripts/run-local.sh`,
  `docs/ARCHITECTURE.md`, `docs/MIGRATION.md`

---

## v2.1 — Sprint RAG ✅ concluído

Foco em **assertividade**: garantir que a resposta correcta está sempre no
contexto enviado ao LLM e que o modelo é guiado a usá-la.

**Resumo do impacto:**

| Métrica | v2.0 | v2.1 |
|---|---|---|
| Testes unitários | 35 | 59 (+24) |
| Maior ficheiro | 302 LoC (`pipeline.py`) | 363 LoC (`pipeline.py`) |
| Granularidade de retrieval | Secção SmPC inteira (~4–8 kB) | Chunk de ~350 tokens com overlap |
| Retrieval | BM25 puro | BM25 + denso (embeddings) com RRF |
| Resposta do LLM | Texto livre | JSON estruturado tipado (`LLMResponse`) |
| Fallback de resposta vaga | Anexava metadados estáticos | **Re-prompta com contexto expandido** |
| Escolha de PDF na busca | `details[0]` arbitrário | Score por similaridade + bónus espécie/substância |
| Contexto enviado ao LLM | 12 000 chars (limite ignorado) | 30 000 chars com truncamento real |

### P1 — Chunking semântico em 3 níveis ✅

**Problema na v2.0:** `SectionSplitter` ([pdf/section_splitter.py:13](backend/pdf/section_splitter.py#L13))
era mono-nível e devolvia secções SmPC inteiras (4 000–8 000 chars). Quando
a regex de header não casava (PDF mal estruturado), devolvia o PDF inteiro
como uma só secção.

**Mudança aplicada:**
- Novo módulo `backend/pdf/chunker.py` com `Chunk` (dataclass) e
  `SemanticChunker` em 3 níveis:
  1. Secção SmPC (regex tolerante: maiúsculas, espaços múltiplos)
  2. Parágrafos de ~350 tokens com 80 tokens de overlap
  3. Tabelas como chunks autocontidos
- `PDFExtractor.extract_chunks()` (nova API; `extract()` antiga mantida)
- `DetailFetcher` agora preenche `MedicamentoDetail.pdf_chunks`

**Ficheiros afectados:**
- 🆕 [`backend/pdf/chunker.py`](backend/pdf/chunker.py)
- 🔄 [`backend/pdf/extractor.py`](backend/pdf/extractor.py) (nova API; compat preservada)
- 🔄 [`backend/medvet/detail_fetcher.py`](backend/medvet/detail_fetcher.py) (preenche `pdf_chunks`)
- 🆕 [`backend/tests/unit/test_chunker.py`](backend/tests/unit/test_chunker.py) (6 testes)

### P2 — Embeddings + ChromaDB + retriever híbrido (RRF) ✅

**Problema na v2.0:** `LexicalRetriever` (BM25 puro) falhava quando a query
usava vocabulário não-literal (ex.: "felinos" vs "gatos" no PDF). O
`EmbeddingRetriever` da v2.0 indexava in-memory por sessão, sem persistência
nem filtros metadata.

**Mudança aplicada:**
- Novo `VectorStore` protocol com 2 backends:
  - `ChromaVectorStore` (persistente, cosine + HNSW, filtros metadata)
  - `InMemoryVectorStore` (fallback sem deps — usado em testes)
  - Factory `get_vector_store()` escolhe automaticamente
- `DenseRetriever` v2.1 com cache persistente de embeddings (DiskKVStore)
- `HybridRetriever` combina lexical + denso via **Reciprocal Rank Fusion**
  (`k=60`, fórmula canónica do paper Cormack 2009)
- Degradação graciosa: se ChromaDB não instalado → InMemory; se Ollama embed
  model não disponível → BM25 puro
- Filtros metadata pré-retrieval: `where={"medicamento": "X", "section_num": "4.9"}`

**Ficheiros afectados:**
- 🆕 [`backend/retriever/vector_store.py`](backend/retriever/vector_store.py)
- 🆕 [`backend/retriever/hybrid.py`](backend/retriever/hybrid.py)
- 🔄 [`backend/retriever/dense.py`](backend/retriever/dense.py) (reescrito v2.1)
- 🔄 [`backend/retriever/lexical.py`](backend/retriever/lexical.py) (aceita `Chunk` ou `PDFSection`)
- 🆕 [`backend/tests/unit/test_hybrid_retriever.py`](backend/tests/unit/test_hybrid_retriever.py) (4 testes com fake LLM)

### P3 — Desambiguação entidade → PDF ✅

**Problema na v2.0:** `_handle_medicamento` em [pipeline.py:135](backend/orchestrator/pipeline.py#L135)
fazia `primary = details[0]`. Se a busca por "Senvelgo" devolvia "Senvelgo
Plus 30 mg/ml" + "Senvelgo 15 mg/ml", pegava o primeiro arbitrariamente.

**Mudança aplicada:**
- Novo módulo `backend/medvet/disambiguator.py`:
  - `_similarity()` usa `difflib.SequenceMatcher` (zero deps)
  - `_token_overlap()` mede sobreposição de tokens
  - `rank_listings()` calcula score:
    `0.55 × name_sim + 0.25 × token_overlap + 0.10 × species_bonus + 0.10 × substancia_bonus`
  - `confidence_gap()` mede ambiguidade entre top-1 e top-2
  - `pick_best()` API conveniente
- Pipeline usa `pick_best()` e regista no log: `Disambiguator: best=… score=…`
- Se top-1 ≈ top-2 (gap < 0.10), anexa os candidatos na resposta para utilizador validar

**Ficheiros afectados:**
- 🆕 [`backend/medvet/disambiguator.py`](backend/medvet/disambiguator.py)
- 🔄 [`backend/medvet/__init__.py`](backend/medvet/__init__.py) (export)
- 🔄 [`backend/orchestrator/pipeline.py`](backend/orchestrator/pipeline.py) (etapa `disambiguation`)
- 🆕 [`backend/tests/unit/test_disambiguator.py`](backend/tests/unit/test_disambiguator.py) (5 testes)

### P4 — Re-prompting em vez de fallbacks fixos ✅

**Problema na v2.0:** quando a resposta era vaga, o código anexava `"Secções
consideradas: …"` ([pipeline.py:233-235](backend/orchestrator/pipeline.py#L233))
— METADADOS, não conteúdo. E `_deterministic_dose_answer` devolvia template
fixo quando o validador rejeitava dose.

**Mudança aplicada:**
- Pipeline usa `LLMResponse.needs_reprompt()` (P5) para decidir
- Em caso de baixa confiança / `encontrada_no_documento=False`:
  - `_expand_context()` alarga top-k por `REPROMPT_EXPAND_FACTOR` (default 2×)
  - Faz 2ª chamada ao LLM com mais contexto
  - Fica com a melhor resposta entre as duas
- Mensagens de fallback em buscas vazias agora explícitas (sem expor termos
  internos crípticos ao utilizador)

**Ficheiros afectados:**
- 🔄 [`backend/orchestrator/pipeline.py`](backend/orchestrator/pipeline.py) (`_expand_context`, etapa `reprompt`)
- 🔄 [`backend/config/settings.py`](backend/config/settings.py) (`REPROMPT_EXPAND_FACTOR`, `ANSWER_MIN_CONFIDENCE`)

### P5 — Output estruturado JSON do LLM ✅

**Problema na v2.0:** LLM devolvia texto livre; código procurava
"não encontrei" com regex para inferir se a resposta era vaga. Zero confiança
quantitativa.

**Mudança aplicada:**
- Prompts (`build_rag_prompt`, `build_dose_prompt`) agora pedem JSON:
  ```json
  {
    "resposta": "texto em pt-PT",
    "encontrada_no_documento": true|false,
    "fontes": [{"secao": "4.9", "trecho": "..."}],
    "confianca": 0.0..1.0
  }
  ```
- `OllamaClient.chat(..., json_mode=True)` força `format="json"`
- `parse_llm_response()` tolerante a:
  - Texto antes/depois do `{...}`
  - Code fences ```` ```json ```` …`` ``` ``
  - Aspas curvas “ ” → "
  - Vírgula final `,}` `,]`
- Fallback para texto bruto se nada salvável

**Ficheiros afectados:**
- 🆕 [`backend/prompts/structured.py`](backend/prompts/structured.py) (`LLMResponse`, parser, render)
- 🔄 [`backend/prompts/templates.py`](backend/prompts/templates.py) (`JSON_SCHEMA_HINT`)
- 🔄 [`backend/orchestrator/pipeline.py`](backend/orchestrator/pipeline.py) (usa `parse_llm_response`)
- 🆕 [`backend/tests/unit/test_structured_output.py`](backend/tests/unit/test_structured_output.py) (8 testes)

### P6 — Janela de contexto útil + threshold ✅

**Problema na v2.0:** `CONTEXT_CHARS_LIMIT=12000` definido mas **nunca usado
no caminho activo**. Secções inteiras iam sem truncamento, podendo ultrapassar
o context window do modelo.

**Mudança aplicada:**
- Default subiu de 12 000 → 30 000 chars (~8k tokens) — viável com GPUs
  modernas e modelos 32k+ contexto
- `Pipeline._truncate_to_budget()` aplica o limite efectivamente após o
  retrieval, mantendo ordem por relevância
- Novo flag `RETRIEVER_DENSE_MIN_SIM=0.30`: chunks abaixo do threshold cosine
  são descartados antes de irem para a fusão
- Novo flag `ANSWER_MIN_CONFIDENCE=0.55`: limiar para acionar re-prompting (P4)

**Ficheiros afectados:**
- 🔄 [`backend/config/settings.py`](backend/config/settings.py) (defaults novos, flags novas)
- 🔄 [`backend/orchestrator/pipeline.py`](backend/orchestrator/pipeline.py) (`_truncate_to_budget`)
- 🔄 [`.env.example`](.env.example) (documenta flags novas)

### Bibliotecas adicionadas em v2.1

| Pacote | Função | Onde |
|---|---|---|
| `chromadb>=0.4` | Vector store persistente (P2) | `requirements.txt`, `pyproject.toml` |

> **Acção necessária:** correr `make install` (ou `pip install -e .[dev]`) após
> pull para baixar o `chromadb`. Caso prefira não instalar, o sistema continua
> a funcionar com `InMemoryVectorStore` (fallback automático).

### Bibliotecas removidas em v2.1

Nenhuma.

### Modelos Ollama recomendados

| Modelo | Função | Comando |
|---|---|---|
| `gemma3n:e4b` ou similar | LLM principal (chat) | `ollama pull gemma3n:e4b` |
| `nomic-embed-text` | Embeddings para RAG denso (P2) | `ollama pull nomic-embed-text` |

Se o segundo não estiver instalado, o sistema desliga automaticamente o
retrieval denso e usa só BM25 (sem erro).

### Estrutura final do `backend/`

```
backend/
├── pdf/
│   ├── chunker.py            🆕 P1 — Chunk, SemanticChunker
│   ├── extractor.py          🔄 P1 — API extract_chunks()
│   ├── section_splitter.py   ↺ (compat)
│   └── table_extractor.py    ↺
├── retriever/
│   ├── dense.py              🔄 P2 — DenseRetriever sobre VectorStore
│   ├── hybrid.py             🆕 P2 — HybridRetriever (BM25 + denso, RRF)
│   ├── lexical.py            🔄 P2 — aceita Chunk ou PDFSection
│   ├── section_filter.py     🔄 P2 — devolve None se nada bate (era top-N)
│   └── vector_store.py       🆕 P2 — Chroma + InMemory
├── medvet/
│   ├── disambiguator.py      🆕 P3 — rank + pick_best
│   ├── detail_fetcher.py     🔄 P1 — preenche pdf_chunks
│   ├── search.py             ↺
│   ├── pdf_fetcher.py        ↺
│   └── parser_listing.py     ↺
├── prompts/
│   ├── structured.py         🆕 P5 — LLMResponse + parser
│   ├── templates.py          🔄 P5 — pedem JSON
│   ├── system.py             ↺
│   └── validators.py         ↺
├── orchestrator/
│   ├── pipeline.py           🔄 P3+P4+P5+P6 — integra tudo
│   ├── conversation.py       ↺
│   ├── followup.py           ↺
│   └── dose_extractor.py     ↺
├── config/settings.py        🔄 P6 — defaults novos, flags novas
└── tests/unit/
    ├── test_chunker.py             🆕 P1
    ├── test_hybrid_retriever.py    🆕 P2
    ├── test_disambiguator.py       🆕 P3
    ├── test_structured_output.py   🆕 P5
    └── test_retriever.py           🔄 (compat com nova API)
```

🆕 novo · 🔄 modificado · ↺ inalterado

### Pipeline de execução (v2.1)

```
pergunta
  │
  ├─ followup.detect_and_rewrite (state)
  ├─ normalize_species
  ├─ IntentClassifier (regras → LLM fallback)
  │
  ├─ MedVetSearch (HTTP → Selenium fallback) → List[ListingResult]
  ├─ DetailFetcher.fetch_many → details (cada um com pdf_chunks)
  │
  ├─ P3: pick_best(details) → primary (com log de confidence gap)
  │
  ├─ retrieval (P1+P2):
  │     SectionRetriever (filtra por SmPC se aplicável)
  │     → HybridRetriever
  │          ├─ LexicalRetriever (BM25 top-k×3)
  │          └─ DenseRetriever (Chroma/InMemory + Ollama embed)
  │     → RRF → top-k chunks
  │
  ├─ P6: truncate_to_budget(top-k, 30 000 chars)
  │
  ├─ answer (P5):
  │     build_rag_prompt (JSON schema) → ollama.chat(json_mode=True)
  │     → parse_llm_response → LLMResponse
  │
  ├─ P4: if llm_resp.needs_reprompt():
  │         expand_context (×2) → 2ª chamada → fica com a melhor
  │
  └─ render_for_user → format_provenance → cache → finalize
```

---

## v2.1.1 — Bugfixes pós-release ✅

Dois bugs reportados após o primeiro deploy do v2.1 com `gemma3n:e4b`.

### Bug A: `termo_busca` arrastava preposição + espécie

**Sintoma:** Para "Qual a forma de administração do medicamento **Hidrocol em
suínos**?" o sistema fazia GET MedVet com `?search=Hidrocol+em+suínos` →
**404 NOT FOUND**.

**Causa:** o regex `_MED_INLINE` usava `re.IGNORECASE`, o que torna
`[A-ZÀ-Ú0-9]` equivalente a `[A-Za-zÀ-Úà-ú0-9]`. Resultado: as palavras
seguintes em minúsculas ("em", "suínos") passavam pelo classificador, e o
nome do medicamento era capturado como "Hidrocol em suínos" em vez de
apenas "Hidrocol".

**Correção:**
- Dividido o regex em 2 partes:
  - `_MED_INLINE_PREFIX` (case-insensitive) — casa "do medicamento "
  - `_MED_INLINE_NAME` (case-sensitive) — casa só nomes próprios
- Cinto-e-suspensórios: `EntityExtractor.extract()` também aplica
  `re.sub(r"\s+(?:em|para|de|do|da|com|a|o)\s+\w+.*$", "", termo)` após a
  extracção, garantindo que mesmo um fallback capture um termo limpo.

**Verificação:**

| Query | `termo_busca` (antes) | `termo_busca` (depois) |
|---|---|---|
| `Hidrocol em suínos?` | "Hidrocol em suínos" | **"Hidrocol"** |
| `do medicamento Hidrocol em suínos` | "Hidrocol em suínos" | **"Hidrocol"** |
| `Simparica Trio para cães` | "Simparica Trio para cães" | **"Simparica Trio"** |
| `Senvelgo 15 mg/ml em gatos` | "Senvelgo 15 mg/ml em gatos" | **"Senvelgo 15 mg/ml"** |

### Bug B: "Não foi possível gerar resposta" com fontes preenchidas

**Sintoma:** Para "Para que espécies está indicado o medicamento Simparica?"
o sistema mostrou:
```
Não foi possível gerar resposta.

Fontes (excertos):
- 4.2: O Sarolaner é ativo contra pulgas adultas...
```

**Causa:** o `gemma3n:e4b`, ao gerar JSON estruturado (P5), preencheu
`fontes` mas deixou o campo `resposta` vazio. O `render_for_user` caía no
fallback "Não foi possível gerar resposta." porque a lógica era
`response.resposta or "Não foi possível gerar resposta."`.

**Correção dupla:**
1. `LLMResponse.needs_reprompt()` agora retorna `True` quando `resposta`
   está vazia (mesmo com `encontrada_no_documento=True` e confiança alta) →
   pipeline faz re-prompt automático (P4) com mais contexto.
2. `render_for_user()` agora **sintetiza** uma resposta a partir dos
   trechos das `fontes` se a `resposta` vier vazia, em vez do fallback
   genérico. Última linha de defesa caso o re-prompt também devolva vazio.

**Ficheiros afectados v2.1.1:**
- 🔄 [`backend/entities/extractor.py`](backend/entities/extractor.py) — regex split em prefixo/nome + cleanup do termo
- 🔄 [`backend/prompts/structured.py`](backend/prompts/structured.py) — `needs_reprompt` detecta vazio + síntese a partir de fontes
- 🔄 [`backend/tests/unit/test_entities.py`](backend/tests/unit/test_entities.py) — +3 testes regressão
- 🔄 [`backend/tests/unit/test_structured_output.py`](backend/tests/unit/test_structured_output.py) — +2 testes regressão

**Testes:** 64/64 passam (era 59 em v2.1 → +5 testes para os bugs).

---

## v2.2 — Benchmark multi-modelo CLI ✅

Para servir a tese: precisamos correr os mesmos 35 prompts em N modelos
Ollama diferentes, em condições idênticas, e gerar evidência empírica
comparável.

**Decisões do utilizador:**
- Output: JSON acumulativo (machine-readable, fácil de processar)
- Cache scope: **clean slate** (apaga TUDO entre modelos para isolar a LLM)
- Lista de modelos: argumentos CLI

**Mudança aplicada:**

- 🆕 [`backend/tests/benchmark/run_multi.py`](backend/tests/benchmark/run_multi.py)
  - `load_questions()` — lê golden set, filtra apenas linhas que terminam em `?`
  - `ensure_pulled()` — `ollama list` + `ollama pull` se faltar
  - `clean_slate()` — apaga `data/cache/`, `pdf_cache_otimizado/`, `data/index/`
  - `run_one_model()` — recria `OllamaClient`+`IntentClassifier`+`Pipeline`
    com o modelo certo; loop pelas 35 perguntas; captura excepção por
    pergunta (continua)
  - `save_results()` — escrita atómica APÓS cada modelo (preserva progresso
    se Ctrl+C)
  - `host_info()` — regista nvidia-smi + ollama --version no JSON
- 🆕 `backend/tests/benchmark/__init__.py`
- 🔄 `Makefile` — target `bench-multi MODELS="..." [LIMIT=N]`

**Schema JSON de saída:**

```json
{
  "started_at": "2026-05-26T09:30:00+00:00",
  "finished_at": "2026-05-26T13:15:42+00:00",
  "total_duration_s": 13542.0,
  "config": {
    "questions_count": 35,
    "questions_file": "data/perguntas_exemplo.txt",
    "cache_scope": "clean_slate",
    "models_planned": ["gemma3:27b", "aya-expanse:32b", "qwen3:32b"],
    "host": {
      "hostname": "vm-faculdade",
      "gpu": "NVIDIA RTX PRO 4000 Black, 24576 MiB, 595.71.05",
      "ollama_version": "ollama version is 0.x.y"
    },
    "settings_snapshot": {
      "retriever_top_k": 8,
      "retriever_use_embeddings": true,
      "context_chars_limit": 30000,
      "answer_min_confidence": 0.55,
      "ollama_embed_model": "nomic-embed-text"
    }
  },
  "runs": [
    {
      "modelo": "gemma3:27b",
      "started_at": "...", "finished_at": "...", "duration_s": 1234.5,
      "cleanup_stats": {"cache_dir": 142, "pdf_cache_dir": 13, "index_dir": 1},
      "perguntas": [
        {
          "pergunta": "Para que espécies está indicado o medicamento Simparica?",
          "resposta": "Cães adultos (consoante peso) ...",
          "tempo_total_s": 28.501
        }
      ],
      "summary": {"n_questions": 35, "n_ok": 34, "n_falha": 1, "tempo_medio_s": 22.3}
    }
  ]
}
```

**v2.2.1 (2026-05-26):** simplificado para 3 campos por pergunta (`pergunta`,
`resposta`, `tempo_total_s`) a pedido do utilizador. Em caso de erro, o campo
`resposta` recebe `"[ERRO] <mensagem>"` para preservar a indicação sem
inflar o schema.

**Uso:**

```bash
# 5 modelos, 35 perguntas cada
make bench-multi MODELS="gemma3:27b aya-expanse:32b qwen3:32b mistral-small:24b gemma3n:e4b"

# Sanity check (5 perguntas só)
make bench-multi MODELS="gemma3:27b" LIMIT=5

# Output em data/benchmarks/run_2026-05-26_HHMMSS.json
```

**Resistência a falhas:**
- Modelo inexistente → tenta pull; se falhar, regista `erro_inicial` no run e passa adiante.
- Erro numa pergunta → captura traceback no campo `erro`, continua.
- Ctrl+C → `finally` salva progresso até onde chegou.

