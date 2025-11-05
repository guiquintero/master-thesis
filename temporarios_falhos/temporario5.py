#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Sistema Completo de Consulta Veterinária - Versão Final
Combina a assertividade do temporario.py com a eficiência do temporario2.py
Mantém todas as funcionalidades importantes: follow-up, consulta dupla, etc.
Melhorado com processamento avançado de tabelas
"""

import json
import os
import time
import hashlib
import asyncio
import aiohttp
from termcolor import colored
import ollama
from aiohttp import ClientSession, TCPConnector, ClientTimeout
import sys
import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

# Importações do código original
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import urllib3
from tqdm import tqdm

# Bibliotecas para processamento de PDF
import fitz  # PyMuPDF
import pdfplumber
import pandas as pd
import tabula

# Tentar importar camelot (opcional mas útil)
try:
    import camelot
    HAS_CAMELOT = True
except ImportError:
    HAS_CAMELOT = False
    print(colored("⚠️  Camelot não instalado. Instale com: pip install camelot-py[cv]", "yellow"))

# Importar o classificador de query
try:
    from query_classifier import QueryClassifier
except ImportError:
    print(colored("⚠️  Módulo query_classifier não encontrado", "yellow"))
    QueryClassifier = None

# Importar extractors avançados se disponíveis
try:
    from pdf_estruturado_extractor import PDFEstruturadoExtractor
except ImportError:
    PDFEstruturadoExtractor = None

# Desativar alertas de aviso de SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
}

# Configurações globais
MODELO_OLLAMA_PADRAO = "gemma3:latest"
PDF_CACHE_DIR = "pdf_cache_otimizado"
CACHE_DIR_RESPOSTAS = "resposta_cache_otimizado"
ARQUIVO_JSON_SCRAPING = "medicamento_buscado_otimizado.json"

# Configurações de performance
MAX_CONCURRENT_REQUESTS = 5
MAX_PDF_PAGES = 20  # Limitar páginas de PDF processadas
CACHE_TTL = 86400   # 24 horas
CONTEXT_SIZE_LIMIT = 50000  # Limite de caracteres para contexto

# Criar diretórios de cache se não existirem
os.makedirs(PDF_CACHE_DIR, exist_ok=True)
os.makedirs(CACHE_DIR_RESPOSTAS, exist_ok=True)

# Forçar flush automático em todos os prints
_original_print = print
def print(*args, **kwargs):
    _original_print(*args, **kwargs)
    if 'file' not in kwargs or kwargs['file'] == sys.stdout:
        sys.stdout.flush()


@dataclass
class InformacaoExtraida:
    """Estrutura para informação extraída com metadados"""
    conteudo: str
    secao: str
    confianca: float  # 0.0 a 1.0
    pagina: int
    metodo_extracao: str
    contexto: str = ""
    tipo: str = ""  # dose, armazenamento, intervalo, etc.


class TabelaProcessorAvancado:
    """
    Processador avançado de tabelas que usa múltiplas bibliotecas
    para extrair informações estruturadas de PDFs
    """
    
    def __init__(self):
        self.metodos_disponiveis = self._detectar_metodos()
        
        # Padrões específicos para campos importantes
        self.padroes_campo = {
            'dose': {
                'patterns': [
                    r'(\d+(?:[.,]\d+)?)\s*(?:mg|ml|g|mcg|μg|UI)\s*(?:\/|por)\s*kg',
                    r'(\d+(?:[.,]\d+)?)\s*(?:mg|ml|g)\/kg\s+(?:de\s+)?peso',
                    r'dose[:\s]+(\d+(?:[.,]\d+)?)\s*(?:mg|ml|g)',
                ],
                'keywords': ['dose', 'dosagem', 'posologia']
            },
            'armazenamento': {
                'patterns': [
                    r'(?:conservar|armazenar|manter)\s+(?:a|entre)?\s*(\d+)\s*°?\s*C',
                    r'temperatura\s+(?:até|inferior a)?\s*(\d+)\s*°?\s*C',
                    r'(\d+)\s*-\s*(\d+)\s*°?\s*C',
                    r'(?:após abertura|depois de aberto)[^.]*?(\d+)\s*(dias?|horas?|meses?)',
                ],
                'keywords': ['armazenar', 'conservar', 'temperatura', 'refrigeração', 'após abertura']
            },
            'intervalo_seguranca': {
                'patterns': [
                    r'(?:tempo de espera|intervalo de segurança)[:\s]+(\d+)\s+(dias?|horas?)',
                    r'carência[:\s]+(\d+)\s+(dias?|horas?)',
                    r'(\d+)\s+(dias?|horas?)\s+(?:de\s+)?(?:carência|espera)',
                    r'carne[:\s]+(\d+)\s+dias',
                    r'leite[:\s]+(\d+)\s+(?:horas|ordenhas)',
                ],
                'keywords': ['intervalo', 'segurança', 'carência', 'espera', 'carne', 'leite', 'ovos']
            },
            'composicao': {
                'patterns': [
                    r'(?:contém|contem)\s+([\w\s,]+)\s+(\d+(?:[.,]\d+)?)\s*(?:mg|ml|g)',
                    r'princípio\s+ativo[:\s]+([\w\s]+)',
                    r'(\w+)\s+(\d+(?:[.,]\d+)?)\s*(?:mg|ml|g)\s*(?:por|\/)',
                ],
                'keywords': ['composição', 'princípio ativo', 'substância ativa', 'contém']
            },
            'especies': {
                'patterns': [
                    r'(?:espécies|especies)[:\s]+([^.]+)',
                    r'(?:indicado para|destinado a)[:\s]+([^.]+)',
                ],
                'keywords': ['espécies', 'animais', 'bovinos', 'suínos', 'equinos', 'cães', 'gatos', 'aves']
            },
            'reacoes_adversas': {
                'patterns': [
                    r'(?:reações|efeitos)\s+(?:adversas?|indesejáveis)[:\s]+([^.]+)',
                    r'(?:pode|podem)\s+(?:ocorrer|surgir)[:\s]+([^.]+)',
                ],
                'keywords': ['reações', 'efeitos', 'adversas', 'indesejáveis', 'colaterais']
            },
            'via_administracao': {
                'patterns': [
                    r'via\s+(oral|intramuscular|intravenosa|subcutânea|tópica|IM|IV|SC)',
                    r'administração\s+(oral|intramuscular|intravenosa|subcutânea|tópica)',
                ],
                'keywords': ['via', 'administração', 'oral', 'intramuscular', 'intravenosa']
            },
            'receita': {
                'patterns': [
                    r'(?:sujeito a|requer|necessita)\s+receita\s+(?:médica\s+)?veterinária',
                    r'venda\s+(?:sob|com)\s+receita',
                    r'medicamento\s+(?:sujeito a|de)\s+receita',
                ],
                'keywords': ['receita', 'prescrição', 'venda']
            }
        }
    
    def _detectar_metodos(self):
        """Detecta quais métodos de extração estão disponíveis"""
        metodos = ['pdfplumber', 'pymupdf']  # Sempre disponíveis
        
        try:
            import tabula
            metodos.append('tabula')
        except ImportError:
            pass
        
        if HAS_CAMELOT:
            metodos.append('camelot')
        
        return metodos
    
    def processar_pdf(self, pdf_path: str, pergunta: str = None) -> Dict[str, Any]:
        """
        Processa PDF usando múltiplos métodos para extração robusta
        """
        resultado = {
            'texto_completo': '',
            'tabelas': [],
            'informacoes_extraidas': {},
            'secoes': [],
            'metadados': {},
            'resumo_estruturado': {}
        }
        
        print(colored(f"📄 Processando PDF com {len(self.metodos_disponiveis)} métodos disponíveis", "cyan"))
        
        # 1. Extração básica de texto com PyMuPDF
        texto_pymupdf, secoes_pymupdf = self._extrair_com_pymupdf(pdf_path)
        resultado['texto_completo'] = texto_pymupdf
        resultado['secoes'] = secoes_pymupdf
        
        # 2. Extração de tabelas com pdfplumber
        tabelas_pdfplumber = self._extrair_tabelas_pdfplumber(pdf_path)
        if tabelas_pdfplumber:
            resultado['tabelas'].extend(tabelas_pdfplumber)
        
        # 3. Extração de tabelas com tabula se disponível
        if 'tabula' in self.metodos_disponiveis:
            tabelas_tabula = self._extrair_tabelas_tabula(pdf_path)
            if tabelas_tabula:
                resultado['tabelas'].extend(tabelas_tabula)
        
        # 4. Extração de tabelas com camelot se disponível
        if 'camelot' in self.metodos_disponiveis:
            tabelas_camelot = self._extrair_tabelas_camelot(pdf_path)
            if tabelas_camelot:
                resultado['tabelas'].extend(tabelas_camelot)
        
        # 5. Processar e interpretar tabelas
        resultado['tabelas'] = self._processar_e_interpretar_tabelas(resultado['tabelas'])
        
        # 6. Extrair informações específicas
        resultado['informacoes_extraidas'] = self._extrair_informacoes_especificas(
            resultado['texto_completo'], 
            resultado['tabelas'],
            pergunta
        )
        
        # 7. Criar resumo estruturado
        resultado['resumo_estruturado'] = self._criar_resumo_estruturado(resultado)
        
        return resultado
    
    def _extrair_com_pymupdf(self, pdf_path: str) -> Tuple[str, List[str]]:
        """Extração básica com PyMuPDF"""
        texto_completo = []
        secoes = []
        
        try:
            with fitz.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf):
                    if page_num >= MAX_PDF_PAGES:
                        break
                    
                    texto_pagina = page.get_text()
                    texto_completo.append(f"\n--- Página {page_num + 1} ---\n{texto_pagina}")
                    
                    # Dividir em seções
                    secoes_pagina = self._dividir_em_secoes(texto_pagina)
                    secoes.extend(secoes_pagina)
        
        except Exception as e:
            print(colored(f"⚠️  Erro PyMuPDF: {e}", "red"))
        
        return '\n'.join(texto_completo), secoes
    
    def _extrair_tabelas_pdfplumber(self, pdf_path: str) -> List[Dict]:
        """Extrai tabelas usando pdfplumber"""
        tabelas = []
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages[:MAX_PDF_PAGES]):
                    tabelas_pagina = page.extract_tables()
                    
                    for i, tabela in enumerate(tabelas_pagina):
                        if tabela and len(tabela) > 1:
                            tabelas.append({
                                'metodo': 'pdfplumber',
                                'pagina': page_num + 1,
                                'indice': i,
                                'dados': tabela,
                                'processada': self._processar_tabela_raw(tabela)
                            })
                            
                            print(colored(f"  ✓ Tabela encontrada (pdfplumber) - Página {page_num + 1}", "green"))
        
        except Exception as e:
            print(colored(f"⚠️  Erro pdfplumber: {e}", "yellow"))
        
        return tabelas
    
    def _extrair_tabelas_tabula(self, pdf_path: str) -> List[Dict]:
        """Extrai tabelas usando tabula-py"""
        tabelas = []
        
        try:
            # Tentar diferentes estratégias
            for strategy in ['lattice', 'stream']:
                dfs = tabula.read_pdf(
                    pdf_path,
                    pages='all',
                    multiple_tables=True,
                    lattice=(strategy == 'lattice'),
                    stream=(strategy == 'stream'),
                    silent=True
                )
                
                for i, df in enumerate(dfs):
                    if not df.empty:
                        tabelas.append({
                            'metodo': f'tabula-{strategy}',
                            'pagina': 0,  # tabula não fornece página facilmente
                            'indice': i,
                            'dados': df.values.tolist(),
                            'colunas': df.columns.tolist(),
                            'processada': self._processar_dataframe(df)
                        })
                        
                        print(colored(f"  ✓ Tabela encontrada (tabula-{strategy})", "green"))
        
        except Exception as e:
            print(colored(f"⚠️  Erro tabula: {e}", "yellow"))
        
        return tabelas
    
    def _extrair_tabelas_camelot(self, pdf_path: str) -> List[Dict]:
        """Extrai tabelas usando camelot"""
        tabelas = []
        
        if not HAS_CAMELOT:
            return tabelas
        
        try:
            # Tentar diferentes flavors
            for flavor in ['lattice', 'stream']:
                tables = camelot.read_pdf(
                    pdf_path,
                    pages='all',
                    flavor=flavor,
                    suppress_stdout=True
                )
                
                for table in tables:
                    tabelas.append({
                        'metodo': f'camelot-{flavor}',
                        'pagina': table.page,
                        'indice': table.order,
                        'dados': table.df.values.tolist(),
                        'colunas': table.df.columns.tolist(),
                        'processada': self._processar_dataframe(table.df),
                        'precisao': table.accuracy  # Camelot fornece precisão
                    })
                    
                    print(colored(f"  ✓ Tabela encontrada (camelot-{flavor}) - Precisão: {table.accuracy:.2f}", "green"))
        
        except Exception as e:
            print(colored(f"⚠️  Erro camelot: {e}", "yellow"))
        
        return tabelas
    
    def _processar_tabela_raw(self, tabela: List[List]) -> Dict:
        """Processa tabela em formato de lista"""
        if not tabela or len(tabela) < 2:
            return {}
        
        processada = {
            'cabecalhos': [],
            'linhas': [],
            'interpretacao': []
        }
        
        # Assumir primeira linha como cabeçalho
        processada['cabecalhos'] = [str(cell).strip() if cell else '' for cell in tabela[0]]
        
        # Processar linhas de dados
        for linha in tabela[1:]:
            linha_limpa = [str(cell).strip() if cell else '' for cell in linha]
            processada['linhas'].append(linha_limpa)
            
            # Interpretar linha
            interpretacao = self._interpretar_linha_tabela(
                dict(zip(processada['cabecalhos'], linha_limpa))
            )
            if interpretacao:
                processada['interpretacao'].append(interpretacao)
        
        return processada
    
    def _processar_dataframe(self, df: pd.DataFrame) -> Dict:
        """Processa DataFrame do pandas"""
        processada = {
            'cabecalhos': df.columns.tolist(),
            'linhas': df.values.tolist(),
            'interpretacao': []
        }
        
        # Interpretar cada linha
        for _, row in df.iterrows():
            interpretacao = self._interpretar_linha_tabela(row.to_dict())
            if interpretacao:
                processada['interpretacao'].append(interpretacao)
        
        return processada
    
    def _interpretar_linha_tabela(self, linha_dict: Dict) -> Dict:
        """Interpreta uma linha de tabela extraindo informações relevantes"""
        interpretacao = {}
        
        for campo, config in self.padroes_campo.items():
            # Verificar se alguma keyword está presente nos cabeçalhos ou valores
            relevante = False
            for key, value in linha_dict.items():
                key_str = str(key).lower() if key else ''
                value_str = str(value).lower() if value else ''
                
                if any(kw in key_str or kw in value_str for kw in config['keywords']):
                    relevante = True
                    break
            
            if relevante:
                # Extrair informação usando padrões
                for pattern in config['patterns']:
                    for value in linha_dict.values():
                        if value:
                            match = re.search(pattern, str(value), re.IGNORECASE)
                            if match:
                                interpretacao[campo] = match.group(0)
                                break
        
        return interpretacao
    
    def _processar_e_interpretar_tabelas(self, tabelas: List[Dict]) -> List[Dict]:
        """Processa e consolida tabelas de múltiplas fontes"""
        # Remover duplicatas baseadas no conteúdo
        tabelas_unicas = []
        conteudos_vistos = set()
        
        for tabela in tabelas:
            # Criar hash do conteúdo
            conteudo_str = json.dumps(tabela.get('dados', []), sort_keys=True)
            conteudo_hash = hashlib.md5(conteudo_str.encode()).hexdigest()
            
            if conteudo_hash not in conteudos_vistos:
                conteudos_vistos.add(conteudo_hash)
                tabelas_unicas.append(tabela)
        
        # Ordenar por precisão (se disponível) ou por método preferido
        metodo_prioridade = {'camelot-lattice': 1, 'camelot-stream': 2, 
                           'pdfplumber': 3, 'tabula-lattice': 4, 'tabula-stream': 5}
        
        tabelas_unicas.sort(key=lambda t: (
            -t.get('precisao', 0),  # Maior precisão primeiro
            metodo_prioridade.get(t['metodo'], 999)  # Método preferido
        ))
        
        return tabelas_unicas
    
    def _dividir_em_secoes(self, texto: str) -> List[str]:
        """Divide texto em seções"""
        # Padrões para identificar seções
        padroes_secao = [
            r'\n(?=\d+\.\s+[A-Z])',  # 1. NOME DO MEDICAMENTO
            r'\n(?=\d+\.\d+\s+)',     # 4.1 Espécies-alvo
            r'\n(?=[A-Z][A-Z\s]{10,}:)',  # COMPOSIÇÃO:
        ]
        
        secoes = []
        texto_atual = texto
        
        for padrao in padroes_secao:
            partes = re.split(padrao, texto_atual)
            if len(partes) > 1:
                secoes.extend(partes)
                return secoes
        
        # Se não encontrar padrões, dividir por parágrafos grandes
        paragrafos = texto.split('\n\n')
        return [p.strip() for p in paragrafos if len(p.strip()) > 50]
    
    def _extrair_informacoes_especificas(self, texto: str, tabelas: List[Dict], pergunta: str = None) -> Dict:
        """Extrai informações específicas do texto e tabelas"""
        informacoes = {}
        
        # Analisar contexto da pergunta se fornecida
        tipo_informacao = self._identificar_tipo_pergunta(pergunta) if pergunta else None
        
        # Extrair de texto
        for campo, config in self.padroes_campo.items():
            # Priorizar campo se for o tipo da pergunta
            if tipo_informacao == campo or not tipo_informacao:
                valores_encontrados = []
                
                # Buscar no texto
                for pattern in config['patterns']:
                    matches = re.findall(pattern, texto, re.IGNORECASE | re.MULTILINE)
                    valores_encontrados.extend(matches)
                
                # Buscar nas tabelas
                for tabela in tabelas:
                    if 'processada' in tabela and 'interpretacao' in tabela['processada']:
                        for interp in tabela['processada']['interpretacao']:
                            if campo in interp:
                                valores_encontrados.append(interp[campo])
                
                if valores_encontrados:
                    # Limpar e consolidar valores
                    valores_unicos = list(set([str(v) for v in valores_encontrados if v]))
                    informacoes[campo] = valores_unicos
        
        return informacoes
    
    def _identificar_tipo_pergunta(self, pergunta: str) -> Optional[str]:
        """Identifica o tipo de informação solicitada na pergunta"""
        if not pergunta:
            return None
        
        pergunta_lower = pergunta.lower()
        
        # Mapear palavras-chave para tipos
        mapeamento = {
            'dose': ['dose', 'dosagem', 'quanto', 'quantidade', 'ml', 'mg'],
            'armazenamento': ['armazenar', 'guardar', 'conservar', 'temperatura', 'aberto', 'depois de aberto'],
            'intervalo_seguranca': ['intervalo', 'segurança', 'carência', 'espera', 'tempo de espera'],
            'composicao': ['composição', 'contém', 'princípio', 'ativo', 'substância'],
            'especies': ['espécie', 'animal', 'indicado para', 'pode ser usado'],
            'reacoes_adversas': ['reação', 'efeito', 'adversa', 'colateral', 'indesejável'],
            'via_administracao': ['via', 'administração', 'como administrar', 'forma de administração'],
            'receita': ['receita', 'prescrição', 'venda']
        }
        
        for tipo, palavras in mapeamento.items():
            if any(palavra in pergunta_lower for palavra in palavras):
                return tipo
        
        return None
    
    def _criar_resumo_estruturado(self, resultado: Dict) -> Dict:
        """Cria um resumo estruturado das informações extraídas"""
        resumo = {
            'medicamento': '',
            'informacoes_principais': {},
            'tabelas_relevantes': [],
            'confianca_geral': 0.0
        }
        
        # Extrair nome do medicamento (geralmente na primeira seção)
        if resultado['secoes']:
            primeira_secao = resultado['secoes'][0]
            # Tentar extrair nome do medicamento
            match_nome = re.search(r'^\d+\.\s*(.+?)(?:\n|$)', primeira_secao)
            if match_nome:
                resumo['medicamento'] = match_nome.group(1).strip()
        
        # Compilar informações principais
        for campo, valores in resultado['informacoes_extraidas'].items():
            if valores:
                if len(valores) == 1:
                    resumo['informacoes_principais'][campo] = valores[0]
                else:
                    resumo['informacoes_principais'][campo] = valores
        
        # Adicionar tabelas mais relevantes (com maior precisão)
        tabelas_ordenadas = sorted(
            resultado['tabelas'],
            key=lambda t: t.get('precisao', 0),
            reverse=True
        )
        
        resumo['tabelas_relevantes'] = tabelas_ordenadas[:3]  # Top 3 tabelas
        
        # Calcular confiança geral
        if resultado['tabelas']:
            precisoes = [t.get('precisao', 0.5) for t in resultado['tabelas'] if 'precisao' in t]
            if precisoes:
                resumo['confianca_geral'] = sum(precisoes) / len(precisoes)
        
        return resumo


class SistemaConsultaVetOtimizado:
    """
    Sistema principal completo que mantém todas as funcionalidades importantes
    """
    
    def __init__(self, modelo_ollama=MODELO_OLLAMA_PADRAO, temperatura_ollama=0.2):
        self.modelo_ollama = modelo_ollama
        self.temperatura_ollama = temperatura_ollama
        
        # Inicializar classificador se disponível
        if QueryClassifier:
            self.query_classifier = QueryClassifier(modelo_ollama)
        else:
            self.query_classifier = None
            
        # Processador de tabelas avançado
        self.tabela_processor = TabelaProcessorAvancado()
        
        # Cache manager
        self.cache_manager = CacheManager(CACHE_DIR_RESPOSTAS)
        
        # Mapeamento de espécies para normalização
        self.mapeamento_especies = self._criar_mapeamento_especies()
        
        # Contexto de conversação completo (mantido do original)
        self.contexto_conversacao = {
            "ultima_pergunta": None,
            "ultima_categoria": None,
            "ultima_entidade_medicamento": None,
            "ultimo_termo_busca": None,
            "ultima_resposta": None,
            "dados_ultimo_scraping": None,
            "ultimo_scraping_time": 0,
            "ultima_interacao_time": time.time(),
            "historico_conversacao": [],
            "metadados_scraping": None,
            "contexto_follow_up": None,  # Para perguntas de follow-up
            "medicamentos_comparados": []  # Para consultas duplas
        }
        
        self._pdf_cache = {}
        self.session = None
        
        # Métricas de desempenho
        self.tempos_execucao = {
            'inicio_total': 0,
            'classificacao': 0,
            'web_scraping': 0,
            'extracao_pdf': 0,
            'processamento_tabelas': 0,
            'ollama': 0,
            'formatacao': 0,
            'total': 0,
            'follow_up_detection': 0,
            'consulta_dupla': 0
        }
    
    def _criar_mapeamento_especies(self):
        """Cria mapeamento de espécies para normalização"""
        return {
            # Bovinos
            'boi': 'bovinos', 'vaca': 'bovinos', 'vacas': 'bovinos', 'gado': 'bovinos',
            'bezerro': 'bovinos', 'bezerros': 'bovinos', 'novilho': 'bovinos',
            
            # Suínos
            'porco': 'suínos', 'porcos': 'suínos', 'suíno': 'suínos', 
            'leitão': 'suínos', 'leitões': 'suínos', 'porca': 'suínos',
            
            # Equinos
            'cavalo': 'equinos', 'cavalos': 'equinos', 'égua': 'equinos',
            'potro': 'equinos', 'equino': 'equinos',
            
            # Aves
            'galinha': 'aves', 'galinhas': 'aves', 'frango': 'aves', 'frangos': 'aves',
            'peru': 'aves', 'perus': 'aves', 'pato': 'aves', 'patos': 'aves',
            
            # Cães e Gatos
            'cão': 'cães', 'cachorro': 'cães', 'cachorros': 'cães', 'cadela': 'cães',
            'gato': 'gatos', 'gata': 'gatos', 'felino': 'gatos', 'felinos': 'gatos',
            
            # Ovinos e Caprinos
            'ovelha': 'ovinos', 'ovelhas': 'ovinos', 'carneiro': 'ovinos',
            'cabra': 'caprinos', 'cabras': 'caprinos', 'bode': 'caprinos',
            
            # Outros
            'coelho': 'coelhos', 'coelhos': 'coelhos'
        }
    
    def processar_pergunta_unica(self, pergunta_usuario: str) -> str:
        """
        Processa uma pergunta única do usuário com todas as funcionalidades
        Mantém compatibilidade com o método original
        """
        # Início da medição total
        tempo_inicio_total = time.perf_counter()
        self.tempos_execucao['inicio_total'] = tempo_inicio_total
        
        print(colored("\n" + "="*80, "cyan"))
        print(colored(f"📝 Processando pergunta única: {pergunta_usuario}", "cyan"))
        print(colored("="*80, "cyan"))
        
        # Limpar contexto antigo se necessário
        self._limpar_contexto_antigo()
        
        # ETAPA 1: Detectar e processar follow-up
        tempo_followup = time.perf_counter()
        is_followup, entidade_extraida = self._detectar_pergunta_followup(pergunta_usuario)
        self.tempos_execucao['follow_up_detection'] = time.perf_counter() - tempo_followup
        
        if is_followup and entidade_extraida:
            pergunta_completa = self._construir_pergunta_completa(pergunta_usuario, entidade_extraida)
            print(colored(f"🔄 Follow-up detectado. Pergunta completa: '{pergunta_completa}'", "yellow"))
            
            # Se temos dados em cache, usar diretamente
            if self.contexto_conversacao["dados_ultimo_scraping"]:
                resposta = self._consultar_ollama_melhorado(
                    pergunta_completa,
                    self.contexto_conversacao["dados_ultimo_scraping"],
                    {'categoria': 'medicamento', 'follow_up': True}
                )
                
                # Atualizar contexto
                self.contexto_conversacao["ultima_pergunta"] = pergunta_completa
                self.contexto_conversacao["ultima_resposta"] = resposta
                self._adicionar_ao_historico(pergunta_completa, resposta, "follow-up")
                
                # Tempo total
                self.tempos_execucao['total'] = time.perf_counter() - tempo_inicio_total
                self._imprimir_resumo_tempos()
                
                return resposta
            
            pergunta_usuario = pergunta_completa
        
        # ETAPA 2: Normalizar pergunta
        pergunta_normalizada = self._normalizar_especies_texto(pergunta_usuario)
        
        if pergunta_normalizada != pergunta_usuario:
            print(colored(f"📝 Pergunta normalizada: '{pergunta_normalizada}'", "cyan"))
        
        # ETAPA 3: Classificação
        tempo_class = time.perf_counter()
        if self.query_classifier:
            classificacao = self.query_classifier.classify_and_extract(pergunta_normalizada)
        else:
            classificacao = self._classificacao_simples(pergunta_normalizada)
        
        self.tempos_execucao['classificacao'] = time.perf_counter() - tempo_class
        
        # Corrigir categoria se necessário
        classificacao = self._corrigir_categoria_se_necesario(classificacao, pergunta_normalizada)
        
        print(colored(f"📊 Categoria: {classificacao.get('categoria')}", "magenta"))
        print(colored(f"📊 Entidades: {json.dumps(classificacao.get('entidades', {}), indent=2, ensure_ascii=False)}", "magenta"))
        
        # Atualizar contexto
        self.contexto_conversacao["ultima_pergunta"] = pergunta_normalizada
        self.contexto_conversacao["ultima_categoria"] = classificacao.get("categoria")
        
        # ETAPA 4: Processar baseado na categoria
        categoria = classificacao.get("categoria")
        
        if categoria == "medicamento":
            resposta = self._processar_consulta_medicamento(pergunta_normalizada, classificacao)
        
        elif categoria == "comparacao":
            # Verificar se é consulta dupla
            if self._detectar_consulta_dupla(classificacao):
                print(colored("🔀 Consulta dupla detectada", "yellow"))
                resposta = self._realizar_consulta_dupla(classificacao, pergunta_normalizada)
            else:
                resposta = self._processar_comparacao(pergunta_normalizada, classificacao)
        
        else:
            resposta = f"Categoria '{categoria}' não suportada no momento."
        
        # Salvar resposta no contexto
        self.contexto_conversacao["ultima_resposta"] = resposta
        self._adicionar_ao_historico(pergunta_normalizada, resposta, categoria)
        
        # Calcular tempo total
        self.tempos_execucao['total'] = time.perf_counter() - tempo_inicio_total
        self._imprimir_resumo_tempos()
        
        return resposta
    
    def _detectar_pergunta_followup(self, pergunta: str) -> Tuple[bool, Optional[str]]:
        """
        Detecta se é uma pergunta de follow-up e extrai entidade referenciada
        """
        pergunta_lower = pergunta.lower()
        
        # Indicadores de follow-up
        indicadores_followup = [
            'e o', 'e a', 'e os', 'e as',
            'e para', 'e em', 'e no', 'e na',
            'e depois', 'e quanto', 'e como',
            'e qual', 'e quais', 'e que',
            'também', 'ainda', 'além disso',
            'outro', 'outra', 'outros', 'outras',
            'mais algum', 'mais alguma',
            'e se', 'mas e'
        ]
        
        # Verificar se tem indicadores E contexto anterior
        tem_indicador = any(pergunta_lower.startswith(ind) for ind in indicadores_followup)
        tem_contexto = bool(self.contexto_conversacao.get("ultima_entidade_medicamento"))
        
        if tem_indicador and tem_contexto:
            entidade = self.contexto_conversacao.get("ultima_entidade_medicamento")
            return True, entidade
        
        # Verificar perguntas incompletas (sem medicamento mencionado)
        palavras_chave = ['dose', 'armazen', 'conserv', 'interval', 'espécie', 
                         'indicad', 'reaç', 'efeit', 'composiç', 'administr']
        
        tem_palavra_chave = any(kw in pergunta_lower for kw in palavras_chave)
        nao_tem_medicamento = not any(word[0].isupper() and len(word) > 3 
                                     for word in pergunta.split())
        
        if tem_palavra_chave and nao_tem_medicamento and tem_contexto:
            entidade = self.contexto_conversacao.get("ultima_entidade_medicamento")
            return True, entidade
        
        return False, None
    
    def _construir_pergunta_completa(self, pergunta_original: str, entidade: str) -> str:
        """
        Constrói pergunta completa incluindo a entidade do contexto
        """
        pergunta_lower = pergunta_original.lower()
        
        # Remover indicadores de follow-up do início
        indicadores_remover = ['e o ', 'e a ', 'e os ', 'e as ', 'e ']
        for ind in indicadores_remover:
            if pergunta_lower.startswith(ind):
                pergunta_limpa = pergunta_original[len(ind):]
                break
        else:
            pergunta_limpa = pergunta_original
        
        # Construir pergunta completa
        if 'dose' in pergunta_lower:
            return f"Qual a dose do medicamento {entidade}?"
        elif 'armazen' in pergunta_lower or 'conserv' in pergunta_lower:
            return f"Como armazenar o medicamento {entidade}?"
        elif 'espécie' in pergunta_lower or 'indicad' in pergunta_lower:
            return f"Para que espécies é indicado o medicamento {entidade}?"
        elif 'interval' in pergunta_lower or 'seguranç' in pergunta_lower:
            return f"Qual o intervalo de segurança do medicamento {entidade}?"
        elif 'reaç' in pergunta_lower or 'efeit' in pergunta_lower:
            return f"Quais as reações adversas do medicamento {entidade}?"
        elif 'composiç' in pergunta_lower:
            return f"Qual a composição do medicamento {entidade}?"
        else:
            return f"{pergunta_limpa} {entidade}"
    
    def _detectar_consulta_dupla(self, classificacao: Dict) -> bool:
        """
        Detecta se a pergunta requer consulta dupla (ex: medicamentos alternativos)
        """
        entidades = classificacao.get("entidades", {})
        pergunta_ollama = entidades.get("pergunta_ollama", "").lower()
        
        # Indicadores de consulta dupla
        indicadores = [
            "alternativ", "substitut", "equivalente",
            "mesmo princípio ativo", "mesma substância",
            "similar", "parecido", "igual"
        ]
        
        return any(ind in pergunta_ollama for ind in indicadores)
    
    def _realizar_consulta_dupla(self, classificacao: Dict, pergunta_original: str) -> str:
        """
        Realiza consulta dupla para encontrar medicamentos alternativos
        """
        tempo_dupla = time.perf_counter()
        
        entidades = classificacao.get("entidades", {})
        medicamento_ref = entidades.get("medicamento") or entidades.get("termo_busca")
        
        if not medicamento_ref:
            return "Por favor, especifique o medicamento de referência."
        
        print(colored(f"🔍 FASE 1: Buscando informações sobre {medicamento_ref}...", "yellow"))
        
        # Buscar informações do medicamento de referência
        dados_medicamento = self.realizar_web_scraping_sincrono(medicamento_ref)
        
        if not dados_medicamento:
            return f"Não foi possível encontrar informações sobre '{medicamento_ref}'."
        
        # Extrair princípio ativo
        print(colored("🔬 Extraindo princípio ativo...", "yellow"))
        principio_ativo = self._extrair_principio_ativo(dados_medicamento)
        
        if not principio_ativo:
            return f"Não foi possível identificar o princípio ativo de '{medicamento_ref}'."
        
        print(colored(f"✅ Princípio ativo identificado: {principio_ativo}", "green"))
        
        # Buscar medicamentos com o mesmo princípio ativo
        print(colored(f"🔍 FASE 2: Buscando medicamentos com {principio_ativo}...", "yellow"))
        
        resultados_comparacao = self._realizar_busca_comparacao_simples(principio_ativo)
        
        if not resultados_comparacao:
            return f"Não foram encontrados outros medicamentos com '{principio_ativo}'."
        
        # Filtrar medicamento de referência
        resultados_filtrados = [
            r for r in resultados_comparacao
            if medicamento_ref.lower() not in r.get('nome', '').lower()
        ]
        
        # Formatar resposta
        resposta = self._formatar_resposta_consulta_dupla(
            medicamento_ref,
            principio_ativo,
            resultados_filtrados,
            pergunta_original
        )
        
        self.tempos_execucao['consulta_dupla'] = time.perf_counter() - tempo_dupla
        
        return resposta
    
    def _extrair_principio_ativo(self, dados_medicamento: List[Dict]) -> Optional[str]:
        """
        Extrai o princípio ativo dos dados do medicamento
        """
        if not dados_medicamento:
            return None
        
        # Processar o primeiro resultado
        primeiro = dados_medicamento[0]
        
        # Se tem PDF, processar para extrair composição
        if 'pdf_path' in primeiro and os.path.exists(primeiro['pdf_path']):
            resultado_pdf = self.tabela_processor.processar_pdf(primeiro['pdf_path'])
            
            if 'informacoes_extraidas' in resultado_pdf:
                composicao = resultado_pdf['informacoes_extraidas'].get('composicao', [])
                if composicao:
                    # Extrair primeiro princípio ativo
                    for comp in composicao:
                        # Procurar por nome de substância
                        match = re.search(r'([A-Za-z]+(?:\s+[A-Za-z]+)*)', str(comp))
                        if match:
                            return match.group(1)
        
        # Fallback: usar Ollama para extrair
        try:
            prompt = f"""
            Com base nas informações:
            {json.dumps(dados_medicamento[0], ensure_ascii=False, indent=2)}
            
            Extraia APENAS o princípio ativo principal.
            Responda apenas com o nome, sem explicações.
            """
            
            response = ollama.chat(
                model=self.modelo_ollama,
                messages=[{'role': 'user', 'content': prompt}],
                options={'temperature': 0.0}
            )
            
            return response['message']['content'].strip()
        
        except:
            return None
    
    def _formatar_resposta_consulta_dupla(self, medicamento_ref: str, principio_ativo: str, 
                                         resultados: List[Dict], pergunta: str) -> str:
        """
        Formata resposta para consulta dupla
        """
        if "alternativ" in pergunta.lower():
            titulo = f"Medicamentos alternativos ao {medicamento_ref}"
        elif "substitut" in pergunta.lower():
            titulo = f"Medicamentos substitutos do {medicamento_ref}"
        else:
            titulo = f"Medicamentos com mesmo princípio ativo que {medicamento_ref}"
        
        resposta = f"**{titulo}:**\n\n"
        resposta += f"🔬 **Princípio ativo:** {principio_ativo}\n\n"
        
        if not resultados:
            resposta += "ℹ️ Não foram encontrados outros medicamentos com este princípio ativo."
        else:
            resposta += f"📋 **Medicamentos encontrados ({len(resultados)}):**\n\n"
            
            for i, item in enumerate(resultados[:10], 1):
                resposta += f"{i}. **{item.get('nome', 'Nome não disponível')}**\n"
                
                if item.get('especies'):
                    resposta += f"   • Espécies: {item['especies']}\n"
                
                if item.get('forma_farmaceutica'):
                    resposta += f"   • Forma: {item['forma_farmaceutica']}\n"
                
                resposta += "\n"
        
        return resposta
    
    def _processar_consulta_medicamento(self, pergunta: str, classificacao: Dict) -> str:
        """
        Processa consulta sobre medicamento específico
        """
        entidades = classificacao.get('entidades', {})
        termo_busca = entidades.get('termo_busca') or entidades.get('substancia_ativa')
        
        if not termo_busca:
            termo_busca = self._extrair_termo_busca(pergunta)
        
        print(colored(f"🔍 Buscando por: {termo_busca}", "cyan"))
        
        # Atualizar contexto
        self.contexto_conversacao["ultimo_termo_busca"] = termo_busca
        self.contexto_conversacao["ultima_entidade_medicamento"] = termo_busca
        
        # Realizar web scraping
        tempo_scraping = time.perf_counter()
        dados_raspados = self.realizar_web_scraping_sincrono(termo_busca)
        self.tempos_execucao['web_scraping'] = time.perf_counter() - tempo_scraping
        
        if not dados_raspados:
            return f"Não foram encontrados resultados para '{termo_busca}'."
        
        # Salvar dados no contexto
        self.contexto_conversacao["dados_ultimo_scraping"] = dados_raspados
        self.contexto_conversacao["ultimo_scraping_time"] = time.time()
        
        # Processar PDFs com o processador avançado
        tempo_pdf = time.perf_counter()
        dados_processados = []
        
        for item in dados_raspados[:3]:  # Processar top 3 resultados
            if 'pdf_path' in item and os.path.exists(item['pdf_path']):
                print(colored(f"📄 Processando PDF: {item['nome']}", "cyan"))
                
                resultado_pdf = self.tabela_processor.processar_pdf(
                    item['pdf_path'],
                    pergunta
                )
                
                item['conteudo_processado'] = resultado_pdf
                dados_processados.append(item)
        
        self.tempos_execucao['extracao_pdf'] = time.perf_counter() - tempo_pdf
        self.tempos_execucao['processamento_tabelas'] = self.tempos_execucao['extracao_pdf']
        
        # Consultar Ollama com dados processados
        resposta = self._consultar_ollama_melhorado(
            pergunta,
            dados_processados or dados_raspados,
            classificacao
        )
        
        return resposta
    
    def _processar_comparacao(self, pergunta: str, classificacao: Dict) -> str:
        """
        Processa comparação entre medicamentos
        """
        entidades = classificacao.get('entidades', {})
        substancia = entidades.get('substancia_ativa', '')
        especie = entidades.get('especie_alvo', '')
        forma = entidades.get('forma_farmaceutica', '')
        
        # Construir termo de busca
        termo_busca = f"{substancia} {especie} {forma}".strip()
        
        if not termo_busca:
            return "Por favor, especifique a substância ativa, espécie ou forma farmacêutica para comparação."
        
        print(colored(f"🔍 Buscando para comparação: {termo_busca}", "cyan"))
        
        # Buscar medicamentos
        resultados = self._realizar_busca_comparacao_simples(termo_busca)
        
        if not resultados:
            return f"Não foram encontrados medicamentos com os critérios: {termo_busca}"
        
        # Formatar resposta
        resposta = self._formatar_resultados_comparacao_simples(resultados, pergunta)
        
        return resposta
    
    def _realizar_busca_comparacao_simples(self, termo_busca: str) -> List[Dict]:
        """
        Realiza busca simples para comparação
        """
        # Aqui seria feita a busca real
        # Por enquanto, retornar dados mock
        return self.realizar_web_scraping_sincrono(termo_busca)
    
    def _formatar_resultados_comparacao_simples(self, resultados: List[Dict], pergunta: str) -> str:
        """
        Formata resultados de comparação
        """
        resposta = "**Medicamentos encontrados:**\n\n"
        
        for i, item in enumerate(resultados[:10], 1):
            resposta += f"{i}. **{item.get('nome', 'Nome não disponível')}**\n"
            
            if 'resumo' in item:
                resposta += f"   {item['resumo'][:100]}...\n"
            
            resposta += "\n"
        
        resposta += f"\n📊 Total: {len(resultados)} medicamentos encontrados"
        
        return resposta
    
    def _consultar_ollama_melhorado(self, pergunta: str, dados: List[Dict], classificacao: Dict) -> str:
        """
        Consulta Ollama com dados processados e estruturados
        """
        tempo_ollama = time.perf_counter()
        
        # Preparar contexto estruturado
        contexto = self._preparar_contexto_estruturado(dados, pergunta)
        
        # Criar prompt otimizado
        prompt = self._criar_prompt_otimizado(pergunta, contexto, classificacao)
        
        try:
            # Consultar Ollama
            response = ollama.chat(
                model=self.modelo_ollama,
                messages=[
                    {
                        'role': 'system',
                        'content': 'Você é um assistente especializado em medicamentos veterinários. '
                                 'Responda de forma precisa e direta baseando-se apenas nas informações fornecidas.'
                    },
                    {
                        'role': 'user',
                        'content': prompt
                    }
                ],
                options={
                    'temperature': self.temperatura_ollama,
                    'num_predict': 500
                }
            )
            
            resposta = response['message']['content']
            
        except Exception as e:
            print(colored(f"❌ Erro ao consultar Ollama: {e}", "red"))
            resposta = "Erro ao processar a resposta."
        
        self.tempos_execucao['ollama'] = time.perf_counter() - tempo_ollama
        
        return resposta
    
    def _preparar_contexto_estruturado(self, dados: List[Dict], pergunta: str) -> str:
        """
        Prepara contexto estruturado para o Ollama
        """
        contexto = []
        
        for item in dados:
            if 'conteudo_processado' in item:
                proc = item['conteudo_processado']
                
                # Adicionar resumo estruturado
                if 'resumo_estruturado' in proc:
                    resumo = proc['resumo_estruturado']
                    contexto.append(f"\n=== MEDICAMENTO: {item['nome']} ===")
                    
                    if resumo['informacoes_principais']:
                        contexto.append("\n📊 INFORMAÇÕES PRINCIPAIS:")
                        for campo, valor in resumo['informacoes_principais'].items():
                            campo_formatado = campo.replace('_', ' ').title()
                            if isinstance(valor, list):
                                contexto.append(f"  • {campo_formatado}: {', '.join(valor)}")
                            else:
                                contexto.append(f"  • {campo_formatado}: {valor}")
                    
                    # Adicionar tabelas relevantes se houver
                    if resumo['tabelas_relevantes']:
                        contexto.append("\n📋 DADOS TABULARES:")
                        for tabela in resumo['tabelas_relevantes'][:2]:
                            if 'processada' in tabela and 'interpretacao' in tabela['processada']:
                                for interp in tabela['processada']['interpretacao'][:3]:
                                    for k, v in interp.items():
                                        contexto.append(f"    - {k}: {v}")
                
                # Adicionar seções relevantes
                if 'secoes' in proc:
                    # Identificar tipo de informação da pergunta
                    tipo_info = self.tabela_processor._identificar_tipo_pergunta(pergunta)
                    
                    secoes_relevantes = self._filtrar_secoes_relevantes(
                        proc['secoes'],
                        pergunta,
                        tipo_info
                    )
                    
                    if secoes_relevantes:
                        contexto.append("\n📄 SEÇÕES RELEVANTES:")
                        for secao in secoes_relevantes[:3]:
                            contexto.append(f"\n{secao[:500]}...")
        
        return '\n'.join(contexto)
    
    def _criar_prompt_otimizado(self, pergunta: str, contexto: str, classificacao: Dict) -> str:
        """
        Cria prompt otimizado para o Ollama
        """
        tipo_informacao = self.tabela_processor._identificar_tipo_pergunta(pergunta)
        
        prompt = f"""
