import json
import os
import time
import hashlib
import asyncio
import aiohttp
from termcolor import colored
import ollama
from aiohttp import ClientSession, TCPConnector, ClientTimeout
import time
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
from ollama_wrapper import OllamaWrapperSeguro
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import urllib3
import fitz  # PyMuPDF
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
#MODELO_OLLAMA_PADRAO = "gemma3:latest"
#MODELO_OLLAMA_PADRAO =  "deepseek-r1:8b"
#MODELO_OLLAMA_PADRAO =  "qwen2.5:7b"
MODELO_OLLAMA_PADRAO = "qwen2.5:14b"
#MODELO_OLLAMA_PADRAO =  "gpt-oss:20b"
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

class TabelaInterpreter:
    """
    Classe focada APENAS em detectar e explicar tabelas para o Ollama
    """
    
    def processar_pdf_completo(self, pdf_path):
        """
        Extrai TODO o PDF e identifica tabelas
        """
        try:
            texto_completo = []
            
            with fitz.open(pdf_path) as pdf_file:
                for page_num, page in enumerate(pdf_file):
                    texto_pagina = page.get_text()
                    
                    # Detectar se tem estrutura tabular
                    if self._tem_tabela(texto_pagina):
                        texto_processado = self._explicar_tabela_para_ollama(texto_pagina, page_num)
                    else:
                        texto_processado = texto_pagina
                    
                    texto_completo.append(texto_processado)
            
            # Juntar e limpar
            texto_unificado = "\n\n".join(texto_completo)
            texto_limpo = self._limpar_texto_basico(texto_unificado)
            
            # Dividir em seções (sem duplicação)
            secoes = self._dividir_em_secoes(texto_limpo)
            
            return secoes
            
        except Exception as e:
            print(colored(f"Erro ao processar PDF: {e}", "red"))
            return []
    
    def _tem_tabela(self, texto):
        """
        Detecta se o texto contém estrutura tabular
        """
        # Indicadores de tabela:
        # 1. Múltiplas linhas com espaçamento similar
        # 2. Presença de números e unidades (mg, kg, ml)
        # 3. Palavras-chave de cabeçalhos
        
        indicadores = 0
        
        # Verificar espaçamento regular (múltiplos espaços consecutivos)
        if re.search(r'\s{3,}', texto):
            indicadores += 1
        
        # Verificar números com unidades em múltiplas linhas
        linhas_com_unidades = len(re.findall(r'\d+\.?\d*\s*(mg|ml|kg|mcg)', texto, re.IGNORECASE))
        if linhas_com_unidades >= 3:
            indicadores += 1
        
        # Verificar palavras de cabeçalho de tabela
        headers_tabela = ['espécie', 'dose', 'via', 'administração', 'peso', 'animal', 
                         'posologia', 'frequência', 'intervalo', 'temperatura']
        headers_encontrados = sum(1 for h in headers_tabela if h in texto.lower())
        if headers_encontrados >= 2:
            indicadores += 1
        
        return indicadores >= 2
    
    def _explicar_tabela_para_ollama(self, texto_pagina, page_num):
        """
        Converte tabela em formato ULTRA-EXPLÍCITO para o Ollama
        """
        resultado = f"\n{'='*80}\n"
        resultado += f"📊 PÁGINA {page_num + 1} - CONTÉM DADOS TABULARES\n"
        resultado += f"{'='*80}\n\n"
        resultado += "⚠️ ATENÇÃO: Os dados abaixo estão organizados em TABELA.\n"
        resultado += "Leia LINHA POR LINHA, associando cada valor ao seu cabeçalho.\n\n"
        
        # Tentar identificar linhas da tabela
        linhas = texto_pagina.split('\n')
        
        # Procurar padrão: linha com espécies/categorias seguida de valores
        tabela_interpretada = []
        linha_anterior = ""
        
        for i, linha in enumerate(linhas):
            linha_limpa = linha.strip()
            if not linha_limpa:
                continue
            
            # Detectar linha com dados (tem números e unidades)
            tem_dados = bool(re.search(r'\d+\.?\d*\s*(mg|ml|kg|mcg|°c|dias)', linha_limpa, re.IGNORECASE))
            
            # Detectar linha com categorias (espécies, etc)
            especies = ['suínos', 'bovinos', 'equinos', 'cães', 'gatos', 'aves', 
                       'ovinos', 'caprinos', 'coelhos', 'peru']
            tem_categoria = any(esp in linha_limpa.lower() for esp in especies)
            
            if tem_dados or tem_categoria:
                # Tentar extrair informação estruturada
                interpretacao = self._interpretar_linha_tabela(linha_limpa, linha_anterior)
                if interpretacao:
                    tabela_interpretada.append(interpretacao)
            
            linha_anterior = linha_limpa
        
        # Adicionar interpretações ao texto
        if tabela_interpretada:
            resultado += "📋 INTERPRETAÇÃO DA TABELA (leia com atenção):\n\n"
            for i, interp in enumerate(tabela_interpretada, 1):
                resultado += f"Entrada {i}:\n{interp}\n\n"
        
        # Adicionar texto original para contexto
        resultado += "📄 TEXTO ORIGINAL DA TABELA:\n"
        resultado += "-" * 80 + "\n"
        resultado += texto_pagina
        resultado += "\n" + "-" * 80 + "\n\n"
        
        return resultado
    
    def _interpretar_linha_tabela(self, linha, contexto_anterior):
        """
        Interpreta uma linha de tabela e retorna explicação textual
        """
        linha_lower = linha.lower()
        
        # Extrair componentes
        especie = None
        dose = None
        via = None
        frequencia = None
        temperatura = None
        intervalo = None
        
        # Espécie
        especies_map = {
            'suínos': 'Suínos', 'suino': 'Suínos', 'porco': 'Suínos',
            'bovinos': 'Bovinos', 'bovino': 'Bovinos', 'vaca': 'Bovinos',
            'equinos': 'Equinos', 'equino': 'Equinos', 'cavalo': 'Equinos',
            'cães': 'Cães', 'cão': 'Cães', 'cao': 'Cães', 'cachorro': 'Cães',
            'gatos': 'Gatos', 'gato': 'Gatos',
            'aves': 'Aves', 'galinhas': 'Aves', 'frangos': 'Aves',
            'ovinos': 'Ovinos', 'ovelha': 'Ovinos',
            'caprinos': 'Caprinos', 'cabra': 'Caprinos',
            'peru': 'Peru', 'perus': 'Peru'
        }
        
        for key, value in especies_map.items():
            if key in linha_lower:
                especie = value
                break
        
        # Dose (mg/kg, ml/kg, etc)
        dose_match = re.search(r'(\d+\.?\d*)\s*(mg|ml|mcg|µg)\s*/\s*(kg|quilograma)', linha, re.IGNORECASE)
        if dose_match:
            dose = f"{dose_match.group(1)} {dose_match.group(2)}/{dose_match.group(3)}"
        
        # Via de administração
        vias = ['oral', 'im', 'intramuscular', 'sc', 'subcutânea', 'subcutanea', 
                'iv', 'intravenosa', 'tópica', 'topica']
        for v in vias:
            if v in linha_lower:
                via = v.upper() if len(v) <= 2 else v.capitalize()
                break
        
        # Frequência
        freq_match = re.search(r'(\d+)\s*(vez|vezes|x)\s*(ao dia|por dia|diária|diariamente)', linha_lower)
        if freq_match:
            frequencia = f"{freq_match.group(1)} vez(es) ao dia"
        
        # Temperatura
        temp_match = re.search(r'(\d+)\s*°?\s*c', linha_lower)
        if temp_match:
            temperatura = f"{temp_match.group(1)}°C"
        
        # Intervalo de segurança
        intervalo_match = re.search(r'(\d+)\s*(dias?|horas?)', linha_lower)
        if intervalo_match and 'intervalo' in contexto_anterior.lower():
            intervalo = f"{intervalo_match.group(1)} {intervalo_match.group(2)}"
        
        # Montar explicação
        if especie or dose or via or temperatura or intervalo:
            explicacao = ""
            if especie:
                explicacao += f"  🐾 Espécie: {especie}\n"
            if dose:
                explicacao += f"  💉 Dose: {dose}\n"
            if via:
                explicacao += f"  📍 Via: {via}\n"
            if frequencia:
                explicacao += f"  🕐 Frequência: {frequencia}\n"
            if temperatura:
                explicacao += f"  🌡️ Temperatura: {temperatura}\n"
            if intervalo:
                explicacao += f"  ⏰ Intervalo de segurança: {intervalo}\n"
            
            return explicacao
        
        return None
    
    def _limpar_texto_basico(self, texto):
        """Limpeza básica do texto"""
        # Remover cabeçalhos/rodapés
        texto = re.sub(
            r"\nDireção Geral de Alimentação e Veterinária.*?Página \d+ de \d+ \n", 
            "", 
            texto, 
            flags=re.DOTALL
        )
        
        # Normalizar quebras de linha
        texto = re.sub(r'\n{3,}', '\n\n', texto)
        
        return texto.strip()
    
    def _dividir_em_secoes(self, texto):
        """Divide texto em seções SEM remover conteúdo"""
        # Dividir por seções numeradas (1., 2., 3., etc)
        partes = re.split(r'\n(?=\d+\.\s)', texto)
        
        # Dividir também por marcadores de tabela
        secoes_finais = []
        for parte in partes:
            if '='*80 in parte:
                # Já é uma seção de tabela processada
                secoes_finais.append(parte.strip())
            else:
                secoes_finais.append(parte.strip())
        
        return [s for s in secoes_finais if s]


