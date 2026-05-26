#!/usr/bin/env bash
# Libera as portas passadas como argumento, matando o que estiver ouvindo.
# Uso: scripts/kill-ports.sh 5000 8000

set -u

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [ $# -eq 0 ]; then
    echo "Uso: $0 <porta1> [porta2] ..."
    exit 1
fi

_pids_on_port() {
    local port=$1
    if command -v lsof >/dev/null 2>&1; then
        lsof -ti:"$port" 2>/dev/null || true
    elif command -v fuser >/dev/null 2>&1; then
        fuser "$port/tcp" 2>/dev/null | tr -s ' ' '\n' | grep -v '^$' || true
    elif command -v ss >/dev/null 2>&1; then
        ss -tlnp 2>/dev/null \
            | awk -v p=":$port " '$4 ~ p { if (match($0, /pid=([0-9]+)/, m)) print m[1] }' \
            || true
    else
        echo "" # sem ferramenta
    fi
}

for port in "$@"; do
    pids=$(_pids_on_port "$port")
    if [ -z "$pids" ]; then
        echo -e "  ${GREEN}✓${NC} porta $port livre"
        continue
    fi

    for pid in $pids; do
        # Quem está usando?
        owner=$(ps -p "$pid" -o comm= 2>/dev/null || echo "?")
        echo -e "  ${YELLOW}!${NC} porta $port em uso por PID $pid ($owner) — encerrando"
        kill "$pid" 2>/dev/null || true
    done

    # Espera o SO realmente liberar a porta (até 2s)
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        sleep 0.2
        [ -z "$(_pids_on_port "$port")" ] && break
    done

    # Ainda preso? mata com -9
    remaining=$(_pids_on_port "$port")
    if [ -n "$remaining" ]; then
        for pid in $remaining; do
            echo -e "  ${RED}!!${NC} forçando SIGKILL no PID $pid"
            kill -9 "$pid" 2>/dev/null || true
        done
        sleep 0.3
    fi

    if [ -z "$(_pids_on_port "$port")" ]; then
        echo -e "  ${GREEN}✓${NC} porta $port liberada"
    else
        echo -e "  ${RED}✗${NC} porta $port AINDA ocupada — verifique manualmente"
        exit 2
    fi
done

# Limpa também PIDs antigos do iniciar_web.sh / Makefile que possam ter ficado
rm -f /tmp/consultavet_api.pid /tmp/consultavet_web.pid /tmp/consultavet_pids.txt 2>/dev/null || true
