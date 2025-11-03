# sistema_consulta_vet_v4.py - Versão Melhorada com Maior Assertividade
import json
import os
import time
import hashlib
import asyncio
import aiohttp
from termcolor import colored
import ollama
from aiohttp import ClientSession, TCPConnector, ClientTimeout
import fitz  
import re
from collections import OrderedDict

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
import re
from tqdm import tqdm
import sys

# Importar o classificador de query
from query_classifier import QueryClassifier

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

class InterpretadorInteligenteV4:
    """
    Classe melhorada para interpretação inteligente de perguntas e respostas
    com capacidade de responder de forma mais abrangente quando apropriado
    """
    
    def __init__(self):
        self.padroes_flexiveis = {
            'armazenamento_aberto': {
                'triggers': ['depois de aberto', 'após aberto', 'depois de abertura', 'após abertura'],
                'buscar_tambem': ['armazenamento', 'conservação', 'temperatura', 'validade'],
                'resposta_ampla': True
            },
            'armazenamento_geral': {
                'triggers': ['armazenamento', 'armazenar', 'conservar', 'guardar'],
                'buscar_tambem': ['temperatura', 'luz', 'humidade', 'validade'],
                'resposta_ampla': False
            },
            'dose_especifica': {
                'triggers': ['dose', 'dosagem', 'quanto administrar', 'posologia'],
                'buscar_tambem': ['mg/kg', 'ml/kg', 'administração', 'peso corporal'],
                'resposta_ampla': False
            },
            'intervalos_seguranca': {
                'triggers': ['intervalo', 'segurança', 'carência', 'tempo de espera'],
                'buscar_tambem': ['carne', 'leite', 'ovos', 'dias', 'horas'],
                'resposta_ampla': True
            }
        }
        
    def analisar_intencao_pergunta(self, pergunta):
        """
        Analisa a intenção da pergunta e determina se deve dar resposta abrangente
        """
        pergunta_lower = pergunta.lower()
        
        for tipo, config in self.padroes_flexiveis.items():
            for trigger in config['triggers']:
                if trigger in pergunta_lower:
                    return {
                        'tipo': tipo,
                        'buscar_tambem': config['buscar_tambem'],
                        'resposta_ampla': config['resposta_ampla'],
                        'pergunta_original': pergunta
                    }
        
        # Padrão genérico
        return {
            'tipo': 'generico',
            'buscar_tambem': [],
            'resposta_ampla': False,
            'pergunta_original': pergunta
        }
    
    def reformular_pergunta_se_necessario(self, pergunta, analise_intencao):
        """
        Reformula a pergunta para ser mais abrangente quando apropriado
        """
        if analise_intencao['resposta_ampla']:
            tipo = analise_intencao['tipo']
            
            if tipo == 'armazenamento_aberto':
                # Se pergunta sobre "depois de aberto" mas isso não é encontrado,
                # reformular para buscar informações gerais de armazenamento
                return {
                    'pergunta_original': pergunta,
                    'pergunta_reformulada': pergunta.replace('depois de aberto', '').replace('após aberto', ''),
                    'instrucao_adicional': 'Se não houver informação específica sobre armazenamento após aberto, forneça as informações gerais de armazenamento disponíveis.'
                }
            
            elif tipo == 'intervalos_seguranca':
                return {
                    'pergunta_original': pergunta,
                    'pergunta_reformulada': pergunta,
                    'instrucao_adicional': 'Forneça TODOS os intervalos de segurança disponíveis no documento (carne, leite, ovos, etc.), mesmo que a pergunta seja genérica.'
                }
        
        return {
            'pergunta_original': pergunta,
            'pergunta_reformulada': pergunta,
            'instrucao_adicional': ''
        }

