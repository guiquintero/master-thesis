#Qual a forma de administração do medicamento Animedazon em porcos ( ou outra espécie pecuária)?

import json
import os
import time
import hashlib
from termcolor import colored
import ollama
import asyncio

# Importações do código original (serão adaptadas e integradas)
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
import fitz  # PyMuPDF
import re
import concurrent.futures
from tqdm import tqdm

# Importar o classificador de query
from query_classifier import QueryClassifier

# Desativar alertas de aviso de SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
}

# Configurações globais
MODELO_OLLAMA_PADRAO = "gemma3:latest"
PDF_CACHE_DIR = "pdf_cache_novo"
CACHE_DIR_RESPOSTAS = "resposta_cache_novo"
ARQUIVO_JSON_SCRAPING = "medicamento_buscado_novo.json"

MAX_CONCURRENT_REQUESTS = 5
MAX_PDF_PAGES = 10  # Limitar páginas de PDF processadas
CACHE_TTL = 86400   # 24 horas
CONTEXT_SIZE_LIMIT = 30000  # Limite de caracteres para contexto


# Criar diretórios de cache se não existirem
os.makedirs(PDF_CACHE_DIR, exist_ok=True)
os.makedirs(CACHE_DIR_RESPOSTAS, exist_ok=True)

# Variáveis globais para web scraping (serão encapsuladas em uma classe ou função)
resultados_scraping = []
urls_visitadas_scraping = set()

