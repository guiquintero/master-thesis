#!/bin/bash
# Script para iniciar API + Interface Web simultaneamente
# Inicia ambos os servidores necessários para a interface funcionar

echo "================================================"
echo "  Iniciando API + Interface Web - Novavet  "
echo "================================================"
echo ""

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Verificar se ambiente virtual existe
if [ ! -d ".venv" ]; then
    echo -e "${RED}✗${NC} Ambiente virtual não encontrado!"
    echo "Execute primeiro: ./scripts/iniciar_sistema.sh"
    exit 1
fi

# Ativar ambiente virtual
source .venv/bin/activate

# Verificar Ollama
echo -e "${BLUE}🤖 Verificando Ollama...${NC}"
if ! ollama list &> /dev/null; then
    echo -e "${YELLOW}⚠${NC} Ollama não está rodando. Iniciando..."
    ollama serve > /dev/null 2>&1 &
    sleep 2
fi

echo -e "${GREEN}✓${NC} Ollama OK"
echo ""

# Criar arquivo temporário para PIDs
PIDS_FILE="/tmp/novavet_pids.txt"
> "$PIDS_FILE"

# Função para cleanup
cleanup() {
    echo ""
    echo -e "${YELLOW}Encerrando servidores...${NC}"
    
    if [ -f "$PIDS_FILE" ]; then
        while read pid; do
            if ps -p $pid > /dev/null 2>&1; then
                kill $pid 2>/dev/null
            fi
        done < "$PIDS_FILE"
        rm -f "$PIDS_FILE"
    fi
    
    echo -e "${GREEN}Servidores encerrados.${NC}"
    exit 0
}

# Capturar Ctrl+C
trap cleanup INT TERM

echo -e "${BLUE}🚀 Iniciando API Flask (porta 5000)...${NC}"
python3 src/api/api_vet.py > /tmp/api_vet.log 2>&1 &
API_PID=$!
echo $API_PID >> "$PIDS_FILE"

# Aguardar API iniciar
sleep 3

# Verificar se API está rodando
if ps -p $API_PID > /dev/null; then
    echo -e "${GREEN}✓${NC} API Flask rodando (PID: $API_PID)"
else
    echo -e "${RED}✗${NC} Erro ao iniciar API. Verifique logs em /tmp/api_vet.log"
    exit 1
fi

echo ""
echo -e "${BLUE}🌐 Iniciando servidor web (porta 8000)...${NC}"
python3 -m http.server 8000 > /dev/null 2>&1 &
WEB_PID=$!
echo $WEB_PID >> "$PIDS_FILE"

sleep 1

if ps -p $WEB_PID > /dev/null; then
    echo -e "${GREEN}✓${NC} Servidor web rodando (PID: $WEB_PID)"
else
    echo -e "${RED}✗${NC} Erro ao iniciar servidor web"
    cleanup
    exit 1
fi

echo ""
echo "================================================"
echo -e "${GREEN}✓ Servidores iniciados com sucesso!${NC}"
echo "================================================"
echo ""
echo -e "${BLUE}📱 Interface Web:${NC}"
echo -e "   ${GREEN}http://localhost:8000/frontend/site.html${NC}"
echo ""
echo -e "${BLUE}🔌 API REST:${NC}"
echo -e "   ${GREEN}http://localhost:5000/api/perguntar${NC}"
echo ""
echo -e "${YELLOW}Pressione Ctrl+C para encerrar os servidores${NC}"
echo ""

# Manter script rodando
wait
