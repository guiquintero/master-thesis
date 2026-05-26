# Makefile — atalhos para os dois modos de execução.
#
#   make install        Instala deps em venv local
#   make local          Roda API + frontend (libera portas antes)
#   make local-api      Só a API
#   make local-cli      CLI interactivo
#   make docker-local   Compose usando Ollama do host
#   make docker-server  Compose completo (Ollama em container)
#   make stop           Mata API + frontend + containers
#   make kill-ports     Apenas libera as portas (útil quando algo travou)
#   make test           pytest
#   make watch          pytest em modo watch
#   make bench          Roda o golden set
#   make clean          Limpa caches

.PHONY: help install local local-api local-cli docker-local docker-server stop kill-ports test watch bench clean

PYTHON ?= python3
VENV   ?= .venv
# Portas usadas pela aplicação. Sobrescreva com `make local PORTS="5000 8000 9000"`
PORTS  ?= 5000 8000

help:
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | awk 'BEGIN {FS=":.*?## "}; {printf "%-18s %s\n", $$1, $$2}'

install: ## Cria venv e instala dependências
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -U pip
	$(VENV)/bin/pip install -e .[dev]
	@test -f .env || cp .env.example .env
	@echo "✓ Instalado. Active com: source $(VENV)/bin/activate"

kill-ports: ## Libera as portas $(PORTS) caso estejam ocupadas
	@echo "→ Verificando portas: $(PORTS)"
	@bash scripts/kill-ports.sh $(PORTS)

local: ## Sobe API + servidor web estático (libera portas antes)
	@bash scripts/run-local.sh

local-api: kill-ports ## Só a API (libera porta antes)
	@$(VENV)/bin/python -m backend.api.app

local-cli: ## CLI interactivo
	$(VENV)/bin/python -m backend.cli

docker-local: kill-ports ## Docker usando Ollama do host
	docker compose -f docker-compose.local.yml down 2>/dev/null || true
	docker compose -f docker-compose.local.yml up --build

docker-server: kill-ports ## Docker compose completo (Ollama em container)
	docker compose down 2>/dev/null || true
	docker compose up -d --build
	@echo "✓ API:      http://localhost:$$(grep API_PORT .env | cut -d= -f2 || echo 5000)/api/status"
	@echo "✓ Frontend: http://localhost:$$(grep WEB_PORT .env | cut -d= -f2 || echo 8000)/"

stop: ## Mata API + frontend + containers
	@-kill $$(cat /tmp/consultavet_api.pid 2>/dev/null) 2>/dev/null || true
	@-kill $$(cat /tmp/consultavet_web.pid 2>/dev/null) 2>/dev/null || true
	@rm -f /tmp/consultavet_api.pid /tmp/consultavet_web.pid /tmp/consultavet_pids.txt
	@bash scripts/kill-ports.sh $(PORTS) || true
	@docker compose down 2>/dev/null || true
	@docker compose -f docker-compose.local.yml down 2>/dev/null || true
	@echo "✓ Parado"

test: ## Suite de testes (unit + integration)
	$(VENV)/bin/pytest -v

watch: ## Re-executa testes a cada salvamento
	$(VENV)/bin/ptw --runner '$(VENV)/bin/pytest -q' backend

bench: ## Roda o golden set num único modelo (o do .env)
	$(VENV)/bin/python -m backend.tests.golden.run_golden

bench-multi: ## Multi-modelo. Uso: make bench-multi MODELS="gemma3:27b aya-expanse:32b" [LIMIT=5]
	@if [ -z "$(MODELS)" ]; then \
	    echo "✗ MODELS não definido. Exemplo:"; \
	    echo "    make bench-multi MODELS=\"gemma3:27b aya-expanse:32b qwen3:32b\""; \
	    exit 1; \
	fi
	$(VENV)/bin/python -m backend.tests.benchmark.run_multi --models $(MODELS) $(if $(LIMIT),--limit $(LIMIT),)

clean: ## Limpa caches em disco
	rm -rf data/cache pdf_cache_otimizado/*.json
	@echo "✓ Caches limpos"