class SistemaConsultaVet:
    def __init__(self, modelo_ollama=MODELO_OLLAMA_PADRAO, temperatura_ollama=0.2):
        self.modelo_ollama = modelo_ollama
        self.temperatura_ollama = temperatura_ollama
        self.query_classifier = QueryClassifier(modelo_ollama)

        self.mapeamento_especies = self._criar_mapeamento_especies()
        
        # Adicionar contexto de conversação
        self.contexto_conversacao = {
            "ultima_pergunta": None,
            "ultima_categoria": None,
            "ultima_entidade_medicamento": None,
            "ultimo_termo_busca": None,
            "ultima_resposta": None,
            "dados_ultimo_scraping": None
        }

    # def _gerar_hash_consulta(self, texto):
    #     return hashlib.md5(texto.encode('utf-8')).hexdigest()

    def _gerar_cache_key_inteligente(self, classificacao):
        """Gera uma chave de cache baseada nas entidades extraídas"""
        entidades = classificacao.get("entidades", {})
        categoria = classificacao.get("categoria", "")
        
        # Criar uma string única baseada na categoria e entidades principais
        if categoria == "medicamento":
            key_parts = [
                categoria,
                entidades.get("termo_busca", "").lower().strip()
            ]
        elif categoria == "comparacao":
            key_parts = [
                categoria,
                entidades.get("substancia_ativa", "").lower().strip(),
                entidades.get("especie_alvo", "").lower().strip(),
                entidades.get("forma_farmaceutica", "").lower().strip()
            ]

        else:
            key_parts = [categoria, entidades.get("pergunta_ollama", "").lower()]
        
        # Remover partes vazias e criar hash
        key_parts = [part for part in key_parts if part]
        cache_key = "_".join(key_parts)
        return hashlib.md5(cache_key.encode('utf-8')).hexdigest()
    
    
    def _verificar_intencao_rapida(self, pergunta1, pergunta2):
        """
        Verificação rápida de intenção sem usar Ollama
        """
        # Casos óbvios onde as perguntas são muito similares
        p1 = pergunta1.lower().strip()
        p2 = pergunta2.lower().strip()
        
        # Se forem exatamente iguais
        if p1 == p2:
            return True
        
        # Se uma é substring da outra
        if p1 in p2 or p2 in p1:
            return True
        
        # Verificar palavras-chave em comum
        palavras1 = set(p1.split())
        palavras2 = set(p2.split())
        palavras_comuns = palavras1.intersection(palavras2)
        
        # Se tiverem pelo menos 60% de palavras em comum
        if (len(palavras_comuns) / max(len(palavras1), len(palavras2))) > 0.6:
            return True
        
        # Para casos não óbvios, usar verificação com Ollama (mais lenta)
        return self._verificar_intencao_similar(pergunta1, pergunta2)

    # def _verificar_intencao_similar(self, pergunta_atual, pergunta_cache):
    #     """Usa IA para verificar se duas perguntas têm intenção similar"""
    #     prompt = f"""
    #     Analise se as duas perguntas abaixo têm a mesma intenção/objetivo, mesmo que sejam formuladas de forma diferente.
        
    #     Pergunta 1: "{pergunta_atual}"
    #     Pergunta 2: "{pergunta_cache}"
        
    #     Responda apenas "SIM" se as perguntas têm a mesma intenção ou "NAO" se têm intenções diferentes.
        
    #     Exemplos de perguntas com mesma intenção:
    #     - "Qual a dose do medicamento X?" e "Que dose devo dar do X?"
    #     - "Como armazenar Y?" e "Qual a forma de armazenamento do Y?"
    #     - "Para que serve Z?" e "Qual a indicação do Z?"
        
    #     Resposta:
    #     """
        
    #     try:
    #         response = ollama.chat(
    #             model=self.modelo_ollama,
    #             messages=[
    #                 {
    #                     'role': 'system',
    #                     'content': 'Você é um analisador de intenções de perguntas. Responda apenas SIM ou NAO.'
    #                 },
    #                 {
    #                     'role': 'user',
    #                     'content': prompt,
    #                 }
    #             ],
    #             options={'temperature': 0.0}  # Determinístico
    #         )
    #         resposta = response['message']['content'].strip().upper()
    #         return resposta == "SIM"
    #     except Exception as e:
    #         print(colored(f"Erro ao verificar intenção: {e}", "red"))
    #         return False

    def _carregar_resposta_cache_inteligente(self, classificacao, pergunta_atual):
        """Versão otimizada do cache inteligente"""
        cache_key = self._gerar_cache_key_inteligente(classificacao)
        arquivo_cache = os.path.join(CACHE_DIR_RESPOSTAS, f"smart_{cache_key}.json")
        
        if not os.path.exists(arquivo_cache):
            return None
        
        try:
            # Verificar se o cache é recente (menos de 24 horas)
            cache_age = time.time() - os.path.getmtime(arquivo_cache)
            if cache_age > 86400:  # 24 horas
                return None
                
            with open(arquivo_cache, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Verificação rápida de entidades (sem IA para maior velocidade)
            entidades_cache = cache_data.get('entidades', {})
            entidades_atual = classificacao.get('entidades', {})
            
            categoria = classificacao.get('categoria')
            if categoria == "medicamento":
                if (entidades_cache.get('termo_busca', '').lower() != 
                    entidades_atual.get('termo_busca', '').lower()):
                    return None
                    
            # Verificação de intenção simplificada para casos óbvios
            pergunta_cache = cache_data.get('pergunta_original', '')
            if self._verificar_intencao_rapida(pergunta_atual, pergunta_cache):
                return cache_data.get('resposta')
                
        except Exception:
            return None
        
        return None

    def _salvar_resposta_cache_inteligente(self, classificacao, pergunta_original, resposta):
        """Salva resposta no cache inteligente com entidades e intenção"""
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
            print(colored("Resposta salva no cache inteligente.", "green"))
        except Exception as e:
            print(colored(f"Erro ao salvar cache inteligente: {e}", "red"))

    def _carregar_resposta_cache(self, hash_consulta):
        arquivo_cache = os.path.join(CACHE_DIR_RESPOSTAS, f"{hash_consulta}.json")
        if os.path.exists(arquivo_cache):
            try:
                with open(arquivo_cache, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
                    return cache.get('resposta')
            except:
                return None
        return None

    def _salvar_resposta_cache(self, hash_consulta, resposta):
        arquivo_cache = os.path.join(CACHE_DIR_RESPOSTAS, f"{hash_consulta}.json")
        with open(arquivo_cache, 'w', encoding='utf-8') as f:
            json.dump({'resposta': resposta}, f, ensure_ascii=False, indent=2)

    def _consultar_ollama_otimizado(self, pergunta_ollama, contexto_dados, tipo_consulta="medicamento", classificacao=None, pergunta_original=None):
        """
        Versão otimizada da consulta Ollama com compressão de contexto e cache inteligente
        """
        # 1. Verificar cache inteligente primeiro
        if classificacao and pergunta_original:
            resposta_cache = self._carregar_resposta_cache_inteligente(classificacao, pergunta_original)
            if resposta_cache:
                print(colored("✓ Resposta encontrada no cache inteligente", "green"))
                return resposta_cache

        # 2. Comprimir contexto se for muito grande
        contexto_otimizado = self._comprimir_contexto_ollama(contexto_dados, tipo_consulta, pergunta_ollama)
        
        # 3. Gerar prompt otimizado
        prompt = self._gerar_prompt_otimizado(pergunta_ollama, contexto_otimizado, tipo_consulta)
        
        # 4. Fazer consulta com timeout
        try:
            print(colored("Consultando Ollama (versão otimizada)...", "yellow"))
            start_time = time.perf_counter()
            
            response = ollama.chat(
                model=self.modelo_ollama,
                messages=[
                    {
                        'role': 'system',
                        'content': 'Você é um assistente especializado em informações veterinárias portuguesas. Responda de forma concisa e baseada estritamente no contexto fornecido.'
                    },
                    {
                        'role': 'user',
                        'content': prompt,
                    }
                ],
                options={
                    'temperature': self.temperatura_ollama,
                    'num_predict': 500,  # Limitar tamanho da resposta
                    'timeout': 120  # Timeout de 2 minutos
                }
            )
            
            resposta_ollama = response['message']['content']
            end_time = time.perf_counter()
            
            print(colored(f"Consulta Ollama concluída em {(end_time - start_time):.2f}s", "yellow"))
            
            # 5. Salvar no cache inteligente
            if classificacao and pergunta_original:
                self._salvar_resposta_cache_inteligente(classificacao, pergunta_original, resposta_ollama)
            
            return resposta_ollama
            
        except Exception as e:
            error_msg = f"Erro ao consultar Ollama: {e}"
            print(colored(error_msg, "red"))
            return error_msg

    def _comprimir_contexto_ollama(self, contexto_dados, tipo_consulta, pergunta_ollama):
        """
        Comprime o contexto mantendo apenas informações relevantes para a pergunta
        """
        if not contexto_dados:
            return []
        
        # Se o contexto já é pequeno, não comprimir
        contexto_str = json.dumps(contexto_dados, ensure_ascii=False)
        if len(contexto_str) <= 20000:
            return contexto_dados
        
        print(colored(f"Comprimindo contexto ({len(contexto_str)} chars -> ~20000 chars)", "yellow"))
        
        contexto_comprimido = []
        
        if tipo_consulta == "medicamento":
            # Para consultas de medicamento, priorizar informações do medicamento principal
            palavras_chave = pergunta_ollama.lower().split()
            
            for item in contexto_dados:
                item_comprimido = {
                    'nome': item.get('nome'),
                    'url': item.get('url')
                }
                
                # Manter HTML relevante (limitado)
                if item.get('conteudo_html'):
                    html = item['conteudo_html']
                    # Manter apenas partes que contêm palavras-chave
                    linhas_relevantes = []
                    for linha in html.split('\n'):
                        if any(palavra in linha.lower() for palavra in palavras_chave):
                            linhas_relevantes.append(linha)
                    
                    if linhas_relevantes:
                        item_comprimido['conteudo_html'] = '\n'.join(linhas_relevantes[:10])  # Limitar a 10 linhas
                    else:
                        # Se não encontrar palavras-chave, manter um resumo
                        item_comprimido['conteudo_html'] = html[:500] + "..." if len(html) > 500 else html
                
                # Manter apenas as primeiras 3 seções do PDF
                if item.get('conteudo_pdf'):
                    item_comprimido['conteudo_pdf'] = item['conteudo_pdf'][:3]
                
                contexto_comprimido.append(item_comprimido)
        
        elif tipo_consulta == "comparacao":
            # Para comparações, manter apenas informações de listagem
            for item in contexto_dados:
                item_comprimido = {
                    'nome': item.get('nome'),
                    'url': item.get('url'),
                    'informacoes_visiveis': item.get('informacoes_visiveis', '')[:300] + "..."
                }
                contexto_comprimido.append(item_comprimido)
        
        else:
            # Estratégia genérica de compressão
            for item in contexto_dados[:3]:  # Limitar a 3 itens
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
        """
        Gera prompt otimizado baseado no tipo de consulta
        """
        contexto_json = json.dumps(contexto_otimizado, ensure_ascii=False, indent=2)
        
        if tipo_consulta == "medicamento":
            return f"""
            ANALISE ESTRITA DO CONTEXTO - MEDICAMENTO VETERINÁRIO

            CONTEXTO DISPONÍVEL (extraído de fontes oficiais):
            ```json
            {contexto_json}
            ```

            PERGUNTA ESPECÍFICA: "{pergunta_ollama}"

            INSTRUÇÕES RÍGIDAS:
            1. Responda APENAS com base nas informações presentes no contexto acima
            2. Seja extremamente conciso e direto ao ponto
            3. Se a informação não estiver no contexto, responda: "Não encontrei informações sobre isso no material disponível"
            4. Cite a URL de origem quando aplicável
            5. Não faça inferências ou suposições não baseadas no contexto

            RESPOSTA:
            """
        
        elif tipo_consulta == "comparacao":
            return f"""
            ANÁLISE COMPARATIVA - MEDICAMENTOS VETERINÁRIOS

            LISTA DE MEDICAMENTOS DISPONÍVEIS:
            ```json
            {contexto_json}
            ```

            SOLICITAÇÃO DE COMPARAÇÃO: "{pergunta_ollama}"

            INSTRUÇÕES:
            1. Liste apenas os medicamentos presentes no contexto acima
            2. Compare as características relevantes (espécie, forma farmacêutica, etc.)
            3. Seja objetivo e organize a resposta em tópicos
            4. Se não houver medicamentos no contexto, informe: "Nenhum medicamento encontrado para os critérios solicitados"

            RESPOSTA COMPARATIVA:
            """
        
        else:
            return f"""
            Com base no seguinte contexto:
            {contexto_json}
            
            Responda à pergunta: "{pergunta_ollama}"
            """

    def _criar_mapeamento_especies(self):
        """Cria um dicionário de mapeamento para normalizar nomes de espécies animais"""
        mapeamento = {}
        
        # Suínos
        sinonimos_suinos = ["suíno", "suino", "suínos", "suinos", "porco", "porcos", "leitão", "leitões", "porcino"]
        for sinonimo in sinonimos_suinos:
            mapeamento[sinonimo.lower()] = "suínos"
        
        # Cães
        sinonimos_caes = ["cão", "cao", "cães", "cachorro", "cachorros", "cadela", "cadelas", "canino", "caninos"]
        for sinonimo in sinonimos_caes:
            mapeamento[sinonimo.lower()] = "cães"
        
        # Gatos
        sinonimos_gatos = ["gato", "gatos", "gata", "gatas", "felino", "felinos", "gatinho", "gatinhos"]
        for sinonimo in sinonimos_gatos:
            mapeamento[sinonimo.lower()] = "gatos"
        
        # Bovinos
        sinonimos_bovinos = ["bovino", "bovinos", "vaca", "vacas", "novilho", "novilhos", "touro", "touros", 
                            "bezerro", "bezerros", "vitela", "vitelas", "vitelo", "vitelos"]
        for sinonimo in sinonimos_bovinos:
            mapeamento[sinonimo.lower()] = "bovinos"
        
        # Ovinos
        sinonimos_ovinos = ["ovino", "ovinos", "ovelha", "ovelhas", "carneiro", "carneiros", 
                           "borrego", "borregos", "cordeiro", "cordeiros"]
        for sinonimo in sinonimos_ovinos:
            mapeamento[sinonimo.lower()] = "ovinos"
        
        # Caprinos
        sinonimos_caprinos = ["caprino", "caprinos", "cabra", "cabras", "bode", "bodes"]
        for sinonimo in sinonimos_caprinos:
            mapeamento[sinonimo.lower()] = "caprinos" 
        
        # Coelhos
        sinonimos_coelhos = ["coelho", "coelhos", "coelha", "coelhas", "leporídeo", "leporídeos", 
                            "leporideo", "leporideos"]
        for sinonimo in sinonimos_coelhos:
            mapeamento[sinonimo.lower()] = "coelhos"
        
        # Equinos
        sinonimos_equinos = ["cavalo", "cavalos", "égua", "éguas", "egua", "eguas", "potro", "potros", 
                            "equino", "equinos", "equideo", "equideos", "equídeo", "equídeos"]
        for sinonimo in sinonimos_equinos:
            mapeamento[sinonimo.lower()] = "equinos"
        
        return mapeamento

    def _normalizar_especies_texto(self, texto):
        """Normaliza as espécies animais no texto substituindo sinônimos pelos termos padrão"""
        import re
        
        texto_normalizado = texto
        
        # Para cada mapeamento, substituir as palavras preservando maiúsculas/minúsculas do contexto
        for sinonimo, padrao in self.mapeamento_especies.items():
            # Criar padrão regex para encontrar a palavra completa (não parte de outra palavra)
            pattern = r'\b' + re.escape(sinonimo) + r'\b'
            
            def substituir_preservando_caso(match):
                palavra_encontrada = match.group()
                # Se a palavra original estava em maiúscula, manter maiúscula
                if palavra_encontrada.isupper():
                    return padrao.upper()
                elif palavra_encontrada.istitle():
                    return padrao.capitalize()
                else:
                    return padrao
            
            # Substituir ignorando maiúsculas/minúsculas mas preservando o caso original
            texto_normalizado = re.sub(pattern, substituir_preservando_caso, texto_normalizado, flags=re.IGNORECASE)
        
        return texto_normalizado



    # ========== FUNÇÕES DE WEB SCRAPING  ==========

    def _extrair_conteudo_pdf_otimizado(self, pdf_url):
        cache_filename = os.path.join(PDF_CACHE_DIR, hashlib.md5(pdf_url.encode()).hexdigest() + ".pdf")
        
        # Verificar se já temos o conteúdo extraído em cache
        text_cache = cache_filename.replace(".pdf", ".txt")
        if os.path.exists(text_cache):
            try:
                with open(text_cache, 'r', encoding='utf-8') as f:
                    return f.read()
            except:
                pass
        
        # Se não, processar o PDF
        if not os.path.exists(cache_filename):
            try:
                pdf_response = requests.get(pdf_url, timeout=15, headers=HEADERS, verify=False)
                pdf_response.raise_for_status()
                with open(cache_filename, 'wb') as f:
                    f.write(pdf_response.content)
            except:
                return None
        
        try:
            with fitz.open(cache_filename) as pdf_file:
                texto = "\n".join([page.get_text() for page in pdf_file])
                
                # Salvar texto extraído em cache
                with open(text_cache, 'w', encoding='utf-8') as f:
                    f.write(texto)
                
                return texto
        except:
            return None

    def _formatar_conteudo_pdf(self, texto):
        if not texto:
            return []
        texto_limpo = texto
        texto_limpo = re.sub(r"\nDireção Geral de Alimentação e Veterinária – DGAMV.*?Página \d+ de \d+ \n", "", texto_limpo, flags=re.DOTALL)
        texto_limpo = re.sub(r"\n\d+\.\d+ \n", "--", texto_limpo)
        texto_limpo = re.sub(r"\n\d+\.\d+  \n", "--", texto_limpo)
        partes_folheto = re.split(r"(FOLHETO INFORMATIVO)", texto_limpo, flags=re.IGNORECASE)
        if len(partes_folheto) > 1:
            texto_limpo = partes_folheto[0]
        partes = re.split(r"\n \n\d+\. \n", texto_limpo)
        partes_formatadas = []
        for parte in partes:
            parte_limpa = parte.strip()
            parte_limpa = re.sub(r"\n(?!\n)", " ", parte_limpa)
            parte_limpa = re.sub(r"\n\n+", "\n\n", parte_limpa)
            partes_formatadas.append(parte_limpa)
        return partes_formatadas

    def _formatar_texto_html(self, elemento):
        if elemento.name in {"h1", "h2", "h3", "h4", "h5", "a", "p"}:
            return elemento.get_text(strip=True)
        return None

    def _encontrar_link_pdf(self, soup, url):
        pdf_tag = soup.find("a", href=True, target="_blank")
        if pdf_tag and pdf_tag.find("span", class_="fa-file-pdf-o"):
            return urljoin(url, pdf_tag["href"])
        return None

    async def _processar_links_async(self, links_info):
        """Processa múltiplos links de forma assíncrona"""
        connector = TCPConnector(limit=5, ssl=False)  # 5 conexões simultâneas
        async with ClientSession(connector=connector, headers=HEADERS) as session:
            tasks = []
            for link_info in links_info:
                task = self._processar_link_async(session, link_info)
                tasks.append(task)
            
            # Processar todos os links simultaneamente
            resultados = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Filtrar resultados válidos
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
                    print(colored(f"Erro HTTP {response.status} em {link_info['link']}", "red"))
                    return None
                
                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")
                
                # Extrair conteúdo HTML (igual ao método original)
                conteudo_item = {
                    "url": link_info['link'],
                    "titulo": link_info['titulo'],
                    "conteudo_html": "",
                    "conteudo_pdf": []
                }
                
                tags_permitidas = {"h1", "h2", "h3", "h4", "h5", "p", "a"}
                encontrou_titulo_no_html = False
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
                                if not encontrou_titulo_no_html and link_info['titulo'].lower() in texto_formatado.lower():
                                    encontrou_titulo_no_html = True
                            else:
                                html_str += texto_formatado + " "
                
                conteudo_item["conteudo_html"] = html_str.strip()
                
                # Extrair PDF de forma assíncrona
                pdf_url = self._encontrar_link_pdf(soup, link_info['link'])
                if pdf_url:
                    pdf_text = await self._extrair_conteudo_pdf_async(pdf_url)
                    if pdf_text:
                        conteudo_item["conteudo_pdf"] = self._formatar_conteudo_pdf(pdf_text)
                        print(colored(f"✓ PDF extraído de: {pdf_url}", "green"))
                    else:
                        print(colored(f"⚠ Erro ao extrair PDF de: {pdf_url}", "yellow"))
                
                # Mesclar com dados básicos
                resultado_final = {**link_info['dados_basicos'], **conteudo_item}
                return resultado_final
                
        except Exception as e:
            print(colored(f"Erro ao processar {link_info['link']}: {e}", "red"))
            # Retornar pelo menos os dados básicos
            return link_info['dados_basicos']

    async def _extrair_conteudo_pdf_async(self, pdf_url):
        """Versão assíncrona da extração de PDF"""
        cache_filename = os.path.join(PDF_CACHE_DIR, hashlib.md5(pdf_url.encode()).hexdigest() + ".pdf")
        text_cache = cache_filename.replace(".pdf", ".txt")
        
        # Verificar cache de texto primeiro
        if os.path.exists(text_cache):
            try:
                with open(text_cache, 'r', encoding='utf-8') as f:
                    return f.read()
            except:
                pass
        
        # Baixar PDF se necessário
        if not os.path.exists(cache_filename):
            try:
                async with aiohttp.ClientSession(headers=HEADERS) as session:
                    async with session.get(pdf_url, ssl=False) as response:
                        if response.status == 200:
                            pdf_content = await response.read()
                            with open(cache_filename, 'wb') as f:
                                f.write(pdf_content)
            except:
                return None
        
        # Processar PDF (esta parte ainda é síncrona, mas rápida)
        try:
            with fitz.open(cache_filename) as pdf_file:
                texto = "\n".join([page.get_text() for page in pdf_file])
                
                # Salvar em cache de texto
                with open(text_cache, 'w', encoding='utf-8') as f:
                    f.write(texto)
                
                return texto
        except:
            return None

    def _extrair_conteudo_pagina_resultados(self, url_busca):
        """Extrai os links dos resultados da página de busca."""
        global urls_visitadas_scraping, resultados_scraping
        if url_busca in urls_visitadas_scraping:
            return
        urls_visitadas_scraping.add(url_busca)

        try:
            response = requests.get(url_busca, timeout=20, headers=HEADERS, verify=False)
            response.raise_for_status()
            response.encoding = "utf-8"
        except requests.RequestException as e:
            print(colored(f"Erro ao acessar página de resultados {url_busca}: {e}", "red"))
            return

        soup = BeautifulSoup(response.text, "html.parser")
        # A classe 'search-result' é do código original, verificar se ainda é válida
        itens_resultado = soup.find_all("div", class_="search-result") 

        if not itens_resultado:
            print(colored(f"Nenhuma div 'search-result' encontrada em {url_busca}", "yellow"))
            # Tentar uma abordagem mais genérica se a específica falhar
            # Por exemplo, procurar por todos os links dentro de uma área principal
            # Esta parte pode precisar de ajuste dependendo da estrutura real do site
            links_na_pagina = soup.find_all("a", href=True)
            for link_tag in links_na_pagina:
                link_url = urljoin(url_busca, link_tag["href"])
                # Adicionar heurísticas para filtrar links relevantes (ex: contêm 'produto', 'medicamento')
                if "medvet.dgav.pt/medvet/med" in link_url: # Exemplo de filtro
                    titulo = link_tag.get_text(strip=True) or "Título não encontrado"
                    if not any(r['link'] == link_url for r in resultados_scraping):
                         resultados_scraping.append({"titulo": titulo, "link": link_url})
            return

        for div in itens_resultado:
            h5 = div.find("h5")
            link_tag = div.find("a", href=True)
            if h5 and link_tag:
                titulo = h5.text.strip()
                link_url = urljoin(url_busca, link_tag["href"])
                if not any(r['link'] == link_url for r in resultados_scraping):
                    resultados_scraping.append({"titulo": titulo, "link": link_url})
        
        # Lógica de paginação (se houver)
        navbar = soup.find("div", class_="navbar") # Do código original
        if navbar:
            for link_tag in navbar.find_all("a", href=True):
                link_url = urljoin(url_busca, link_tag["href"])
                if link_url not in urls_visitadas_scraping:
                    self._extrair_conteudo_pagina_resultados(link_url)

    def _extrair_informacoes_pagina_busca(self, url_busca, urls_processadas=None):
        """Extrai informações diretamente da página de busca sem entrar em cada medicamento"""
        if urls_processadas is None:
            urls_processadas = set()
        
        # Evitar processamento duplicado de URLs
        if url_busca in urls_processadas:
            return []
        urls_processadas.add(url_busca)
        
        print(colored(f"Processando URL: {url_busca}", "cyan"))
        
        try:
            response = requests.get(url_busca, timeout=20, headers=HEADERS, verify=False)
            response.raise_for_status()
            response.encoding = "utf-8"
        except requests.RequestException as e:
            print(colored(f"Erro ao acessar página de resultados {url_busca}: {e}", "red"))
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        
        # Procurar por divs de resultado
        itens_resultado = soup.find_all("div", class_="search-result")
        
        if not itens_resultado:
            print(colored(f"Nenhuma div 'search-result' encontrada em {url_busca}", "yellow"))
            # Tentar abordagem alternativa
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
                
                # Extrair título/nome do medicamento
                h5 = div.find("h5")
                if h5:
                    item_info["nome"] = h5.get_text(strip=True)
                
                # Extrair link
                link_tag = div.find("a", href=True)
                if link_tag:
                    item_info["link"] = urljoin(url_busca, link_tag["href"])
                
                # Extrair todas as informações visíveis no resultado
                texto_completo = div.get_text(separator=" ", strip=True)
                item_info["informacoes_visiveis"] = texto_completo
                
                # Tentar extrair informações específicas se estiverem estruturadas
                linhas = texto_completo.split('\n')
                for linha in linhas:
                    linha_limpa = linha.strip()
                    if linha_limpa:
                        # Procurar padrões específicos
                        if any(palavra in linha_limpa.lower() for palavra in ['espécie', 'especie', 'animal']):
                            item_info["especies"] = linha_limpa
                        elif any(palavra in linha_limpa.lower() for palavra in ['forma', 'tipo', 'apresentação', 'apresentacao']):
                            item_info["forma_farmaceutica"] = linha_limpa
                        elif any(palavra in linha_limpa.lower() for palavra in ['princípio', 'principio', 'ativo', 'substância', 'substancia']):
                            item_info["principio_ativo"] = linha_limpa
                
                if item_info.get("nome"):
                    resultados_pagina.append(item_info)

        print(colored(f"Encontrados {len(resultados_pagina)} resultados nesta página", "green"))

        # Buscar por links de paginação - versão melhorada
        print(colored("Procurando por links de paginação...", "blue"))
        
        # Procurar por diferentes estruturas de paginação
        links_paginacao = []
        
        # 1. Procurar por div navbar (estrutura original)
        navbar = soup.find("div", class_="navbar")
        if navbar:
            print(colored("Encontrada navbar para paginação", "blue"))
            
            # Primeiro, vamos extrair TODOS os links numéricos da navbar
            links_numericos = []
            for link_tag in navbar.find_all("a", href=True):
                link_url = urljoin(url_busca, link_tag["href"])
                link_text = link_tag.get_text(strip=True)
                print(colored(f"Link encontrado na navbar: {link_text} -> {link_url}", "yellow"))
                
                # Se o texto é um número, adicionar à lista de páginas numéricas
                if link_text.isdigit():
                    pagina_num = int(link_text)
                    links_numericos.append((pagina_num, link_url))
                    if link_url not in urls_processadas:
                        links_paginacao.append(link_url)
                        print(colored(f"Link de página numérica identificado: {link_text} -> {link_url}", "green"))
                
                # Verificar se é link de paginação (não numérico)
                elif (link_url != url_busca and 
                      link_url not in urls_processadas):
                    
                    # Critérios para outros tipos de paginação
                    is_pagination = (
                        "page=" in link_url.lower() or
                        "p=" in link_url.lower() or
                        any(palavra in link_text.lower() for palavra in ['próxima', 'next', '>', 'seguinte', 'anterior', 'prev', '<']) or
                        "offset=" in link_url.lower() or
                        "start=" in link_url.lower()
                    )
                    
                    if is_pagination:
                        links_paginacao.append(link_url)
                        print(colored(f"Link de paginação identificado: {link_url}", "green"))
            
            # Ordenar links numéricos e adicionar informação sobre eles
            if links_numericos:
                links_numericos.sort(key=lambda x: x[0])  # Ordenar por número da página
                print(colored(f"Encontradas {len(links_numericos)} páginas numéricas: {[x[0] for x in links_numericos]}", "blue"))
        
        # 2. Procurar por outras estruturas de paginação comuns
        for class_name in ["pagination", "pager", "page-nav", "nav-pages"]:
            paginacao_div = soup.find("div", class_=class_name)
            if paginacao_div:
                print(colored(f"Encontrada div de paginação: {class_name}", "blue"))
                for link_tag in paginacao_div.find_all("a", href=True):
                    link_url = urljoin(url_busca, link_tag["href"])
                    if link_url not in urls_processadas and link_url != url_busca:
                        links_paginacao.append(link_url)
                        print(colored(f"Link de paginação adicional: {link_url}", "green"))
        
        # 3. Procurar por links com texto indicativo de "próxima página"
        all_links = soup.find_all("a", href=True)
        for link_tag in all_links:
            link_text = link_tag.get_text(strip=True).lower()
            if any(palavra in link_text for palavra in ['próxima', 'next', 'seguinte', 'mais resultados']):
                link_url = urljoin(url_busca, link_tag["href"])
                if link_url not in urls_processadas and link_url != url_busca:
                    links_paginacao.append(link_url)
                    print(colored(f"Link 'próxima' encontrado: {link_url}", "green"))
        
        # Remover duplicatas
        links_paginacao = list(set(links_paginacao))
        
        if links_paginacao:
            print(colored(f"Total de {len(links_paginacao)} links de paginação encontrados", "green"))
            # Processar páginas de paginação (limitar para evitar loops infinitos)
            for i, link_paginacao in enumerate(links_paginacao[:10]):  # Aumentei para 10 páginas
                print(colored(f"Processando página adicional {i+1}/{min(len(links_paginacao), 10)}: {link_paginacao}", "blue"))
                resultados_adicionais = self._extrair_informacoes_pagina_busca(link_paginacao, urls_processadas)
                resultados_pagina.extend(resultados_adicionais)
                
                # Pequena pausa entre requisições para não sobrecarregar o servidor
                time.sleep(1)
        else:
            print(colored("Nenhum link de paginação encontrado", "yellow"))
        
        print(colored(f"Total de {len(resultados_pagina)} resultados extraídos da página: {url_busca}", "green"))
        return resultados_pagina

    def _realizar_busca_comparacao_simples(self, termo_busca):
        """Realiza busca e extrai informações diretamente da página de resultados"""
        print(colored(f"Iniciando busca de comparação simples para: '{termo_busca}'", "blue"))
        
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
            time.sleep(5)
            url_pagina_busca = driver.current_url
        except Exception as e:
            print(colored(f"Erro durante a navegação com Selenium: {e}", "red"))
            if driver:
                driver.quit()
            return None
        finally:
            if driver:
                driver.quit()

        if not url_pagina_busca or url_pagina_busca == "https://medvet.dgav.pt/":
            print(colored("Não foi possível obter a URL da página de resultados da busca.", "red"))
            return None

        print(colored(f"Extraindo informações da página de resultados: {url_pagina_busca}", "blue"))
        # Inicializar o conjunto de URLs processadas para evitar loops
        urls_processadas = set()
        resultados = self._extrair_informacoes_pagina_busca(url_pagina_busca, urls_processadas)
        
        # Remover duplicatas baseadas no nome do medicamento
        resultados_unicos = []
        nomes_vistos = set()
        for resultado in resultados:
            nome = resultado.get('nome', '').strip()
            if nome and nome not in nomes_vistos:
                nomes_vistos.add(nome)
                resultados_unicos.append(resultado)
        
        print(colored(f"Total de resultados únicos encontrados: {len(resultados_unicos)}", "green"))
        return resultados_unicos

    def _formatar_resultados_comparacao_simples(self, resultados, pergunta_original):
        """Formata os resultados da comparação simples para exibição"""
        if not resultados:
            return "Nenhum medicamento encontrado para os critérios de busca."
        
        resposta = f"Resultados encontrados para: '{pergunta_original}'\n\n"
        resposta += f"Total de medicamentos encontrados: {len(resultados)}\n\n"
        
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
            
            # Se não tiver informações específicas, mostrar as informações visíveis resumidas
            if not any([item.get('especies'), item.get('forma_farmaceutica'), item.get('principio_ativo')]):
                info_resumida = item.get('informacoes_visiveis', '')
                if len(info_resumida) > 150:
                    info_resumida = info_resumida[:150] + "..."
                resposta += f"   - Informações: {info_resumida}\n"
            
            resposta += "\n"
        
        resposta += "\nNota: Estas informações foram extraídas diretamente da página de busca com paginação automática. Para informações mais detalhadas, consulte os links individuais dos medicamentos."
        
        return resposta

    async def realizar_web_scraping(self, termo_busca):
        """Realiza o web scraping com base no termo de busca fornecido."""
        print(colored(f"Iniciando web scraping para o termo: '{termo_busca}'", "blue"))
        
        # Configurar opções do Chrome para execução headless
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
            # Abrir o navegador e acessar o site
            driver = webdriver.Chrome(options=chrome_options)
            driver.get("https://medvet.dgav.pt/")
            wait = WebDriverWait(driver, 20)
            
            # Localizar a barra de busca e inserir o termo
            input_box = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text'], input[type='search']")))
            input_box.send_keys(termo_busca)
            input_box.send_keys(Keys.RETURN)
            time.sleep(5)
            
            # Capturar a URL da página de resultados
            url_pagina_busca = driver.current_url
        except Exception as e:
            print(colored(f"Erro durante a navegação com Selenium: {e}", "red"))
            if driver:
                driver.quit()
            return None
        finally:
            if driver:
                driver.quit()

        if not url_pagina_busca or url_pagina_busca == "https://medvet.dgav.pt/":
            print(colored("Não foi possível obter a URL da página de resultados da busca.", "red"))
            return None

        print(colored(f"Extraindo informações da página de resultados: {url_pagina_busca}", "blue"))
        
        # PASSO 1: Extrair informações básicas da página de resultados
        urls_processadas = set()
        resultados_basicos = self._extrair_informacoes_pagina_busca(url_pagina_busca, urls_processadas)
        
        if not resultados_basicos:
            print(colored("Nenhum resultado encontrado na página de busca.", "yellow"))
            return None
        
        # PASSO 2: Processar links individualmente de forma ASSÍNCRONA
        print(colored(f"Processando {len(resultados_basicos)} medicamentos para extrair PDFs...", "blue"))
        
        # Limitar o número de medicamentos processados para evitar sobrecarga
        max_medicamentos = min(len(resultados_basicos), 10)
        
        # Preparar lista de links para processamento assíncrono
        links_para_processar = []
        for resultado_basico in resultados_basicos[:max_medicamentos]:
            link_medicamento = resultado_basico.get('link')
            nome_medicamento = resultado_basico.get('nome', 'Nome não disponível')
            
            if link_medicamento:
                links_para_processar.append({
                    'link': link_medicamento,
                    'titulo': nome_medicamento,
                    'dados_basicos': resultado_basico  # Manter dados básicos para mesclar depois
                })
                print(colored(f"Adicionado para processamento assíncrono: {nome_medicamento}", "cyan"))

        # Processar todos os links simultaneamente
        resultados_completos = await self._processar_links_async(links_para_processar)
        
        # Remover duplicatas baseadas no nome do medicamento
        resultados_unicos = []
        nomes_vistos = set()
        
        for resultado in resultados_completos:
            nome = resultado.get('nome', '').strip()
            if nome and nome not in nomes_vistos:
                nomes_vistos.add(nome)
                resultados_unicos.append(resultado)

        print(colored(f"Total de resultados únicos com processamento completo: {len(resultados_unicos)}", "green"))
        
        # Mostrar estatísticas dos PDFs
        com_pdf = sum(1 for r in resultados_unicos if r.get('conteudo_pdf'))
        print(colored(f"Medicamentos com PDF extraído: {com_pdf}/{len(resultados_unicos)}", "blue"))
        
        return resultados_unicos

    def _detectar_consulta_dupla(self, classificacao):
        """Detecta se a pergunta requer uma consulta dupla (medicamento específico + comparação)"""
        entidades = classificacao.get("entidades", {})
        substancia_ativa = entidades.get("substancia_ativa", "").strip()
        pergunta_ollama = entidades.get("pergunta_ollama", "").lower()
        
        # Verificar se a substância ativa é na verdade um nome de medicamento
        # e se a pergunta pede comparação/busca por princípio ativo
        indicadores_dupla = [
            "mesmo princípio ativo",
            "mesma substância ativa", 
            "princípio ativo do medicamento",
            "substância ativa do medicamento",
            "medicamentos com o princípio ativo"
        ]
        
        # Se substancia_ativa parece ser um nome de medicamento (maiúscula ou formato de marca)
        # E a pergunta contém indicadores de consulta dupla
        if (substancia_ativa and 
            (substancia_ativa[0].isupper() or len(substancia_ativa.split()) == 1) and
            any(indicador in pergunta_ollama for indicador in indicadores_dupla)):
            return True
        
        return False

    def _realizar_consulta_dupla(self, classificacao, pergunta_normalizada):
        """Realiza consulta dupla: primeiro busca o princípio ativo, depois faz comparação"""
        entidades = classificacao.get("entidades", {})
        medicamento_referencia = entidades.get("substancia_ativa", "").strip()
        pergunta_ollama = entidades.get("pergunta_ollama", "")
        
        print(colored(f"Detectada consulta dupla para medicamento: {medicamento_referencia}", "cyan"))
        
        # FASE 1: Buscar informações do medicamento de referência
        print(colored("FASE 1: Buscando informações do medicamento de referência...", "blue"))
        dados_medicamento = self.realizar_web_scraping(medicamento_referencia)
        
        if not dados_medicamento:
            return f"Não foi possível encontrar informações sobre o medicamento '{medicamento_referencia}' para fazer a comparação."
        
        # Extrair o princípio ativo usando IA
        prompt_principio = f"""
        Com base nas seguintes informações sobre o medicamento {medicamento_referencia}:
        
        ```json
        {json.dumps(dados_medicamento, ensure_ascii=False, indent=2)}
        ```
        
        Extraia APENAS o princípio ativo (substância ativa) deste medicamento. 
        Responda apenas com o nome da substância ativa, sem explicações adicionais.
        Se não encontrar a informação, responda "NÃO ENCONTRADO".
        """
        
        try:
            print(colored("Extraindo princípio ativo...", "yellow"))
            response = ollama.chat(
                model=self.modelo_ollama,
                messages=[
                    {
                        'role': 'system',
                        'content': 'Você é um especialista em medicamentos veterinários. Extraia apenas a substância ativa solicitada.'
                    },
                    {
                        'role': 'user',
                        'content': prompt_principio,
                    }
                ],
                options={'temperature': 0.0}
            )
            principio_ativo = response['message']['content'].strip()
            
            if principio_ativo.upper() == "NÃO ENCONTRADO":
                return f"Não foi possível identificar o princípio ativo do medicamento '{medicamento_referencia}'."
            
            print(colored(f"Princípio ativo identificado: {principio_ativo}", "green"))
            
        except Exception as e:
            return f"Erro ao extrair princípio ativo: {e}"
        
        # FASE 2: Buscar medicamentos com o mesmo princípio ativo
        print(colored("FASE 2: Buscando medicamentos com o mesmo princípio ativo...", "blue"))
        
        # Usar busca de comparação simples (sem IA) para listar todos os medicamentos
        resultados_comparacao = self._realizar_busca_comparacao_simples(principio_ativo)
        
        if not resultados_comparacao:
            return f"Não foram encontrados outros medicamentos com o princípio ativo '{principio_ativo}'."
        
        # Filtrar o medicamento de referência dos resultados (opcional)
        resultados_filtrados = [
            resultado for resultado in resultados_comparacao
            if medicamento_referencia.lower() not in resultado.get('nome', '').lower()
        ]
        
        if not resultados_filtrados:
            return f"Apenas o medicamento '{medicamento_referencia}' foi encontrado com o princípio ativo '{principio_ativo}'. Não há outros medicamentos similares disponíveis."
        
        # Formatar resposta final
        resposta = f"Medicamentos com o mesmo princípio ativo que {medicamento_referencia}:\n\n"
        resposta += f"Princípio ativo identificado: **{principio_ativo}**\n\n"
        resposta += f"Outros medicamentos encontrados ({len(resultados_filtrados)} encontrados):\n\n"
        
        for i, item in enumerate(resultados_filtrados, 1):
            resposta += f"{i}. **{item.get('nome', 'Nome não disponível')}**\n"
            
            if item.get('especies'):
                resposta += f"   - Espécies: {item['especies']}\n"
            
            if item.get('forma_farmaceutica'):
                resposta += f"   - Forma farmacêutica: {item['forma_farmaceutica']}\n"
            
            if item.get('link'):
                resposta += f"   - Link: {item['link']}\n"
            
            # Se não tiver informações específicas, mostrar informações resumidas
            if not any([item.get('especies'), item.get('forma_farmaceutica')]):
                info_resumida = item.get('informacoes_visiveis', '')
                if len(info_resumida) > 100:
                    info_resumida = info_resumida[:100] + "..."
                resposta += f"   - Informações: {info_resumida}\n"
            
            resposta += "\n"
        
        resposta += f"\nNota: Foram encontrados {len(resultados_comparacao)} medicamentos no total com '{principio_ativo}', "
        resposta += f"sendo {len(resultados_filtrados)} além do medicamento de referência '{medicamento_referencia}'."
        
        return resposta

    def _detectar_pergunta_followup(self, pergunta_atual):
        """Detecta se a pergunta atual é um follow-up da anterior, com critérios mais rigorosos."""
        # Se não temos contexto anterior, não é follow-up
        if not self.contexto_conversacao["ultima_pergunta"]:
            return False, None

        # 1. Critério de brevidade: A pergunta deve ser curta (ex: 1 a 5 palavras).
        palavras_pergunta_atual = pergunta_atual.lower().split()
        if not (1 <= len(palavras_pergunta_atual) <= 5):
            return False, None

        # 2. Critério de especificidade: A pergunta deve conter um indicador claro de follow-up.
        indicadores_especie_ou_aspecto = [
            "e em", "e para", "em gatos", "em cães", "em suínos", "em bovinos", "em equinos",
            "para gatos", "para cães", "para suínos", "para bovinos", "para equinos", "para aves",
            "para galinhas", "para caprinos", "para coelhos", "para ovinos", "para roedores",
            "gatos?", "cães?", "suínos?", "bovinos?", "equinos?", "aves?", "galinhas?", "caprinos?",
            "coelhos?", "ovinos?", "roedores?",
            "dose?", "dosagem?", "armazenamento?", "composição?", "indicação?", "reações?", "fabricante?",
            "validade?", "receita?", "alternativa?", "mesmo princípio?", "mesma substância?"
        ]

        tem_indicador = any(indicador in pergunta_atual.lower() for indicador in indicadores_especie_ou_aspecto)
        if not tem_indicador:
            return False, None

        # 3. Confirmação com Ollama: Usar Ollama para uma verificação final da intenção.
        try:
            prompt = f"""
            Determine se a "Pergunta atual" é um acompanhamento (follow-up) da "Pergunta anterior".

            Pergunta anterior: "{self.contexto_conversacao["ultima_pergunta"]}"
            Pergunta atual: "{pergunta_atual}"

            Responda "SIM" apenas se a "Pergunta atual" for uma continuação direta, curta e específica da "Pergunta anterior".
            Caso contrário, responda "NAO".

            Exemplos de "SIM":
            - Anterior: "Qual a dose do Medicamento X para cães?" / Atual: "e para gatos?"
            - Anterior: "Como devo armazenar o Produto Y?" / Atual: "e a dosagem?"

            Exemplos de "NAO":
            - Anterior: "Qual a dose do Medicamento X para cães?" / Atual: "Que outros medicamentos existem para cães com a mesma substância?"
            - Anterior: "Qual a validade da receita?" / Atual: "E para gatos, qual a dose do medicamento X?"
            """
            
            response = ollama.chat(
                model=self.modelo_ollama,
                messages=[{
                    'role': 'system',
                    'content': 'Você é um analisador de relação entre perguntas. Responda apenas SIM ou NAO.'
                }, {
                    'role': 'user',
                    'content': prompt,
                }],
                options={'temperature': 0.0}
            )
            resposta = response['message']['content'].strip().upper()

            if resposta == "SIM":
                print(colored("Detectada pergunta de follow-up!", "cyan"))
                
                # Extrair a entidade alvo (ex: espécie) usando Ollama
                entidade_prompt = f"""
                Da pergunta de follow-up: "{pergunta_atual}"
                Extraia APENAS a entidade principal (ex: a espécie animal, o aspecto como "dose", "armazenamento", etc.).
                Responda apenas com a entidade, sem pontuação ou explicações.
                Exemplos:
                - "E em bovinos?" -> bovinos
                - "E para gatos?" -> gatos
                - "E quanto à dose?" -> dose
                """
                
                entity_response = ollama.chat(
                    model=self.modelo_ollama,
                    messages=[{
                        'role': 'user',
                        'content': entidade_prompt,
                    }],
                    options={'temperature': 0.0}
                )
                
                entidade_extraida = entity_response['message']['content'].strip()
                
                return True, entidade_extraida
        except Exception as e:
            print(colored(f"Erro ao verificar follow-up com Ollama: {e}", "red"))
        
        return False, None

    def _construir_pergunta_completa(self, pergunta_followup, entidade_extraida):
        """Constrói uma pergunta completa a partir de um follow-up"""
        ultima_pergunta = self.contexto_conversacao["ultima_pergunta"]
        
        if not ultima_pergunta:
            return pergunta_followup
            
        # Buscar por padrões de espécies animais na pergunta original
        import re
        
        # Padrão para capturar "em X" ou "para X" onde X é uma espécie animal
        padrao_especie = r"(?:em|para)\s+([a-záàâãéèêíïóôõöúçñ]+)"
        match_especie = re.search(padrao_especie, ultima_pergunta, re.IGNORECASE)
        
        if match_especie:
            # Substitui a espécie antiga pela nova espécie
            especie_antiga = match_especie.group(1)
            preposicao = match_especie.group(0).split()[0]  # "em" ou "para"
            nova_pergunta = ultima_pergunta.replace(f"{preposicao} {especie_antiga}", f"{preposicao} {entidade_extraida}")
            print(colored(f"Pergunta reconstruída: {nova_pergunta}", "cyan"))
            return nova_pergunta
        else:
            # Se não conseguir construir com precisão, faz uma construção genérica
            medicamento = self.contexto_conversacao["ultima_entidade_medicamento"]
            if medicamento:
                nova_pergunta = f"Informações sobre {medicamento} para {entidade_extraida}"
                return nova_pergunta
            else:
                return pergunta_followup

    def processar_pergunta_unica(self, pergunta_usuario):
        # Verificar se é uma pergunta de follow-up
        is_followup, entidade_extraida = self._detectar_pergunta_followup(pergunta_usuario)
        
        if is_followup and entidade_extraida:
            print(colored(f"Entidade extraída do follow-up: '{entidade_extraida}'", "yellow"))
            pergunta_completa = self._construir_pergunta_completa(pergunta_usuario, entidade_extraida)
            print(colored(f"Usando contexto anterior. Pergunta processada: '{pergunta_completa}'", "cyan"))
            
            # Se temos dados do último scraping, reutilizá-los
            if self.contexto_conversacao["dados_ultimo_scraping"] and self.contexto_conversacao["ultimo_termo_busca"]:
                # Preparar a pergunta Ollama usando a entidade extraída
                if self.contexto_conversacao["ultima_categoria"] == "medicamento":
                    pergunta_ollama = pergunta_completa
                    
                    # Usar os mesmos dados do scraping anterior, mas mudar a pergunta
                    return self._consultar_ollama_otimizado(
                        pergunta_ollama,
                        self.contexto_conversacao["dados_ultimo_scraping"],
                        tipo_consulta="medicamento"
                    )
            
            # Se chegou aqui, não foi possível usar o contexto diretamente
            # Proceder com o processamento normal da pergunta reconstruída
            pergunta_usuario = pergunta_completa
        
        # Normalizar espécies animais na pergunta antes de processar
        pergunta_normalizada = self._normalizar_especies_texto(pergunta_usuario)
        
        if pergunta_normalizada != pergunta_usuario:
            print(colored(f"Pergunta normalizada: '{pergunta_normalizada}'", "cyan"))
        
        print(colored(f"\nProcessando pergunta: '{pergunta_normalizada}'", "cyan"))
        classificacao = self.query_classifier.classify_and_extract(pergunta_normalizada)

        if not classificacao or classificacao.get("categoria") == "erro":
            return "Não foi possível classificar sua pergunta. Tente reformulá-la."

        categoria = classificacao.get("categoria")
        entidades = classificacao.get("entidades", {})
        pergunta_para_ollama = entidades.get("pergunta_ollama", pergunta_usuario) # Fallback

        print(colored(f"Categoria identificada: {categoria}", "magenta"))
        print(colored(f"Entidades extraídas: {json.dumps(entidades, indent=2, ensure_ascii=False)}", "magenta"))

        # Atualizar contexto de conversação
        self.contexto_conversacao["ultima_pergunta"] = pergunta_normalizada
        self.contexto_conversacao["ultima_categoria"] = categoria
        
        if categoria == "medicamento":
            termo_busca = entidades.get("termo_busca")
            if not termo_busca:
                return "Não foi possível identificar o termo de busca para o medicamento."
            
            # Extrair nome do medicamento para o contexto
            for palavra in termo_busca.split():
                if palavra[0].isupper():  # Assume que nome de medicamento começa com maiúscula
                    self.contexto_conversacao["ultima_entidade_medicamento"] = palavra
                    break
            
            self.contexto_conversacao["ultimo_termo_busca"] = termo_busca
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                dados_raspados = loop.run_until_complete(self.realizar_web_scraping(termo_busca))
            finally:
                loop.close()

            if not dados_raspados:
                return f"Não foram encontrados resultados no web scraping para '{termo_busca}'."
            
            # Salvar os dados raspados no contexto
            self.contexto_conversacao["dados_ultimo_scraping"] = dados_raspados
            
            resposta = self._consultar_ollama_otimizado(
                pergunta_para_ollama, 
                dados_raspados, 
                tipo_consulta="medicamento",
                classificacao=classificacao,
                pergunta_original=pergunta_normalizada
            )
            
            # Salvar a resposta no contexto
            self.contexto_conversacao["ultima_resposta"] = resposta
            
            return resposta



        elif categoria == "comparacao":
            # Verificar se é uma consulta dupla
            if self._detectar_consulta_dupla(classificacao):
                print(colored("Detectada consulta dupla (medicamento + comparação)", "yellow"))
                
                # Limpar contexto de medicamento, pois é uma comparação diferente
                self.contexto_conversacao["ultima_entidade_medicamento"] = None
                self.contexto_conversacao["ultimo_termo_busca"] = None
                self.contexto_conversacao["dados_ultimo_scraping"] = None
                
                resposta = self._realizar_consulta_dupla(classificacao, pergunta_normalizada)
                self.contexto_conversacao["ultima_resposta"] = resposta
                return resposta
            
            # TODAS as comparações agora usam web scraping simples (sem IA)
            substancia = entidades.get("substancia_ativa", "")
            especie = entidades.get("especie_alvo", "")
            forma = entidades.get("forma_farmaceutica", "")
            termo_busca_comparacao = f"{substancia} {especie} {forma}".strip()
            
            # Limpar contexto de medicamento, pois é uma comparação diferente
            self.contexto_conversacao["ultima_entidade_medicamento"] = None
            self.contexto_conversacao["ultimo_termo_busca"] = None
            self.contexto_conversacao["dados_ultimo_scraping"] = None
            
            if not termo_busca_comparacao:
                return "Para comparação, por favor, forneça pelo menos uma substância ativa, espécie alvo ou forma farmacêutica."

            # Sempre realizar busca simples sem IA para comparações
            print(colored("Realizando busca de comparação com web scraping simples (sem IA).", "blue"))
            resultados_simples = self._realizar_busca_comparacao_simples(termo_busca_comparacao)
            if not resultados_simples:
                return f"Não foram encontrados resultados na busca para: '{termo_busca_comparacao}'."
            
            resposta = self._formatar_resultados_comparacao_simples(resultados_simples, pergunta_normalizada)
            self.contexto_conversacao["ultima_resposta"] = resposta
            return resposta

        else:
            # Limpar contexto para categoria desconhecida
            self.contexto_conversacao["ultima_entidade_medicamento"] = None
            self.contexto_conversacao["ultimo_termo_busca"] = None
            self.contexto_conversacao["dados_ultimo_scraping"] = None
            
            resposta = f"Categoria de pergunta '{categoria}' não suportada no momento."
            self.contexto_conversacao["ultima_resposta"] = resposta
            return resposta
        
    def _limpar_contexto_antigo(self):
        """Limpa dados antigos do contexto para economizar memória"""
        current_time = time.time()
        
        # Manter apenas os últimos 5 contextos
        if len(self.contexto_conversacao.get('historico', [])) > 5:
            self.contexto_conversacao['historico'] = self.contexto_conversacao['historico'][-5:]
        
        # Limpar dados pesados após 10 minutos
        if (self.contexto_conversacao.get('dados_ultimo_scraping') and 
            current_time - self.contexto_conversacao.get('ultimo_scraping_time', 0) > 600):
            self.contexto_conversacao['dados_ultimo_scraping'] = None

# Função principal para executar o sistema
def main():
    print(colored("=== Sistema Inteligente de Consulta Veterinária ===", "green"))
    sistema = SistemaConsultaVet()

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
            print(colored(f"Ocorreu um erro inesperado no loop principal: {e}", "red"))

if __name__ == "__main__":
    main()


