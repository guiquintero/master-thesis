# sistema_consulta_vet_otimizado.py
import json
import os
import time
import hashlib
import asyncio
import aiohttp
from termcolor import colored
import ollama
from aiohttp import ClientSession, TCPConnector, ClientTimeout

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
import fitz  # PyMuPDF
import re
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
PDF_CACHE_DIR = "pdf_cache_otimizado"
CACHE_DIR_RESPOSTAS = "resposta_cache_otimizado"
ARQUIVO_JSON_SCRAPING = "medicamento_buscado_otimizado.json"

# Configurações de performance
MAX_CONCURRENT_REQUESTS = 5
MAX_PDF_PAGES = 10  # Limitar páginas de PDF processadas
CACHE_TTL = 86400   # 24 horas
CONTEXT_SIZE_LIMIT = 30000  # Limite de caracteres para contexto

# Criar diretórios de cache se não existirem
os.makedirs(PDF_CACHE_DIR, exist_ok=True)
os.makedirs(CACHE_DIR_RESPOSTAS, exist_ok=True)

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

class SistemaConsultaVetOtimizado:
    def __init__(self, modelo_ollama=MODELO_OLLAMA_PADRAO, temperatura_ollama=0.2):
        self.modelo_ollama = modelo_ollama
        self.temperatura_ollama = temperatura_ollama
        self.query_classifier = QueryClassifier(modelo_ollama)
        self.cache_manager = CacheManager(CACHE_DIR_RESPOSTAS)
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

    # async def __aenter__(self):
    #     self.session = ClientSession(
    #         connector=TCPConnector(limit=MAX_CONCURRENT_REQUESTS, ssl=False),
    #         headers=HEADERS
    #     )
    #     return self

    # async def __aexit__(self, exc_type, exc_val, exc_tb):
    #     if self.session:
    #         await self.session.close()

    # Métodos de cache inteligente (mantidos do original)
    def _gerar_cache_key_inteligente(self, classificacao):
        entidades = classificacao.get("entidades", {})
        categoria = classificacao.get("categoria", "")
        
        if categoria == "medicamento":
            key_parts = [categoria, entidades.get("termo_busca", "").lower().strip()]
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
        p1 = pergunta1.lower().strip()
        p2 = pergunta2.lower().strip()
        
        if p1 == p2:
            return True
        
        if p1 in p2 or p2 in p1:
            return True
        
        palavras1 = set(p1.split())
        palavras2 = set(p2.split())
        palavras_comuns = palavras1.intersection(palavras2)
        
        if (len(palavras_comuns) / max(len(palavras1), len(palavras2))) > 0.6:
            return True
        
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
        if classificacao and pergunta_original:
            resposta_cache = self._carregar_resposta_cache_inteligente(classificacao, pergunta_original)
            if resposta_cache:
                print(colored("✓ Resposta do cache inteligente", "green"))
                return resposta_cache

        contexto_otimizado = self._comprimir_contexto_ollama(contexto_dados, tipo_consulta, pergunta_ollama)
        prompt = self._gerar_prompt_otimizado(pergunta_ollama, contexto_otimizado, tipo_consulta)
        
        try:
            print(colored("Consultando Ollama...", "yellow"))
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
                    'num_predict': 500,
                    'timeout': 120
                }
            )
            
            resposta_ollama = response['message']['content']
            end_time = time.perf_counter()
            
            print(colored(f"Consulta concluída em {(end_time - start_time):.2f}s", "yellow"))
            
            if classificacao and pergunta_original:
                self._salvar_resposta_cache_inteligente(classificacao, pergunta_original, resposta_ollama)
            
            return resposta_ollama
            
        except Exception as e:
            return f"Erro ao consultar Ollama: {e}"

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
        contexto_limpo = {
            'historico_conversacao': self.contexto_conversacao.get('historico_conversacao', [])[-3:],
            'ultima_interacao_time': time.time()
        }
        self.contexto_conversacao = contexto_limpo

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
        cache_filename = os.path.join(PDF_CACHE_DIR, hashlib.md5(pdf_url.encode()).hexdigest() + ".pdf")
        text_cache = cache_filename.replace(".pdf", ".txt")
        
        if os.path.exists(text_cache):
            try:
                with open(text_cache, 'r', encoding='utf-8') as f:
                    return f.read()
            except:
                pass
        
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
        
        try:
            with fitz.open(cache_filename) as pdf_file:
                texto = "\n".join([page.get_text() for page in pdf_file])
                
                with open(text_cache, 'w', encoding='utf-8') as f:
                    f.write(texto)
                
                return texto
        except:
            return None

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
        """Detecta se a pergunta requer consulta dupla"""
        entidades = classificacao.get("entidades", {})
        substancia_ativa = entidades.get("substancia_ativa", "").strip()
        pergunta_ollama = entidades.get("pergunta_ollama", "").lower()
        
        # Indicadores mais específicos
        indicadores_dupla = [
            "mesmo princípio ativo", "mesma substância ativa", 
            "princípio ativo do medicamento", "substância ativa do medicamento",
            "medicamentos com o princípio ativo", "qual o princípio ativo"
        ]
        
        # Verificar se substancia_ativa parece ser um nome de medicamento
        is_nome_medicamento = (
            substancia_ativa and 
            (substancia_ativa[0].isupper() or any(c.isupper() for c in substancia_ativa)) and
            any(indicador in pergunta_ollama for indicador in indicadores_dupla)
        )
    
        return is_nome_medicamento

    def _detectar_pergunta_followup(self, pergunta_atual):
        if not self.contexto_conversacao["ultima_pergunta"]:
            return False, None

        palavras_pergunta_atual = pergunta_atual.lower().split()
        if not (1 <= len(palavras_pergunta_atual) <= 5):
            return False, None

        indicadores_especie_ou_aspecto = [
            "e em", "e para", "em gatos", "em cães", "em suínos", "em bovinos", "em equinos",
            "para gatos", "para cães", "para suínos", "para bovinos", "para equinos", "para aves",
            "gatos?", "cães?", "suínos?", "bovinos?", "equinos?", "aves?",
            "dose?", "dosagem?", "armazenamento?", "composição?", "indicação?"
        ]

        tem_indicador = any(indicador in pergunta_atual.lower() for indicador in indicadores_especie_ou_aspecto)
        if not tem_indicador:
            return False, None

        try:
            prompt = f"""
            Determine se é follow-up da pergunta anterior.
            Anterior: "{self.contexto_conversacao["ultima_pergunta"]}"
            Atual: "{pergunta_atual}"
            Responda apenas SIM ou NAO.
            """
            
            response = ollama.chat(
                model=self.modelo_ollama,
                messages=[{
                    'role': 'system',
                    'content': 'Analisador de relação entre perguntas. Responda apenas SIM ou NAO.'
                }, {
                    'role': 'user',
                    'content': prompt,
                }],
                options={'temperature': 0.0}
            )
            resposta = response['message']['content'].strip().upper()

            if resposta == "SIM":
                entidade_prompt = f"Da pergunta: '{pergunta_atual}' extraia APENAS a entidade principal. Responda apenas com a entidade."
                
                entity_response = ollama.chat(
                    model=self.modelo_ollama,
                    messages=[{'role': 'user', 'content': entidade_prompt}],
                    options={'temperature': 0.0}
                )
                
                entidade_extraida = entity_response['message']['content'].strip()
                return True, entidade_extraida
        except Exception as e:
            print(colored(f"Erro ao verificar follow-up: {e}", "red"))
        
        return False, None

    def _construir_pergunta_completa(self, pergunta_followup, entidade_extraida):
        ultima_pergunta = self.contexto_conversacao["ultima_pergunta"]
        
        if not ultima_pergunta:
            return pergunta_followup
            
        import re
        padrao_especie = r"(?:em|para)\s+([a-záàâãéèêíïóôõöúçñ]+)"
        match_especie = re.search(padrao_especie, ultima_pergunta, re.IGNORECASE)
        
        if match_especie:
            especie_antiga = match_especie.group(1)
            preposicao = match_especie.group(0).split()[0]
            nova_pergunta = ultima_pergunta.replace(f"{preposicao} {especie_antiga}", f"{preposicao} {entidade_extraida}")
            return nova_pergunta
        else:
            medicamento = self.contexto_conversacao["ultima_entidade_medicamento"]
            if medicamento:
                return f"Informações sobre {medicamento} para {entidade_extraida}"
            else:
                return pergunta_followup

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

    def _realizar_consulta_dupla(self, classificacao, pergunta_normalizada):
        entidades = classificacao.get("entidades", {})
        medicamento_referencia = entidades.get("substancia_ativa", "").strip()
        pergunta_ollama = entidades.get("pergunta_ollama", "")
        
        print(colored(f"Consulta dupla para: {medicamento_referencia}", "cyan"))
        
        # FASE 1: Buscar informações do medicamento de referência
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            dados_medicamento = loop.run_until_complete(self.realizar_web_scraping(medicamento_referencia))
        finally:
            loop.close()
        
        if not dados_medicamento:
            return f"Não foi possível encontrar informações sobre '{medicamento_referencia}'."
        
        # Extrair princípio ativo
        prompt_principio = f"""
        Com base nas informações sobre {medicamento_referencia}:
        {json.dumps(dados_medicamento, ensure_ascii=False, indent=2)}
        Extraia APENAS o princípio ativo. Responda apenas com o nome da substância ativa.
        Se não encontrar, responda "NÃO ENCONTRADO".
        """
        
        try:
            response = ollama.chat(
                model=self.modelo_ollama,
                messages=[{
                    'role': 'system',
                    'content': 'Extraia apenas a substância ativa solicitada.'
                }, {
                    'role': 'user',
                    'content': prompt_principio,
                }],
                options={'temperature': 0.0}
            )
            principio_ativo = response['message']['content'].strip()
            
            if principio_ativo.upper() == "NÃO ENCONTRADO":
                return f"Não foi possível identificar o princípio ativo de '{medicamento_referencia}'."
            
            print(colored(f"Princípio ativo: {principio_ativo}", "green"))
            
        except Exception as e:
            return f"Erro ao extrair princípio ativo: {e}"
        
        # FASE 2: Buscar medicamentos com o mesmo princípio ativo
        resultados_comparacao = self._realizar_busca_comparacao_simples(principio_ativo)
        
        if not resultados_comparacao:
            return f"Não foram encontrados outros medicamentos com '{principio_ativo}'."
        
        resultados_filtrados = [
            resultado for resultado in resultados_comparacao
            if medicamento_referencia.lower() not in resultado.get('nome', '').lower()
        ]
        
        if not resultados_filtrados:
            return f"Apenas '{medicamento_referencia}' foi encontrado com '{principio_ativo}'."
        
        resposta = f"Medicamentos com mesmo princípio ativo que {medicamento_referencia}:\n\n"
        resposta += f"Princípio ativo: **{principio_ativo}**\n\n"
        resposta += f"Outros medicamentos ({len(resultados_filtrados)}):\n\n"
        
        for i, item in enumerate(resultados_filtrados, 1):
            resposta += f"{i}. **{item.get('nome', 'Nome não disponível')}**\n"
            
            if item.get('especies'):
                resposta += f"   - Espécies: {item['especies']}\n"
            
            if item.get('forma_farmaceutica'):
                resposta += f"   - Forma farmacêutica: {item['forma_farmaceutica']}\n"
            
            if item.get('link'):
                resposta += f"   - Link: {item['link']}\n"
            
            resposta += "\n"
        
        resposta += f"\nTotal: {len(resultados_comparacao)} medicamentos com '{principio_ativo}'."
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
        self._limpar_contexto_antigo()
        self._verificar_uso_memoria()
        
        is_followup, entidade_extraida = self._detectar_pergunta_followup(pergunta_usuario)
        
        if is_followup and entidade_extraida:
            pergunta_completa = self._construir_pergunta_completa(pergunta_usuario, entidade_extraida)
            print(colored(f"Pergunta processada: '{pergunta_completa}'", "cyan"))
            
            if self.contexto_conversacao["dados_ultimo_scraping"] and self.contexto_conversacao["ultimo_termo_busca"]:
                return self._consultar_ollama_otimizado(
                    pergunta_completa,
                    self.contexto_conversacao["dados_ultimo_scraping"],
                    tipo_consulta="medicamento"
                )
            
            pergunta_usuario = pergunta_completa
        
        pergunta_normalizada = self._normalizar_especies_texto(pergunta_usuario)
        
        if pergunta_normalizada != pergunta_usuario:
            print(colored(f"Pergunta normalizada: '{pergunta_normalizada}'", "cyan"))
        
        print(colored(f"\nProcessando: '{pergunta_normalizada}'", "cyan"))
        classificacao = self.query_classifier.classify_and_extract(pergunta_normalizada)

        classificacao = self._corrigir_categoria_se_necesario(classificacao, pergunta_normalizada)

        if not classificacao or classificacao.get("categoria") == "erro":
            return "Não foi possível classificar sua pergunta."
        
        classificacao = self._corrigir_categoria_se_necesario(classificacao, pergunta_normalizada)

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
                termo_busca = entidades.get("termo_busca")
                if not termo_busca:
                    termo_busca = entidades.get("substancia_ativa") or self._extrair_medicamento_query(pergunta_normalizada)
                    print(colored(f"⚠️  Termo de busca não encontrado, usando fallback: '{termo_busca}'", "yellow"))
            
            for palavra in termo_busca.split():
                if palavra[0].isupper():
                    self.contexto_conversacao["ultima_entidade_medicamento"] = palavra
                    break
            
            self.contexto_conversacao["ultimo_termo_busca"] = termo_busca
            
            # CORREÇÃO: Usar a versão síncrona do web scraping
            dados_raspados = self.realizar_web_scraping_sincrono(termo_busca)
            
            if not dados_raspados:
                return f"Não foram encontrados resultados para '{termo_busca}'."
            
            self.contexto_conversacao["dados_ultimo_scraping"] = dados_raspados
            self.contexto_conversacao["ultimo_scraping_time"] = time.time()
            
            resposta = self._consultar_ollama_otimizado(
                pergunta_para_ollama, 
                dados_raspados, 
                tipo_consulta="medicamento",
                classificacao=classificacao,
                pergunta_original=pergunta_normalizada
            )
            
            self.contexto_conversacao["ultima_resposta"] = resposta
            self._adicionar_ao_historico(pergunta_normalizada, resposta, categoria)
            return resposta

        elif categoria == "comparacao":
            if self._detectar_consulta_dupla(classificacao):
                self.contexto_conversacao["ultima_entidade_medicamento"] = None
                self.contexto_conversacao["ultimo_termo_busca"] = None
                self.contexto_conversacao["dados_ultimo_scraping"] = None
                
                resposta = self._realizar_consulta_dupla(classificacao, pergunta_normalizada)
                self.contexto_conversacao["ultima_resposta"] = resposta
                self._adicionar_ao_historico(pergunta_normalizada, resposta, categoria)
                return resposta
            
            substancia = entidades.get("substancia_ativa", "")
            especie = entidades.get("especie_alvo", "")
            forma = entidades.get("forma_farmaceutica", "")
            termo_busca_comparacao = f"{substancia} {especie} {forma}".strip()
            
            self.contexto_conversacao["ultima_entidade_medicamento"] = None
            self.contexto_conversacao["ultimo_termo_busca"] = None
            self.contexto_conversacao["dados_ultimo_scraping"] = None
            
            if not termo_busca_comparacao:
                return "Para comparação, forneça substância ativa, espécie ou forma farmacêutica."

            resultados_simples = self._realizar_busca_comparacao_simples(termo_busca_comparacao)
            if not resultados_simples:
                return f"Não foram encontrados resultados para: '{termo_busca_comparacao}'."
            
            resposta = self._formatar_resultados_comparacao_simples(resultados_simples, pergunta_normalizada)
            self.contexto_conversacao["ultima_resposta"] = resposta
            self._adicionar_ao_historico(pergunta_normalizada, resposta, categoria)
            return resposta

        else:
            self.contexto_conversacao["ultima_entidade_medicamento"] = None
            self.contexto_conversacao["ultimo_termo_busca"] = None
            self.contexto_conversacao["dados_ultimo_scraping"] = None
            
            resposta = f"Categoria '{categoria}' não suportada."
            self.contexto_conversacao["ultima_resposta"] = resposta
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