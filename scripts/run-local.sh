#!/usr/bin/env bash
# Sobe API Flask + servidor estático do frontend para uso local.
# - Libera portas antes (chama kill-ports.sh)
# - Captura SIGINT/SIGTERM e desliga tudo limpo
# - `wait` realmente bloqueia (problema do recipe make multi-shell)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

VENV="${VENV:-.venv}"
if [ ! -x "$VENV/bin/python" ]; then
    echo "✗ Virtualenv não encontrado em $VENV. Execute: make install" >&2
    exit 1
fi

# Carrega .env se existir
if [ -f .env ]; then
    set -a; source .env; set +a
fi
API_PORT="${API_PORT:-5000}"
WEB_PORT="${WEB_PORT:-8000}"

# 1) Libera portas
bash "$SCRIPT_DIR/kill-ports.sh" "$API_PORT" "$WEB_PORT"

# 2) Avisa qual modelo está configurado (ajuda a confirmar se OLLAMA_MODEL=... pegou)
echo
echo "→ Modelo Ollama: ${OLLAMA_MODEL:-(default do código)}"
echo "→ Ollama host:   ${OLLAMA_HOST:-http://127.0.0.1:11434}"

# 3) Sobe API e frontend em background, mas no MESMO shell, para o wait funcionar
"$VENV/bin/python" -m backend.api.app &
API_PID=$!
echo "$API_PID" > /tmp/consultavet_api.pid

"$VENV/bin/python" -m http.server "$WEB_PORT" --directory frontend >/tmp/consultavet_web.log 2>&1 &
WEB_PID=$!
echo "$WEB_PID" > /tmp/consultavet_web.pid

echo
echo "✓ API:      http://localhost:$API_PORT/api/status  (PID $API_PID)"
echo "✓ Frontend: http://localhost:$WEB_PORT/site.html   (PID $WEB_PID)"
echo
echo "Ctrl+C para encerrar (ambos serão mortos automaticamente)"

# 4) Trap para encerrar tudo no Ctrl+C / kill
cleanup() {
    echo
    echo "→ Encerrando..."
    kill "$API_PID" "$WEB_PID" 2>/dev/null || true
    # dá tempo para finalizarem; depois força
    sleep 1
    kill -9 "$API_PID" "$WEB_PID" 2>/dev/null || true
    rm -f /tmp/consultavet_api.pid /tmp/consultavet_web.pid
    echo "✓ Parado"
    exit 0
}
trap cleanup INT TERM

# 5) Aguarda enquanto qualquer um dos dois estiver vivo
wait -n "$API_PID" "$WEB_PID" 2>/dev/null || true
# Se um caiu, mata o outro e sai com o mesmo código
cleanup