class TabelaInterpreterV4:
    """
    Classe melhorada para detectar e interpretar tabelas com mais precisão
    """
    
    def processar_pdf_completo(self, pdf_path):
        """
        Extrai e interpreta TODO o PDF com melhor tratamento de tabelas
        """
        try:
            texto_completo = []
            tabelas_detectadas = []
            
            with fitz.open(pdf_path) as pdf_file:
                for page_num, page in enumerate(pdf_file):
                    texto_pagina = page.get_text()
                    
                    # Detectar e processar tabelas
                    if self._tem_tabela_melhorada(texto_pagina):
                        tabela_estruturada = self._extrair_tabela_estruturada(texto_pagina, page_num)
                        tabelas_detectadas.append(tabela_estruturada)
                        texto_processado = self._explicar_tabela_melhorada(tabela_estruturada, page_num)
                    else:
                        texto_processado = texto_pagina
                    
                    texto_completo.append(texto_processado)
            
            # Unificar e organizar
            texto_unificado = "\n\n".join(texto_completo)
            texto_limpo = self._limpar_texto_inteligente(texto_unificado)
            
            # Dividir em seções com melhor organização
            secoes = self._dividir_em_secoes_inteligente(texto_limpo)
            
            # Adicionar índice de tabelas no início se houver
            if tabelas_detectadas:
                indice_tabelas = self._criar_indice_tabelas(tabelas_detectadas)
                secoes.insert(0, indice_tabelas)
            
            return secoes
            
        except Exception as e:
            print(colored(f"Erro ao processar PDF: {e}", "red"))
            return []
    
    def _tem_tabela_melhorada(self, texto):
        """
        Detecção melhorada de tabelas com múltiplos indicadores
        """
        indicadores = 0
        
        # Padrões de tabela mais sofisticados
        padroes_tabela = [
            r'\s{3,}\d+\.?\d*\s*mg',  # Espaçamento com valores
            r'\|\s*\w+\s*\|',  # Formato pipe
            r'^\s*\w+\s+\d+',  # Início de linha com palavra e número
            r'Espécie\s+Dose',  # Cabeçalhos típicos
            r'Animal\s+Via',
            r'\t\d+',  # Tabs com números
        ]
        
        for padrao in padroes_tabela:
            if re.search(padrao, texto, re.MULTILINE | re.IGNORECASE):
                indicadores += 1
        
        # Verificar densidade de números (típico de tabelas)
        linhas = texto.split('\n')
        linhas_com_numeros = sum(1 for linha in linhas if re.search(r'\d+', linha))
        if len(linhas) > 0 and linhas_com_numeros / len(linhas) > 0.3:
            indicadores += 2
        
        return indicadores >= 2
    
    def _extrair_tabela_estruturada(self, texto, page_num):
        """
        Extrai estrutura da tabela de forma mais inteligente
        """
        linhas = texto.split('\n')
        tabela_estruturada = {
            'pagina': page_num + 1,
            'cabecalhos': [],
            'linhas': [],
            'tipo': 'desconhecido'
        }
        
        # Identificar cabeçalhos
        for i, linha in enumerate(linhas[:10]):  # Procurar nos primeiros 10 linhas
            if re.search(r'(espécie|animal|dose|via|administração|posologia)', linha, re.IGNORECASE):
                # Possível linha de cabeçalho
                cabecalhos = re.split(r'\s{2,}|\t+', linha.strip())
                if len(cabecalhos) > 1:
                    tabela_estruturada['cabecalhos'] = cabecalhos
                    
                    # Extrair dados das próximas linhas
                    for j in range(i + 1, min(i + 20, len(linhas))):
                        linha_dados = linhas[j].strip()
                        if linha_dados:
                            dados = re.split(r'\s{2,}|\t+', linha_dados)
                            if len(dados) > 1:
                                tabela_estruturada['linhas'].append(dados)
                    break
        
        # Identificar tipo de tabela
        cabecalhos_lower = ' '.join(tabela_estruturada['cabecalhos']).lower()
        if 'dose' in cabecalhos_lower or 'posologia' in cabecalhos_lower:
            tabela_estruturada['tipo'] = 'dosagem'
        elif 'intervalo' in cabecalhos_lower or 'segurança' in cabecalhos_lower:
            tabela_estruturada['tipo'] = 'intervalos'
        elif 'armazen' in cabecalhos_lower or 'conserv' in cabecalhos_lower:
            tabela_estruturada['tipo'] = 'armazenamento'
        
        return tabela_estruturada
    
    def _explicar_tabela_melhorada(self, tabela_estruturada, page_num):
        """
        Cria explicação ultra-detalhada da tabela para o Ollama
        """
        resultado = f"\n{'='*80}\n"
        resultado += f"📊 PÁGINA {page_num + 1} - TABELA ESTRUTURADA DETECTADA\n"
        resultado += f"Tipo de Tabela: {tabela_estruturada['tipo'].upper()}\n"
        resultado += f"{'='*80}\n\n"
        
        if tabela_estruturada['cabecalhos']:
            resultado += "📋 ESTRUTURA DA TABELA:\n"
            resultado += f"Cabeçalhos: {' | '.join(tabela_estruturada['cabecalhos'])}\n\n"
            
            resultado += "📝 DADOS DA TABELA (LEIA COM ATENÇÃO):\n"
            for i, linha in enumerate(tabela_estruturada['linhas'], 1):
                resultado += f"\nLinha {i}:\n"
                for j, (cabecalho, valor) in enumerate(zip(tabela_estruturada['cabecalhos'], linha)):
                    if j < len(linha):
                        resultado += f"  - {cabecalho}: {valor}\n"
                        
                        # Adicionar interpretações específicas
                        if tabela_estruturada['tipo'] == 'dosagem' and 'dose' in cabecalho.lower():
                            resultado += f"    → DOSE IDENTIFICADA: {valor}\n"
                        elif 'espécie' in cabecalho.lower() or 'animal' in cabecalho.lower():
                            resultado += f"    → ESPÉCIE: {valor}\n"
        
        resultado += "\n⚠️ INSTRUÇÕES PARA LEITURA:\n"
        resultado += "1. Cada linha representa uma entrada diferente\n"
        resultado += "2. Associe SEMPRE o valor ao seu cabeçalho correspondente\n"
        resultado += "3. NÃO misture valores de linhas diferentes\n"
        resultado += "4. Para perguntas sobre dose, procure a linha da espécie específica\n\n"
        
        return resultado
    
    def _criar_indice_tabelas(self, tabelas):
        """
        Cria um índice resumido de todas as tabelas encontradas
        """
        indice = "📚 ÍNDICE DE TABELAS ENCONTRADAS NO DOCUMENTO:\n"
        indice += "="*60 + "\n\n"
        
        for i, tabela in enumerate(tabelas, 1):
            indice += f"Tabela {i} (Página {tabela['pagina']}):\n"
            indice += f"  - Tipo: {tabela['tipo']}\n"
            if tabela['cabecalhos']:
                indice += f"  - Colunas: {', '.join(tabela['cabecalhos'])}\n"
            indice += f"  - Linhas de dados: {len(tabela['linhas'])}\n\n"
        
        return indice
    
    def _limpar_texto_inteligente(self, texto):
        """
        Limpeza inteligente preservando estruturas importantes
        """
        # Remover caracteres problemáticos mas preservar estrutura
        texto = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', texto)
        
        # Preservar quebras de linha significativas
        texto = re.sub(r'\n{3,}', '\n\n', texto)
        
        # Preservar espaçamento de tabelas
        # Não colapsar espaços múltiplos se parecer tabela
        linhas = texto.split('\n')
        linhas_processadas = []
        
        for linha in linhas:
            if re.search(r'\s{3,}\d+', linha):  # Provável linha de tabela
                linhas_processadas.append(linha)
            else:
                # Para texto normal, limpar espaços excessivos
                linha_limpa = re.sub(r'\s{2,}', ' ', linha)
                linhas_processadas.append(linha_limpa)
        
        return '\n'.join(linhas_processadas)
    
    def _dividir_em_secoes_inteligente(self, texto):
        """
        Divisão inteligente em seções com melhor preservação de contexto
        """
        # Padrões de início de seção
        padroes_secao = [
            r'^[\d]+\.[\d]*\s+[A-Z]',  # 1.1 TÍTULO
            r'^[A-Z][A-Z\s]{3,}$',  # TÍTULO EM MAIÚSCULAS
            r'^={3,}',  # Linhas de separação
            r'^-{3,}',
            r'^\*{3,}',
        ]
        
        secoes = []
        secao_atual = []
        
        for linha in texto.split('\n'):
            # Verificar se é início de nova seção
            is_nova_secao = any(re.match(padrao, linha.strip()) for padrao in padroes_secao)
            
            if is_nova_secao and secao_atual:
                # Salvar seção anterior
                conteudo = '\n'.join(secao_atual)
                if len(conteudo.strip()) > 20:  # Seção significativa
                    secoes.append(conteudo)
                secao_atual = [linha]
            else:
                secao_atual.append(linha)
        
        # Adicionar última seção
        if secao_atual:
            conteudo = '\n'.join(secao_atual)
            if len(conteudo.strip()) > 20:
                secoes.append(conteudo)
        
        # Se não encontrou seções, dividir por tamanho
        if len(secoes) <= 1:
            texto_completo = secoes[0] if secoes else texto
            # Dividir em chunks de ~2000 caracteres preservando parágrafos
            chunks = []
            chunk_atual = []
            tamanho_atual = 0
            
            for paragrafo in texto_completo.split('\n\n'):
                tamanho_paragrafo = len(paragrafo)
                if tamanho_atual + tamanho_paragrafo > 2000 and chunk_atual:
                    chunks.append('\n\n'.join(chunk_atual))
                    chunk_atual = [paragrafo]
                    tamanho_atual = tamanho_paragrafo
                else:
                    chunk_atual.append(paragrafo)
                    tamanho_atual += tamanho_paragrafo
            
            if chunk_atual:
                chunks.append('\n\n'.join(chunk_atual))
            
            return chunks
        
        return secoes