class PDFProcessor:
    """Classe dedicada ao processamento avançado de PDFs"""
    
    def __init__(self):
        self.secoes_importantes = [
            '1.', '2.', '3.', '4.', '5.', '6.',  # Seções numeradas
            'composição', 'indicações', 'posologia', 'contra-indicações',
            'advertências', 'reações adversas', 'interações', 'sobredosagem',
            'propriedades', 'incompatibilidades', 'validade', 'armazenamento',
            'titular', 'fabricante', 'data de aprovação'
        ]
    
    def extrair_e_processar_pdf(self, pdf_path):
        """
        Extrai texto do PDF com tratamento especial para tabelas
        e remove duplicações
        """
        try:
            texto_completo = []
            
            with fitz.open(pdf_path) as pdf_file:
                for page_num, page in enumerate(pdf_file):
                    # Extrair texto normal
                    texto_pagina = page.get_text()
                    
                    # Tentar extrair tabelas estruturadas
                    tabelas = self._extrair_tabelas_estruturadas(page)
                    
                    if tabelas:
                        # Se encontrou tabelas, processar separadamente
                        texto_processado = self._processar_pagina_com_tabelas(
                            texto_pagina, 
                            tabelas, 
                            page_num
                        )
                    else:
                        texto_processado = texto_pagina
                    
                    texto_completo.append(texto_processado)
            
            # Juntar todo o texto
            texto_unificado = "\n\n".join(texto_completo)
            
            # Limpar e formatar
            texto_limpo = self._limpar_texto_pdf(texto_unificado)
            
            # Dividir em seções e remover duplicações
            secoes = self._dividir_em_secoes_sem_duplicacao(texto_limpo)
            
            return secoes
            
        except Exception as e:
            print(f"Erro ao processar PDF: {e}")
            return []
    
    def _extrair_tabelas_estruturadas(self, page):
        """
        Tenta identificar e extrair tabelas do PDF usando análise de layout
        """
        tabelas = []
        
        try:
            # Obter blocos de texto com coordenadas
            blocos = page.get_text("dict")["blocks"]
            
            # Identificar possíveis tabelas (blocos alinhados verticalmente)
            linhas_tabela = []
            linha_atual = []
            y_anterior = None
            
            for bloco in blocos:
                if "lines" in bloco:
                    for linha in bloco["lines"]:
                        for span in linha["spans"]:
                            texto = span["text"].strip()
                            if texto:
                                y = span["bbox"][1]  # coordenada y
                                x = span["bbox"][0]  # coordenada x
                                
                                # Se mudou de linha (y diferente)
                                if y_anterior is not None and abs(y - y_anterior) > 5:
                                    if len(linha_atual) > 1:  # Linha com múltiplas colunas
                                        linhas_tabela.append(sorted(linha_atual, key=lambda item: item[1]))
                                    linha_atual = []
                                
                                linha_atual.append((texto, x, y))
                                y_anterior = y
            
            # Adicionar última linha
            if len(linha_atual) > 1:
                linhas_tabela.append(sorted(linha_atual, key=lambda item: item[1]))
            
            # Se encontrou estrutura tabular, formatar
            if len(linhas_tabela) >= 2:
                tabela_formatada = self._formatar_tabela(linhas_tabela)
                if tabela_formatada:
                    tabelas.append(tabela_formatada)
        
        except Exception as e:
            print(f"Erro ao extrair tabelas: {e}")
        
        return tabelas
    
    def _formatar_tabela(self, linhas_tabela):
        """
        Formata linhas de tabela em texto estruturado legível
        """
        if not linhas_tabela:
            return None
        
        # Verificar se é realmente uma tabela (consistência de colunas)
        num_colunas = [len(linha) for linha in linhas_tabela]
        if len(set(num_colunas)) > 2:  # Muita variação no número de colunas
            return None
        
        # Formatar como tabela markdown-like
        tabela_texto = "\n=== TABELA ===\n"
        
        # Primeira linha como cabeçalho (se aplicável)
        if linhas_tabela:
            cabecalho = " | ".join([item[0] for item in linhas_tabela[0]])
            tabela_texto += cabecalho + "\n"
            tabela_texto += "-" * len(cabecalho) + "\n"
        
        # Demais linhas como dados
        for linha in linhas_tabela[1:]:
            linha_texto = " | ".join([item[0] for item in linha])
            tabela_texto += linha_texto + "\n"
        
        tabela_texto += "=== FIM TABELA ===\n"
        
        return tabela_texto
    
    def _processar_pagina_com_tabelas(self, texto_pagina, tabelas, page_num):
        """
        Combina texto normal com tabelas formatadas
        """
        resultado = f"\n--- Página {page_num + 1} ---\n"
        resultado += texto_pagina
        
        for i, tabela in enumerate(tabelas):
            resultado += f"\n\n{tabela}\n"
        
        return resultado
    
    def _limpar_texto_pdf(self, texto):
        """
        Limpa texto do PDF removendo artefatos comuns
        """
        # Remover cabeçalhos/rodapés repetitivos
        texto = re.sub(
            r"\nDireção Geral de Alimentação e Veterinária.*?Página \d+ de \d+ \n", 
            "", 
            texto, 
            flags=re.DOTALL
        )
        
        # Normalizar quebras de linha múltiplas
        texto = re.sub(r'\n{3,}', '\n\n', texto)
        
        # Remover espaços em excesso
        texto = re.sub(r' {2,}', ' ', texto)
        
        return texto.strip()
    
    def _dividir_em_secoes_sem_duplicacao(self, texto):
        """
        Divide o texto em seções E remove conteúdo duplicado
        """
        # Dividir por seções numeradas principais (1., 2., 3., etc)
        # MAS manter TODO o conteúdo (incluindo após FOLHETO)
        
        partes = re.split(r'\n(?=\d+\.\s)', texto)
        
        # Usar OrderedDict para manter ordem e remover duplicações
        secoes_unicas = OrderedDict()
        
        for parte in partes:
            if not parte.strip():
                continue
            
            # Gerar hash do conteúdo para detectar duplicações
            conteudo_normalizado = self._normalizar_para_comparacao(parte)
            hash_conteudo = hash(conteudo_normalizado)
            
            # Se não existe ainda, adicionar
            if hash_conteudo not in secoes_unicas:
                secoes_unicas[hash_conteudo] = parte.strip()
            else:
                # Se existe, verificar se a nova versão tem mais informações
                parte_existente = secoes_unicas[hash_conteudo]
                if len(parte.strip()) > len(parte_existente):
                    secoes_unicas[hash_conteudo] = parte.strip()
        
        # Retornar lista de seções únicas
        return list(secoes_unicas.values())
    
    def _normalizar_para_comparacao(self, texto):
        """
        Normaliza texto para comparação (remove espaços, pontuação, etc)
        """
        # Converter para minúsculas
        texto_norm = texto.lower()
        
        # Remover pontuação e espaços extras
        texto_norm = re.sub(r'[^\w\s]', '', texto_norm)
        texto_norm = re.sub(r'\s+', ' ', texto_norm)
        
        return texto_norm.strip()
    
    def formatar_conteudo_para_ollama(self, secoes, pergunta):
        """
        Formata seções do PDF de maneira otimizada para o Ollama,
        com ênfase especial em tabelas
        """
        # Identificar seções relevantes para a pergunta
        secoes_relevantes = self._filtrar_secoes_relevantes(secoes, pergunta)
        
        # Formatar para melhor compreensão
        texto_formatado = []
        
        for i, secao in enumerate(secoes_relevantes):
            # Detectar se tem tabela
            if '=== TABELA ===' in secao:
                # Processar tabela de forma especial
                texto_formatado.append(
                    self._formatar_secao_com_tabela(secao, i)
                )
            else:
                # Seção normal
                texto_formatado.append(f"\n### Seção {i+1}\n{secao}\n")
        
        return texto_formatado
    
    def _filtrar_secoes_relevantes(self, secoes, pergunta):
        """
        Filtra seções mais relevantes para a pergunta
        """
        pergunta_lower = pergunta.lower()
        palavras_chave = pergunta_lower.split()
        
        # Pontuar cada seção por relevância
        secoes_pontuadas = []
        
        for secao in secoes:
            secao_lower = secao.lower()
            pontuacao = 0
            
            # Pontos por palavra-chave encontrada
            for palavra in palavras_chave:
                if len(palavra) > 3:  # Ignorar palavras muito curtas
                    pontuacao += secao_lower.count(palavra) * 2
            
            # Pontos extras para seções importantes
            for termo_importante in self.secoes_importantes:
                if termo_importante in secao_lower:
                    pontuacao += 5
            
            # Pontos extras para tabelas
            if '=== TABELA ===' in secao:
                pontuacao += 10
            
            secoes_pontuadas.append((secao, pontuacao))
        
        # Ordenar por pontuação e retornar top seções
        secoes_pontuadas.sort(key=lambda x: x[1], reverse=True)
        
        # Retornar todas com pontuação > 0, ou pelo menos as 10 primeiras
        secoes_relevantes = [s[0] for s in secoes_pontuadas if s[1] > 0]
        
        if not secoes_relevantes:
            secoes_relevantes = [s[0] for s in secoes_pontuadas[:10]]
        
        return secoes_relevantes
    
    def _formatar_secao_com_tabela(self, secao, indice):
        """
        Formata seção que contém tabela de forma especial para o Ollama
        """
        resultado = f"\n### Seção {indice+1} [CONTÉM TABELA]\n"
        resultado += "⚠️ ATENÇÃO: Esta seção contém dados tabulares. Leia linha por linha.\n\n"
        
        # Extrair e reformatar a tabela
        partes = secao.split('=== TABELA ===')
        
        # Texto antes da tabela
        if partes[0].strip():
            resultado += "Contexto:\n" + partes[0].strip() + "\n\n"
        
        # Tabela
        if len(partes) > 1:
            tabela_parte = partes[1].split('=== FIM TABELA ===')[0]
            
            resultado += "DADOS TABULARES (leia cuidadosamente):\n"
            resultado += "```\n"
            resultado += tabela_parte.strip()
            resultado += "\n```\n\n"
            
            # Converter tabela para formato mais explícito
            resultado += "INTERPRETAÇÃO DA TABELA:\n"
            linhas = [l.strip() for l in tabela_parte.strip().split('\n') if l.strip() and not l.startswith('-')]
            
            if linhas:
                # Primeira linha = cabeçalhos
                cabecalhos = [c.strip() for c in linhas[0].split('|') if c.strip()]
                resultado += f"Colunas: {', '.join(cabecalhos)}\n\n"
                
                # Demais linhas = dados
                for i, linha in enumerate(linhas[1:], 1):
                    valores = [v.strip() for v in linha.split('|') if v.strip()]
                    resultado += f"Linha {i}:\n"
                    for j, valor in enumerate(valores):
                        if j < len(cabecalhos):
                            resultado += f"  - {cabecalhos[j]}: {valor}\n"
                    resultado += "\n"
        
        # Texto depois da tabela
        if len(partes) > 1 and '=== FIM TABELA ===' in partes[1]:
            texto_depois = partes[1].split('=== FIM TABELA ===')[1].strip()
            if texto_depois:
                resultado += "Informações adicionais:\n" + texto_depois + "\n"
        
        return resultado



#Força flush automático em todos os prints
_original_print = print
def print(*args, **kwargs):
    _original_print(*args, **kwargs)
    if 'file' not in kwargs or kwargs['file'] == sys.stdout:
        sys.stdout.flush()

class CacheManager:
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

def formatar_links_resposta(resposta, dados_scraping):
    """
    Substitui URLs longas por referências numeradas elegantes
    Exemplo: https://medvet.dgav.pt/... → [Fonte 1]
    """
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
    
    # Adicionar lista de fontes no final
    if urls_encontradas:
        resposta_formatada += "\n\n📚 **Fontes:**\n"
        for url, numero in sorted(urls_encontradas.items(), key=lambda x: x[1]):
            # Tentar encontrar o nome do medicamento correspondente
            nome_medicamento = "Informação"
            for item in dados_scraping:
                if item.get('url') == url:
                    nome_medicamento = item.get('nome', 'Informação')
                    break
            
            resposta_formatada += f"{numero}. {nome_medicamento}: {url}\n"
    
    return resposta_formatada

