# Sistema de Consulta Veterinária — v2.0

Chatbot que responde perguntas sobre medicamentos veterinários portugueses
usando uma LLM local (via [Ollama](https://ollama.com)) + dados da base oficial
[MedVet/DGAV](https://medvet.dgav.pt).

> **v2.0**: refactor arquitetural completo. A god-class de 3 397 linhas foi
> substituída por ~15 módulos coesos. Veja `docs/ARCHITECTURE.md` para o
> roadmap detalhado.

---

## Estrutura

```
backend/                   # nova implementação (entrar aqui para tudo)
  api/                     # Flask + SSE
  orchestrator/            # Pipeline + estado de conversa
  intent/                  # Classificação (regras → LLM em cascata)
  entities/                # Extração de medicamento/espécie/info-type
  retriever/               # Section + lexical (BM25) + embeddings (TIER 2)
  medvet/                  # Busca, parsing, download PDF
  pdf/                     # Extração e split por secção SmPC
  prompts/                 # Templates + validadores
  llm/                     # Cliente Ollama + language guard único
  comparison/              # Alternativas / mesmo princípio activo
  cache/                   # KV store unificado
  observability/           # Logging estruturado + métricas
  config/                  # Settings por env
  cli.py                   # Modo interativo de terminal
  tests/                   # unit + integration + golden
frontend/                  # Interface web estática
data/
  perguntas_exemplo.txt    # Golden set
  results/                 # Benchmarks (gerados)
  cache/                   # Cache em disco (gerado)
pdf_cache_otimizado/       # Cache de PDFs MedVet (mantido p/ compat)
src/                       # LEGADO — a desativar
```

---

## Pré-requisitos

- Python ≥ 3.10
- [Ollama](https://ollama.com) (local ou remoto)
- Chrome/Chromium + chromedriver (apenas se `SELENIUM_ENABLED=true`)

---

## Deploy local (sua máquina)

### Opção A — venv direto

```bash
make install                 # cria .venv e instala em modo -e
source .venv/bin/activate
ollama serve &               # se ainda não estiver rodando
ollama pull qwen3:8b         # modelo padrão (ver .env)
make local                   # sobe API:5000 + frontend:8000
```

Abrir [http://localhost:8000/site.html](http://localhost:8000/site.html).

### Opção B — Docker, mas com Ollama no host

```bash
cp .env.example .env
# Garanta que Ollama está rodando no host (ollama serve)
make docker-local
```

### Opção C — CLI interativo

```bash
make local-cli
# ou: python -m backend.cli
# ou pergunta única:
python -m backend.cli -q "Qual a dose do Senvelgo para gatos?"
```

---

## Deploy servidor da faculdade (VM Ubuntu nua)

Sequência completa do zero, sem Docker:

```bash
# 1) Pré-requisitos do sistema
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip git build-essential \
                    chromium-browser chromium-chromedriver curl

# 2) Ollama (uma vez)
curl -fsSL https://ollama.com/install.sh | sh
ollama serve > /tmp/ollama.log 2>&1 &

# 3) Clonar + setup
git clone <URL-do-repo> master-thesis
cd master-thesis
make install                 # cria .venv, instala -e, copia .env.example

# 4) Editar .env conforme servidor (CORS_ORIGINS, etc.)
nano .env

# 5) Pull dos modelos que vai testar
ollama pull gemma3:27b
ollama pull nomic-embed-text      # RAG denso
# (outros conforme benchmark)

# 6) Verificar
make test                          # 64/64 deve passar

# 7) Subir
make local                         # API:5000 + frontend:8000
# OU benchmark direto:
make bench-multi MODELS="gemma3:27b aya-expanse:32b"
```

### Deploy servidor — Docker compose (alternativa empacotada)

### Opção A — Docker compose (recomendado)

```bash
cp .env.example .env
# Edite .env: CORS_ORIGINS, OLLAMA_MODEL, ...
make docker-server
# Ou diretamente:
# docker compose up -d --build
```

Sobe três containers:

| Container             | Porta | Função                              |
|-----------------------|-------|-------------------------------------|
| `consultavet-ollama`  | 11434 | LLM local                           |
| `consultavet-api`     | 5000  | Flask + gunicorn (4 threads)        |
| `consultavet-web`     | 8000  | nginx servindo frontend + proxy API |

O nginx faz proxy reverso `/api/* → api:5000`, então o frontend não precisa
de CORS para acessar a API — tudo é mesmo origin.

Primeira execução: o Ollama dentro do container precisa baixar o modelo:

```bash
docker exec consultavet-ollama ollama pull qwen3:8b
docker exec consultavet-ollama ollama pull nomic-embed-text  # se for usar RAG
```

### Opção B — Sem Docker, no servidor

```bash
git clone <repo>
cd master-thesis
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[server]
cp .env.example .env
# Edite .env para o servidor (CORS_ORIGINS=..., OLLAMA_HOST=..., etc)
gunicorn -b 0.0.0.0:5000 -w 4 -k gthread --threads 4 \
         --timeout 180 'backend.api.app:create_app()'
```

Servir o `frontend/` com nginx ou Apache (`scripts/nginx.conf` é o template).

---

## Configuração (.env)

| Variável                    | Default                   | Notas                                    |
|-----------------------------|---------------------------|------------------------------------------|
| `APP_MODE`                  | `local`                   | `local` / `docker` / `server`            |
| `APP_DEBUG`                 | `false`                   | Liga reload Flask e logs DEBUG           |
| `OLLAMA_HOST`               | `http://127.0.0.1:11434`  | URL do Ollama                            |
| `OLLAMA_MODEL`              | `qwen3:8b`                | Modelo principal                         |
| `OLLAMA_EMBED_MODEL`        | `nomic-embed-text`        | Modelo de embeddings (TIER 2)            |
| `OLLAMA_TIMEOUT`            | `120`                     | Timeout por chamada (s)                  |
| `MEDVET_BASE_URL`           | `https://medvet.dgav.pt`  | Endpoint MedVet                          |
| `MEDVET_MAX_RESULTS`        | `10`                      | Limite por busca                         |
| `MEDVET_CONCURRENT`         | `5`                       | Paralelismo do scraping                  |
| `SELENIUM_ENABLED`          | `true`                    | Fallback Selenium se HTTP falhar         |
| `SELENIUM_HEADLESS`         | `true`                    |                                          |
| `API_HOST` / `API_PORT`     | `0.0.0.0` / `5000`        |                                          |
| `CORS_ORIGINS`              | `*`                       | Lista separada por vírgula em produção   |
| `CACHE_TTL_RESPONSE`        | `86400`                   | TTL do cache de respostas (s)            |
| `CACHE_TTL_SEARCH`          | `86400`                   | TTL do cache de buscas MedVet            |
| `RETRIEVER_TOP_K`           | `6`                       | Quantas secções enviar ao LLM            |
| `RETRIEVER_USE_EMBEDDINGS`  | `false`                   | **TIER 2** — ativar após popular índice  |

---

## Endpoints da API

| Método | Path                       | Descrição                                |
|--------|----------------------------|------------------------------------------|
| GET    | `/api/status`              | Health check + info de modelo            |
| POST   | `/api/consulta`            | Pergunta síncrona, JSON                  |
| POST   | `/api/consulta/stream`     | Pergunta com streaming SSE (logs + resp) |
| POST   | `/api/limpar_contexto`     | Reset do estado da sessão                |

Todas as requisições aceitam header `X-Session-Id` (ou campo `session_id`
no JSON) para isolar contexto entre utilizadores concorrentes.

### Exemplo

```bash
curl -X POST http://localhost:5000/api/consulta \
     -H "Content-Type: application/json" \
     -H "X-Session-Id: alice-1" \
     -d '{"pergunta": "Qual a dose do Senvelgo para gatos?"}'
```

```json
{
  "success": true,
  "resposta": "Segundo o documento, a dose indicada para gatos é 1 mg/kg.",
  "categoria": "medicamento",
  "entidades": {
    "termo_busca": "Senvelgo 15 mg/ml",
    "info_type": "dose",
    "especie_alvo": "gatos"
  },
  "via": "rules",
  "timings": { "classification": 0.001, "scraping": 2.4, "answer": 7.1, "total": 9.6 },
  "session_id": "alice-1"
}
```

---

## Testes

```bash
make test                              # unit + integration
.venv/bin/pytest backend/tests/unit -v # só unit
```

### Benchmark — único modelo (golden set)

```bash
make bench                                          # usa OLLAMA_MODEL do .env
python -m backend.tests.golden.run_golden --limit 5 # rápido
python -m backend.tests.golden.run_golden --model gemma2:9b
```

Saída em `data/results/golden_<modelo>_<timestamp>.json`.

### Benchmark — multi-modelo (CLI, clean slate entre modelos)

Para a tese: corre as 35 perguntas em vários modelos com cache LIMPO entre
cada um, gera ficheiro JSON único acumulativo.

```bash
# Exemplo: 5 modelos
make bench-multi MODELS="gemma3:27b aya-expanse:32b qwen3:32b mistral-small:24b gemma3n:e4b"

# Dev: só 5 perguntas para validar pipeline
make bench-multi MODELS="gemma3:27b" LIMIT=5

# Equivalente via Python directo
python -m backend.tests.benchmark.run_multi \
    --models gemma3:27b aya-expanse:32b qwen3:32b \
    --output data/benchmarks/comparativo.json
```

**Cuidado:** clean slate apaga PDFs e índice ChromaDB entre modelos
(intencional para isolar a LLM). Cada modelo re-baixa PDFs e re-embedda —
1 run de 5 modelos pode demorar 2–4 h.

Output JSON em `data/benchmarks/run_<timestamp>.json` com schema documentado
em [docs/MIGRATION.md](docs/MIGRATION.md#v22--benchmark-multi-modelo-cli-).

---

## O que mudou da v1 para a v2

### Eliminado
- God-class `SistemaConsultaVetOtimizado` (3 397 linhas → distribuída em ~15 módulos)
- 3 detectores de idioma divergentes → 1 (`backend/llm/language_guard.py`)
- 5 montadores de prompt → 4 templates versionados (`backend/prompts/templates.py`)
- 4 mapas de espécies → 1 fonte de verdade (`backend/entities/species_map.py`)
- Mapa de "tipo de informação" duplicado em 5 lugares → 1 (`backend/entities/info_type.py`)
- 2 processadores de PDF redundantes (`TabelaInterpreter` + `PDFProcessor`) → 1
- `api_vet_mv.py` (broken) e `start_system.sh` (redundante) — removidos
- Rebind global de `print()` — removido
- Hijack global de `sys.stdout/stderr` na API — removido
- Estado mutável compartilhado `contexto_conversacao` → ConversationStore por sessão
- `pdfplumber`, `tabula-py`, `pandas`, `openpyxl`, `camelot-py` (declarados, nunca usados)

### Adicionado
- Classificação em cascata (regras → LLM apenas como fallback)
- Cache unificado com chaves canônicas (acentos/case-insensitive)
- BM25 lexical retriever sem deps externas
- Split por secção SmPC (4.1, 4.9, 6.4, ...) — retrieval determinístico
- Extração estruturada de doses `(valor, unidade, espécie)`
- Validação rigorosa de doses (distingue concentração `mg/ml` de dose `mg/kg`)
- ConversationStore com TTL + LRU
- Streaming SSE sem hijack de stdout
- Headers `X-Session-Id` para isolamento concorrente
- Dual deployment: Docker compose (servidor) + Makefile (local)
- Suite de testes unitários (35/35 passam)
- Golden set runner com export JSON

---

## TIER 2 — Próximos passos (precisam do seu ambiente)

Estas melhorias têm o **código preparado** mas precisam de validação no seu
ambiente (Ollama rodando, conexão MedVet) para serem ativadas. Estão
documentadas em `docs/ARCHITECTURE.md` com instruções.

1. **Popular índice de embeddings**
   ```bash
   ollama pull nomic-embed-text
   # Após primeira consulta, embeddings ficam em cache. Ativar:
   echo "RETRIEVER_USE_EMBEDDINGS=true" >> .env
   ```

2. **Crawl do catálogo MedVet** (elimina Selenium do caminho quente)
   ```bash
   python -m backend.medvet.crawler --output data/medvet_catalog/  # TODO
   ```

3. **Calibrar o classificador via golden set** (já estruturalmente pronto)

4. **Substituir Selenium por requests** — `backend/medvet/search.py` já tenta
   HTTP primeiro; basta validar empiricamente que a maioria dos termos
   funciona sem JS e desligar `SELENIUM_ENABLED=false`.

5. **Benchmark antes/depois** com `make bench` → comparar com
   `data/perguntas_exemplo.txt` (tabela de assertividade no fim do ficheiro).

---

## Licença

MIT