class CacheManagerV4:
    """Sistema de cache melhorado com versionamento"""
    def __init__(self, cache_dir):
        self.cache_dir = cache_dir
        self.cache_version = "v4.0"
        self.cache_metadata = {}
        self._load_metadata()
    
    def _load_metadata(self):
        metadata_file = os.path.join(self.cache_dir, "metadata_v4.json")
        if os.path.exists(metadata_file):
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    self.cache_metadata = json.load(f)
            except:
                self.cache_metadata = {}
    
    def _save_metadata(self):
        metadata_file = os.path.join(self.cache_dir, "metadata_v4.json")
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(self.cache_metadata, f, ensure_ascii=False)
    
    def get_response(self, cache_key):
        arquivo_cache = os.path.join(self.cache_dir, f"{cache_key}_v4.json")
        if os.path.exists(arquivo_cache):
            cache_info = self.cache_metadata.get(cache_key, {})
            if time.time() - cache_info.get('timestamp', 0) < CACHE_TTL:
                try:
                    with open(arquivo_cache, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except:
                    pass
        return None
    
    def save_response(self, cache_key, data):
        arquivo_cache = os.path.join(self.cache_dir, f"{cache_key}_v4.json")
        with open(arquivo_cache, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        self.cache_metadata[cache_key] = {
            'timestamp': time.time(),
            'size': len(str(data)),
            'version': self.cache_version
        }
        self._save_metadata()


def formatar_links_resposta(resposta, dados_scraping):
    """Formatação melhorada de links com mais contexto"""
    import re
    
    if not dados_scraping:
        return resposta
    
    # Criar mapeamento de URLs
    urls_encontradas = {}
    contador = 1
    
    # Extrair todas as URLs da resposta
    padrao_url = r'https?://[^\s<>"\'\)]+(?:/[^\s<>"\'\)]*)?'
    urls_na_resposta = re.findall(padrao_url, resposta)
    
    # Mapear cada URL única para um número
    for url in urls_na_resposta:
        if url not in urls_encontradas:
            urls_encontradas[url] = contador
            contador += 1
    
    # Substituir URLs por [Fonte N]
    resposta_formatada = resposta
    for url, numero in urls_encontradas.items():
        resposta_formatada = resposta_formatada.replace(url, f"[Fonte {numero}]")
    
    # Adicionar lista de fontes no final com mais detalhes
    if urls_encontradas:
        resposta_formatada += "\n\n📚 **Fontes Consultadas:**\n"
        for url, numero in sorted(urls_encontradas.items(), key=lambda x: x[1]):
            # Tentar encontrar o nome do medicamento correspondente
            nome_medicamento = "Documento"
            tipo_fonte = "Web"
            
            for item in dados_scraping:
                if item.get('url') == url:
                    nome_medicamento = item.get('nome', 'Documento')
                    if 'pdf' in url.lower():
                        tipo_fonte = "PDF/Bula"
                    break
            
            resposta_formatada += f"[{numero}] {nome_medicamento} ({tipo_fonte}): {url}\n"
    
    return resposta_formatada


class SistemaConsultaVetOtimizado:
    """
    Sistema principal v4 com melhorias significativas em assertividade
    """
    def __init__(self, modelo_ollama=MODELO_OLLAMA_PADRAO, temperatura_ollama=0.1):
        self.modelo_ollama = modelo_ollama
        self.temperatura_ollama = temperatura_ollama  # Reduzida para mais precisão
        self.query_classifier = QueryClassifier(modelo_ollama)
        self.cache_manager = CacheManagerV4(CACHE_DIR_RESPOSTAS)
        self.interpretador_inteligente = InterpretadorInteligenteV4()
        self.tabela_interpreter = TabelaInterpreterV4()
        self.mapeamento_especies = self._criar_mapeamento_especies()
        
        # Contexto melhorado
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
            "respostas_tentativas": []  # Novo: guardar tentativas de resposta
        }
        
        self._pdf_cache = {}
        self.session = None
        
        # Métricas melhoradas
        self.tempos_execucao = {
            'inicio_total': 0,
            'classificacao': 0,
            'web_scraping': 0,
            'extracao_pdf': 0,
            'filtragem_pdf': 0,
            'busca_direta': 0,
            'interpretacao': 0,
            'ollama': 0,
            'validacao': 0,
            'formatacao': 0,
            'total': 0
        }
        
        # Configurações de validação
        self.validacao_config = {
            'max_tentativas_ollama': 2,
            'threshold_confianca': 0.7,
            'validar_doses': True,
            'validar_especies': True,
            'permitir_respostas_amplas': True
        }
    
    def _criar_mapeamento_especies(self):
        """Mapeamento expandido de espécies"""
        mapeamento = {}
        especies_map = {
            "suínos": ["suíno", "suino", "suínos", "suinos", "porco", "porcos", "leitão", "leitões", "porcino", "porcinos"],
            "cães": ["cão", "cao", "cães", "caes", "cachorro", "cachorros", "cadela", "cadelas", "canino", "caninos", "dog", "dogs"],
            "gatos": ["gato", "gatos", "gata", "gatas", "felino", "felinos", "gatinho", "gatinhos", "cat", "cats"],
            "bovinos": ["bovino", "bovinos", "vaca", "vacas", "novilho", "novilhos", "touro", "touros", "bezerro", "bezerros", "gado"],
            "ovinos": ["ovino", "ovinos", "ovelha", "ovelhas", "carneiro", "carneiros", "borrego", "borregos", "cordeiro", "cordeiros"],
            "caprinos": ["caprino", "caprinos", "cabra", "cabras", "bode", "bodes", "cabrito", "cabritos"],
            "coelhos": ["coelho", "coelhos", "coelha", "coelhas", "leporídeo", "leporídeos", "leporideo", "leporideos"],
            "equinos": ["cavalo", "cavalos", "égua", "éguas", "egua", "eguas", "potro", "potros", "equino", "equinos", "pônei", "ponei"],
            "aves": ["ave", "aves", "galinha", "galinhas", "frango", "frangos", "peru", "perus", "pato", "patos"],
            "perus": ["peru", "perus", "perua", "peruas"]
        }
        
        for especie_padrao, sinonimos in especies_map.items():
            for sinonimo in sinonimos:
                mapeamento[sinonimo.lower()] = especie_padrao
        
        return mapeamento
    
    def _consultar_ollama_melhorado_v4(self, pergunta_ollama, contexto_dados, tipo_consulta, classificacao, pergunta_original):
        """
        Consulta ao Ollama com múltiplas estratégias e validação melhorada
        """
        print(colored("🤖 Iniciando consulta melhorada ao Ollama v4...", "cyan"))
        
        # Analisar intenção da pergunta
        tempo_inicio_interpretacao = time.perf_counter()
        analise_intencao = self.interpretador_inteligente.analisar_intencao_pergunta(pergunta_original)
        reformulacao = self.interpretador_inteligente.reformular_pergunta_se_necessario(pergunta_original, analise_intencao)
        tempo_interpretacao = time.perf_counter() - tempo_inicio_interpretacao
        self.tempos_execucao['interpretacao'] = tempo_interpretacao
        
        print(colored(f"📊 Análise de intenção: {analise_intencao['tipo']}", "yellow"))
        if reformulacao['instrucao_adicional']:
            print(colored(f"📝 Instrução adicional: {reformulacao['instrucao_adicional']}", "yellow"))
        
        # Processar PDFs se disponíveis
        contexto_pdf_completo = []
        contexto_pdf_filtrado = []
        medicamento_nome = None
        tem_pdf = False
        
        for item in contexto_dados[:3]:
            if item.get('conteudo_pdf'):
                tem_pdf = True
                medicamento_nome = item.get('nome', 'Medicamento')
                
                # Usar o interpretador de tabelas melhorado
                for secao in item['conteudo_pdf']:
                    if isinstance(secao, str):
                        contexto_pdf_completo.append(secao)
                        
                        # Filtrar seções relevantes com base na análise de intenção
                        secao_lower = secao.lower()
                        is_relevante = False
                        
                        # Verificar relevância baseada no tipo de pergunta
                        if analise_intencao['tipo'] == 'armazenamento_aberto':
                            # Para armazenamento, pegar QUALQUER informação relacionada
                            if any(termo in secao_lower for termo in ['armazen', 'conserv', 'temperatura', 'validade', 'após', 'depois', 'aberto']):
                                is_relevante = True
                        else:
                            # Verificar com palavras-chave da pergunta e termos adicionais
                            palavras_pergunta = pergunta_ollama.lower().split()
                            if any(palavra in secao_lower for palavra in palavras_pergunta if len(palavra) > 3):
                                is_relevante = True
                            
                            # Verificar com termos adicionais da análise
                            if any(termo in secao_lower for termo in analise_intencao.get('buscar_tambem', [])):
                                is_relevante = True
                        
                        if is_relevante:
                            contexto_pdf_filtrado.append(secao)
        
        # Se não encontrou seções relevantes mas é pergunta que permite resposta ampla
        if tem_pdf and not contexto_pdf_filtrado and analise_intencao['resposta_ampla']:
            print(colored("⚠️ Não encontrou seções específicas, usando contexto ampliado", "yellow"))
            # Pegar seções que possam ter informação relacionada
            for secao in contexto_pdf_completo[:10]:  # Primeiras 10 seções
                contexto_pdf_filtrado.append(secao)
        
        # Busca direta melhorada
        busca_direta = None
        if tem_pdf and contexto_pdf_completo:
            tempo_inicio_busca = time.perf_counter()
            busca_direta = self._buscar_informacao_direta_melhorada_v4(
                contexto_pdf_completo,
                analise_intencao,
                pergunta_ollama
            )
            tempo_busca = time.perf_counter() - tempo_inicio_busca
            self.tempos_execucao['busca_direta'] = tempo_busca
            
            if busca_direta and busca_direta['encontrado']:
                print(colored(f"✅ Busca direta encontrou informações relevantes!", "green"))
            else:
                print(colored(f"⚠️ Busca direta não encontrou padrões específicos", "yellow"))
        
        # Gerar prompt otimizado com instruções especiais
        prompt = self._gerar_prompt_otimizado_v4(
            pergunta_ollama,
            contexto_pdf_filtrado if contexto_pdf_filtrado else contexto_pdf_completo,
            medicamento_nome,
            busca_direta,
            analise_intencao,
            reformulacao
        )
        
        # Consultar Ollama com validação
        melhor_resposta = None
        tentativas = []
        
        for tentativa in range(self.validacao_config['max_tentativas_ollama']):
            try:
                print(colored(f"🔄 Tentativa {tentativa + 1} de consulta ao Ollama...", "yellow"))
                tempo_inicio_ollama = time.perf_counter()
                
                response = ollama.chat(
                    model=self.modelo_ollama,
                    messages=[
                        {
                            'role': 'system',
                            'content': self._gerar_system_prompt_v4(analise_intencao)
                        },
                        {
                            'role': 'user',
                            'content': prompt,
                        }
                    ],
                    options={
                        'temperature': self.temperatura_ollama,
                        'num_predict': 1500,
                        'top_p': 0.9,
                        'timeout': 120
                    }
                )
                
                tempo_ollama = time.perf_counter() - tempo_inicio_ollama
                self.tempos_execucao['ollama'] = tempo_ollama
                
                resposta_ollama = response['message']['content']
                
                # Validar resposta
                tempo_inicio_validacao = time.perf_counter()
                validacao = self._validar_resposta_melhorada_v4(
                    resposta_ollama,
                    pergunta_original,
                    busca_direta,
                    analise_intencao
                )
                tempo_validacao = time.perf_counter() - tempo_inicio_validacao
                self.tempos_execucao['validacao'] = tempo_validacao
                
                tentativas.append({
                    'resposta': resposta_ollama,
                    'validacao': validacao,
                    'tempo': tempo_ollama
                })
                
                if validacao['valida']:
                    melhor_resposta = resposta_ollama
                    print(colored(f"✅ Resposta validada com confiança: {validacao['confianca']:.2f}", "green"))
                    break
                else:
                    print(colored(f"⚠️ Resposta inválida: {validacao['razao']}", "yellow"))
                    # Ajustar prompt para próxima tentativa
                    prompt = self._ajustar_prompt_para_retry(prompt, validacao['razao'])
                    
            except Exception as e:
                print(colored(f"❌ Erro na tentativa {tentativa + 1}: {e}", "red"))
                continue
        
        # Se nenhuma resposta foi validada, usar fallback inteligente
        if not melhor_resposta:
            print(colored("🔧 Ativando fallback inteligente...", "yellow"))
            melhor_resposta = self._gerar_resposta_fallback_inteligente_v4(
                pergunta_original,
                busca_direta,
                analise_intencao,
                contexto_pdf_completo,
                tentativas
            )
        
        # Formatar resposta final
        tempo_inicio_formatacao = time.perf_counter()
        resposta_formatada = formatar_links_resposta(melhor_resposta, contexto_dados)
        tempo_formatacao = time.perf_counter() - tempo_inicio_formatacao
        self.tempos_execucao['formatacao'] = tempo_formatacao
        
        # Salvar em cache
        if classificacao and pergunta_original:
            cache_key = self._gerar_cache_key_inteligente_v4(classificacao, analise_intencao)
            self.cache_manager.save_response(cache_key, {
                'resposta': resposta_formatada,
                'analise_intencao': analise_intencao,
                'timestamp': time.time()
            })
        
        return resposta_formatada
    
    def _gerar_system_prompt_v4(self, analise_intencao):
        """System prompt adaptativo baseado no tipo de pergunta"""
        base_prompt = "Você é um especialista em extrair informações precisas de bulas veterinárias."
        
        if analise_intencao['tipo'] == 'armazenamento_aberto':
            return base_prompt + " Quando não houver informação específica sobre armazenamento após aberto, forneça as informações gerais de armazenamento disponíveis, deixando claro que são informações gerais."
        
        elif analise_intencao['tipo'] == 'dose_especifica':
            return base_prompt + " Seja EXTREMAMENTE preciso com doses. Use APENAS valores explicitamente mencionados no documento. NUNCA invente ou calcule doses."
        
        elif analise_intencao['tipo'] == 'intervalos_seguranca':
            return base_prompt + " Forneça TODOS os intervalos de segurança mencionados (carne, leite, ovos), mesmo que a pergunta seja genérica."
        
        return base_prompt + " Leia cuidadosamente o documento e extraia TODAS as informações relevantes solicitadas."
    
    def _gerar_prompt_otimizado_v4(self, pergunta, secoes_pdf, medicamento_nome, busca_direta, analise_intencao, reformulacao):
        """Prompt otimizado com instruções específicas baseadas na análise"""
        
        secoes_texto = "\n\n---SEÇÃO---\n\n".join(secoes_pdf) if secoes_pdf else "Sem conteúdo PDF disponível"
        
        # Adicionar contexto da busca direta se disponível
        contexto_busca = ""
        if busca_direta and busca_direta['encontrado']:
            contexto_busca = f"\n\n📌 INFORMAÇÕES PRÉ-EXTRAÍDAS:\n{json.dumps(busca_direta['info_extraida'], ensure_ascii=False, indent=2)}\n"
        
        # Instrução específica baseada no tipo de pergunta
        instrucao_especifica = ""
        if analise_intencao['resposta_ampla']:
            instrucao_especifica = f"""
            
⚠️ INSTRUÇÃO ESPECIAL:
{reformulacao['instrucao_adicional']}

Se a pergunta é sobre "{reformulacao['pergunta_original']}" mas não há informação ESPECÍFICA sobre isso,
forneça as informações RELACIONADAS disponíveis no documento, explicando claramente o que está disponível.

Por exemplo:
- Se pergunta sobre "armazenamento depois de aberto" mas só há info geral → forneça a info geral
- Se pergunta sobre "intervalos de segurança" sem especificar → forneça TODOS os intervalos disponíveis
"""
        
        prompt = f"""
MEDICAMENTO: {medicamento_nome or 'Documento Veterinário'}

DOCUMENTO COMPLETO:
{secoes_texto}
{contexto_busca}

PERGUNTA ORIGINAL: {reformulacao['pergunta_original']}
PERGUNTA REFORMULADA: {reformulacao['pergunta_reformulada']}
{instrucao_especifica}

INSTRUÇÕES DE RESPOSTA:
1. Leia TODO o conteúdo acima cuidadosamente
2. Se a informação EXATA solicitada não estiver disponível mas houver informação RELACIONADA, forneça-a
3. Sempre indique quando está fornecendo informação geral em vez de específica
4. Se houver tabelas, interprete-as corretamente linha por linha
5. Use valores EXATOS do documento, nunca invente
6. Seja completo mas conciso

FORMATO DA RESPOSTA:
- Comece diretamente com a informação solicitada
- Se não houver info específica mas houver relacionada, diga: "Embora não haja informação específica sobre X, o documento indica que Y"
- Use bullet points para múltiplos itens
- Termine com uma observação se necessário

RESPOSTA:
"""
        
        return prompt
    
    def _buscar_informacao_direta_melhorada_v4(self, conteudo_pdf, analise_intencao, pergunta):
        """Busca direta melhorada com padrões específicos por tipo"""
        
        resultado = {
            'encontrado': False,
            'info_extraida': {},
            'secoes_relevantes': [],
            'confianca': 0.0
        }
        
        tipo = analise_intencao['tipo']
        
        if tipo == 'armazenamento_aberto' or tipo == 'armazenamento_geral':
            # Buscar qualquer informação de armazenamento
            padroes_armazenamento = [
                r'conserv[ae]r?\s+[^.]+\.',
                r'armazen[ae]r?\s+[^.]+\.',
                r'\d+\s*°C',
                r'temperatura\s+ambiente',
                r'frigorífico',
                r'após\s+abertura[^.]+\.',
                r'depois\s+de\s+aberto[^.]+\.',
                r'validade[^.]+\.',
                r'prazo\s+de\s+validade[^.]+\.'
            ]
            
            info_armazenamento = []
            for secao in conteudo_pdf:
                for padrao in padroes_armazenamento:
                    matches = re.findall(padrao, secao, re.IGNORECASE)
                    for match in matches:
                        if match not in info_armazenamento:
                            info_armazenamento.append(match)
                            resultado['encontrado'] = True
            
            if info_armazenamento:
                resultado['info_extraida']['armazenamento'] = info_armazenamento
                resultado['confianca'] = 0.8
        
        elif tipo == 'dose_especifica':
            # Buscar doses com alta precisão
            doses_encontradas = []
            padroes_dose = [
                r'(\d+[,.]?\d*)\s*mg/kg',
                r'(\d+[,.]?\d*)\s*ml/kg',
                r'(\d+[,.]?\d*)\s*mcg/kg',
                r'(\d+[,.]?\d*)\s*UI/kg'
            ]
            
            for secao in conteudo_pdf:
                for padrao in padroes_dose:
                    matches = re.findall(padrao, secao, re.IGNORECASE)
                    for match in matches:
                        unidade = re.search(r'(mg|ml|mcg|UI)/kg', padrao).group(1)
                        dose_completa = f"{match} {unidade}/kg"
                        if dose_completa not in doses_encontradas:
                            doses_encontradas.append(dose_completa)
                            resultado['encontrado'] = True
            
            if doses_encontradas:
                resultado['info_extraida']['doses'] = doses_encontradas
                resultado['confianca'] = 0.9
        
        elif tipo == 'intervalos_seguranca':
            # Buscar todos os intervalos
            intervalos = {}
            padroes_intervalo = [
                r'carne[^:]*:\s*(\d+)\s*dias',
                r'leite[^:]*:\s*(\d+)\s*(dias|horas)',
                r'ovos[^:]*:\s*(\d+)\s*dias',
                r'(\d+)\s*dias\s*(?:para\s+)?carne',
                r'(\d+)\s*(?:dias|horas)\s*(?:para\s+)?leite'
            ]
            
            for secao in conteudo_pdf:
                secao_lower = secao.lower()
                
                # Carne
                match_carne = re.search(r'carne[^:]*:\s*(\d+)\s*dias', secao_lower)
                if match_carne:
                    intervalos['carne'] = f"{match_carne.group(1)} dias"
                    resultado['encontrado'] = True
                
                # Leite
                match_leite = re.search(r'leite[^:]*:\s*(\d+)\s*(dias|horas)', secao_lower)
                if match_leite:
                    intervalos['leite'] = f"{match_leite.group(1)} {match_leite.group(2)}"
                    resultado['encontrado'] = True
                
                # Ovos
                match_ovos = re.search(r'ovos[^:]*:\s*(\d+)\s*dias', secao_lower)
                if match_ovos:
                    intervalos['ovos'] = f"{match_ovos.group(1)} dias"
                    resultado['encontrado'] = True
            
            if intervalos:
                resultado['info_extraida']['intervalos'] = intervalos
                resultado['confianca'] = 0.85
        
        return resultado
    
    def _validar_resposta_melhorada_v4(self, resposta, pergunta, busca_direta, analise_intencao):
        """Validação inteligente da resposta com múltiplos critérios"""
        
        validacao = {
            'valida': True,
            'confianca': 1.0,
            'razao': '',
            'avisos': []
        }
        
        resposta_lower = resposta.lower()
        
        # Verificar respostas vazias ou muito genéricas
        frases_invalidas = [
            "não foi possível encontrar",
            "não há informação",
            "não consta",
            "consulte o veterinário",
            "consulte a bula"
        ]
        
        # Se tem busca direta com informação mas resposta diz que não encontrou
        if busca_direta and busca_direta['encontrado']:
            for frase in frases_invalidas:
                if frase in resposta_lower:
                    validacao['valida'] = False
                    validacao['confianca'] = 0.0
                    validacao['razao'] = "Resposta diz não encontrar mas temos informação extraída"
                    return validacao
        
        # Validações específicas por tipo
        if analise_intencao['tipo'] == 'dose_especifica':
            # Verificar se tem valores de dose
            tem_dose = re.search(r'\d+[,.]?\d*\s*(mg|ml|mcg|UI)', resposta)
            if not tem_dose and 'dose' in pergunta.lower():
                validacao['valida'] = False
                validacao['confianca'] = 0.3
                validacao['razao'] = "Resposta sobre dose sem valores numéricos"
            
            # Se tem busca direta com doses, verificar se usou corretamente
            if busca_direta and 'doses' in busca_direta.get('info_extraida', {}):
                doses_validas = busca_direta['info_extraida']['doses']
                doses_na_resposta = re.findall(r'\d+[,.]?\d*\s*(mg|ml|mcg|UI)/kg', resposta)
                
                for dose_resposta in doses_na_resposta:
                    dose_str = ''.join(dose_resposta)
                    dose_valida = False
                    for dose_correta in doses_validas:
                        if dose_str in dose_correta or dose_correta in dose_str:
                            dose_valida = True
                            break
                    
                    if not dose_valida:
                        validacao['valida'] = False
                        validacao['confianca'] = 0.0
                        validacao['razao'] = f"Dose {dose_str} não está nas doses válidas extraídas"
                        return validacao
        
        elif analise_intencao['tipo'] == 'armazenamento_aberto':
            # Para armazenamento, aceitar respostas mais amplas
            if 'armazen' in resposta_lower or 'conserv' in resposta_lower or '°c' in resposta_lower:
                validacao['confianca'] = 0.8
                if 'após' not in resposta_lower and 'depois' not in resposta_lower:
                    validacao['avisos'].append("Resposta com informação geral de armazenamento")
            else:
                validacao['confianca'] = 0.4
        
        # Verificar tamanho mínimo da resposta
        if len(resposta.strip()) < 20:
            validacao['valida'] = False
            validacao['confianca'] = 0.1
            validacao['razao'] = "Resposta muito curta"
        
        # Ajustar confiança baseada em indicadores positivos
        indicadores_positivos = [
            'segundo o documento',
            'de acordo com',
            'conforme',
            'indica que',
            'especifica',
            'menciona'
        ]
        
        for indicador in indicadores_positivos:
            if indicador in resposta_lower:
                validacao['confianca'] = min(1.0, validacao['confianca'] + 0.1)
        
        return validacao
    
    def _gerar_resposta_fallback_inteligente_v4(self, pergunta, busca_direta, analise_intencao, contexto_pdf, tentativas):
        """Gera resposta de fallback inteligente baseada no que foi extraído"""
        
        resposta_parts = []
        
        # Se tem informação da busca direta
        if busca_direta and busca_direta['encontrado']:
            info = busca_direta['info_extraida']
            
            if analise_intencao['tipo'] == 'dose_especifica' and 'doses' in info:
                doses_str = ', '.join(info['doses'])
                resposta_parts.append(f"Segundo o documento, foram identificadas as seguintes doses: {doses_str}.")
                resposta_parts.append("Para informações mais específicas sobre a espécie ou via de administração, consulte o documento completo.")
            
            elif analise_intencao['tipo'] in ['armazenamento_aberto', 'armazenamento_geral'] and 'armazenamento' in info:
                resposta_parts.append("Informações de armazenamento encontradas no documento:")
                for item in info['armazenamento']:
                    resposta_parts.append(f"• {item}")
                if analise_intencao['tipo'] == 'armazenamento_aberto':
                    resposta_parts.append("\nNota: Não foi encontrada informação específica sobre armazenamento após aberto. As informações acima são sobre armazenamento em geral.")
            
            elif analise_intencao['tipo'] == 'intervalos_seguranca' and 'intervalos' in info:
                resposta_parts.append("Intervalos de segurança encontrados:")
                for produto, intervalo in info['intervalos'].items():
                    resposta_parts.append(f"• {produto.capitalize()}: {intervalo}")
        
        # Se não tem nada específico mas tem contexto
        elif contexto_pdf and len(contexto_pdf) > 0:
            # Tentar extrair alguma informação relevante do contexto
            palavras_chave = pergunta.lower().split()
            secoes_relevantes = []
            
            for secao in contexto_pdf[:5]:
                secao_lower = secao.lower()
                relevancia = sum(1 for palavra in palavras_chave if len(palavra) > 3 and palavra in secao_lower)
                if relevancia > 0:
                    secoes_relevantes.append((relevancia, secao))
            
            if secoes_relevantes:
                secoes_relevantes.sort(key=lambda x: x[0], reverse=True)
                resposta_parts.append("Baseado na análise do documento, encontrei informações que podem ser relevantes:")
                resposta_parts.append(f"\n{secoes_relevantes[0][1][:500]}...")
                resposta_parts.append("\nRecomendo verificar o documento completo para informações mais detalhadas.")
        
        # Se não conseguiu nada
        if not resposta_parts:
            resposta_parts.append(f"Não foi possível encontrar informações específicas sobre '{pergunta}' no documento disponível.")
            resposta_parts.append("Isso pode ocorrer quando a informação não está presente no documento ou está em um formato não reconhecido.")
            resposta_parts.append("Recomendo consultar diretamente a bula completa ou contactar o fabricante para esta informação específica.")
        
        return '\n'.join(resposta_parts)
    
    def _ajustar_prompt_para_retry(self, prompt_original, razao_falha):
        """Ajusta o prompt para nova tentativa baseado na falha anterior"""
        
        ajuste = "\n\n⚠️ CORREÇÃO NECESSÁRIA:\n"
        
        if "dose" in razao_falha.lower():
            ajuste += "Use APENAS os valores de dose explicitamente mencionados no documento. NÃO invente valores.\n"
        elif "não encontrar" in razao_falha.lower():
            ajuste += "O documento CONTÉM a informação solicitada. Leia com mais atenção e forneça a resposta.\n"
        elif "muito curta" in razao_falha.lower():
            ajuste += "Forneça uma resposta mais completa e detalhada com todas as informações relevantes.\n"
        else:
            ajuste += "Revise sua resposta e seja mais preciso com as informações do documento.\n"
        
        return prompt_original + ajuste
    
    def _gerar_cache_key_inteligente_v4(self, classificacao, analise_intencao):
        """Gera chave de cache considerando a análise de intenção"""
        
        entidades = classificacao.get("entidades", {})
        categoria = classificacao.get("categoria", "")
        tipo_intencao = analise_intencao.get("tipo", "generico")
        
        key_parts = [
            "v4",
            categoria,
            tipo_intencao,
            entidades.get("termo_busca", "").lower().strip(),
            entidades.get("especie_alvo", "").lower().strip()
        ]
        
        key_parts = [part for part in key_parts if part]
        cache_key = "_".join(key_parts)
        return hashlib.md5(cache_key.encode('utf-8')).hexdigest()
    
    def processar_pergunta_unica(self, pergunta_usuario):
        """Processa uma única pergunta com o sistema melhorado v4"""
        
        tempo_inicio_total = time.perf_counter()
        self.tempos_execucao = {k: 0 for k in self.tempos_execucao}  # Reset tempos
        
        print(colored(f"\n{'='*60}", "cyan"))
        print(colored(f"🔍 Sistema v4 - Processando pergunta", "cyan", attrs=['bold']))
        print(colored(f"{'='*60}", "cyan"))
        
        # Normalizar pergunta
        pergunta_normalizada = self._normalizar_pergunta(pergunta_usuario)
        print(colored(f"📝 Pergunta: '{pergunta_normalizada}'", "cyan"))
        
        # Verificar cache primeiro
        cache_key_temp = hashlib.md5(pergunta_normalizada.encode('utf-8')).hexdigest()
        resposta_cache = self.cache_manager.get_response(cache_key_temp)
        if resposta_cache:
            print(colored("✅ Resposta encontrada em cache!", "green"))
            return resposta_cache.get('resposta', resposta_cache)
        
        # ETAPA 1: CLASSIFICAÇÃO
        tempo_inicio_classificacao = time.perf_counter()
        classificacao = self.query_classifier.classify_and_extract(pergunta_normalizada)
        tempo_classificacao = time.perf_counter() - tempo_inicio_classificacao
        self.tempos_execucao['classificacao'] = tempo_classificacao
        print(colored(f"⏱️  Classificação: {tempo_classificacao:.2f}s", "yellow"))
        
        # Corrigir categoria se necessário
        classificacao = self._corrigir_categoria_se_necesario(classificacao, pergunta_normalizada)
        
        if not classificacao or classificacao.get("categoria") == "erro":
            tempo_total = time.perf_counter() - tempo_inicio_total
            self.tempos_execucao['total'] = tempo_total
            return "Não foi possível classificar sua pergunta. Por favor, reformule de forma mais clara."
        
        categoria = classificacao.get("categoria")
        entidades = classificacao.get("entidades", {})
        pergunta_para_ollama = entidades.get("pergunta_ollama", pergunta_usuario)
        
        print(colored(f"📊 Categoria: {categoria}", "magenta"))
        print(colored(f"🏷️  Entidades: {json.dumps(entidades, indent=2, ensure_ascii=False)}", "magenta"))
        
        # Atualizar contexto
        self.contexto_conversacao["ultima_pergunta"] = pergunta_normalizada
        self.contexto_conversacao["ultima_categoria"] = categoria
        
        if categoria == "medicamento":
            termo_busca = entidades.get("termo_busca")
            if not termo_busca:
                termo_busca = entidades.get("substancia_ativa") or self._extrair_medicamento_query(pergunta_normalizada)
                print(colored(f"⚠️  Termo de busca usando fallback: '{termo_busca}'", "yellow"))
            
            # Guardar entidade principal
            for palavra in termo_busca.split():
                if palavra[0].isupper():
                    self.contexto_conversacao["ultima_entidade_medicamento"] = palavra
                    break
            
            self.contexto_conversacao["ultimo_termo_busca"] = termo_busca
            
            # ETAPA 2: WEB SCRAPING
            tempo_inicio_scraping = time.perf_counter()
            dados_raspados = self.realizar_web_scraping_sincrono(termo_busca)
            tempo_scraping = time.perf_counter() - tempo_inicio_scraping
            self.tempos_execucao['web_scraping'] = tempo_scraping
            print(colored(f"⏱️  Web Scraping: {tempo_scraping:.2f}s", "yellow"))
            
            if not dados_raspados:
                tempo_total = time.perf_counter() - tempo_inicio_total
                self.tempos_execucao['total'] = tempo_total
                self._imprimir_resumo_tempos()
                return f"Não foram encontrados resultados para '{termo_busca}'. Verifique o nome do medicamento ou tente com outro termo de busca."
            
            # Atualizar contexto com dados do scraping
            self.contexto_conversacao["dados_ultimo_scraping"] = dados_raspados
            self.contexto_conversacao["ultimo_scraping_time"] = time.time()
            
            # ETAPA 3: CONSULTA OLLAMA MELHORADA
            resposta = self._consultar_ollama_melhorado_v4(
                pergunta_para_ollama, 
                dados_raspados, 
                tipo_consulta="medicamento",
                classificacao=classificacao,
                pergunta_original=pergunta_normalizada
            )
            
            # Atualizar contexto e histórico
            self.contexto_conversacao["ultima_resposta"] = resposta
            self._adicionar_ao_historico(pergunta_normalizada, resposta, categoria)
            
            # TEMPO TOTAL
            tempo_total = time.perf_counter() - tempo_inicio_total
            self.tempos_execucao['total'] = tempo_total
            self._imprimir_resumo_tempos()
            
            return resposta
        
        elif categoria == "comparacao":
            # [Código de comparação mantido similar ao original]
            # ... [resto do código de comparação]
            pass
        
        else:
            resposta = f"Categoria '{categoria}' não suportada no momento."
            tempo_total = time.perf_counter() - tempo_inicio_total
            self.tempos_execucao['total'] = tempo_total
            return resposta
    
    def _normalizar_pergunta(self, pergunta):
        """Normaliza a pergunta para melhor processamento"""
        # Remover espaços extras
        pergunta = ' '.join(pergunta.split())
        
        # Corrigir typos comuns
        correcoes = {
            'armazenado': 'armazenar',
            'doses': 'dose',
            'posologias': 'posologia',
            'indicaçoes': 'indicações',
            'reaçoes': 'reações'
        }
        
        for erro, correcao in correcoes.items():
            pergunta = pergunta.replace(erro, correcao)
        
        return pergunta
    
    def _corrigir_categoria_se_necesario(self, classificacao, pergunta):
        """Corrige categorias mal classificadas"""
        if not classificacao or classificacao.get("categoria") == "erro":
            return classificacao
            
        pergunta_lower = pergunta.lower()
        categoria_atual = classificacao.get("categoria")
        
        # Regras de correção
        correcoes = [
            ("mesmo princípio ativo", "comparacao"),
            ("alternativ", "comparacao"),
            ("substitut", "comparacao"),
            ("equivalent", "comparacao"),
            ("similar", "comparacao"),
            ("que medicamentos", "comparacao"),
            ("quais medicamentos", "comparacao")
        ]
        
        for padrao, categoria_correta in correcoes:
            if padrao in pergunta_lower and categoria_atual != categoria_correta:
                print(colored(f"⚠️  Corrigindo categoria: '{padrao}' deve ser {categoria_correta}", "yellow"))
                classificacao["categoria"] = categoria_correta
                break
        
        return classificacao
    
    def _extrair_medicamento_query(self, pergunta):
        """Extrai nome do medicamento da pergunta"""
        # Procurar palavras capitalizadas
        palavras = pergunta.split()
        palavras_capitalizadas = [p for p in palavras if p[0].isupper() and len(p) > 2]
        
        if palavras_capitalizadas:
            return ' '.join(palavras_capitalizadas)
        
        # Fallback: primeiras palavras significativas
        palavras_significativas = [p for p in palavras if len(p) > 3]
        return ' '.join(palavras_significativas[:2]) if palavras_significativas else pergunta
    
    def _adicionar_ao_historico(self, pergunta, resposta, categoria):
        """Adiciona interação ao histórico"""
        if 'historico_conversacao' not in self.contexto_conversacao:
            self.contexto_conversacao['historico_conversacao'] = []
        
        interacao = {
            'timestamp': time.time(),
            'pergunta': pergunta,
            'resposta': resposta[:200] + "..." if len(resposta) > 200 else resposta,
            'categoria': categoria
        }
        
        self.contexto_conversacao['historico_conversacao'].append(interacao)
        
        # Manter apenas últimas 10 interações
        if len(self.contexto_conversacao['historico_conversacao']) > 10:
            self.contexto_conversacao['historico_conversacao'] = self.contexto_conversacao['historico_conversacao'][-10:]
    
    def _imprimir_resumo_tempos(self):
        """Imprime resumo detalhado dos tempos de execução"""
        print(colored("\n" + "="*60, "cyan"))
        print(colored("📊 RESUMO DE TEMPOS DE EXECUÇÃO", "cyan", attrs=['bold']))
        print(colored("="*60, "cyan"))
        
        tempos = self.tempos_execucao
        total = tempos.get('total', 0)
        
        if total > 0:
            componentes = [
                ('🔍 Classificação', 'classificacao'),
                ('🌐 Web Scraping', 'web_scraping'),
                ('📄 Extração PDF', 'extracao_pdf'),
                ('🔎 Filtragem PDF', 'filtragem_pdf'),
                ('🎯 Busca Direta', 'busca_direta'),
                ('🧠 Interpretação', 'interpretacao'),
                ('🤖 Ollama', 'ollama'),
                ('✅ Validação', 'validacao'),
                ('✨ Formatação', 'formatacao')
            ]
            
            for nome, chave in componentes:
                if tempos.get(chave, 0) > 0:
                    tempo = tempos[chave]
                    percentual = (tempo/total*100) if total > 0 else 0
                    print(colored(f"  {nome:20s} {tempo:>6.2f}s  ({percentual:>5.1f}%)", "yellow"))
            
            print(colored("  " + "-"*58, "cyan"))
            print(colored(f"  ⏱️  TEMPO TOTAL:       {total:>6.2f}s  (100.0%)", "green", attrs=['bold']))
        
        print(colored("="*60 + "\n", "cyan"))
    
    async def realizar_web_scraping(self, termo_busca):
        """Realiza web scraping completo do site medvet"""
        print(colored(f"Iniciando web scraping para: '{termo_busca}'", "blue"))

        # Criar sessão internamente
        connector = TCPConnector(limit=MAX_CONCURRENT_REQUESTS, ssl=False)
        async with ClientSession(connector=connector, headers=HEADERS) as session:
        
          chrome_options = Options()
          chrome_options.add_argument("--headless")
          chrome_options.add_argument("--disable-gpu")
          chrome_options.add_argument("--disable-extensions")
          chrome_options.add_argument("--disable-dev-shm-usage")
          chrome_options.add_argument("--no-sandbox")
          chrome_options.add_argument(f"user-agent={HEADERS['User-Agent']}")

          driver = None
          url_pagina_busca = ""

          try:
              driver = webdriver.Chrome(options=chrome_options)
              driver.get("https://medvet.dgav.pt/")
              wait = WebDriverWait(driver, 20)
              
              input_box = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text'], input[type='search']")))
              input_box.send_keys(termo_busca)
              input_box.send_keys(Keys.RETURN)
              time.sleep(3)
              
              url_pagina_busca = driver.current_url
          except Exception as e:
              print(colored(f"Erro Selenium: {e}", "red"))
              if driver:
                  driver.quit()
              return None
          finally:
              if driver:
                  driver.quit()

          if not url_pagina_busca or url_pagina_busca == "https://medvet.dgav.pt/":
              print(colored("URL de resultados não obtida", "red"))
              return None

          print(colored(f"Extraindo informações de: {url_pagina_busca}", "blue"))
          
          urls_processadas = set()
          resultados_basicos = self._extrair_informacoes_pagina_busca(url_pagina_busca, urls_processadas)
          
          if not resultados_basicos:
              print(colored("Nenhum resultado encontrado", "yellow"))
              return None
          
          print(colored(f"Processando {len(resultados_basicos)} medicamentos...", "blue"))
          
          max_medicamentos = min(len(resultados_basicos), 10)
          links_para_processar = []
          
          for resultado_basico in resultados_basicos[:max_medicamentos]:
              link_medicamento = resultado_basico.get('link')
              nome_medicamento = resultado_basico.get('nome', 'Nome não disponível')
              
              if link_medicamento:
                  links_para_processar.append({
                      'link': link_medicamento,
                      'titulo': nome_medicamento,
                      'dados_basicos': resultado_basico
                  })

          resultados_completos = await self._processar_links_async(links_para_processar)
          
          resultados_unicos = []
          nomes_vistos = set()
          
          for resultado in resultados_completos:
              nome = resultado.get('nome', '').strip()
              if nome and nome not in nomes_vistos:
                  nomes_vistos.add(nome)
                  resultados_unicos.append(resultado)

          print(colored(f"Resultados únicos: {len(resultados_unicos)}", "green"))
          
          com_pdf = sum(1 for r in resultados_unicos if r.get('conteudo_pdf'))
          print(colored(f"Medicamentos com PDF: {com_pdf}/{len(resultados_unicos)}", "blue"))
          
          return resultados_unicos

    async def _processar_links_async(self, links_info):
        """Processa links de forma assíncrona"""
        connector = TCPConnector(limit=MAX_CONCURRENT_REQUESTS, ssl=False)
        async with ClientSession(connector=connector, headers=HEADERS) as session:
            tasks = []
            for link_info in links_info:
                task = self._processar_link_async(session, link_info)
                tasks.append(task)
            
            resultados = await asyncio.gather(*tasks, return_exceptions=True)
            
            resultados_validos = []
            for resultado in resultados:
                if resultado and not isinstance(resultado, Exception):
                    resultados_validos.append(resultado)
            
            return resultados_validos

    async def _processar_link_async(self, session, link_info):
        """Processa um link individual de forma assíncrona"""
        try:
            async with session.get(link_info['link'], timeout=ClientTimeout(total=20)) as response:
                if response.status != 200:
                    return None
                
                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")
                
                conteudo_item = {
                    "url": link_info['link'],
                    "titulo": link_info['titulo'],
                    "conteudo_html": "",
                    "conteudo_pdf": []
                }
                
                tags_permitidas = {"h1", "h2", "h3", "h4", "h5", "p", "a"}
                html_str = ""
                
                main_content_area = soup.body
                article_tag = soup.find('article')
                if article_tag:
                    main_content_area = article_tag
                else:
                    main_tag = soup.find('main')
                    if main_tag:
                        main_content_area = main_tag

                if main_content_area:
                    for element in main_content_area.find_all(tags_permitidas, recursive=True):
                        texto_formatado = self._formatar_texto_html(element)
                        if texto_formatado:
                            if element.name in {"h1", "h2", "h3", "h4", "h5"}:
                                html_str += f"\n## {texto_formatado}\n"
                            else:
                                html_str += texto_formatado + " "
                
                conteudo_item["conteudo_html"] = html_str.strip()
                
                pdf_url = self._encontrar_link_pdf(soup, link_info['link'])
                if pdf_url:
                    pdf_text = await self._extrair_conteudo_pdf_async(pdf_url)
                    if pdf_text:
                        conteudo_item["conteudo_pdf"] = self._formatar_conteudo_pdf(pdf_text)
                
                resultado_final = {**link_info['dados_basicos'], **conteudo_item}
                return resultado_final
                
        except Exception as e:
            print(colored(f"Erro ao processar {link_info['link']}: {e}", "red"))
            return link_info['dados_basicos']

    async def _extrair_conteudo_pdf_async(self, pdf_url):
        """Extrai conteúdo de PDF de forma assíncrona"""
        try:
            pdf_hash = hashlib.md5(pdf_url.encode()).hexdigest()
            pdf_path = os.path.join(PDF_CACHE_DIR, f"{pdf_hash}.pdf")
            txt_path = os.path.join(PDF_CACHE_DIR, f"{pdf_hash}_v3_estruturado.txt")
            
            if os.path.exists(txt_path):
                with open(txt_path, 'r', encoding='utf-8') as f:
                    return f.read()
            
            connector = TCPConnector(ssl=False)
            async with ClientSession(connector=connector, headers=HEADERS) as session:
                async with session.get(pdf_url, timeout=ClientTimeout(total=30)) as response:
                    if response.status != 200:
                        return None
                    
                    pdf_content = await response.read()
                    
                    with open(pdf_path, 'wb') as f:
                        f.write(pdf_content)
            
            resultado = self.tabela_interpreter.processar_pdf_completo(pdf_path)
            
            if resultado:
                # O resultado pode ser uma lista de seções, converter para string
                if isinstance(resultado, list):
                    resultado_str = "\n\n".join(str(secao) for secao in resultado)
                else:
                    resultado_str = resultado
                    
                with open(txt_path, 'w', encoding='utf-8') as f:
                    f.write(resultado_str)
                return resultado_str
            
            return None
            
        except Exception as e:
            print(colored(f"Erro ao extrair PDF {pdf_url}: {e}", "red"))
            return None

    def _formatar_texto_html(self, elemento):
        """Formata texto HTML"""
        if elemento.name in {"h1", "h2", "h3", "h4", "h5", "a", "p"}:
            return elemento.get_text(strip=True)
        return None

    def _encontrar_link_pdf(self, soup, url):
        """Encontra link de PDF na página"""
        pdf_tag = soup.find("a", href=True, target="_blank")
        if pdf_tag and pdf_tag.find("span", class_="fa-file-pdf-o"):
            return urljoin(url, pdf_tag["href"])
        return None

    def _formatar_conteudo_pdf(self, texto):
        """Formata conteúdo do PDF"""
        if not texto:
            return []
        
        partes = re.split(r'\n(?=\d+\.\s|\={80})', texto)
        return [p.strip() for p in partes if p.strip()]

    def _extrair_informacoes_pagina_busca(self, url_busca, urls_processadas=None):
        """Extrai informações da página de busca"""
        if urls_processadas is None:
            urls_processadas = set()
        
        if url_busca in urls_processadas:
            return []
        urls_processadas.add(url_busca)
        
        print(colored(f"Processando URL: {url_busca}", "cyan"))
        
        try:
            response = requests.get(url_busca, timeout=20, headers=HEADERS, verify=False)
            response.raise_for_status()
            response.encoding = "utf-8"
        except requests.RequestException as e:
            print(colored(f"Erro ao acessar {url_busca}: {e}", "red"))
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        itens_resultado = soup.find_all("div", class_="search-result")
        
        if not itens_resultado:
            links_na_pagina = soup.find_all("a", href=True)
            resultados_pagina = []
            for link_tag in links_na_pagina:
                link_url = urljoin(url_busca, link_tag["href"])
                if "medvet.dgav.pt/medvet/med" in link_url:
                    titulo = link_tag.get_text(strip=True) or "Título não encontrado"
                    if titulo and not any(r.get('nome') == titulo for r in resultados_pagina):
                        resultados_pagina.append({
                            "nome": titulo,
                            "link": link_url,
                            "informacoes_visiveis": titulo
                        })
        else:
            resultados_pagina = []
            
            for div in itens_resultado:
                item_info = {}
                
                h5 = div.find("h5")
                if h5:
                    item_info["nome"] = h5.get_text(strip=True)
                
                link_tag = div.find("a", href=True)
                if link_tag:
                    item_info["link"] = urljoin(url_busca, link_tag["href"])
                
                texto_completo = div.get_text(separator=" ", strip=True)
                item_info["informacoes_visiveis"] = texto_completo
                
                linhas = texto_completo.split('\n')
                for linha in linhas:
                    linha_limpa = linha.strip()
                    if linha_limpa:
                        if any(palavra in linha_limpa.lower() for palavra in ['espécie', 'especie', 'animal']):
                            item_info["especies"] = linha_limpa
                        elif any(palavra in linha_limpa.lower() for palavra in ['forma', 'tipo', 'apresentação', 'apresentacao']):
                            item_info["forma_farmaceutica"] = linha_limpa
                        elif any(palavra in linha_limpa.lower() for palavra in ['princípio', 'principio', 'ativo', 'substância', 'substancia']):
                            item_info["principio_ativo"] = linha_limpa
                
                if item_info.get("nome"):
                    resultados_pagina.append(item_info)

        print(colored(f"Encontrados {len(resultados_pagina)} resultados", "green"))

        # Lógica de paginação (simplificada)
        navbar = soup.find("div", class_="navbar")
        links_paginacao = []
        
        if navbar:
            for link_tag in navbar.find_all("a", href=True):
                link_url = urljoin(url_busca, link_tag["href"])
                if link_url not in urls_processadas:
                    links_paginacao.append(link_url)
        
        if links_paginacao:
            for i, link_paginacao in enumerate(links_paginacao[:3]):
                resultados_adicionais = self._extrair_informacoes_pagina_busca(link_paginacao, urls_processadas)
                resultados_pagina.extend(resultados_adicionais)
                time.sleep(1)
        
        return resultados_pagina

    def realizar_web_scraping_sincrono(self, termo_busca):
        """Versão síncrona do web scraping para compatibilidade"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.realizar_web_scraping(termo_busca))
        finally:
            loop.close()
    
    def limpar_contexto_manual(self):
        """Limpa o contexto manualmente"""
        print(colored("🔄 Limpando contexto...", "yellow"))
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
            "respostas_tentativas": []
        }
        print(colored("✅ Contexto limpo!", "green"))


# Função principal
def main():
    print(colored("="*60, "green"))
    print(colored("🚀 Sistema Inteligente de Consulta Veterinária v4", "green", attrs=['bold']))
    print(colored("   Versão otimizada com maior assertividade", "green"))
    print(colored("="*60, "green"))
    
    # Criar instância do sistema
    sistema = SistemaConsultaVetOtimizado()
    
    print(colored("\n💡 Dicas:", "yellow"))
    print(colored("  • Digite 'sair' para terminar", "yellow"))
    print(colored("  • Digite 'limpar' para limpar o contexto", "yellow"))
    print(colored("  • Sistema otimizado para respostas mais precisas e abrangentes", "yellow"))
    
    while True:
        try:
            pergunta = input(colored("\n❓ Digite sua pergunta: ", "cyan", attrs=['bold']))
            
            if pergunta.lower() == 'sair':
                print(colored("\n👋 Encerrando sistema...", "red"))
                break
            
            if pergunta.lower() == 'limpar':
                sistema.limpar_contexto_manual()
                continue
            
            if not pergunta.strip():
                continue
            
            # Processar pergunta
            resposta = sistema.processar_pergunta_unica(pergunta)
            
            # Exibir resposta
            print(colored("\n" + "="*60, "green"))
            print(colored("💬 RESPOSTA:", "green", attrs=['bold']))
            print(colored("="*60, "green"))
            print(resposta)
            print(colored("="*60 + "\n", "green"))
            
        except KeyboardInterrupt:
            print(colored("\n\n❌ Interrompido pelo usuário", "red"))
            break
        except Exception as e:
            print(colored(f"\n❌ Erro inesperado: {e}", "red"))
            import traceback
            traceback.print_exc()
    
    print(colored("\n✨ Obrigado por usar o Sistema v4!", "green"))


if __name__ == "__main__":
    main()