class SistemaConsultaVetOtimizado:
    def __init__(self, modelo_ollama=MODELO_OLLAMA_PADRAO, temperatura_ollama=0.0):
        self.modelo_ollama = modelo_ollama
        self.temperatura_ollama = temperatura_ollama
        
        # NOVO: Usar wrapper seguro
        self.ollama_seguro = OllamaWrapperSeguro(model=modelo_ollama)
        
        self.query_classifier = QueryClassifier(modelo_ollama)
        self.mapeamento_especies = self._criar_mapeamento_especies()
        
        # Contexto de conversação otimizado
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
            "metadados_scraping": None
        }
        
        self._pdf_cache = {}
        self.session = None

        self.tempos_execucao = {
            'inicio_total': 0,
            'classificacao': 0,
            'web_scraping': 0,
            'extracao_pdf': 0,
            'filtragem_pdf': 0,
            'busca_direta': 0,
            'ollama': 0,
            'formatacao': 0,
            'total': 0
        }

    def _gerar_cache_key_inteligente(self, classificacao):
        """
        Gera chave de cache considerando medicamento + tipo de informação
        CORRIGIDO: Agora diferencia perguntas sobre o mesmo medicamento
        """
        entidades = classificacao.get("entidades", {})
        categoria = classificacao.get("categoria", "")
        pergunta_ollama = entidades.get("pergunta_ollama", "").lower()
        
        if categoria == "medicamento":
            medicamento = entidades.get("termo_busca", "").lower().strip()
            especie = entidades.get("especie_alvo", "").lower().strip()
            
            # NOVO: Identificar o TIPO de informação solicitada
            tipo_info = self._identificar_tipo_informacao(pergunta_ollama)
            
            # Chave: categoria + medicamento + tipo_info + especie
            key_parts = [categoria, medicamento, tipo_info, especie]
            
        elif categoria == "comparacao":
            key_parts = [
                categoria,
                entidades.get("substancia_ativa", "").lower().strip(),
                entidades.get("especie_alvo", "").lower().strip(),
                entidades.get("forma_farmaceutica", "").lower().strip()
            ]
        else:
            key_parts = [categoria, entidades.get("pergunta_ollama", "").lower()]
        
        key_parts = [part for part in key_parts if part]
        cache_key = "_".join(key_parts)
        return hashlib.md5(cache_key.encode('utf-8')).hexdigest()
    
    def _identificar_tipo_informacao(self, pergunta):
        """
        Identifica o tipo de informação solicitada na pergunta
        Retorna uma string que representa o tipo
        """
        pergunta_lower = pergunta.lower()
        
        # Mapeamento de palavras-chave para tipos
        tipos_info = {
            'dose': ['dose', 'dosagem', 'posologia', 'quanto administrar'],
            'armazenamento': ['armazenamento', 'armazenar', 'conservar', 'conservação', 'guardar', 'validade'],
            'administracao': ['administração', 'administrar', 'forma de administração', 'via de administração', 'como usar'],
            'composicao': ['composição', 'princípio ativo', 'substância ativa', 'componentes'],
            'indicacao': ['indicação', 'indicado', 'usado para', 'serve para', 'para que', 'utilização'],
            'especies': ['espécies', 'espécie', 'animais', 'espécies-alvo', 'para que espécies'],
            'reacoes': ['reações adversas', 'efeitos colaterais', 'efeitos indesejáveis', 'reações'],
            'intervalos': ['intervalos', 'intervalo de segurança', 'tempo de espera', 'carência'],
            'contraindicacoes': ['contraindicações', 'contraindicação', 'não deve ser usado'],
            'receita': ['receita médica', 'receita veterinária', 'prescrição'],
            'fabricante': ['fabricante', 'laboratório', 'titular'],
            'apresentacao': ['apresentação', 'embalagem', 'forma farmacêutica']
        }
        
        # Verificar qual tipo corresponde à pergunta
        for tipo, palavras_chave in tipos_info.items():
            if any(palavra in pergunta_lower for palavra in palavras_chave):
                return tipo
        
        # Se não identificou tipo específico, retorna hash da pergunta
        # Isso garante que perguntas diferentes terão caches diferentes
        return hashlib.md5(pergunta.encode('utf-8')).hexdigest()[:8]
    
    def _imprimir_resumo_tempos(self):
        """Imprime um resumo detalhado dos tempos de execução"""
        print(colored("\n" + "="*60, "cyan"))
        print(colored("📊 RESUMO DE TEMPOS DE EXECUÇÃO", "cyan", attrs=['bold']))
        print(colored("="*60, "cyan"))
        
        tempos = self.tempos_execucao
        total = tempos.get('total', 0)
        
        if tempos.get('classificacao', 0) > 0:
            print(colored(f"  🔍 Classificação:     {tempos['classificacao']:>6.2f}s  ({tempos['classificacao']/total*100:>5.1f}%)", "yellow"))
        
        if tempos.get('web_scraping', 0) > 0:
            print(colored(f"  🌐 Web Scraping:      {tempos['web_scraping']:>6.2f}s  ({tempos['web_scraping']/total*100:>5.1f}%)", "yellow"))
        
        if tempos.get('extracao_pdf', 0) > 0:
            print(colored(f"  📄 Extração PDF:      {tempos['extracao_pdf']:>6.2f}s  ({tempos['extracao_pdf']/total*100:>5.1f}%)", "yellow"))
        
        if tempos.get('filtragem_pdf', 0) > 0:
            print(colored(f"  🔎 Filtragem PDF:     {tempos['filtragem_pdf']:>6.2f}s  ({tempos['filtragem_pdf']/total*100:>5.1f}%)", "yellow"))
        
        if tempos.get('busca_direta', 0) > 0:
            print(colored(f"  🎯 Busca Direta:      {tempos['busca_direta']:>6.2f}s  ({tempos['busca_direta']/total*100:>5.1f}%)", "yellow"))
        
        if tempos.get('ollama', 0) > 0:
            print(colored(f"  🤖 Ollama:            {tempos['ollama']:>6.2f}s  ({tempos['ollama']/total*100:>5.1f}%)", "yellow"))
        
        if tempos.get('formatacao', 0) > 0:
            print(colored(f"  ✨ Formatação:        {tempos['formatacao']:>6.2f}s  ({tempos['formatacao']/total*100:>5.1f}%)", "yellow"))
        
        print(colored("  " + "-"*58, "cyan"))
        print(colored(f"  ⏱️  TEMPO TOTAL:       {total:>6.2f}s  (100.0%)", "green", attrs=['bold']))
        print(colored("="*60 + "\n", "cyan"))

    def _verificar_intencao_similar(self, pergunta_atual, pergunta_cache):
        prompt = f"Analise se as perguntas têm mesma intenção: 1: '{pergunta_atual}' 2: '{pergunta_cache}'. Responda apenas SIM ou NAO."
        try:
            response = ollama.chat(
                model=self.modelo_ollama,
                messages=[{'role': 'system', 'content': 'Analisador de intenções. Responda apenas SIM ou NAO.'},
                         {'role': 'user', 'content': prompt}],
                options={'temperature': 0.0}
            )
            return response['message']['content'].strip().upper() == "SIM"
        except:
            return False

    def _carregar_resposta_cache_inteligente(self, classificacao, pergunta_atual):
        cache_key = self._gerar_cache_key_inteligente(classificacao)
        arquivo_cache = os.path.join(CACHE_DIR_RESPOSTAS, f"smart_{cache_key}.json")
        
        if not os.path.exists(arquivo_cache):
            return None
        
        try:
            cache_age = time.time() - os.path.getmtime(arquivo_cache)
            if cache_age > CACHE_TTL:
                return None
                
            with open(arquivo_cache, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            entidades_cache = cache_data.get('entidades', {})
            entidades_atual = classificacao.get('entidades', {})
            
            categoria = classificacao.get('categoria')
            if categoria == "medicamento":
                if (entidades_cache.get('termo_busca', '').lower().strip() != 
                    entidades_atual.get('termo_busca', '').lower().strip()):
                    return None
                    
            pergunta_cache = cache_data.get('pergunta_original', '')
            if self._verificar_intencao_rapida(pergunta_atual, pergunta_cache):
                return cache_data.get('resposta')
                
        except Exception:
            return None
        
        return None

    def _verificar_intencao_rapida(self, pergunta1, pergunta2):
        """
        Verifica se duas perguntas têm a mesma intenção
        CORRIGIDO: Agora considera o tipo de informação solicitada
        """
        p1 = pergunta1.lower().strip()
        p2 = pergunta2.lower().strip()
        
        # Se são exatamente iguais
        if p1 == p2:
            return True
        
        # Se uma contém a outra completamente
        if p1 in p2 or p2 in p1:
            # MAS: verificar se o tipo de informação é o mesmo
            tipo1 = self._identificar_tipo_informacao(p1)
            tipo2 = self._identificar_tipo_informacao(p2)
            
            # Só considera mesma intenção se o tipo for igual
            if tipo1 != tipo2:
                return False
            return True
        
        # Verificar similaridade por palavras
        palavras1 = set(p1.split())
        palavras2 = set(p2.split())
        palavras_comuns = palavras1.intersection(palavras2)
        
        # Se tem muitas palavras em comum
        if (len(palavras_comuns) / max(len(palavras1), len(palavras2))) > 0.7:
            # Verificar se o tipo de informação é o mesmo
            tipo1 = self._identificar_tipo_informacao(p1)
            tipo2 = self._identificar_tipo_informacao(p2)
            
            # Só considera mesma intenção se o tipo for igual
            if tipo1 != tipo2:
                return False
            return True
        
        # Última verificação: usar Ollama apenas se realmente necessário
        return self._verificar_intencao_similar(pergunta1, pergunta2)

    def _salvar_resposta_cache_inteligente(self, classificacao, pergunta_original, resposta):
        cache_key = self._gerar_cache_key_inteligente(classificacao)
        arquivo_cache = os.path.join(CACHE_DIR_RESPOSTAS, f"smart_{cache_key}.json")
        
        cache_data = {
            'resposta': resposta,
            'pergunta_original': pergunta_original,
            'categoria': classificacao.get('categoria'),
            'entidades': classificacao.get('entidades', {}),
            'timestamp': time.time(),
            'modelo_usado': self.modelo_ollama
        }
        
        try:
            with open(arquivo_cache, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(colored(f"Erro ao salvar cache inteligente: {e}", "red"))

    # Métodos de consulta Ollama otimizados
    def _consultar_ollama_otimizado(self, pergunta_ollama, contexto_dados, tipo_consulta="medicamento", classificacao=None, pergunta_original=None):
        """
        Consulta o Ollama com validação de doses e prompts especializados
        VERSÃO COMPLETA - Compatível com ollama 0.12.9
        """
        
        # ========== CACHE INTELIGENTE ==========
        if classificacao and pergunta_original:
            resposta_cache = self._carregar_resposta_cache_inteligente(classificacao, pergunta_original)
            if resposta_cache:
                print(colored("✓ Resposta do cache inteligente", "green"))
                return formatar_links_resposta(resposta_cache, contexto_dados)

        # ========== PREPARAR CONTEXTO ==========
        tem_pdf = False
        contexto_pdf_completo = []
        contexto_pdf_filtrado = []
        medicamento_nome = ""
        especie_alvo = ""
        
        if contexto_dados and len(contexto_dados) > 0:
            primeiro_item = contexto_dados[0]
            medicamento_nome = primeiro_item.get('nome', '')
            
            # Extrair espécie se tiver
            entidades = classificacao.get('entidades', {}) if classificacao else {}
            especie_alvo = entidades.get('especie_alvo', '')
            
            if primeiro_item.get('conteudo_pdf'):
                tem_pdf = True
                contexto_pdf_completo = primeiro_item.get('conteudo_pdf')
                
                # Filtrar seções relevantes
                tempo_inicio_filtragem = time.perf_counter()
                contexto_pdf_filtrado = self._extrair_secoes_relevantes_pdf(
                    contexto_pdf_completo, 
                    pergunta_ollama
                )
                tempo_filtragem = time.perf_counter() - tempo_inicio_filtragem
                self.tempos_execucao['filtragem_pdf'] = tempo_filtragem
                
                print(colored(f"📄 Seções do PDF filtradas: {len(contexto_pdf_filtrado)}/{len(contexto_pdf_completo)}", "cyan"))
                print(colored(f"⏱️  Filtragem PDF: {tempo_filtragem:.2f}s", "yellow"))
        
        # ========== BUSCA DIRETA ==========
        busca_direta = None
        tipo_info = None
        
        if tem_pdf:
            pergunta_lower = pergunta_ollama.lower()
            
            # Identificar tipo de informação
            if any(palavra in pergunta_lower for palavra in ['dose', 'dosagem', 'posologia']):
                tipo_info = "dosagem"
            elif any(palavra in pergunta_lower for palavra in ['armazenamento', 'armazenar', 'conservar']):
                tipo_info = "armazenamento"
            elif any(palavra in pergunta_lower for palavra in ['espécie', 'especie', 'animal', 'indicado']):
                tipo_info = "especies"
            
            if tipo_info:
                tempo_inicio_busca = time.perf_counter()
                busca_direta = self._buscar_informacao_direta_pdf(
                    contexto_pdf_completo,
                    tipo_info,
                    especie_alvo
                )
                tempo_busca = time.perf_counter() - tempo_inicio_busca
                self.tempos_execucao['busca_direta'] = tempo_busca
                print(colored(f"⏱️  Busca Direta: {tempo_busca:.2f}s", "yellow"))
                
                if busca_direta and busca_direta['encontrado']:
                    print(colored(f"✅ Busca direta encontrou: {tipo_info}", "green"))
                else:
                    print(colored(f"⚠️  Busca direta não encontrou: {tipo_info}", "yellow"))
        
        # ========== VALIDAÇÃO ESPECIAL PARA DOSES ==========
        pergunta_lower = pergunta_ollama.lower()
        is_pergunta_dose = any(palavra in pergunta_lower for palavra in ['dose', 'dosagem', 'posologia'])

        if busca_direta and busca_direta['encontrado'] and is_pergunta_dose:
            doses_extraidas = busca_direta.get('info_extraida', {}).get('doses', [])
            
            if doses_extraidas:
                print(colored(f"🎯 Pergunta sobre DOSE detectada - Usando validação rigorosa", "yellow"))
                print(colored(f"📋 Doses válidas extraídas do documento: {doses_extraidas}", "cyan"))
                
                # Usar prompt super-restritivo para doses
                prompt = self._gerar_prompt_super_restritivo_dose(
                    pergunta_ollama,
                    contexto_pdf_filtrado if contexto_pdf_filtrado else contexto_pdf_completo,
                    medicamento_nome,
                    doses_extraidas
                )
                
                try:
                    print(colored("🤖 Consultando Ollama (modo dose)...", "yellow"))
                    tempo_inicio_ollama = time.perf_counter()
                    
                    # CORRIGIDO: Definir system_prompt ANTES de usar
                    system_prompt_dose = """Você é um especialista veterinário PORTUGUÊS.

        ⚠️ REGRAS OBRIGATÓRIAS:
        1. RESPONDA SEMPRE EM PORTUGUÊS (pt-PT ou pt-BR)
        2. NUNCA use inglês, espanhol ou outros idiomas
        3. Você é um extrator de doses EXATO. Use APENAS valores do documento.
        4. NUNCA invente doses ou valores
        5. Se não encontrar, diga: "Informação não encontrada no documento"

        IMPORTANTE: Extraia APENAS as doses que estão explicitamente no documento fornecido."""
                    
                    # SUBSTITUIR: ollama.chat -> self.ollama_seguro.chat
                    response = self.ollama_seguro.chat(
                        messages=[
                            {
                                'role': 'system',
                                'content': system_prompt_dose  # ← USAR VARIÁVEL CORRETA
                            },
                            {
                                'role': 'user',
                                'content': prompt,
                            }
                        ],
                        options={
                            'temperature': 0.0,
                            'num_predict': 1000,
                            'top_p': 0.9,
                            'timeout': 120
                        }
                    )
                    
                    tempo_ollama = time.perf_counter() - tempo_inicio_ollama
                    self.tempos_execucao['ollama'] = tempo_ollama
                    
                    # VALIDAR ESTRUTURA DA RESPOSTA (compatível 0.12.9)
                    resposta_ollama = None
                    
                    if isinstance(response, dict):
                        if 'message' in response and isinstance(response['message'], dict):
                            resposta_ollama = response['message'].get('content')
                        elif 'content' in response:
                            resposta_ollama = response['content']
                    elif isinstance(response, str):
                        resposta_ollama = response
                    
                    if not resposta_ollama:
                        print(colored(f"❌ Estrutura inesperada: {response.keys() if isinstance(response, dict) else type(response)}", "red"))
                        return "Erro: Não foi possível extrair resposta do modelo"
                    
                    print(colored(f"⏱️  Ollama: {tempo_ollama:.2f}s", "green"))
                    
                    # VALIDAÇÃO: Verificar se resposta inventou doses
                    valido, resposta_validada = self._validar_resposta_dose(resposta_ollama, doses_extraidas, pergunta_ollama)
                    
                    if not valido:
                        resposta_ollama = resposta_validada  # Usar resposta corrigida
                    
                    # VALIDAÇÃO: Detectar idioma errado
                    if self._detectar_idioma_errado(resposta_ollama):
                        print(colored("⚠️ RESPOSTA EM IDIOMA ERRADO - Tentando correção...", "yellow"))
                        resposta_ollama = self._corrigir_idioma_resposta(resposta_ollama)
                    
                    # Salvar em cache
                    if classificacao and pergunta_original:
                        self._salvar_resposta_cache_inteligente(classificacao, pergunta_original, resposta_ollama)
                    
                    # Formatar links
                    resposta_ollama = formatar_links_resposta(resposta_ollama, contexto_dados)
                    
                    return resposta_ollama
                    
                except Exception as e:
                    print(colored(f"❌ Erro ao consultar Ollama (modo dose): {e}", "red"))
                    import traceback
                    traceback.print_exc()
                    # Continuar com fluxo normal abaixo
        
        # ========== GERAR PROMPT (FLUXO NORMAL) ==========
        if tem_pdf and contexto_pdf_filtrado:
            prompt = self._gerar_prompt_direto(
                pergunta_ollama,
                contexto_pdf_filtrado,
                medicamento_nome,
                busca_direta
            )
        else:
            contexto_otimizado = self._comprimir_contexto_ollama(contexto_dados, tipo_consulta, pergunta_ollama)
            prompt = self._gerar_prompt_otimizado(pergunta_ollama, contexto_otimizado, tipo_consulta)
        
        # ========== CONSULTAR OLLAMA (FLUXO NORMAL) ==========
        try:
            print(colored("🤖 Consultando Ollama...", "yellow"))
            tempo_inicio_ollama = time.perf_counter()
            
            # ATUALIZADO: System prompt mais explícito
            system_prompt = """Você é um especialista veterinário PORTUGUÊS.

    ⚠️ REGRAS OBRIGATÓRIAS:
    1. RESPONDA SEMPRE EM PORTUGUÊS (pt-PT ou pt-BR)
    2. NUNCA use inglês, espanhol ou outros idiomas
    3. Extraia informações EXATAS do documento fornecido
    4. NÃO invente doses, valores ou informações
    5. Se não encontrar, diga: "Informação não encontrada no documento"

    IMPORTANTE: Leia cuidadosamente o documento e extraia TODAS as informações relevantes solicitadas. Seja específico e completo."""
            
            response = ollama.chat(
                model=self.modelo_ollama,
                messages=[
                    {
                        'role': 'system',
                        'content': system_prompt
                    },
                    {
                        'role': 'user',
                        'content': prompt,
                    }
                ],
                options={
                    'temperature': 0.0,
                    'num_predict': 1000,
                    'top_p': 0.9,
                    'timeout': 120
                }
            )
            
            tempo_ollama = time.perf_counter() - tempo_inicio_ollama
            self.tempos_execucao['ollama'] = tempo_ollama
            
            # ========== VALIDAR ESTRUTURA DA RESPOSTA (compatível 0.12.9) ==========
            resposta_ollama = None
            
            if isinstance(response, dict):
                if 'message' in response and isinstance(response['message'], dict):
                    resposta_ollama = response['message'].get('content')
                elif 'content' in response:
                    resposta_ollama = response['content']
            elif isinstance(response, str):
                resposta_ollama = response
            
            if not resposta_ollama:
                print(colored(f"❌ Estrutura inesperada: {response.keys() if isinstance(response, dict) else type(response)}", "red"))
                return "Erro: Não foi possível extrair resposta do modelo"
            
            print(colored(f"⏱️  Ollama: {tempo_ollama:.2f}s", "green"))
            
            # ========== VALIDAÇÕES PÓS-RESPOSTA ==========
            
            # VALIDAÇÃO 1: Detectar idioma errado
            if self._detectar_idioma_errado(resposta_ollama):
                print(colored("⚠️ RESPOSTA EM IDIOMA ERRADO - Tentando correção...", "yellow"))
                resposta_ollama = self._corrigir_idioma_resposta(resposta_ollama)
                
                # Se ainda estiver errado, forçar resposta em português
                if self._detectar_idioma_errado(resposta_ollama):
                    print(colored("❌ Correção falhou - Forçando nova geração", "red"))
                    return self._gerar_resposta_forcada_portugues(pergunta_ollama, contexto_dados)
            
            # VALIDAÇÃO 2: Verificar qualidade da resposta
            if self._resposta_muito_vaga(resposta_ollama):
                print(colored("⚠️ Resposta muito vaga", "yellow"))
            
            # VALIDAÇÃO 3: Se busca direta encontrou mas resposta diz "não encontrado"
            if busca_direta and busca_direta['encontrado']:
                if any(frase in resposta_ollama.lower() for frase in ['não foi encontrada', 'não encontrei', 'não há informação']):
                    print(colored("⚠️ Resposta vaga mas busca direta encontrou - forçando resposta direta", "yellow"))
                    
                    info_extraida = busca_direta.get('info_extraida', {})
                    if isinstance(info_extraida, dict):
                        resposta_ollama = f"Segundo o documento:\n\n"
                        for chave, valor in info_extraida.items():
                            if isinstance(valor, list):
                                resposta_ollama += f"**{chave.title()}:**\n"
                                for item in valor:
                                    resposta_ollama += f"- {item}\n"
                            else:
                                resposta_ollama += f"**{chave.title()}:** {valor}\n"
            
            # ========== FORMATAÇÃO E CACHE ==========
            tempo_inicio_formatacao = time.perf_counter()
            resposta_ollama = formatar_links_resposta(resposta_ollama, contexto_dados)
            tempo_formatacao = time.perf_counter() - tempo_inicio_formatacao
            self.tempos_execucao['formatacao'] = tempo_formatacao
            
            # Salvar em cache
            if classificacao and pergunta_original:
                self._salvar_resposta_cache_inteligente(classificacao, pergunta_original, resposta_ollama)
            
            return resposta_ollama
            
        except Exception as e:
            print(colored(f"❌ Erro ao consultar Ollama: {e}", "red"))
            import traceback
            traceback.print_exc()
            return f"Erro ao consultar Ollama: {e}"

    def _detectar_idioma_errado(self, texto):
        """
        Detecta se resposta está em inglês/espanhol
        VERSÃO MELHORADA: Mais rigorosa
        """
        texto_lower = texto.lower()
        
        # Palavras muito comuns em inglês (não existem em português)
        palavras_ingles = [
            'the', 'this', 'that', 'these', 'those',
            'according', 'document', 'information', 'dose', 'administration',
            'storage', 'species', 'indicated', 'should', 'must',
            'please', 'refer', 'consult', 'following'
        ]
        
        # Palavras muito comuns em espanhol
        palavras_espanhol = [
            'según', 'documento', 'información', 'dosis', 'administración',
            'está', 'debe', 'consulte', 'siguiente', 'contiene'
        ]
        
        # Contar palavras estrangeiras
        palavras_texto = texto_lower.split()
        total_palavras = len(palavras_texto)
        
        if total_palavras == 0:
            return False
        
        estrangeiras_ingles = sum(1 for p in palavras_ingles if p in palavras_texto)
        estrangeiras_espanhol = sum(1 for p in palavras_espanhol if p in palavras_texto)
        
        # Se mais de 10% das palavras são estrangeiras, está em idioma errado
        percentual_ingles = estrangeiras_ingles / total_palavras
        percentual_espanhol = estrangeiras_espanhol / total_palavras
        
        if percentual_ingles > 0.10 or percentual_espanhol > 0.10:
            print(colored(f"   🔍 Idioma detectado: {percentual_ingles*100:.1f}% inglês, {percentual_espanhol*100:.1f}% espanhol", "yellow"))
            return True
        
        return False

    def _corrigir_idioma_resposta(self, resposta_errada):
        """
        Tenta corrigir resposta em idioma errado traduzindo para português
        """
        try:
            print(colored("   🔄 Tentando traduzir para português...", "cyan"))
            
            response = ollama.chat(
                model=self.modelo_ollama,
                messages=[
                    {
                        'role': 'system',
                        'content': 'Você é um tradutor. Traduza EXATAMENTE o texto abaixo para PORTUGUÊS. Não adicione nem remova informações.'
                    },
                    {
                        'role': 'user',
                        'content': f"Traduza para português:\n\n{resposta_errada}"
                    }
                ],
                options={'temperature': 0.0}
            )
            
            # Extrair resposta (compatível com 0.12.9)
            if isinstance(response, dict):
                if 'message' in response and 'content' in response['message']:
                    return response['message']['content']
                elif 'content' in response:
                    return response['content']
            
            return resposta_errada
            
        except Exception as e:
            print(colored(f"   ❌ Erro ao traduzir: {e}", "red"))
            return resposta_errada

    def _gerar_resposta_forcada_portugues(self, pergunta, contexto_dados):
        """
        Gera resposta forçada em português quando tudo mais falha
        """
        print(colored("   🔧 Gerando resposta forçada em português...", "yellow"))
        
        # Extrair informações básicas do contexto
        if contexto_dados and len(contexto_dados) > 0:
            medicamento = contexto_dados[0].get('nome', 'o medicamento consultado')
            
            return f"""⚠️ Não foi possível gerar resposta adequada em português.

    📋 Informações disponíveis sobre {medicamento}:
    - Consulte a bula completa do medicamento
    - URL: {contexto_dados[0].get('url', 'não disponível')}

    💡 Sugestão: Reformule a pergunta ou consulte diretamente o documento oficial."""
        
        return "Desculpe, não foi possível processar sua pergunta adequadamente. Por favor, reformule."

    def _resposta_muito_vaga(self, resposta):
        """
        Detecta se resposta é muito vaga/genérica
        """
        indicadores_vagos = [
            "não encontrei",
            "não foi possível encontrar",
            "não há informação",
            "não consta",
            "não está especificado",
            "consulte o veterinário",
            "consulte a bula",
            "informação não disponível"
        ]
        
        resposta_lower = resposta.lower()
        vagos = sum(1 for ind in indicadores_vagos if ind in resposta_lower)
        
        # Se tem muitos indicadores vagos E é muito curta
        if vagos >= 2 or (vagos >= 1 and len(resposta) < 100):
            return True
        
        return False
    def _comprimir_contexto_ollama(self, contexto_dados, tipo_consulta, pergunta_ollama):
        if not contexto_dados:
            return []
        
        contexto_str = json.dumps(contexto_dados, ensure_ascii=False)
        if len(contexto_str) <= CONTEXT_SIZE_LIMIT:
            return contexto_dados
        
        print(colored(f"Comprimindo contexto ({len(contexto_str)} chars)", "yellow"))
        contexto_comprimido = []
        
        if tipo_consulta == "medicamento":
            palavras_chave = pergunta_ollama.lower().split()
            
            for item in contexto_dados:
                item_comprimido = {'nome': item.get('nome'), 'url': item.get('url')}
                
                if item.get('conteudo_html'):
                    html = item['conteudo_html']
                    linhas_relevantes = []
                    for linha in html.split('\n'):
                        if any(palavra in linha.lower() for palavra in palavras_chave):
                            linhas_relevantes.append(linha)
                    
                    if linhas_relevantes:
                        item_comprimido['conteudo_html'] = '\n'.join(linhas_relevantes[:10])
                    else:
                        item_comprimido['conteudo_html'] = html[:500] + "..."
                
                if item.get('conteudo_pdf'):
                    item_comprimido['conteudo_pdf'] = item['conteudo_pdf'][:3]
                
                contexto_comprimido.append(item_comprimido)
        
        else:
            for item in contexto_dados[:3]:
                item_comprimido = {}
                for key, value in item.items():
                    if isinstance(value, str) and len(value) > 500:
                        item_comprimido[key] = value[:500] + "..."
                    elif isinstance(value, list) and len(value) > 3:
                        item_comprimido[key] = value[:3]
                    else:
                        item_comprimido[key] = value
                contexto_comprimido.append(item_comprimido)
        
        return contexto_comprimido

    def _gerar_prompt_otimizado(self, pergunta_ollama, contexto_otimizado, tipo_consulta):
        contexto_json = json.dumps(contexto_otimizado, ensure_ascii=False, indent=2)
        
        if tipo_consulta == "medicamento":
            return f"""
            CONTEXTO:
            ```json
            {contexto_json}
            ```

            PERGUNTA: "{pergunta_ollama}"

            INSTRUÇÕES:
            1. Responda APENAS com base no contexto
            2. Seja conciso e direto
            3. Se não encontrar, diga: "Não encontrei informações sobre isso no material disponível"
            4. Cite URLs quando aplicável

            RESPOSTA:
            """
        
        elif tipo_consulta == "comparacao":
            return f"""
            LISTA DE MEDICAMENTOS:
            ```json
            {contexto_json}
            ```

            COMPARAÇÃO: "{pergunta_ollama}"

            INSTRUÇÕES:
            1. Liste apenas medicamentos do contexto
            2. Compare características relevantes
            3. Seja objetivo e organize em tópicos
            4. Se não houver, informe: "Nenhum medicamento encontrado"

            RESPOSTA:
            """
        
        else:
            return f"Com base em: {contexto_json}\nResponda: {pergunta_ollama}"

    # Métodos de gerenciamento de contexto
    def _limpar_contexto_antigo(self, forcar_limpeza=False):
        current_time = time.time()
        
        scraping_data = self.contexto_conversacao.get("dados_ultimo_scraping")
        ultimo_scraping_time = self.contexto_conversacao.get("ultimo_scraping_time", 0)
        
        if scraping_data and (forcar_limpeza or current_time - ultimo_scraping_time > 600):
            print(colored("♻️  Limpando dados de scraping", "yellow"))
            self.contexto_conversacao["dados_ultimo_scraping"] = None
            
            if scraping_data and len(scraping_data) > 0:
                metadados_leves = []
                for item in scraping_data[:3]:
                    metadados_leves.append({
                        'nome': item.get('nome'),
                        'url': item.get('url'),
                        'tem_pdf': bool(item.get('conteudo_pdf'))
                    })
                self.contexto_conversacao["metadados_scraping"] = metadados_leves
        
        if 'historico_conversacao' not in self.contexto_conversacao:
            self.contexto_conversacao['historico_conversacao'] = []
        
        historico = self.contexto_conversacao['historico_conversacao']
        if len(historico) > 5:
            self.contexto_conversacao['historico_conversacao'] = historico[-5:]
        
        contexto_keys_to_clean = [
            'ultima_pergunta', 'ultima_categoria', 'ultima_entidade_medicamento',
            'ultimo_termo_busca', 'ultima_resposta'
        ]
        
        for key in contexto_keys_to_clean:
            if key in self.contexto_conversacao and self.contexto_conversacao[key]:
                if current_time - self.contexto_conversacao.get('ultima_interacao_time', 0) > 3600:
                    self.contexto_conversacao[key] = None
        
        self.contexto_conversacao['ultima_interacao_time'] = current_time
        self._limpar_cache_memoria()

    def _limpar_cache_memoria(self):
        if hasattr(self, '_pdf_cache'):
            cache_size = len(self._pdf_cache)
            if cache_size > 50:
                itens_ordenados = sorted(self._pdf_cache.items(), 
                                       key=lambda x: x[1]['timestamp'], 
                                       reverse=True)
                self._pdf_cache = dict(itens_ordenados[:20])

    def _adicionar_ao_historico(self, pergunta, resposta, categoria):
        if 'historico_conversacao' not in self.contexto_conversacao:
            self.contexto_conversacao['historico_conversacao'] = []
        
        interacao = {
            'timestamp': time.time(),
            'pergunta': pergunta,
            'resposta': resposta[:200] + "..." if len(resposta) > 200 else resposta,
            'categoria': categoria
        }
        
        self.contexto_conversacao['historico_conversacao'].append(interacao)
        
        if len(self.contexto_conversacao['historico_conversacao']) > 8:
            self.contexto_conversacao['historico_conversacao'] = self.contexto_conversacao['historico_conversacao'][-8:]

    def _verificar_uso_memoria(self):
        try:
            import psutil
            process = psutil.Process()
            memory_usage = process.memory_info().rss / 1024 / 1024
            
            if memory_usage > 500:
                print(colored(f"⚠️  Memória alta: {memory_usage:.2f}MB - Limpando", "red"))
                self._limpar_contexto_antigo(forcar_limpeza=True)
                
        except ImportError:
            pass

    def _reiniciar_contexto(self):
        print(colored("🔄 Reiniciando contexto", "yellow"))
        
        historico_recente = self.contexto_conversacao.get('historico_conversacao', [])[-3:]
        
        # IMPORTANTE: Inicializar TODAS as chaves
        contexto_limpo = {
            'ultima_pergunta': None,
            'ultima_categoria': None,
            'ultima_entidade_medicamento': None,
            'ultimo_termo_busca': None,
            'ultima_resposta': None,
            'dados_ultimo_scraping': None,
            'ultimo_scraping_time': 0,
            'ultima_interacao_time': time.time(),
            'historico_conversacao': historico_recente,
            'metadados_scraping': None
        }
        
        self.contexto_conversacao = contexto_limpo
        print(colored("✅ Contexto reiniciado", "green"))

    # Métodos de mapeamento de espécies (mantidos do original)
    def _criar_mapeamento_especies(self):
        mapeamento = {}
        especies_map = {
            "suínos": ["suíno", "suino", "suínos", "suinos", "porco", "porcos", "leitão", "leitões", "porcino"],
            "cães": ["cão", "cao", "cães", "cachorro", "cachorros", "cadela", "cadelas", "canino", "caninos"],
            "gatos": ["gato", "gatos", "gata", "gatas", "felino", "felinos", "gatinho", "gatinhos"],
            "bovinos": ["bovino", "bovinos", "vaca", "vacas", "novilho", "novilhos", "touro", "touros", "bezerro", "bezerros"],
            "ovinos": ["ovino", "ovinos", "ovelha", "ovelhas", "carneiro", "carneiros", "borrego", "borregos", "cordeiro", "cordeiros"],
            "caprinos": ["caprino", "caprinos", "cabra", "cabras", "bode", "bodes"],
            "coelhos": ["coelho", "coelhos", "coelha", "coelhas", "leporídeo", "leporídeos", "leporideo", "leporideos"],
            "equinos": ["cavalo", "cavalos", "égua", "éguas", "egua", "eguas", "potro", "potros", "equino", "equinos"]
        }
        
        for especie_padrao, sinonimos in especies_map.items():
            for sinonimo in sinonimos:
                mapeamento[sinonimo.lower()] = especie_padrao
        
        return mapeamento

    def _normalizar_especies_texto(self, texto):
        import re
        texto_normalizado = texto
        
        for sinonimo, padrao in self.mapeamento_especies.items():
            pattern = r'\b' + re.escape(sinonimo) + r'\b'
            
            def substituir_preservando_caso(match):
                palavra_encontrada = match.group()
                if palavra_encontrada.isupper():
                    return padrao.upper()
                elif palavra_encontrada.istitle():
                    return padrao.capitalize()
                else:
                    return padrao
            
            texto_normalizado = re.sub(pattern, substituir_preservando_caso, texto_normalizado, flags=re.IGNORECASE)
        
        return texto_normalizado

    # Métodos de web scraping (versão assíncrona)
    async def realizar_web_scraping(self, termo_busca):
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
        """Versão simplificada com foco em tabelas"""
        cache_filename = os.path.join(PDF_CACHE_DIR, hashlib.md5(pdf_url.encode()).hexdigest() + ".pdf")
        text_cache = cache_filename.replace(".pdf", "_v2.txt")  # v2 para invalidar cache antigo
        
        # Verificar cache
        if os.path.exists(text_cache):
            try:
                with open(text_cache, 'r', encoding='utf-8') as f:
                    return f.read()
            except:
                pass
        
        # Baixar PDF se necessário
        if not os.path.exists(cache_filename):
            try:
                async with ClientSession(headers=HEADERS) as session:
                    async with session.get(pdf_url, ssl=False) as response:
                        if response.status == 200:
                            pdf_content = await response.read()
                            with open(cache_filename, 'wb') as f:
                                f.write(pdf_content)
            except:
                return None
    
        # Processar PDF
        try:
            interpreter = TabelaInterpreter()
            secoes = interpreter.processar_pdf_completo(cache_filename)
            
            # Salvar em cache
            texto_completo = "\n\n".join(secoes)
            with open(text_cache, 'w', encoding='utf-8') as f:
                f.write(texto_completo)
            
            return texto_completo
        except Exception as e:
            print(colored(f"Erro ao processar PDF: {e}", "red"))
        return None
    
        
    def _extrair_secoes_relevantes_pdf(self, conteudo_pdf, pergunta):
        """
        Extrai apenas as seções do PDF que são relevantes para a pergunta
        Isso reduz o ruído e melhora a precisão
        """
        if not conteudo_pdf:
            return []
        
        # Palavras-chave da pergunta
        palavras_chave = pergunta.lower().split()
        palavras_chave = [p for p in palavras_chave if len(p) > 3]  # Remover palavras pequenas
        
        # Mapeamento de termos comuns para seções do PDF
        secoes_relevantes = {
            'dose': ['4.9', 'posologia', 'dose', 'dosagem', 'administração'],
            'dosagem': ['4.9', 'posologia', 'dose', 'dosagem', 'administração'],
            'administração': ['4.9', 'posologia', 'administração', 'via de administração'],
            'armazenamento': ['6.4', 'armazenamento', 'conservação', 'validade'],
            'conservação': ['6.4', 'armazenamento', 'conservação', 'validade'],
            'composição': ['6.1', 'composição', 'substância', 'princípio ativo'],
            'indicação': ['4.1', 'indicação', 'indicações terapêuticas'],
            'espécie': ['4.1', 'espécie', 'espécies-alvo', 'espécies alvo'],
            'contraindicação': ['4.3', 'contra-indicação', 'contraindicações'],
            'efeitos': ['4.6', 'efeitos', 'reações adversas', 'efeitos indesejáveis'],
            'reações': ['4.6', 'reações', 'reações adversas', 'efeitos indesejáveis'],
            'gravidez': ['4.7', 'gravidez', 'lactação', 'reprodução'],
            'interação': ['4.8', 'interação', 'interações medicamentosas'],
            'sobredosagem': ['4.10', 'sobredosagem', 'sobredose'],
            'carência': ['4.11', 'tempo de espera', 'carência'],
        }
        
        # Identificar que tipo de informação está sendo buscada
        termos_busca = set()
        for palavra in palavras_chave:
            for termo, secoes in secoes_relevantes.items():
                if termo in palavra or palavra in termo:
                    termos_busca.update(secoes)
        
        # Se não encontrou termos específicos, retorna tudo
        if not termos_busca:
            return conteudo_pdf
        
        # Filtrar seções relevantes
        secoes_filtradas = []
        for secao in conteudo_pdf:
            secao_lower = secao.lower()
            # Verificar se a seção contém algum dos termos de busca
            if any(termo.lower() in secao_lower for termo in termos_busca):
                secoes_filtradas.append(secao)
            # Ou se contém palavras-chave da pergunta
            elif any(palavra in secao_lower for palavra in palavras_chave):
                secoes_filtradas.append(secao)
        
        # Se filtrou muito e ficou vazio, retorna as primeiras seções
        if not secoes_filtradas and len(conteudo_pdf) > 0:
            return conteudo_pdf[:5]
        
        return secoes_filtradas if secoes_filtradas else conteudo_pdf

    def _gerar_prompt_especializado_pdf(self, pergunta, contexto_html, contexto_pdf, medicamento_nome):
        """
        Gera um prompt mais específico que guia o Ollama a encontrar informações precisas
        """
        
        # Identificar o tipo de pergunta
        pergunta_lower = pergunta.lower()
        
        tipo_info = "geral"
        instrucoes_especificas = ""
        
        if any(palavra in pergunta_lower for palavra in ['dose', 'dosagem', 'posologia']):
            tipo_info = "dosagem"
            instrucoes_especificas = """
            FOCO: Encontre informações sobre DOSAGEM/POSOLOGIA
            Procure por:
            - Dose em mg/kg ou ml/kg
            - Frequência de administração
            - Duração do tratamento
            - Via de administração (oral, injetável, etc)
            
            Formato esperado da resposta:
            "A dose recomendada é X mg/kg ou X ml/kg, administrada [via], [frequência], durante [duração]."
            """
        
        elif any(palavra in pergunta_lower for palavra in ['armazenamento', 'conservação', 'armazenar']):
            tipo_info = "armazenamento"
            instrucoes_especificas = """
            FOCO: Encontre informações sobre ARMAZENAMENTO
            Procure por:
            - Temperatura de conservação
            - Condições de armazenamento
            - Prazo de validade
            - Cuidados especiais
            
            Formato esperado da resposta:
            "Deve ser armazenado [condições de temperatura], [cuidados especiais]. Validade: [prazo]."
            """
        
        elif any(palavra in pergunta_lower for palavra in ['espécie', 'espécies', 'animal', 'animais']):
            tipo_info = "especies"
            instrucoes_especificas = """
            FOCO: Encontre as ESPÉCIES-ALVO
            Procure por:
            - Lista de animais/espécies para os quais o medicamento é indicado
            - Seção "Espécies-alvo" ou "Indicações terapêuticas"
            
            Formato esperado da resposta:
            "Este medicamento é indicado para: [lista de espécies]."
            """
        
        elif any(palavra in pergunta_lower for palavra in ['composição', 'princípio', 'substância', 'ativo']):
            tipo_info = "composicao"
            instrucoes_especificas = """
            FOCO: Encontre a COMPOSIÇÃO
            Procure por:
            - Princípio(s) ativo(s)
            - Substância(s) ativa(s)
            - Composição qualitativa e quantitativa
            
            Formato esperado da resposta:
            "O medicamento contém: [substância ativa] na concentração de [quantidade]."
            """
        
        elif any(palavra in pergunta_lower for palavra in ['indicação', 'indicado', 'serve', 'usar']):
            tipo_info = "indicacao"
            instrucoes_especificas = """
            FOCO: Encontre as INDICAÇÕES TERAPÊUTICAS
            Procure por:
            - Para que serve o medicamento
            - Doenças/condições que trata
            - Indicações terapêuticas
            
            Formato esperado da resposta:
            "Este medicamento é indicado para: [indicações terapêuticas]."
            """
        
        # Construir prompt otimizado
        prompt = f"""
        MEDICAMENTO: {medicamento_nome}
        
        PERGUNTA: "{pergunta}"
        
        TIPO DE INFORMAÇÃO: {tipo_info.upper()}
        
        {instrucoes_especificas}
        
        CONTEXTO DA PÁGINA WEB:
        {contexto_html[:1000]}
        
        CONTEXTO DO PDF (SEÇÕES RELEVANTES):
        {json.dumps(contexto_pdf, ensure_ascii=False, indent=2)}
        
        INSTRUÇÕES CRÍTICAS:
        1. Leia CUIDADOSAMENTE todo o contexto do PDF
        2. Procure especificamente pela informação pedida
        3. Se encontrar a informação, cite-a EXATAMENTE como está no documento
        4. Se a informação estiver em uma TABELA ou LISTA, organize claramente
        5. Se NÃO encontrar a informação específica, diga: "Esta informação não foi encontrada no documento"
        6. NUNCA invente ou assuma informações que não estão no contexto
        7. Seja PRECISO e DIRETO
        
        RESPOSTA:
        """
        
        return prompt

    def _buscar_informacao_direta_pdf(self, conteudo_pdf, tipo_info, especie=None):
        """
        Versão melhorada que prioriza contexto de tabelas
        """
        if not conteudo_pdf:
            return None
        
        resultado = {
            'encontrado': False,
            'secoes_relevantes': [],
            'info_extraida': None
        }
        
        if tipo_info == "dosagem":
            import re
            
            doses_encontradas = []
            contexto_doses = []
            
            for i, secao in enumerate(conteudo_pdf):
                secao_lower = secao.lower()
                secao_original = conteudo_pdf[i]
                
                # PRIORIDADE 1: Detectar TABELAS
                is_tabela = '===' in secao_original or '|' in secao_original
                
                # PRIORIDADE 2: Seção de dosagem
                is_secao_dosagem = any(termo in secao_lower for termo in [
                    '4.9', '4.2', 'posologia', 'dose', 'dosagem', 'administração'
                ])
                
                if is_secao_dosagem or is_tabela:
                    # Se tem espécie, verificar
                    if especie:
                        especie_variantes = [
                            especie.lower(), 
                            especie.lower().rstrip('s'),
                            especie.lower() + 's'
                        ]
                        tem_especie = any(var in secao_lower for var in especie_variantes)
                        if not tem_especie and not is_tabela:
                            continue
                    
                    # EXTRAÇÃO PRIORITÁRIA: De tabelas estruturadas
                    if is_tabela:
                        
                        # Extrair doses de formato tabular
                        linhas = [l.strip() for l in secao_original.split('\n') if l.strip()]
                        
                        for linha in linhas:
                            # Procurar linha com a espécie (se especificada)
                            if especie:
                                tem_especie_na_linha = any(var in linha.lower() for var in especie_variantes)
                                if not tem_especie_na_linha:
                                    continue
                            
                            # Extrair doses da linha
                            padroes_prioritarios = [
                                r'(\d+[,.]?\d*)\s*mg\s*/\s*kg',
                                r'(\d+[,.]?\d*)\s*mg\s+por\s+kg',
                                r'(\d+[,.]?\d*)\s*mcg\s*/\s*kg',
                            ]
                            
                            for padrao in padroes_prioritarios:
                                matches = re.findall(padrao, linha, re.IGNORECASE)
                                for match in matches:
                                    # Determinar unidade
                                    if 'mcg' in padrao or 'µg' in padrao:
                                        unidade = 'mcg/kg'
                                    else:
                                        unidade = 'mg/kg'
                                    
                                    dose_completa = f"{match} {unidade}"
                                    
                                    if dose_completa not in doses_encontradas:
                                        doses_encontradas.append(dose_completa)
                                        print(colored(f"    ✓ Dose extraída da tabela: {dose_completa}", "green"))
                        
                        if secao_original not in contexto_doses:
                            contexto_doses.append(secao_original)
                        if secao_original not in resultado['secoes_relevantes']:
                            resultado['secoes_relevantes'].append(secao_original)
                            resultado['encontrado'] = True
                    
                    # EXTRAÇÃO SECUNDÁRIA: De texto corrido (se não achou em tabela)
                    if not doses_encontradas:
                        padroes_texto = [
                            r'(\d+[,.]?\d*)\s*mg\s*/\s*kg',
                            r'(\d+[,.]?\d*)\s*mg\s+por\s+kg',
                        ]
                        
                        for padrao in padroes_texto:
                            matches = re.findall(padrao, secao_lower, re.IGNORECASE)
                            for match in matches:
                                dose_completa = f"{match} mg/kg"
                                if dose_completa not in doses_encontradas:
                                    doses_encontradas.append(dose_completa)
                        
                        if doses_encontradas and secao_original not in contexto_doses:
                            contexto_doses.append(secao_original)
                            resultado['secoes_relevantes'].append(secao_original)
                            resultado['encontrado'] = True
            
            if doses_encontradas or contexto_doses:
                # Remover duplicatas
                doses_unicas = []
                for dose in doses_encontradas:
                    if dose not in doses_unicas:
                        doses_unicas.append(dose)
                
                resultado['info_extraida'] = {
                    'doses': doses_unicas,
                    'contexto': contexto_doses,
                    'secoes': resultado['secoes_relevantes']
                }
                
                print(colored(f"  📊 Doses finais extraídas: {doses_unicas}", "cyan"))
                print(colored(f"  📄 Contextos: {len(contexto_doses)}", "cyan"))
        
        # ARMAZENAMENTO (mantém igual)
        elif tipo_info == "armazenamento":
            for i, secao in enumerate(conteudo_pdf):
                secao_lower = secao.lower()
                
                if any(termo in secao_lower for termo in ['6.4', 'armazen', 'conserv', 'temperatura', 'validade']):
                    if any(termo in secao_lower for termo in [
                        '°c', 'graus', 'temperatura', 'frigorífico', 'congelador',
                        'ambiente', 'fresco', 'seco', 'luz', 'validade'
                    ]):
                        resultado['encontrado'] = True
                        resultado['secoes_relevantes'].append(conteudo_pdf[i])
                        resultado['info_extraida'] = {'secao': conteudo_pdf[i]}
        
        # ESPÉCIES (mantém igual)
        elif tipo_info == "especies":
            especies_conhecidas = [
                'suínos', 'suíno', 'suino', 'porcos', 'porco',
                'bovinos', 'bovino', 'vacas', 'vaca', 'gado',
                'equinos', 'equino', 'cavalos', 'cavalo',
                'cães', 'cão', 'caes', 'cao', 'cachorros',
                'gatos', 'gato', 'felino',
                'aves', 'galinhas', 'frangos',
                'ovinos', 'ovelhas', 'carneiros',
                'caprinos', 'cabras', 'bodes'
            ]
            
            especies_encontradas = []
            for i, secao in enumerate(conteudo_pdf):
                secao_lower = secao.lower()
                
                if any(termo in secao_lower for termo in ['4.1', 'espécie', 'especie', 'indicaç', 'alvo']):
                    for especie in especies_conhecidas:
                        if especie in secao_lower:
                            if 'suí' in especie or 'porco' in especie:
                                especies_encontradas.append('suínos')
                            elif 'bovin' in especie or 'vaca' in especie:
                                especies_encontradas.append('bovinos')
                            elif 'equin' in especie or 'caval' in especie:
                                especies_encontradas.append('equinos')
                            elif 'cã' in especie or 'cao' in especie or 'cachorro' in especie:
                                especies_encontradas.append('cães')
                            elif 'gato' in especie:
                                especies_encontradas.append('gatos')
                            
                            if conteudo_pdf[i] not in resultado['secoes_relevantes']:
                                resultado['secoes_relevantes'].append(conteudo_pdf[i])
                                resultado['encontrado'] = True
            
            if especies_encontradas:
                resultado['info_extraida'] = {'especies': list(set(especies_encontradas))}
        
        return resultado
    
    def _gerar_prompt_super_restritivo_dose(self, pergunta, secoes_pdf, medicamento_nome, doses_encontradas):
        """
        Prompt ULTRA-RESTRITIVO especificamente para perguntas de dose
        que FORÇA o Ollama a usar apenas os valores extraídos
        """
        
        secoes_texto = "\n\n---\n\n".join(secoes_pdf)
        
        # Criar lista explícita de doses válidas
        doses_validas_str = "\n".join([f"  - {dose}" for dose in doses_encontradas])
        
        prompt = f"""
        MEDICAMENTO: {medicamento_nome}

        DOSES IDENTIFICADAS NO DOCUMENTO:
        {doses_validas_str}

        ⚠️ ATENÇÃO CRÍTICA:
        As doses acima foram EXTRAÍDAS DIRETAMENTE do documento oficial.
        Você DEVE usar APENAS essas doses. NÃO invente, NÃO calcule, NÃO assuma.

        DOCUMENTO COMPLETO:
        {secoes_texto}

        PERGUNTA: {pergunta}

        REGRAS OBRIGATÓRIAS:
        1. Use APENAS as doses listadas acima em "DOSES IDENTIFICADAS"
        2. NÃO confunda:
        - Nome do medicamento (ex: "Senvelgo 15 mg/ml") ≠ dose
        - Concentração (mg/ml) ≠ dose por peso (mg/kg)
        3. Se a pergunta menciona uma espécie, encontre a dose ESPECÍFICA para ela
        4. Formato da resposta: "A dose para [espécie] é [valor exato das doses identificadas]"
        5. Se NÃO encontrar dose para a espécie específica, diga: "Não há dose específica para [espécie] no documento"
        6. NUNCA use valores do nome do medicamento como dose

        EXEMPLO DE RESPOSTA CORRETA:
        "Segundo o documento, a dose indicada de {medicamento_nome} para gatos é 1 mg/kg."

        EXEMPLO DE RESPOSTA ERRADA (NÃO FAÇA ISSO):
        ❌ "A dose é 15 mg" (confundiu com concentração do nome)
        ❌ "A dose é 15.0 mg" (inventou baseado no nome)

        AGORA RESPONDA A PERGUNTA USANDO APENAS AS DOSES IDENTIFICADAS:
        """
        
        return prompt
    
    def _validar_resposta_dose(self, resposta_ollama, doses_encontradas, pergunta):
        """
        Valida se a resposta do Ollama contém apenas doses que foram extraídas
        Se não, força correção
        """
        import re
        
        # Extrair todas as menções de dose na resposta do Ollama
        # Padrões: "X mg/kg", "X mg", "X.X mg/kg", etc
        padroes_dose = [
            r'(\d+\.?\d*)\s*mg/kg',
            r'(\d+\.?\d*)\s*mg\s+por\s+kg',
            r'(\d+\.?\d*)\s*mcg/kg',
            r'(\d+\.?\d*)\s*ml/kg',
        ]
        
        doses_na_resposta = []
        for padrao in padroes_dose:
            matches = re.findall(padrao, resposta_ollama, re.IGNORECASE)
            doses_na_resposta.extend(matches)
        
        print(colored(f"🔍 Doses mencionadas na resposta: {doses_na_resposta}", "cyan"))
        print(colored(f"✓ Doses válidas do documento: {doses_encontradas}", "green"))
        
        # Verificar se alguma dose na resposta NÃO está nas doses válidas
        doses_invalidas = []
        for dose_resposta in doses_na_resposta:
            # Normalizar para comparação
            dose_valor = dose_resposta.strip()
            
            # Verificar se esse valor existe em alguma das doses encontradas
            dose_valida = False
            for dose_doc in doses_encontradas:
                # Extrair apenas o número da dose do documento
                match_doc = re.search(r'(\d+\.?\d*)', dose_doc)
                if match_doc:
                    valor_doc = match_doc.group(1)
                    if dose_valor == valor_doc:
                        dose_valida = True
                        break
            
            if not dose_valida:
                doses_invalidas.append(dose_valor)
        
        # Se encontrou doses inválidas, REJEITAR resposta
        if doses_invalidas:
            print(colored(f"❌ RESPOSTA INVÁLIDA! Doses inventadas: {doses_invalidas}", "red"))
            
            # Gerar resposta corretiva forçada
            resposta_corrigida = self._gerar_resposta_forcada(pergunta, doses_encontradas)
            return False, resposta_corrigida
        
        print(colored("✅ Resposta válida - doses conferem com documento", "green"))
        return True, resposta_ollama

    def _gerar_resposta_forcada(self, pergunta, doses_encontradas):
        """
        Gera resposta forçada quando Ollama inventa doses
        """
        pergunta_lower = pergunta.lower()
        
        # Tentar identificar espécie na pergunta
        especies = ['gatos', 'gato', 'cães', 'cão', 'suínos', 'suíno', 'bovinos', 'bovino', 
                    'equinos', 'equino', 'aves', 'ovinos', 'caprinos']
        
        especie_encontrada = None
        for especie in especies:
            if especie in pergunta_lower:
                especie_encontrada = especie
                break
        
        # Construir resposta baseada nas doses extraídas
        if len(doses_encontradas) == 1:
            resposta = f"Segundo o documento, a dose indicada"
            if especie_encontrada:
                resposta += f" para {especie_encontrada}"
            resposta += f" é {doses_encontradas[0]}."
        else:
            resposta = f"Segundo o documento, as doses indicadas são:\n"
            for dose in doses_encontradas:
                resposta += f"  - {dose}\n"
        
        resposta += f"\n⚠️ Nota: Resposta gerada a partir de extração direta do documento, "
        resposta += f"pois o modelo de IA estava retornando valores incorretos."
        
        return resposta


    def _gerar_prompt_direto(self, pergunta, secoes_pdf, medicamento_nome, busca_direta=None):
        """
        Prompt melhorado para interpretação de tabelas
        """
        
        # Detectar se há tabelas nas seções
        tem_tabelas = any('TABELA' in secao or '|' in secao for secao in secoes_pdf)
        
        secoes_texto = "\n\n---\n\n".join(secoes_pdf)
        
        instrucoes_tabela = ""
        if tem_tabelas:
            instrucoes_tabela = """
            
        ATENÇÃO ESPECIAL PARA TABELAS:
        1. Este documento contém TABELAS com dados estruturados
        2. Quando encontrar uma tabela (marcada com === TABELA === ou formato | coluna | coluna |):
        - Leia LINHA POR LINHA
        - Identifique os CABEÇALHOS (primeira linha)
        - Associe cada VALOR ao seu respectivo CABEÇALHO
        3. NÃO invente dados que não estão na tabela
        4. Se a informação está em formato tabular, CITE EXATAMENTE como aparece
        5. Para doses em tabelas: procure pela espécie e leia o valor correspondente
        """
            
            prompt = f"""
        MEDICAMENTO: {medicamento_nome}

        DOCUMENTO COMPLETO (TODAS AS SEÇÕES):
        {secoes_texto}

        PERGUNTA: {pergunta}
        {instrucoes_tabela}

        INSTRUÇÕES CRÍTICAS:
        1. Leia CUIDADOSAMENTE todo o conteúdo acima
        2. Se houver TABELAS, interprete-as corretamente:
        - Identifique os cabeçalhos
        - Encontre a linha correspondente à espécie/situação
        - Leia o valor correto da coluna apropriada
        3. A informação solicitada DEVE estar no documento
        4. NUNCA invente ou assuma informações
        5. Se a informação estiver em tabela, descreva: "Segundo a tabela, [informação]"
        6. Seja PRECISO e cite EXATAMENTE os valores encontrados

        RESPOSTA DETALHADA:
        """
        
        return prompt

    def _validar_qualidade_resposta(self, resposta, pergunta):
        """
        Verifica se a resposta é vaga ou genérica demais
        """
        resposta_lower = resposta.lower()
        
        # Indicadores de resposta vaga
        indicadores_vagos = [
            "não encontrei",
            "não foi possível encontrar",
            "não há informação",
            "não consta",
            "não está especificado",
            "consulte o veterinário",
            "consulte a bula"
        ]
        
        # Se tem muitos indicadores vagos, pode ser resposta ruim
        vagos_encontrados = sum(1 for indicador in indicadores_vagos if indicador in resposta_lower)
        
        # Verificar se tem informação específica
        tem_numeros = any(char.isdigit() for char in resposta)
        tem_unidades = any(unidade in resposta_lower for unidade in ['mg', 'ml', 'kg', 'graus', '°c', 'dias'])
        
        if vagos_encontrados > 0 and not (tem_numeros or tem_unidades):
            return False, "Resposta muito vaga"
        
        return True, "OK"


    # Métodos auxiliares de scraping (mantidos do original)
    def _formatar_texto_html(self, elemento):
        if elemento.name in {"h1", "h2", "h3", "h4", "h5", "a", "p"}:
            return elemento.get_text(strip=True)
        return None

    def _encontrar_link_pdf(self, soup, url):
        pdf_tag = soup.find("a", href=True, target="_blank")
        if pdf_tag and pdf_tag.find("span", class_="fa-file-pdf-o"):
            return urljoin(url, pdf_tag["href"])
        return None

    def _formatar_conteudo_pdf(self, texto):
        """Versão simplificada"""
        if not texto:
            return []
        
        # Dividir por marcadores de tabela ou seções numeradas
        partes = re.split(r'\n(?=\d+\.\s|\={80})', texto)
        
        return [p.strip() for p in partes if p.strip()]

    def _extrair_informacoes_pagina_busca(self, url_busca, urls_processadas=None):
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

    # Métodos de detecção e processamento de perguntas (mantidos)
    def _detectar_consulta_dupla(self, classificacao):
        """
        Detecta se a pergunta requer consulta dupla
        ATUALIZADO: Agora também detecta perguntas sobre "alternativo/alternativa/substituto"
        """
        entidades = classificacao.get("entidades", {})
        substancia_ativa = entidades.get("substancia_ativa", "").strip()
        pergunta_ollama = entidades.get("pergunta_ollama", "").lower()
        
        # Indicadores de consulta dupla - EXPANDIDO
        indicadores_dupla = [
            "mesmo princípio ativo", 
            "mesma substância ativa", 
            "princípio ativo do medicamento", 
            "substância ativa do medicamento",
            "medicamentos com o princípio ativo", 
            "qual o princípio ativo",
            # NOVOS INDICADORES
            "alternativ",  # captura "alternativo", "alternativa", "alternativas"
            "substitut",   # captura "substituto", "substituta", "substituir"
            "equivalente", # medicamento equivalente
            "similar"      # medicamento similar
        ]
        
        # Verificar se substancia_ativa parece ser um nome de medicamento
        is_nome_medicamento = (
            substancia_ativa and 
            (substancia_ativa[0].isupper() or any(c.isupper() for c in substancia_ativa)) and
            any(indicador in pergunta_ollama for indicador in indicadores_dupla)
        )
        
        if is_nome_medicamento:
            print(colored(f"✓ Consulta dupla detectada! Medicamento de referência: {substancia_ativa}", "cyan"))
            print(colored(f"  Indicadores encontrados: {[ind for ind in indicadores_dupla if ind in pergunta_ollama]}", "cyan"))
        
        return is_nome_medicamento

    def _detectar_pergunta_followup(self, pergunta_atual):
        # Verificar se há contexto anterior
        if not self.contexto_conversacao.get("ultima_pergunta"):
            return False, None

        # Obter dados do contexto
        ultima_pergunta = self.contexto_conversacao.get("ultima_pergunta", "")
        ultima_categoria = self.contexto_conversacao.get("ultima_categoria", "")
        ultimo_medicamento = self.contexto_conversacao.get("ultima_entidade_medicamento", "")

        palavras_pergunta_atual = pergunta_atual.lower().split()
        
        # REGRA 1: Perguntas muito curtas (1-3 palavras) + indicadores
        if len(palavras_pergunta_atual) <= 3:
            # Indicadores de follow-up para perguntas curtas
            indicadores_curtos = [
                "e", "para", "em", "gatos", "cães", "suínos", "bovinos", "equinos", 
                "peru", "perus", "aves", "coelhos", "dose", "dosagem", "armazenamento"
            ]
            
            tem_indicador = any(palavra in pergunta_atual.lower() for palavra in indicadores_curtos)
            
            if tem_indicador:
                print(colored(f"🔍 Pergunta curta com indicador detectada: '{pergunta_atual}'", "cyan"))
                
                # Extrair entidade da pergunta
                entidade_extraida = self._extrair_entidade_followup(pergunta_atual)
                return True, entidade_extraida
        
        # REGRA 2: Perguntas com 1-5 palavras + padrões específicos
        if 1 <= len(palavras_pergunta_atual) <= 5:
            indicadores_especie_ou_aspecto = [
                "e em", "e para", "em gatos", "em cães", "em suínos", "em bovinos", "em equinos",
                "para gatos", "para cães", "para suínos", "para bovinos", "para equinos", "para aves",
                "gatos?", "cães?", "suínos?", "bovinos?", "equinos?", "aves?", "perus?",
                "dose?", "dosagem?", "armazenamento?", "composição?", "indicação?",
                "e peru", "e perus", "peru?", "perus?"
            ]

            tem_indicador = any(indicador in pergunta_atual.lower() for indicador in indicadores_especie_ou_aspecto)
            
            if tem_indicador:
                print(colored(f"🔍 Follow-up detectado por padrão: '{pergunta_atual}'", "cyan"))
                entidade_extraida = self._extrair_entidade_followup(pergunta_atual)
                return True, entidade_extraida
        
        
        return False, None
    
    # CORREÇÃO - Construção de Pergunta Follow-up
# Substitua as funções em temporario.py

    def _extrair_entidade_followup(self, pergunta):
        """
        Extrai a entidade principal de uma pergunta de follow-up
        VERSÃO CORRIGIDA - detecta tipos de pergunta vs entidades
        """
        pergunta_lower = pergunta.lower().strip()
        pergunta_original = pergunta.strip()
        
        print(colored(f"🔍 Analisando follow-up: '{pergunta_original}'", "cyan"))
        
        # VERIFICAR SE É PERGUNTA SOBRE INFORMAÇÃO (não entidade)
        perguntas_info = [
            "dose", "dosagem", "qual a dose", "e a dose", "e qual a dose",
            "armazenamento", "como armazenar", "e o armazenamento",
            "composição", "qual a composição", "e a composição",
            "indicação", "para que serve", "e a indicação",
            "efeitos", "reações", "contraindicações"
        ]
        
        for info in perguntas_info:
            if info in pergunta_lower:
                print(colored(f"   ✓ Detectado como pergunta sobre: {info}", "green"))
                
                # Mapear para tipos padrão
                if "dose" in info:
                    return "PERGUNTA_DOSE"
                elif "armazen" in info:
                    return "PERGUNTA_ARMAZENAMENTO"
                elif "composi" in info:
                    return "PERGUNTA_COMPOSICAO"
                elif "indica" in info or "serve" in info:
                    return "PERGUNTA_INDICACAO"
                elif "efeito" in info or "reação" in info or "contra" in info:
                    return "PERGUNTA_EFEITOS"
                else:
                    return "PERGUNTA_GERAL"
        
        # Se não é pergunta sobre informação, extrair entidade (espécie)
        # Remover palavras conectivas
        palavras_ignorar = ["e", "para", "em", "?", "o", "a", "os", "as", "do", "da", "dos", "das", "qual"]
        palavras = [p for p in pergunta_lower.split() if p not in palavras_ignorar and len(p) > 1]
        
        print(colored(f"   📝 Palavras após filtro: {palavras}", "cyan"))
        
        if not palavras:
            return pergunta_original
        
        # Procurar por espécies conhecidas
        especies_mapeamento = {
            "peru": "Peru", "perus": "Peru",
            "gatos": "gatos", "gato": "gatos",
            "cães": "cães", "caes": "cães", "cao": "cães", "cachorro": "cães",
            "suínos": "suínos", "suinos": "suínos", "porco": "suínos", "porcos": "suínos",
            "bovinos": "bovinos", "vacas": "bovinos", "boi": "bovinos", "gado": "bovinos",
            "equinos": "equinos", "cavalos": "equinos", "cavalo": "equinos",
            "aves": "aves", "galinhas": "aves", "galinha": "aves", "frangos": "aves",
            "ovinos": "ovinos", "ovelhas": "ovinos", "carneiro": "ovinos",
            "caprinos": "caprinos", "cabras": "caprinos", "bode": "caprinos"
        }
        
        # Procurar espécie nas palavras
        for palavra in palavras:
            if palavra in especies_mapeamento:
                especie_normalizada = especies_mapeamento[palavra]
                print(colored(f"   ✓ Espécie detectada: {palavra} → {especie_normalizada}", "green"))
                return especie_normalizada
        
        # Se não encontrou espécie conhecida, retornar primeira palavra válida
        primeira_palavra = palavras[0].capitalize()
        print(colored(f"   ⚠ Entidade genérica: {primeira_palavra}", "yellow"))
        return primeira_palavra

    def _construir_pergunta_completa(self, pergunta_followup, entidade_extraida):
        """
        Constrói pergunta completa baseada no contexto anterior
        VERSÃO CORRIGIDA - distingue tipos de pergunta
        """
        ultima_pergunta = self.contexto_conversacao.get("ultima_pergunta")
        ultimo_medicamento = self.contexto_conversacao.get("ultima_entidade_medicamento")
        
        if not ultima_pergunta:
            return pergunta_followup
        
        print(colored(f"🔄 Construindo pergunta completa:", "cyan"))
        print(colored(f"   Última pergunta: {ultima_pergunta}", "cyan"))
        print(colored(f"   Medicamento: {ultimo_medicamento}", "cyan"))
        print(colored(f"   Entidade extraída: {entidade_extraida}", "cyan"))
        
        # CASO 1: É pergunta sobre informação específica
        if entidade_extraida.startswith("PERGUNTA_"):
            if not ultimo_medicamento:
                # Tentar extrair medicamento da pergunta anterior
                import re
                match = re.search(r'(?:medicamento\s+)?(\w+)', ultima_pergunta, re.IGNORECASE)
                if match:
                    ultimo_medicamento = match.group(1)
            
            if ultimo_medicamento:
                if entidade_extraida == "PERGUNTA_DOSE":
                    nova_pergunta = f"Qual a dose do {ultimo_medicamento}?"
                elif entidade_extraida == "PERGUNTA_ARMAZENAMENTO":
                    nova_pergunta = f"Como armazenar o {ultimo_medicamento}?"
                elif entidade_extraida == "PERGUNTA_COMPOSICAO":
                    nova_pergunta = f"Qual a composição do {ultimo_medicamento}?"
                elif entidade_extraida == "PERGUNTA_INDICACAO":
                    nova_pergunta = f"Para que serve o {ultimo_medicamento}?"
                elif entidade_extraida == "PERGUNTA_EFEITOS":
                    nova_pergunta = f"Quais os efeitos adversos do {ultimo_medicamento}?"
                else:
                    nova_pergunta = f"Informações sobre {ultimo_medicamento}"
            else:
                # Sem medicamento no contexto, usar pergunta original
                nova_pergunta = pergunta_followup
            
            print(colored(f"   ✓ Pergunta sobre informação: {nova_pergunta}", "green"))
            return nova_pergunta
        
        # CASO 2: É pergunta sobre espécie diferente
        if ultimo_medicamento:
            # Detectar tipo de informação da pergunta anterior
            ultima_pergunta_lower = ultima_pergunta.lower()
            
            if any(palavra in ultima_pergunta_lower for palavra in ["dose", "dosagem"]):
                tipo_info = "dose"
                nova_pergunta = f"Qual a dose do {ultimo_medicamento} para {entidade_extraida}?"
            elif any(palavra in ultima_pergunta_lower for palavra in ["administração", "forma", "via"]):
                tipo_info = "administração"
                nova_pergunta = f"Qual a forma de administração do {ultimo_medicamento} em {entidade_extraida}?"
            elif any(palavra in ultima_pergunta_lower for palavra in ["armazenamento", "conservar"]):
                tipo_info = "armazenamento"
                nova_pergunta = f"Como armazenar o {ultimo_medicamento}?"
            elif any(palavra in ultima_pergunta_lower for palavra in ["composição", "princípio"]):
                tipo_info = "composição"
                nova_pergunta = f"Qual a composição do {ultimo_medicamento}?"
            elif any(palavra in ultima_pergunta_lower for palavra in ["indicação", "serve"]):
                tipo_info = "indicação"
                nova_pergunta = f"Para que serve o {ultimo_medicamento} em {entidade_extraida}?"
            else:
                # Tipo genérico - assumir que quer a mesma informação
                import re
                # Substituir espécie anterior por nova espécie
                especies_pattern = r'\b(?:em|para)\s+(?:suínos|bovinos|equinos|cães|gatos|aves|peru|perus)\b'
                if re.search(especies_pattern, ultima_pergunta, re.IGNORECASE):
                    nova_pergunta = re.sub(
                        especies_pattern, 
                        f"para {entidade_extraida}", 
                        ultima_pergunta, 
                        flags=re.IGNORECASE
                    )
                else:
                    nova_pergunta = f"{ultima_pergunta.rstrip('?')} para {entidade_extraida}?"
            
            print(colored(f"   ✓ Pergunta sobre nova espécie: {nova_pergunta}", "green"))
            return nova_pergunta
        
        # CASO 3: Fallback - tentar substituição direta
        import re
        especies_antigas = ["suínos", "bovinos", "equinos", "cães", "gatos", "aves", "peru", "perus"]
        
        for especie_antiga in especies_antigas:
            if especie_antiga in ultima_pergunta.lower():
                nova_pergunta = re.sub(
                    rf'\b{especie_antiga}\b', 
                    entidade_extraida, 
                    ultima_pergunta, 
                    flags=re.IGNORECASE
                )
                print(colored(f"   ✓ Substituição direta: {nova_pergunta}", "green"))
                return nova_pergunta
        
        # CASO 4: Fallback final
        nova_pergunta = f"{ultima_pergunta.rstrip('?')} para {entidade_extraida}?"
        print(colored(f"   ⚠ Fallback: {nova_pergunta}", "yellow"))
        return nova_pergunta

    def _realizar_busca_comparacao_simples(self, termo_busca):
        print(colored(f"Busca comparação simples: '{termo_busca}'", "blue"))
        
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

        urls_processadas = set()
        resultados = self._extrair_informacoes_pagina_busca(url_pagina_busca, urls_processadas)
        
        resultados_unicos = []
        nomes_vistos = set()
        for resultado in resultados:
            nome = resultado.get('nome', '').strip()
            if nome and nome not in nomes_vistos:
                nomes_vistos.add(nome)
                resultados_unicos.append(resultado)
        
        print(colored(f"Resultados únicos encontrados: {len(resultados_unicos)}", "green"))
        return resultados_unicos

    def _formatar_resultados_comparacao_simples(self, resultados, pergunta_original):
        if not resultados:
            return "Nenhum medicamento encontrado para os critérios de busca."
        
        resposta = f"Resultados para: '{pergunta_original}'\n\n"
        resposta += f"Total: {len(resultados)}\n\n"
        
        for i, item in enumerate(resultados, 1):
            resposta += f"{i}. **{item.get('nome', 'Nome não disponível')}**\n"
            
            if item.get('especies'):
                resposta += f"   - Espécies: {item['especies']}\n"
            
            if item.get('forma_farmaceutica'):
                resposta += f"   - Forma farmacêutica: {item['forma_farmaceutica']}\n"
            
            if item.get('principio_ativo'):
                resposta += f"   - Princípio ativo: {item['principio_ativo']}\n"
            
            if item.get('link'):
                resposta += f"   - Link: {item['link']}\n"
            
            if not any([item.get('especies'), item.get('forma_farmaceutica'), item.get('principio_ativo')]):
                info_resumida = item.get('informacoes_visiveis', '')
                if len(info_resumida) > 150:
                    info_resumida = info_resumida[:150] + "..."
                resposta += f"   - Informações: {info_resumida}\n"
            
            resposta += "\n"
        
        resposta += "\nNota: Informações extraídas da página de busca."
        return resposta
    
    def _limpar_principio_ativo(self, texto):
        """
        Remove lixo da resposta do Ollama para extração de princípio ativo
        """
        # Remover quebras de linha
        texto = texto.replace('\n', ' ').strip()
        
        # Se tem múltiplas linhas ou frases, pegar só a primeira
        if '.' in texto:
            texto = texto.split('.')[0]
        
        # Remover prefixos comuns
        prefixos_remover = [
            'o princípio ativo é', 'princípio ativo:', 
            'substância ativa:', 'o correto é',
            'aguardando', 'correção'
        ]
        
        texto_lower = texto.lower()
        for prefixo in prefixos_remover:
            if prefixo in texto_lower:
                # Se tem prefixo, tentar extrair o que vem depois
                idx = texto_lower.find(prefixo)
                resto = texto[idx + len(prefixo):].strip()
                if resto:
                    texto = resto
        
        # Remover pontuação no final
        texto = texto.rstrip('.,;:')
        
        # Pegar apenas primeira palavra (se tem múltiplas)
        # Exceto se for nome composto tipo "Ácido Tolfenâmico"
        palavras = texto.split()
        if len(palavras) > 3:
            # Se tem muitas palavras, provavelmente tem lixo
            texto = palavras[0]
        elif len(palavras) == 2:
            # Pode ser nome composto, manter ambos
            texto = ' '.join(palavras)
        
        return texto.strip()
    
    def _realizar_consulta_dupla(self, classificacao, pergunta_normalizada):
        """
        Realiza consulta dupla: primeiro extrai o princípio ativo, depois busca medicamentos
        ATUALIZADO: Melhores mensagens para perguntas sobre "alternativo"
        """
        entidades = classificacao.get("entidades", {})
        medicamento_referencia = entidades.get("substancia_ativa", "").strip()
        pergunta_ollama = entidades.get("pergunta_ollama", "")
        especie_alvo = entidades.get("especie_alvo", "")
        
        # Detectar tipo de pergunta para mensagens melhores
        pergunta_lower = pergunta_normalizada.lower()
        if "alternativ" in pergunta_lower:
            tipo_pergunta = "alternativo"
        elif "substitut" in pergunta_lower:
            tipo_pergunta = "substituto"
        elif "equivalente" in pergunta_lower:
            tipo_pergunta = "equivalente"
        else:
            tipo_pergunta = "mesmo princípio ativo"
        
        print(colored(f"🔄 Consulta dupla para: {medicamento_referencia} (tipo: {tipo_pergunta})", "cyan"))
        
        # FASE 1: Buscar informações do medicamento de referência
        print(colored(f"📋 FASE 1: Buscando informações sobre {medicamento_referencia}...", "yellow"))
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            dados_medicamento = loop.run_until_complete(self.realizar_web_scraping(medicamento_referencia))
        finally:
            loop.close()
        
        if not dados_medicamento:
            return f"❌ Não foi possível encontrar informações sobre '{medicamento_referencia}'."
        
        # FASE 1.5: Extrair princípio ativo
        prompt_principio = f"""
        DOCUMENTO:
        {json.dumps(dados_medicamento, ensure_ascii=False, indent=2)}
        
        TAREFA: Extraia APENAS o princípio ativo (substância ativa) do medicamento {medicamento_referencia}.
        
        REGRAS OBRIGATÓRIAS:
        1. Responda APENAS com o NOME da substância ativa
        2. NÃO adicione explicações, comentários ou observações
        3. NÃO corrija ou sugira alternativas
        4. Se não encontrar, responda apenas: NÃO ENCONTRADO
        
        EXEMPLOS CORRETOS:
        - Meloxicam
        - Oxitetraciclina
        - Fipronil
        
        EXEMPLOS ERRADOS (NÃO FAÇA):
        ❌ "O princípio ativo é Meloxicam"
        ❌ "Aguardando correção, o correto é..."
        ❌ Qualquer texto além do nome
        
        RESPOSTA (apenas o nome):
        """
        
        try:
            response = self.ollama_seguro.chat(
                messages=[{
                    'role': 'system',
                    'content': 'Você extrai substâncias ativas. Responda APENAS com o nome da substância, SEM explicações.'
                }, {
                    'role': 'user',
                    'content': prompt_principio,
                }],
                options={'temperature': 0.0, 'num_predict': 10}  # ← LIMITAR tokens
            )
            
            principio_ativo = response['message']['content'].strip()
            
            # VALIDAÇÃO RIGOROSA - remover lixo se houver
            principio_ativo = self._limpar_principio_ativo(principio_ativo)
            
            if not principio_ativo or principio_ativo.upper() == "NÃO ENCONTRADO":
                return f"❌ Não foi possível identificar o princípio ativo de '{medicamento_referencia}'."
            
            print(colored(f"✅ Princípio ativo identificado: {principio_ativo}", "green"))
            
        except Exception as e:
            return f"❌ Erro ao extrair princípio ativo: {e}"
        
        # FASE 2: Buscar medicamentos com o mesmo princípio ativo
        print(colored(f"🔍 FASE 2: Buscando medicamentos com {principio_ativo}...", "yellow"))
        
        # Se tem espécie especificada, incluir na busca
        termo_busca = principio_ativo
        if especie_alvo:
            termo_busca = f"{principio_ativo} {especie_alvo}"
            print(colored(f"  Incluindo espécie na busca: {especie_alvo}", "cyan"))
        
        resultados_comparacao = self._realizar_busca_comparacao_simples(termo_busca)
        
        if not resultados_comparacao:
            return f"❌ Não foram encontrados outros medicamentos com '{principio_ativo}'."
        
        # Filtrar medicamento de referência dos resultados
        resultados_filtrados = [
            resultado for resultado in resultados_comparacao
            if medicamento_referencia.lower() not in resultado.get('nome', '').lower()
        ]
        
        if not resultados_filtrados:
            return f"ℹ️ Apenas '{medicamento_referencia}' foi encontrado com '{principio_ativo}'."
        
        print(colored(f"✅ Encontrados {len(resultados_filtrados)} medicamentos alternativos", "green"))
        
        # MONTAR RESPOSTA FORMATADA
        if tipo_pergunta == "alternativo":
            resposta = f"**Medicamentos alternativos ao {medicamento_referencia}:**\n\n"
        elif tipo_pergunta == "substituto":
            resposta = f"**Medicamentos substitutos do {medicamento_referencia}:**\n\n"
        elif tipo_pergunta == "equivalente":
            resposta = f"**Medicamentos equivalentes ao {medicamento_referencia}:**\n\n"
        else:
            resposta = f"**Medicamentos com mesmo princípio ativo que {medicamento_referencia}:**\n\n"
        
        resposta += f"🔬 **Princípio ativo:** {principio_ativo}\n"
        
        if especie_alvo:
            resposta += f"🐾 **Espécie:** {especie_alvo}\n"
        
        resposta += f"\n📋 **Medicamentos encontrados ({len(resultados_filtrados)}):**\n\n"
        
        for i, item in enumerate(resultados_filtrados, 1):
            resposta += f"{i}. **{item.get('nome', 'Nome não disponível')}**\n"
            
            if item.get('especies'):
                resposta += f"   - Espécies: {item['especies']}\n"
            
            if item.get('forma_farmaceutica'):
                resposta += f"   - Forma farmacêutica: {item['forma_farmaceutica']}\n"
            
            if item.get('link'):
                resposta += f"   - Link: {item['link']}\n"
            
            resposta += "\n"
        
        resposta += f"\n💡 **Total:** {len(resultados_comparacao)} medicamentos com '{principio_ativo}' "
        resposta += f"({len(resultados_filtrados)} além do {medicamento_referencia})."
        
        return resposta
  
    def realizar_web_scraping_sincrono(self, termo_busca):
      """
      Versão síncrona do web scraping para compatibilidade com código existente
      """
      loop = asyncio.new_event_loop()
      asyncio.set_event_loop(loop)
      try:
          return loop.run_until_complete(self.realizar_web_scraping(termo_busca))
      finally:
          loop.close()

    # Método principal de processamento
    def processar_pergunta_unica(self, pergunta_usuario):
        
        
        # INÍCIO DA MEDIÇÃO TOTAL
        tempo_inicio_total = time.perf_counter()
        self.tempos_execucao['inicio_total'] = tempo_inicio_total
        
        print(colored("⏱️  Iniciando cronômetro...", "cyan"))
        
        self._limpar_contexto_antigo()
        self._verificar_uso_memoria()
        
        # Detectar follow-up
        tempo_inicio_etapa = time.perf_counter()
        is_followup, entidade_extraida = self._detectar_pergunta_followup(pergunta_usuario)
        
        if is_followup and entidade_extraida:
            pergunta_completa = self._construir_pergunta_completa(pergunta_usuario, entidade_extraida)
            print(colored(f"Pergunta processada: '{pergunta_completa}'", "cyan"))
            
            if self.contexto_conversacao["dados_ultimo_scraping"] and self.contexto_conversacao["ultimo_termo_busca"]:
                resposta = self._consultar_ollama_otimizado(
                    pergunta_completa,
                    self.contexto_conversacao["dados_ultimo_scraping"],
                    tipo_consulta="medicamento"
                )
                
                # TEMPO TOTAL
                tempo_total = time.perf_counter() - tempo_inicio_total
                self.tempos_execucao['total'] = tempo_total
                self._imprimir_resumo_tempos()
                
                return resposta
            
            pergunta_usuario = pergunta_completa
        
        # Normalizar pergunta
        pergunta_normalizada = self._normalizar_especies_texto(pergunta_usuario)
        
        if pergunta_normalizada != pergunta_usuario:
            print(colored(f"Pergunta normalizada: '{pergunta_normalizada}'", "cyan"))
        
        print(colored(f"\nProcessando: '{pergunta_normalizada}'", "cyan"))
        
        # ETAPA 1: CLASSIFICAÇÃO
        tempo_inicio_classificacao = time.perf_counter()
        classificacao = self.query_classifier.classify_and_extract(pergunta_normalizada)
        tempo_classificacao = time.perf_counter() - tempo_inicio_classificacao
        self.tempos_execucao['classificacao'] = tempo_classificacao
        print(colored(f"⏱️  Classificação: {tempo_classificacao:.2f}s", "yellow"))

        classificacao = self._corrigir_categoria_se_necesario(classificacao, pergunta_normalizada)

        if not classificacao or classificacao.get("categoria") == "erro":
            tempo_total = time.perf_counter() - tempo_inicio_total
            self.tempos_execucao['total'] = tempo_total
            return "Não foi possível classificar sua pergunta."
        
        categoria = classificacao.get("categoria")
        entidades = classificacao.get("entidades", {})
        pergunta_para_ollama = entidades.get("pergunta_ollama", pergunta_usuario)

        print(colored(f"Categoria: {categoria}", "magenta"))
        print(colored(f"Entidades: {json.dumps(entidades, indent=2, ensure_ascii=False)}", "magenta"))

        self.contexto_conversacao["ultima_pergunta"] = pergunta_normalizada
        self.contexto_conversacao["ultima_categoria"] = categoria
        
        if categoria == "medicamento":
            termo_busca = entidades.get("termo_busca")
            if not termo_busca:
                termo_busca = entidades.get("substancia_ativa") or self._extrair_medicamento_query(pergunta_normalizada)
                print(colored(f"⚠️  Termo de busca usando fallback: '{termo_busca}'", "yellow"))
            
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
                return f"Não foram encontrados resultados para '{termo_busca}'."
            
            self.contexto_conversacao["dados_ultimo_scraping"] = dados_raspados
            self.contexto_conversacao["ultimo_scraping_time"] = time.time()
            
            # ETAPA 3: CONSULTA OLLAMA (já medido internamente)
            resposta = self._consultar_ollama_otimizado(
                pergunta_para_ollama, 
                dados_raspados, 
                tipo_consulta="medicamento",
                classificacao=classificacao,
                pergunta_original=pergunta_normalizada
            )
            
            self.contexto_conversacao["ultima_resposta"] = resposta
            self._adicionar_ao_historico(pergunta_normalizada, resposta, categoria)
            
            # TEMPO TOTAL
            tempo_total = time.perf_counter() - tempo_inicio_total
            self.tempos_execucao['total'] = tempo_total
            self._imprimir_resumo_tempos()
            
            return resposta

        elif categoria == "comparacao":
            if self._detectar_consulta_dupla(classificacao):
                self.contexto_conversacao["ultima_entidade_medicamento"] = None
                self.contexto_conversacao["ultimo_termo_busca"] = None
                self.contexto_conversacao["dados_ultimo_scraping"] = None
                
                resposta = self._realizar_consulta_dupla(classificacao, pergunta_normalizada)
                self.contexto_conversacao["ultima_resposta"] = resposta
                self._adicionar_ao_historico(pergunta_normalizada, resposta, categoria)
                
                tempo_total = time.perf_counter() - tempo_inicio_total
                self.tempos_execucao['total'] = tempo_total
                self._imprimir_resumo_tempos()
                
                return resposta
            
            substancia = entidades.get("substancia_ativa", "")
            especie = entidades.get("especie_alvo", "")
            forma = entidades.get("forma_farmaceutica", "")
            termo_busca_comparacao = f"{substancia} {especie} {forma}".strip()
            
            self.contexto_conversacao["ultima_entidade_medicamento"] = None
            self.contexto_conversacao["ultimo_termo_busca"] = None
            self.contexto_conversacao["dados_ultimo_scraping"] = None
            
            if not termo_busca_comparacao:
                tempo_total = time.perf_counter() - tempo_inicio_total
                self.tempos_execucao['total'] = tempo_total
                return "Para comparação, forneça substância ativa, espécie ou forma farmacêutica."

            resultados_simples = self._realizar_busca_comparacao_simples(termo_busca_comparacao)
            if not resultados_simples:
                tempo_total = time.perf_counter() - tempo_inicio_total
                self.tempos_execucao['total'] = tempo_total
                return f"Não foram encontrados resultados para: '{termo_busca_comparacao}'."
            
            resposta = self._formatar_resultados_comparacao_simples(resultados_simples, pergunta_normalizada)
            self.contexto_conversacao["ultima_resposta"] = resposta
            self._adicionar_ao_historico(pergunta_normalizada, resposta, categoria)
            
            tempo_total = time.perf_counter() - tempo_inicio_total
            self.tempos_execucao['total'] = tempo_total
            self._imprimir_resumo_tempos()
            
            return resposta

        else:
            self.contexto_conversacao["ultima_entidade_medicamento"] = None
            self.contexto_conversacao["ultimo_termo_busca"] = None
            self.contexto_conversacao["dados_ultimo_scraping"] = None
            
            resposta = f"Categoria '{categoria}' não suportada."
            self.contexto_conversacao["ultima_resposta"] = resposta
            
            tempo_total = time.perf_counter() - tempo_inicio_total
            self.tempos_execucao['total'] = tempo_total
            
            return resposta

    def limpar_contexto_manual(self):
        """Limpa o contexto manualmente"""
        self._reiniciar_contexto()
    
    def _corrigir_categoria_se_necesario(self, classificacao, pergunta):
        """Corrige automaticamente categorias erradas"""
        if not classificacao or classificacao.get("categoria") == "erro":
            return classificacao
            
        pergunta_lower = pergunta.lower()
        categoria_atual = classificacao.get("categoria")
        
        # REGRA 1: "mesmo princípio ativo" SEMPRE é comparação
        if "mesmo princípio ativo" in pergunta_lower and categoria_atual != "comparacao":
            print(colored("⚠️  Corrigindo categoria: 'mesmo princípio ativo' deve ser comparação", "yellow"))
            classificacao["categoria"] = "comparacao"
            
        # REGRA 2: "alternativ" SEMPRE é comparação  
        if "alternativ" in pergunta_lower and categoria_atual != "comparacao":
            print(colored("⚠️  Corrigindo categoria: 'alternativa' deve ser comparação", "yellow"))
            classificacao["categoria"] = "comparacao"
            
        return classificacao

# Função principal
def main():
    print(colored("=== Sistema Inteligente de Consulta Veterinária (Otimizado) ===", "green"))
    
    # Criar instância do sistema (não usar async with)
    sistema = SistemaConsultaVetOtimizado()
    
    while True:
        try:
            pergunta = input(colored("\nDigite sua pergunta (ou 'sair' para terminar): ", "yellow"))
            if pergunta.lower() == 'sair':
                break
            if not pergunta.strip():
                continue
            
            resposta = sistema.processar_pergunta_unica(pergunta)
            print(colored("\nResposta do Sistema:", "green"))
            print(resposta)
            
        except KeyboardInterrupt:
            print(colored("\nSaindo do sistema...", "red"))
            break
        except Exception as e:
            print(colored(f"Erro inesperado: {e}", "red"))
    
    # Fechar a sessão manualmente se existir
    if hasattr(sistema, 'session') and sistema.session:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(sistema.session.close())
        finally:
            loop.close()
    

if __name__ == "__main__":
    main()