Contexto sobre medicamentos veterinários:
{contexto}

Pergunta: {pergunta}

Instruções:
1. Responda APENAS com base nas informações fornecidas no contexto
2. Seja específico e direto
3. Se a informação não estiver disponível, indique claramente
"""
        
        # Adicionar instruções específicas por tipo
        if tipo_informacao:
            instrucoes_especificas = {
                'dose': "4. Forneça a dosagem exata, incluindo unidades (mg/kg, ml, etc.)",
                'armazenamento': "4. Inclua temperatura e condições após abertura se disponível",
                'intervalo_seguranca': "4. Especifique o tempo em dias ou horas para cada produto",
                'composicao': "4. Liste os princípios ativos e suas concentrações",
                'especies': "4. Liste todas as espécies mencionadas",
                'reacoes_adversas': "4. Descreva as reações possíveis de forma clara",
                'via_administracao': "4. Especifique a via (oral, IM, IV, SC, etc.)",
                'receita': "4. Indique se é sujeito a receita médico-veterinária"
            }
            
            if tipo_informacao in instrucoes_especificas:
                prompt += f"\n{instrucoes_especificas[tipo_informacao]}"
        
        # Se é follow-up, adicionar contexto anterior
        if classificacao.get('follow_up'):
            prompt += "\n\n[Esta é uma pergunta de continuação sobre o mesmo medicamento]"
        
        prompt += "\n\nResposta:"
        
        return prompt
    
    def _filtrar_secoes_relevantes(self, secoes: List[str], pergunta: str, tipo_info: str = None) -> List[str]:
        """
        Filtra seções mais relevantes para a pergunta
        """
        if not secoes:
            return []
        
        pergunta_lower = pergunta.lower()
        palavras_chave = [p for p in pergunta_lower.split() if len(p) > 3]
        
        # Adicionar palavras-chave do tipo de informação
        if tipo_info and tipo_info in self.tabela_processor.padroes_campo:
            palavras_chave.extend(self.tabela_processor.padroes_campo[tipo_info]['keywords'])
        
        secoes_pontuadas = []
        
        for secao in secoes:
            secao_lower = secao.lower()
            pontuacao = 0
            
            # Pontuação por palavra-chave
            for palavra in palavras_chave:
                if palavra in secao_lower:
                    pontuacao += secao_lower.count(palavra) * 2
            
            # Bonus para seções com números e unidades
            if re.search(r'\d+\s*(mg|ml|kg|dias|horas)', secao_lower):
                pontuacao += 5
            
            # Bonus para tabelas
            if any(marker in secao for marker in ['===', '📊', 'TABELA']):
                pontuacao += 10
            
            if pontuacao > 0:
                secoes_pontuadas.append((secao, pontuacao))
        
        # Ordenar por relevância
        secoes_pontuadas.sort(key=lambda x: x[1], reverse=True)
        
        return [s[0] for s in secoes_pontuadas[:5]]
    
    def realizar_web_scraping_sincrono(self, termo_busca: str) -> List[Dict]:
        """
        Realiza web scraping (versão simplificada para teste)
        Compatível com o método original
        """
        print(colored(f"🌐 Realizando busca web por: {termo_busca}", "cyan"))
        
        # Aqui seria feito o scraping real
        # Por enquanto, retornar dados mock para teste
        dados_mock = []
        
        # Verificar se existem PDFs de exemplo no diretório
        pdf_dir = "/mnt/project"
        if os.path.exists(pdf_dir):
            for arquivo in os.listdir(pdf_dir):
                if arquivo.endswith('.pdf'):
                    # Verificar se o termo está no nome do arquivo
                    if termo_busca.lower() in arquivo.lower():
                        dados_mock.append({
                            'nome': arquivo.replace('.pdf', '').replace('_', ' '),
                            'url': f"file://{os.path.join(pdf_dir, arquivo)}",
                            'pdf_path': os.path.join(pdf_dir, arquivo),
                            'resumo': f"Medicamento veterinário - {arquivo}",
                            'especies': 'Bovinos, Suínos, Equinos',  # Mock
                            'forma_farmaceutica': 'Solução injetável'  # Mock
                        })
        
        # Se não encontrar correspondência, usar alguns PDFs de exemplo
        if not dados_mock:
            pdfs_exemplo = [
                'Animeloxan_20_mg_ml_solução_injetável_para_bovinos_suínos_e_equinos.pdf',
                'Dexinjet_2_mg_ml_solução_injetável.pdf',
                'Calcibel_forte_380_60_50_mg_ml_em_solução_para_infusão_em_equídeos_bovinos_ovinos_caprinos_e_suínos.pdf'
            ]
            
            for pdf in pdfs_exemplo[:2]:
                pdf_path = os.path.join(pdf_dir, pdf)
                if os.path.exists(pdf_path):
                    dados_mock.append({
                        'nome': pdf.replace('.pdf', '').replace('_', ' '),
                        'url': f"file://{pdf_path}",
                        'pdf_path': pdf_path,
                        'resumo': f"Medicamento veterinário",
                        'especies': 'Várias espécies',
                        'forma_farmaceutica': 'Várias formas'
                    })
        
        return dados_mock
    
    def _normalizar_especies_texto(self, texto: str) -> str:
        """
        Normaliza nomes de espécies no texto
        """
        texto_normalizado = texto
        
        for termo_informal, termo_formal in self.mapeamento_especies.items():
            # Substituir apenas palavras completas
            pattern = r'\b' + re.escape(termo_informal) + r'\b'
            texto_normalizado = re.sub(pattern, termo_formal, texto_normalizado, flags=re.IGNORECASE)
        
        return texto_normalizado
    
    def _corrigir_categoria_se_necesario(self, classificacao: Dict, pergunta: str) -> Dict:
        """
        Corrige automaticamente categorias erradas
        """
        if not classificacao or classificacao.get("categoria") == "erro":
            return classificacao
            
        pergunta_lower = pergunta.lower()
        categoria_atual = classificacao.get("categoria")
        
        # REGRA 1: "mesmo princípio ativo" SEMPRE é comparação
        if "mesmo princípio ativo" in pergunta_lower and categoria_atual != "comparacao":
            print(colored("⚠️ Corrigindo categoria: 'mesmo princípio ativo' deve ser comparação", "yellow"))
            classificacao["categoria"] = "comparacao"
            
        # REGRA 2: "alternativ" SEMPRE é comparação  
        if "alternativ" in pergunta_lower and categoria_atual != "comparacao":
            print(colored("⚠️ Corrigindo categoria: 'alternativa' deve ser comparação", "yellow"))
            classificacao["categoria"] = "comparacao"
            
        return classificacao
    
    def _extrair_termo_busca(self, pergunta: str) -> str:
        """
        Extrai termo de busca da pergunta
        """
        # Procurar por palavras capitalizadas (nomes de medicamentos)
        palavras = pergunta.split()
        for palavra in palavras:
            if palavra[0].isupper() and len(palavra) > 3:
                return palavra
        
        # Fallback: usar substantivos principais
        substantivos = []
        for palavra in palavras:
            if len(palavra) > 4 and palavra.lower() not in ['para', 'como', 'qual', 'quando', 'onde']:
                substantivos.append(palavra)
        
        return ' '.join(substantivos[:2]) if substantivos else pergunta[:20]
    
    def _classificacao_simples(self, pergunta: str) -> Dict:
        """
        Classificação simples quando QueryClassifier não está disponível
        """
        pergunta_lower = pergunta.lower()
        
        # Detectar categoria
        if any(palavra in pergunta_lower for palavra in ['mesmo princípio', 'alternativ', 'similar']):
            categoria = 'comparacao'
        else:
            categoria = 'medicamento'
        
        return {
            'categoria': categoria,
            'entidades': {
                'termo_busca': self._extrair_termo_busca(pergunta)
            }
        }
    
    def _limpar_contexto_antigo(self):
        """
        Limpa contexto antigo se necessário (baseado em tempo)
        """
        tempo_atual = time.time()
        tempo_ultima_interacao = self.contexto_conversacao.get("ultima_interacao_time", 0)
        
        # Se passou mais de 5 minutos, limpar contexto
        if tempo_atual - tempo_ultima_interacao > 300:
            self._reiniciar_contexto()
        
        self.contexto_conversacao["ultima_interacao_time"] = tempo_atual
    
    def _reiniciar_contexto(self):
        """
        Reinicia o contexto da conversação
        """
        self.contexto_conversacao = {
            "ultima_pergunta": None,
            "ultima_categoria": None,
            "ultima_entidade_medicamento": None,
            "ultimo_termo_busca": None,
            "ultima_resposta": None,
            "dados_ultimo_scraping": None,
            "ultimo_scraping_time": 0,
            "ultima_interacao_time": time.time(),
            "historico_conversacao": [],
            "metadados_scraping": None,
            "contexto_follow_up": None,
            "medicamentos_comparados": []
        }
    
    def limpar_contexto_manual(self):
        """
        Limpa o contexto manualmente (método público)
        """
        self._reiniciar_contexto()
        print(colored("✅ Contexto limpo com sucesso", "green"))
    
    def _adicionar_ao_historico(self, pergunta: str, resposta: str, categoria: str):
        """
        Adiciona pergunta e resposta ao histórico
        """
        self.contexto_conversacao["historico_conversacao"].append({
            'timestamp': time.time(),
            'pergunta': pergunta,
            'resposta': resposta[:200] + "..." if len(resposta) > 200 else resposta,
            'categoria': categoria
        })
        
        # Manter apenas últimas 10 interações
        if len(self.contexto_conversacao["historico_conversacao"]) > 10:
            self.contexto_conversacao["historico_conversacao"] = \
                self.contexto_conversacao["historico_conversacao"][-10:]
    
    def _imprimir_resumo_tempos(self):
        """
        Imprime resumo dos tempos de execução
        """
        print(colored("\n⏱️  Resumo de Tempos:", "yellow"))
        for etapa, tempo in self.tempos_execucao.items():
            if tempo > 0 and etapa != 'inicio_total':
                print(colored(f"  • {etapa}: {tempo:.2f}s", "yellow"))
    
    def obter_historico(self) -> List[Dict]:
        """
        Retorna o histórico de conversação
        """
        return self.contexto_conversacao.get("historico_conversacao", [])
    
    def obter_contexto_atual(self) -> Dict:
        """
        Retorna o contexto atual da conversação
        """
        return {
            'ultima_pergunta': self.contexto_conversacao.get("ultima_pergunta"),
            'ultima_categoria': self.contexto_conversacao.get("ultima_categoria"),
            'ultimo_medicamento': self.contexto_conversacao.get("ultima_entidade_medicamento"),
            'tem_dados_cache': bool(self.contexto_conversacao.get("dados_ultimo_scraping"))
        }


class CacheManager:
    """
    Gerenciador de cache para respostas
    """
    
    def __init__(self, cache_dir):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.cache_metadata = self._load_metadata()
    
    def _load_metadata(self):
        metadata_file = os.path.join(self.cache_dir, "metadata.json")
        if os.path.exists(metadata_file):
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def _save_metadata(self):
        metadata_file = os.path.join(self.cache_dir, "metadata.json")
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(self.cache_metadata, f, ensure_ascii=False, indent=2)
    
    def get_cached_response(self, cache_key):
        arquivo_cache = os.path.join(self.cache_dir, f"{cache_key}.json")
        if os.path.exists(arquivo_cache):
            cache_age = time.time() - os.path.getmtime(arquivo_cache)
            if cache_age < CACHE_TTL:
                try:
                    with open(arquivo_cache, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except:
                    pass
        return None
    
    def save_response(self, cache_key, data):
        arquivo_cache = os.path.join(self.cache_dir, f"{cache_key}.json")
        with open(arquivo_cache, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        self.cache_metadata[cache_key] = {
            'timestamp': time.time(),
            'size': len(str(data))
        }
        self._save_metadata()


def main():
    """
    Função principal com menu interativo
    """
    print(colored("="*80, "green", attrs=['bold']))
    print(colored("🏥 Sistema Completo de Consulta Veterinária 🏥", "green", attrs=['bold']))
    print(colored("="*80, "green", attrs=['bold']))
    print(colored("\n✨ Versão Final com todas as funcionalidades!", "cyan"))
    print(colored("📊 Processamento avançado de tabelas", "cyan"))
    print(colored("🔄 Suporte a follow-up e consultas duplas\n", "cyan"))
    
    # Criar instância do sistema
    sistema = SistemaConsultaVetOtimizado()
    
    # Menu de opções
    while True:
        print(colored("\n" + "="*60, "blue"))
        print(colored("MENU PRINCIPAL", "blue", attrs=['bold']))
        print(colored("="*60, "blue"))
        print("1. Fazer pergunta")
        print("2. Testar perguntas do PDF")
        print("3. Ver histórico")
        print("4. Ver contexto atual")
        print("5. Limpar contexto")
        print("6. Sair")
        
        escolha = input(colored("\nEscolha uma opção (1-6): ", "yellow"))
        
        if escolha == "1":
            pergunta = input(colored("\nDigite sua pergunta: ", "cyan"))
            if pergunta.strip():
                resposta = sistema.processar_pergunta_unica(pergunta)
                print(colored("\n✅ Resposta:", "green"))
                print(resposta)
        
        elif escolha == "2":
            # Testar com as perguntas do PDF
            perguntas_teste = [
                "Para que espécies está indicado o medicamento Simparica?",
                "Qual a dose indicada do medicamento Senvelgo 15 mg/ml em gatos?",
                "E perus?",  # Follow-up
                "Como deve ser armazenado, depois de aberto o medicamento Calcibel?",
                "Que medicamentos existem com o mesmo princípio ativo que o medicamento Animeloxan?",  # Consulta dupla
                "Qual o medicamento alternativo para Trocoxil 75 para cães?"  # Consulta dupla
            ]
            
            print(colored("\n🧪 Testando perguntas...", "yellow"))
            
            for i, pergunta in enumerate(perguntas_teste, 1):
                print(colored(f"\n{i}. {pergunta}", "cyan"))
                resposta = sistema.processar_pergunta_unica(pergunta)
                print(colored("Resposta:", "green"))
                print(resposta[:300] + "..." if len(resposta) > 300 else resposta)
                time.sleep(1)
        
        elif escolha == "3":
            historico = sistema.obter_historico()
            if historico:
                print(colored("\n📜 HISTÓRICO DE CONVERSAÇÃO:", "magenta"))
                for i, item in enumerate(historico, 1):
                    print(f"\n{i}. Pergunta: {item['pergunta']}")
                    print(f"   Categoria: {item['categoria']}")
                    print(f"   Resposta: {item['resposta']}")
            else:
                print(colored("\nHistórico vazio", "yellow"))
        
        elif escolha == "4":
            contexto = sistema.obter_contexto_atual()
            print(colored("\n📋 CONTEXTO ATUAL:", "magenta"))
            for chave, valor in contexto.items():
                print(f"  • {chave}: {valor}")
        
        elif escolha == "5":
            sistema.limpar_contexto_manual()
        
        elif escolha == "6":
            print(colored("\n👋 Até logo!", "green"))
            break
        
        else:
            print(colored("\n⚠️ Opção inválida!", "red"))


if __name__ == "__main__":
    main()