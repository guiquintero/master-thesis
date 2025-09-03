#Qual a forma de administração do medicamento Animedazon em porcos ( ou outra espécie pecuária)?

import json
import os
import time
import hashlib
from termcolor import colored
import ollama

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
ARQUIVO_LEGISLACAO = "dados_dgav_final.json"

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
        self.query_classifier = QueryClassifier(model=modelo_ollama)
        self.dados_legislacao = self._carregar_dados_legislacao()
        self.mapeamento_especies = self._criar_mapeamento_especies()

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

    def _carregar_dados_legislacao(self):
        if os.path.exists(ARQUIVO_LEGISLACAO):
            try:
                with open(ARQUIVO_LEGISLACAO, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(colored(f"Erro ao carregar o arquivo de legislação '{ARQUIVO_LEGISLACAO}': {e}", "red"))
                return None
        else:
            print(colored(f"Arquivo de legislação '{ARQUIVO_LEGISLACAO}' não encontrado.", "yellow"))
            return None

    # ========== FUNÇÕES DE WEB SCRAPING  ==========

    def _extrair_conteudo_pdf(self, pdf_url):
        cache_filename = os.path.join(PDF_CACHE_DIR, pdf_url.split('/')[-1].replace('?', '_').replace('&', '_'))

        def extrair_conteudo_limite_rotulagem(pdf_file):
            conteudo = []
            for page in pdf_file:
                texto = page.get_text()
                if 'rotulagem' in texto.lower():
                    # Encontrou a palavra, interrompe a extração aqui
                    break
                conteudo.append(texto)
            return "\n".join(conteudo)

        if os.path.exists(cache_filename):
            try:
                with fitz.open(cache_filename) as pdf_file:
                    return extrair_conteudo_limite_rotulagem(pdf_file)
            except Exception:
                pass  # Tentar baixar novamente se o cache estiver corrompido

        try:
            pdf_response = requests.get(pdf_url, timeout=20, headers=HEADERS, verify=False)
            pdf_response.raise_for_status()
            with open(cache_filename, 'wb') as f:
                f.write(pdf_response.content)
            with fitz.open(cache_filename) as pdf_file:
                return extrair_conteudo_limite_rotulagem(pdf_file)
        except requests.RequestException as e:
            print(colored(f"Erro ao acessar o PDF {pdf_url}: {e}", "red"))
        except Exception as e:
            print(colored(f"Erro ao processar o PDF {pdf_url}: {e}", "red"))
            if os.path.exists(cache_filename):
                os.remove(cache_filename)
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

    def _processar_link_scraping(self, link_info):
        global resultados_scraping
        link = link_info['link']
        titulo_busca = link_info['titulo']

        try:
            response = requests.get(link, timeout=20, headers=HEADERS, verify=False)
            response.raise_for_status()
            if "text/html" not in response.headers.get("Content-Type", ""):
                print(colored(f"Ignorando {link}, não é HTML.", "yellow"))
                return None
            response.encoding = "utf-8"
        except requests.RequestException as e:
            print(colored(f"Erro ao acessar {link}: {e}", "red"))
            return None
        
        soup = BeautifulSoup(response.text, "html.parser")
        tags_permitidas = {"h1", "h2", "h3", "h4", "h5", "p", "a"}
        conteudo_item = {"url": link, "titulo": titulo_busca, "conteudo_html": "", "conteudo_pdf": []}
        
        encontrou_titulo_no_html = False
        html_str = ""
        # Tenta encontrar o título exato da busca para focar a extração
        # Se não encontrar, extrai o corpo todo (pode ser melhorado)
        main_content_area = soup.body # Padrão
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
                        if not encontrou_titulo_no_html and titulo_busca.lower() in texto_formatado.lower():
                            encontrou_titulo_no_html = True
                    else:
                        html_str += texto_formatado + " "
        
        conteudo_item["conteudo_html"] = html_str.strip()
        
        pdf_url = self._encontrar_link_pdf(soup, link)
        if pdf_url:
            pdf_text = self._extrair_conteudo_pdf(pdf_url)
            if pdf_text:
                conteudo_item["conteudo_pdf"] = self._formatar_conteudo_pdf(pdf_text)
                print(colored(f"PDF extraído de: {pdf_url}", "blue"))
            else:
                print(colored(f"Erro ao extrair PDF de: {pdf_url}", "yellow"))
        
        # Consideramos o item válido se tivermos HTML ou PDF
        if conteudo_item["conteudo_html"] or conteudo_item["conteudo_pdf"]:
            return conteudo_item
        else:
            print(colored(f"Nenhum conteúdo relevante (HTML ou PDF) extraído de {link}", "yellow"))
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
            for link_tag in navbar.find_all("a", href=True):
                link_url = urljoin(url_busca, link_tag["href"])
                link_text = link_tag.get_text(strip=True)
                print(colored(f"Link encontrado na navbar: {link_text} -> {link_url}", "yellow"))
                
                # Verificar se é link de paginação
                if (link_url != url_busca and 
                    link_url not in urls_processadas):
                    
                    # Critérios mais amplos para detecção de paginação
                    is_pagination = (
                        "page=" in link_url.lower() or
                        "p=" in link_url.lower() or
                        link_text.isdigit() or
                        any(palavra in link_text.lower() for palavra in ['próxima', 'next', '>', 'seguinte', 'anterior', 'prev', '<']) or
                        "offset=" in link_url.lower() or
                        "start=" in link_url.lower()
                    )
                    
                    if is_pagination:
                        links_paginacao.append(link_url)
                        print(colored(f"Link de paginação identificado: {link_url}", "green"))
        
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

    def _consultar_ollama_com_contexto(self, pergunta_ollama, contexto_dados, tipo_consulta="medicamento"):
        hash_consulta = self._gerar_hash_consulta(pergunta_ollama + json.dumps(contexto_dados))
        resposta_cache = self._carregar_resposta_cache(hash_consulta)
        if resposta_cache:
            print(colored("Resposta carregada do cache.", "magenta"))
            return resposta_cache

        if tipo_consulta == "comparacao":
            # Filtrar o contexto para incluir apenas o conteudo_html e excluir o conteudo_pdf
            contexto_dados_filtrado = []
            for item in contexto_dados:
                item_filtrado = item.copy()
                if "conteudo_pdf" in item_filtrado:
                    del item_filtrado["conteudo_pdf"]
                contexto_dados_filtrado.append(item_filtrado)
            contexto_json = json.dumps(contexto_dados_filtrado, ensure_ascii=False, indent=2)
        else:
            contexto_json = json.dumps(contexto_dados, ensure_ascii=False, indent=2)

        # Limitar o tamanho do contexto para evitar erros com Ollama
        # Este limite é arbitrário e pode precisar de ajuste
        max_len_contexto = 60000 
        if len(contexto_json) > max_len_contexto:
            print(colored(f"Contexto muito grande ({len(contexto_json)} chars), truncando para {max_len_contexto} chars.", "yellow"))
            contexto_json = contexto_json[:max_len_contexto] + "... (contexto truncado)"

        if tipo_consulta == "medicamento":
            prompt = f"""
            Com base APENAS no seguinte contexto sobre medicamentos veterinários (que pode incluir HTML e extratos de PDF):
            ```json
            {contexto_json}
            ```
            Responda à pergunta: "{pergunta_ollama}"
            Se a informação não estiver no contexto fornecido, responda 'Não encontrei informações sobre isso no material disponível'.
            Cite as fontes (URLs dos medicamentos) se disponíveis e relevantes para a resposta.
            """
        elif tipo_consulta == "legislacao":
            prompt = f"""
            Com base APENAS no seguinte contexto sobre legislação veterinária portuguesa:
            ```json
            {contexto_json}
            ```
            Responda à pergunta: "{pergunta_ollama}"
            Se a informação não estiver no contexto fornecido, responda 'Não encontrei informações sobre isso no material disponível'.
            """
        elif tipo_consulta == "comparacao":
            prompt = f"""
            Com base APENAS no seguinte contexto sobre medicamentos veterinários (que inclui APENAS conteúdo HTML das páginas):
            ```json
            {contexto_json}
            ```
            Analise os medicamentos no contexto e responda à seguinte solicitação de comparação: "{pergunta_ollama}"
            Apresente a resposta de forma clara, idealmente listando todos os medicamentos que atendem aos critérios e suas características relevantes (como forma farmacêutica, concentração, espécies alvo).
            Se a informação não estiver no contexto fornecido, responda 'Não encontrei informações sobre isso no material disponível'.
            """
        else:
            return "Tipo de consulta desconhecido para Ollama."

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
                options={'temperature': self.temperatura_ollama}
            )
            resposta_ollama = response['message']['content']
            end_time = time.perf_counter()
            print(colored(f"Consulta Ollama concluída em {(end_time - start_time):.2f}s", "yellow"))
            self._salvar_resposta_cache(hash_consulta, resposta_ollama)
            return resposta_ollama
        except Exception as e:
            return f"Erro ao consultar Ollama: {e}"

    def processar_pergunta_unica(self, pergunta_usuario):
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

        if categoria == "medicamento":
            termo_busca = entidades.get("termo_busca")
            if not termo_busca:
                return "Não foi possível identificar o termo de busca para o medicamento."
            
            dados_raspados = self.realizar_web_scraping(termo_busca)
            if not dados_raspados:
                return f"Não foram encontrados resultados no web scraping para '{termo_busca}'."
            
            return self._consultar_ollama_com_contexto(pergunta_para_ollama, dados_raspados, tipo_consulta="medicamento")

        elif categoria == "legislacao":
            if not self.dados_legislacao:
                return f"Os dados de legislação não estão carregados. Verifique o arquivo {ARQUIVO_LEGISLACAO}."
            return self._consultar_ollama_com_contexto(pergunta_para_ollama, self.dados_legislacao, tipo_consulta="legislacao")

        elif categoria == "comparacao":
            # Para comparação, o termo de busca pode ser construído a partir das entidades
            substancia = entidades.get("substancia_ativa", "")
            especie = entidades.get("especie_alvo", "")
            forma = entidades.get("forma_farmaceutica", "")
            termo_busca_comparacao = f"{substancia} {especie} {forma}".strip()
            
            if not termo_busca_comparacao:
                 return "Para comparação, por favor, forneça pelo menos uma substância ativa, espécie alvo ou forma farmacêutica."

            # Verificar se não tem forma farmacêutica especificada
            if not forma.strip():
                print(colored("Forma farmacêutica não especificada. Realizando busca simples sem IA.", "blue"))
                resultados_simples = self._realizar_busca_comparacao_simples(termo_busca_comparacao)
                if not resultados_simples:
                    return f"Não foram encontrados resultados na busca para: '{termo_busca_comparacao}'."
                
                return self._formatar_resultados_comparacao_simples(resultados_simples, pergunta_normalizada)
            else:
                # Realizar busca completa com IA quando há forma farmacêutica especificada
                print(colored(f"Termo de busca para comparação (web scraping): '{termo_busca_comparacao}'", "blue"))
                dados_raspados = self.realizar_web_scraping(termo_busca_comparacao)
                if not dados_raspados:
                    return f"Não foram encontrados resultados no web scraping para os critérios de comparação: '{termo_busca_comparacao}'."
                
                return self._consultar_ollama_com_contexto(pergunta_para_ollama, dados_raspados, tipo_consulta="comparacao")

        else:
            return f"Categoria de pergunta '{categoria}' não suportada no momento."

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


