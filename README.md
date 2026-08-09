# Sistema de Consulta Veterinária

Chatbot que responde a perguntas sobre medicamentos veterinários portugueses.
Corre uma LLM local (via [Ollama](https://ollama.com)) sobre os dados oficiais da
base [MedVet/DGAV](https://medvet.dgav.pt): procura o medicamento, baixa a ficha
(SmPC em PDF), extrai a secção relevante e gera a resposta em pt-PT.

> Projeto de tese de mestrado — IPB. O código atual vive em `backend/`.

---

## Como funciona (resumo)

```
pergunta → classificação (regras → LLM) → busca MedVet → download do PDF
         → retrieval da secção → LLM → resposta
```

O fluxo completo e as decisões de design estão em [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Pré-requisitos

- Python ≥ 3.10
- [Ollama](https://ollama.com) a correr (local ou remoto)
- Docker + Docker Compose (apenas para o deploy em servidor)
- Chrome/Chromium + chromedriver (apenas se `SELENIUM_ENABLED=true`)

---

## Começar rápido (máquina local)

```bash
make install                     # cria .venv, instala deps, copia .env.example → .env
source .venv/bin/activate
ollama serve &                   # se ainda não estiver a correr
ollama pull qwen3:8b             # modelo do .env (pode trocar)
ollama pull nomic-embed-text     # embeddings para RAG (opcional)
make local                       # sobe API (:5000) + frontend (:8000)
```

Abrir **http://localhost:8000/site.html**.

Outras formas de correr:

```bash
make local-cli                                                 # terminal interativo
python -m backend.cli -q "Qual a dose do Senvelgo para gatos?" # pergunta única
make docker-local                                              # tudo em Docker, Ollama no host
```

---

## Deploy no servidor / VM (Docker Compose)

Sobe três containers — Ollama + API (gunicorn) + nginx (frontend e proxy):

```bash
cp .env.example .env                                           # ajuste CORS_ORIGINS, OLLAMA_MODEL, ...
make docker-server                                             # = docker compose up -d --build
docker exec consultavet-ollama ollama pull qwen3:8b            # 1ª vez
docker exec consultavet-ollama ollama pull nomic-embed-text    # se for usar RAG
```

| Container            | Porta | Função                            |
|----------------------|-------|-----------------------------------|
| `consultavet-ollama` | 11434 | LLM local                         |
| `consultavet-api`    | 5000  | Flask + gunicorn                  |
| `consultavet-web`    | 8000  | nginx (frontend + proxy `/api/`)  |

O nginx faz proxy `/api/* → api:5000`, portanto o frontend e a API ficam na mesma
origin (sem necessidade de CORS). Aceder a **http://localhost:8000/**.

<details>
<summary>Alternativa: servidor sem Docker (VM Ubuntu nua)</summary>

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip build-essential \
     chromium-browser chromium-chromedriver curl
curl -fsSL https://ollama.com/install.sh | sh && ollama serve &
git clone <URL-do-repo> master-thesis && cd master-thesis
make install && nano .env        # ajustar CORS_ORIGINS, etc.
ollama pull qwen3:8b
make test                        # 64/64 deve passar
make local                       # ou gunicorn -b 0.0.0.0:5000 ... 'backend.api.app:create_app()'
```

Servir o `frontend/` com nginx/Apache usando `scripts/nginx.conf` como template.
</details>

---

## Configuração (`.env`)

Todas as variáveis têm default seguro. As principais:

| Variável                   | Default                  | Notas                                       |
|----------------------------|--------------------------|---------------------------------------------|
| `APP_MODE`                 | `local`                  | `local` / `docker` / `server`               |
| `OLLAMA_HOST`              | `http://127.0.0.1:11434` | URL do Ollama                               |
| `OLLAMA_MODEL`             | `qwen3:8b`               | Modelo principal                            |
| `OLLAMA_EMBED_MODEL`       | `nomic-embed-text`       | Embeddings (RAG denso)                      |
| `CORS_ORIGINS`             | `*`                      | Restringir aos domínios reais em produção   |
| `SELENIUM_ENABLED`         | `true`                   | Fallback se o GET direto ao MedVet falhar   |
| `RETRIEVER_USE_EMBEDDINGS` | `true`                   | Cai para BM25 se o modelo embed não existir |

A lista completa (cache TTLs, limites de contexto, re-prompting) está comentada em
[`.env.example`](.env.example).

---

## API

| Método | Rota                    | Descrição                    |
|--------|-------------------------|------------------------------|
| GET    | `/api/status`           | Health check + modelo        |
| POST   | `/api/consulta`         | Pergunta síncrona (JSON)     |
| POST   | `/api/consulta/stream`  | Pergunta com streaming SSE   |
| POST   | `/api/limpar_contexto`  | Reset do contexto da sessão  |

Cada pedido aceita o header `X-Session-Id` para isolar o contexto entre utilizadores.
Exemplos completos de request/response em [docs/INSTRUCOES_API.md](docs/INSTRUCOES_API.md).

```bash
curl -X POST http://localhost:5000/api/consulta \
     -H "Content-Type: application/json" \
     -d '{"pergunta": "Qual a dose do Senvelgo para gatos?"}'
```

---

## Testes e benchmark

```bash
make test                                        # 64 testes (unit + integration)
make bench                                       # golden set num modelo (o do .env)
make bench-multi MODELS="gemma3:27b qwen3:32b"   # comparação multi-modelo
```

O benchmark multi-modelo usa *clean slate* entre modelos (apaga cache, PDFs e índice
para isolar a LLM) e grava `data/benchmarks/run_<timestamp>.json`. Schema e detalhes
em [docs/MIGRATION.md](docs/MIGRATION.md).

---

## Estrutura

```
backend/     implementação atual (API, pipeline, retrieval, MedVet, PDF, LLM)
frontend/    interface web estática (site.html + consulta.html)
data/        golden set, resultados e benchmarks da tese
docs/        ARCHITECTURE · MIGRATION · INSTRUCOES_API
scripts/     run-local, kill-ports, nginx.conf
src/         código v1 (legado — mantido apenas como referência histórica)
```

## Documentação

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — fluxo end-to-end, decisões de design, roadmap
- [docs/MIGRATION.md](docs/MIGRATION.md) — histórico v1 → v2.2 e schema do benchmark
- [docs/INSTRUCOES_API.md](docs/INSTRUCOES_API.md) — referência da API

## Licença

MIT — ver [LICENSE](LICENSE).
