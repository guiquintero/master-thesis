#!/bin/bash

# Script de inicialização do Sistema Veterinário
# Autor: Guilherme Quintero
# Data: Dezembro 2025

echo "========================================"
echo "🚀 Sistema Veterinário - Inicialização"
echo "========================================"
echo ""

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Diretório do projeto
PROJECT_DIR="/home/guilherme-quintero/Documents/IPB/Tese/Testes"
cd "$PROJECT_DIR" || exit 1

# Função para verificar se um processo está rodando
check_process() {
    if pgrep -f "$1" > /dev/null; then
        echo -e "${GREEN}✅ $2 está rodando${NC}"
        return 0
    else
        echo -e "${RED}❌ $2 NÃO está rodando${NC}"
        return 1
    fi
}

# Verificar Ollama
echo "🔍 Verificando Ollama..."
if check_process "ollama serve" "Ollama"; then
    echo ""
else
    echo -e "${YELLOW}⚠️  Iniciando Ollama...${NC}"
    nohup ollama serve > /dev/null 2>&1 &
    sleep 3
    if check_process "ollama serve" "Ollama"; then
        echo -e "${GREEN}✅ Ollama iniciado com sucesso!${NC}"
    else
        echo -e "${RED}❌ Erro ao iniciar Ollama. Execute manualmente: ollama serve${NC}"
        exit 1
    fi
fi

# Verificar se o modelo está disponível
echo ""
echo "🔍 Verificando modelo de IA..."
if ollama list | grep -q "qwen2.5:14b"; then
    echo -e "${GREEN}✅ Modelo qwen2.5:14b disponível${NC}"
else
    echo -e "${YELLOW}⚠️  Modelo não encontrado. Baixando...${NC}"
    ollama pull qwen2.5:14b
fi

# Verificar ambiente virtual
echo ""
echo "🔍 Verificando ambiente virtual Python..."
if [ -d "venv" ]; then
    echo -e "${GREEN}✅ Ambiente virtual encontrado${NC}"
    source venv/bin/activate
else
    echo -e "${YELLOW}⚠️  Criando ambiente virtual...${NC}"
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
fi

# Verificar dependências Python
echo ""
echo "🔍 Verificando dependências Python..."
if python3 -c "import flask, aiohttp, selenium, bs4" 2>/dev/null; then
    echo -e "${GREEN}✅ Dependências instaladas${NC}"
else
    echo -e "${YELLOW}⚠️  Instalando dependências...${NC}"
    pip install -r requirements.txt
fi

# Verificar se a API já está rodando
echo ""
echo "🔍 Verificando API Flask..."
if check_process "api_vet.py" "API Flask"; then
    echo -e "${YELLOW}⚠️  API já está rodando. Deseja reiniciar? (s/n)${NC}"
    read -r resposta
    if [ "$resposta" = "s" ] || [ "$resposta" = "S" ]; then
        echo "🔄 Parando API..."
        pkill -f "api_vet.py"
        sleep 2
    else
        echo "✅ Mantendo API rodando"
        API_RUNNING=true
    fi
fi

# Iniciar API se não estiver rodando
if [ -z "$API_RUNNING" ]; then
    echo ""
    echo "🚀 Iniciando API Flask..."
    nohup python3 api_vet.py > api_vet.log 2>&1 &
    sleep 5
    
    if check_process "api_vet.py" "API Flask"; then
        echo -e "${GREEN}✅ API iniciada com sucesso!${NC}"
    else
        echo -e "${RED}❌ Erro ao iniciar API. Verifique o log: tail -f api_vet.log${NC}"
        exit 1
    fi
fi

# Verificar se a API está respondendo
echo ""
echo "🔍 Testando conexão com a API..."
sleep 2
response=$(curl -s http://localhost:5000/api/status)

if echo "$response" | grep -q "online"; then
    echo -e "${GREEN}✅ API está respondendo corretamente!${NC}"
    modelo=$(echo "$response" | grep -o '"modelo":"[^"]*"' | cut -d'"' -f4)
    echo -e "${GREEN}   Modelo: $modelo${NC}"
else
    echo -e "${RED}❌ API não está respondendo. Verifique: tail -f api_vet.log${NC}"
    exit 1
fi

# Resumo
echo ""
echo "========================================"
echo -e "${GREEN}✅ Sistema Inicializado com Sucesso!${NC}"
echo "========================================"
echo ""
echo "📍 Acessos:"
echo "   - API: http://localhost:5000"
echo "   - Status: http://localhost:5000/api/status"
echo "   - Interface: file://$PROJECT_DIR/site.html"
echo ""
echo "📝 Logs:"
echo "   - API: tail -f $PROJECT_DIR/api_vet.log"
echo "   - Ollama: journalctl -u ollama -f"
echo ""
echo "🛑 Para parar:"
echo "   pkill -f api_vet.py"
echo "   pkill -f ollama"
echo ""
echo "🌐 Abra o navegador e acesse:"
echo "   file://$PROJECT_DIR/site.html"
echo ""
