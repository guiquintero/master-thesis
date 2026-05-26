#!/bin/bash
# Inicia API (backend novo) + servidor estático do frontend.
# Para deploy em container ver `make docker-local` ou `make docker-server`.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

if [ ! -d ".venv" ]; then
    echo -e "${RED}✗${NC} .venv não encontrado. Execute: make install"
    exit 1
fi

source .venv/bin/activate

if [ -f .env ]; then
    set -a; source .env; set +a
fi

# Libera portas antes de subir (evita "address already in use")
API_PORT="${API_PORT:-5000}"
WEB_PORT="${WEB_PORT:-8000}"
bash "$PROJECT_ROOT/scripts/kill-ports.sh" "$API_PORT" "$WEB_PORT"

if ! command -v ollama >/dev/null 2>&1; then
    echo -e "${YELLOW}⚠${NC} Comando 'ollama' não encontrado no host."
    echo "   Se Ollama estiver remoto, ignore este aviso."
else
    if ! ollama list &>/dev/null; then
        echo -e "${YELLOW}⚠${NC} Ollama parado — iniciando..."
        ollama serve >/tmp/ollama.log 2>&1 &
        sleep 2
    fi
    echo -e "${GREEN}✓${NC} Ollama ativo"
fi

PIDS_FILE=/tmp/consultavet_pids.txt
: > "$PIDS_FILE"

cleanup() {
    echo
    echo -e "${YELLOW}Encerrando servidores...${NC}"
    while read -r pid; do
        kill "$pid" 2>/dev/null || true
    done < "$PIDS_FILE"
    rm -f "$PIDS_FILE"
}
trap cleanup INT TERM

echo -e "🚀 API Flask (porta ${API_PORT:-5000})"
python -m backend.api.app >/tmp/consultavet_api.log 2>&1 &
echo $! >> "$PIDS_FILE"

sleep 2

echo -e "🌐 Frontend (porta ${WEB_PORT:-8000})"
python -m http.server "${WEB_PORT:-8000}" --directory frontend >/tmp/consultavet_web.log 2>&1 &
echo $! >> "$PIDS_FILE"

echo
echo -e "${GREEN}✓ Servidores iniciados${NC}"
echo -e "   Frontend: http://localhost:${WEB_PORT:-8000}/site.html"
echo -e "   API:      http://localhost:${API_PORT:-5000}/api/status"
echo -e "   Logs:     /tmp/consultavet_api.log  /tmp/consultavet_web.log"
echo
echo -e "${YELLOW}Ctrl+C para encerrar${NC}"
wait
