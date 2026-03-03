#!/bin/bash
# Script de inicialização rápida do sistema
# Verifica dependências e inicia o sistema

echo "=================================="
echo "   Sistema Veterinário Novavet   "
echo "=================================="
echo ""

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Diretório raiz do projeto
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${BLUE}📂 Diretório:${NC} $PROJECT_ROOT"
echo ""

# Verificar Python
echo -e "${BLUE}🐍 Verificando Python...${NC}"
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo -e "${GREEN}✓${NC} $PYTHON_VERSION"
else
    echo -e "${RED}✗${NC} Python 3 não encontrado!"
    exit 1
fi

# Verificar ambiente virtual
echo -e "${BLUE}📦 Verificando ambiente virtual...${NC}"
if [ -d ".venv" ]; then
    echo -e "${GREEN}✓${NC} Ambiente virtual encontrado"
    source .venv/bin/activate
    echo -e "${GREEN}✓${NC} Ambiente virtual ativado"
else
    echo -e "${YELLOW}⚠${NC} Ambiente virtual não encontrado"
    echo -e "${BLUE}Criando ambiente virtual...${NC}"
    python3 -m venv .venv
    source .venv/bin/activate
    echo -e "${GREEN}✓${NC} Ambiente virtual criado e ativado"
    
    echo -e "${BLUE}Instalando dependências...${NC}"
    pip install -r requirements.txt
    echo -e "${GREEN}✓${NC} Dependências instaladas"
fi

# Verificar Ollama
echo -e "${BLUE}🤖 Verificando Ollama...${NC}"
if command -v ollama &> /dev/null; then
    echo -e "${GREEN}✓${NC} Ollama instalado"
    
    # Verificar se está rodando
    if ollama list &> /dev/null; then
        echo -e "${GREEN}✓${NC} Ollama está rodando"
    else
        echo -e "${YELLOW}⚠${NC} Ollama não está rodando"
        echo -e "${BLUE}Iniciando Ollama...${NC}"
        ollama serve > /dev/null 2>&1 &
        sleep 2
        echo -e "${GREEN}✓${NC} Ollama iniciado"
    fi
else
    echo -e "${RED}✗${NC} Ollama não encontrado!"
    echo "Instale com: curl -fsSL https://ollama.com/install.sh | sh"
    exit 1
fi

# Verificar estrutura de diretórios
echo -e "${BLUE}📁 Verificando estrutura...${NC}"
mkdir -p data/cache/pdf_cache_otimizado
mkdir -p data/cache/resposta_cache_otimizado
mkdir -p data/results
echo -e "${GREEN}✓${NC} Estrutura de diretórios OK"

echo ""
echo -e "${GREEN}Sistema pronto!${NC}"
echo ""
echo "Escolha o modo de execução:"
echo "  1) CLI Interativo"
echo "  2) API REST (Flask)"
echo "  3) Testes Automatizados"
echo "  4) Interface Web (API + Frontend)"
echo "  5) Apenas Frontend (sem API)"
echo ""
read -p "Opção (1-5): " opcao

case $opcao in
    1)
        echo ""
        echo -e "${BLUE}Iniciando CLI Interativo...${NC}"
        python3 src/core/sistema_consulta.py
        ;;
    2)
        echo ""
        echo -e "${BLUE}Iniciando API REST em http://localhost:5000${NC}"
        python3 src/api/api_vet.py
        ;;
    3)
        echo ""
        echo -e "${BLUE}Executando testes automatizados...${NC}"
        if [ -f "data/perguntas_exemplo.txt" ]; then
            python3 src/tests/testes_automatizados.py data/perguntas_exemplo.txt
        else
            echo -e "${RED}✗${NC} Arquivo data/perguntas_exemplo.txt não encontrado"
        fi
        ;;
    4)
        echo ""
        echo -e "${BLUE}Iniciando API + Interface Web...${NC}"
        ./scripts/iniciar_web.sh
        ;;
    5)
        echo ""
        echo -e "${BLUE}Iniciando apenas servidor web...${NC}"
        echo -e "${YELLOW}⚠ Atenção: API não será iniciada, funcionalidades limitadas${NC}"
        echo -e "${GREEN}Acesse: http://localhost:8000/frontend/site.html${NC}"
        python3 -m http.server 8000
        ;;
    *)
        echo -e "${RED}Opção inválida!${NC}"
        exit 1
        ;;
esac
