#!/bin/bash
# Script de validação da estrutura do projeto
# Verifica se todos os componentes estão no lugar certo

echo "=========================================="
echo "  Validação da Estrutura do Projeto  "
echo "=========================================="
echo ""

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

errors=0
warnings=0
checks=0

# Função para verificar arquivo/diretório
check_exists() {
    local path=$1
    local type=$2  # file ou directory
    local required=$3  # true ou false
    
    checks=$((checks + 1))
    
    if [ "$type" == "file" ]; then
        if [ -f "$path" ]; then
            echo -e "${GREEN}✓${NC} Arquivo encontrado: $path"
            return 0
        else
            if [ "$required" == "true" ]; then
                echo -e "${RED}✗${NC} Arquivo FALTANDO: $path"
                errors=$((errors + 1))
            else
                echo -e "${YELLOW}⚠${NC} Arquivo opcional não encontrado: $path"
                warnings=$((warnings + 1))
            fi
            return 1
        fi
    else
        if [ -d "$path" ]; then
            echo -e "${GREEN}✓${NC} Diretório encontrado: $path"
            return 0
        else
            if [ "$required" == "true" ]; then
                echo -e "${RED}✗${NC} Diretório FALTANDO: $path"
                errors=$((errors + 1))
            else
                echo -e "${YELLOW}⚠${NC} Diretório opcional não encontrado: $path"
                warnings=$((warnings + 1))
            fi
            return 1
        fi
    fi
}

echo -e "${BLUE}Verificando estrutura de diretórios...${NC}"
echo ""

# Diretórios principais
check_exists "src" "directory" "true"
check_exists "src/core" "directory" "true"
check_exists "src/api" "directory" "true"
check_exists "src/utils" "directory" "true"
check_exists "src/tests" "directory" "true"
check_exists "frontend" "directory" "true"
check_exists "assets" "directory" "true"
check_exists "data" "directory" "true"
check_exists "data/cache" "directory" "true"
check_exists "data/results" "directory" "true"
check_exists "docs" "directory" "true"
check_exists "scripts" "directory" "true"

echo ""
echo -e "${BLUE}Verificando arquivos de código...${NC}"
echo ""

# Código fonte
check_exists "src/__init__.py" "file" "true"
check_exists "src/core/__init__.py" "file" "true"
check_exists "src/core/sistema_consulta.py" "file" "true"
check_exists "src/core/query_classifier.py" "file" "true"
check_exists "src/api/__init__.py" "file" "true"
check_exists "src/api/api_vet.py" "file" "true"
check_exists "src/api/api_vet_mv.py" "file" "true"
check_exists "src/utils/__init__.py" "file" "true"
check_exists "src/utils/ollama_wrapper.py" "file" "true"
check_exists "src/tests/__init__.py" "file" "true"
check_exists "src/tests/testes_automatizados.py" "file" "true"

echo ""
echo -e "${BLUE}Verificando interface e assets...${NC}"
echo ""

# Frontend e assets
check_exists "frontend/site.html" "file" "true"
check_exists "frontend/consulta.html" "file" "true"
check_exists "assets/cao.png" "file" "true"
check_exists "assets/fluxo.png" "file" "false"

echo ""
echo -e "${BLUE}Verificando documentação...${NC}"
echo ""

# Documentação
check_exists "README.md" "file" "true"
check_exists "CHANGELOG.md" "file" "true"
check_exists "ESTRUTURA.md" "file" "true"
check_exists "LICENSE" "file" "true"
check_exists "docs/ARQUITETURA.md" "file" "true"
check_exists "docs/GUIA_USO.md" "file" "true"
check_exists "docs/INSTRUCOES_API.md" "file" "true"
check_exists "data/results/README.md" "file" "true"

echo ""
echo -e "${BLUE}Verificando scripts...${NC}"
echo ""

# Scripts
check_exists "scripts/iniciar_sistema.sh" "file" "true"
check_exists "scripts/limpar_sistema.sh" "file" "true"

# Verificar se são executáveis
if [ -f "scripts/iniciar_sistema.sh" ]; then
    if [ -x "scripts/iniciar_sistema.sh" ]; then
        echo -e "${GREEN}✓${NC} Script é executável: scripts/iniciar_sistema.sh"
    else
        echo -e "${YELLOW}⚠${NC} Script não é executável: scripts/iniciar_sistema.sh"
        warnings=$((warnings + 1))
    fi
fi

if [ -f "scripts/limpar_sistema.sh" ]; then
    if [ -x "scripts/limpar_sistema.sh" ]; then
        echo -e "${GREEN}✓${NC} Script é executável: scripts/limpar_sistema.sh"
    else
        echo -e "${YELLOW}⚠${NC} Script não é executável: scripts/limpar_sistema.sh"
        warnings=$((warnings + 1))
    fi
fi

echo ""
echo -e "${BLUE}Verificando configurações...${NC}"
echo ""

# Configurações
check_exists "requirements.txt" "file" "true"
check_exists ".gitignore" "file" "true"

echo ""
echo -e "${BLUE}Verificando dados...${NC}"
echo ""

# Dados
check_exists "data/perguntas_exemplo.txt" "file" "false"
check_exists "data/cache/pdf_cache_otimizado" "directory" "true"
check_exists "data/cache/resposta_cache_otimizado" "directory" "true"

echo ""
echo "=========================================="
echo "           RESUMO DA VALIDAÇÃO"
echo "=========================================="
echo ""
echo -e "Total de verificações: ${BLUE}$checks${NC}"
echo -e "Sucesso: ${GREEN}$((checks - errors - warnings))${NC}"
echo -e "Avisos: ${YELLOW}$warnings${NC}"
echo -e "Erros: ${RED}$errors${NC}"
echo ""

if [ $errors -eq 0 ]; then
    echo -e "${GREEN}✓ Estrutura do projeto está CORRETA!${NC}"
    echo ""
    
    # Mostrar estatísticas adicionais
    echo "Estatísticas adicionais:"
    echo "  - Arquivos Python: $(find src -name '*.py' | wc -l)"
    echo "  - Arquivos HTML: $(find frontend -name '*.html' | wc -l)"
    echo "  - Arquivos de documentação: $(find docs -name '*.md' | wc -l)"
    echo "  - Scripts: $(find scripts -name '*.sh' | wc -l)"
    echo ""
    
    # Tamanho dos diretórios
    if command -v du &> /dev/null; then
        echo "Tamanho dos diretórios principais:"
        du -sh src 2>/dev/null | sed 's/^/  /'
        du -sh data 2>/dev/null | sed 's/^/  /'
        du -sh docs 2>/dev/null | sed 's/^/  /'
    fi
    
    exit 0
else
    echo -e "${RED}✗ Estrutura do projeto tem ERROS!${NC}"
    echo "Por favor, corrija os arquivos/diretórios faltantes."
    exit 1
fi
