#!/bin/bash
# Script de limpeza do sistema
# Remove caches antigos e arquivos temporários

echo "=================================="
echo "  Limpeza do Sistema - Novavet  "
echo "=================================="
echo ""

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Diretório raiz do projeto
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${YELLOW}Diretório do projeto:${NC} $PROJECT_ROOT"
echo ""

# Função para perguntar confirmação
confirm() {
    read -p "$1 (s/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[SsYy]$ ]]; then
        return 0
    else
        return 1
    fi
}

# Limpar cache de respostas
if confirm "Limpar cache de respostas?"; then
    if [ -d "data/cache/resposta_cache_otimizado" ]; then
        rm -rf data/cache/resposta_cache_otimizado/*
        echo -e "${GREEN}✓${NC} Cache de respostas limpo"
    else
        echo -e "${YELLOW}⚠${NC} Diretório de cache de respostas não encontrado"
    fi
fi

# Limpar cache de PDFs
if confirm "Limpar cache de PDFs?"; then
    if [ -d "data/cache/pdf_cache_otimizado" ]; then
        rm -rf data/cache/pdf_cache_otimizado/*
        echo -e "${GREEN}✓${NC} Cache de PDFs limpo"
    else
        echo -e "${YELLOW}⚠${NC} Diretório de cache de PDFs não encontrado"
    fi
fi

# Limpar __pycache__
if confirm "Limpar arquivos __pycache__?"; then
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
    find . -type f -name "*.pyc" -delete 2>/dev/null
    echo -e "${GREEN}✓${NC} Arquivos Python cache limpos"
fi

# Limpar arquivos temporários
if confirm "Limpar arquivos temporários (.tmp, .log)?"; then
    find . -type f -name "*.tmp" -delete 2>/dev/null
    find . -type f -name "*.log" -delete 2>/dev/null
    echo -e "${GREEN}✓${NC} Arquivos temporários limpos"
fi

# Recriar estrutura de diretórios
echo ""
echo "Recriando estrutura de diretórios..."
mkdir -p data/cache/pdf_cache_otimizado
mkdir -p data/cache/resposta_cache_otimizado
mkdir -p data/results
echo -e "${GREEN}✓${NC} Estrutura de diretórios recriada"

echo ""
echo -e "${GREEN}Limpeza concluída!${NC}"
echo ""

# Mostrar tamanho dos diretórios
echo "Tamanho dos diretórios:"
du -sh data/cache/* 2>/dev/null
du -sh data/results 2>/dev/null
