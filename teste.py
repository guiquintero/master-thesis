from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import urllib3
import json
import fitz  # PyMuPDF
import re
import concurrent.futures
import os
from tqdm import tqdm
import ollama
import hashlib
from termcolor import colored
import shutil

# Desativar alertas de aviso de SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
}

# Configurações globais
MODELO_PADRAO = "gemma3:latest"
PDF_CACHE_DIR = "pdf_cache"
CACHE_DIR = "resposta_cache"
ARQUIVO_JSON = "medicamento_buscado.json"

# Criar diretórios de cache
os.makedirs(PDF_CACHE_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

# Variáveis globais para web scraping
resultados = []
urls_visitadas = set()

class MedicineScraperConsultor:
    def __init__(self, modelo=MODELO_PADRAO, temperatura=0.2):
        self.modelo = modelo
        self.temperatura = temperatura
        self.dados = None
        
    # ========== FUNÇÕES DE WEB SCRAPING ==========
    
    def extrair_conteudo_pdf(self, pdf_url):
        """Função para extrair conteúdo do PDF com cache"""
        cache_filename = os.path.join(PDF_CACHE_DIR, pdf_url.split('/')[-1].replace('?', '_').replace('&', '_'))
        
        # Verificar se já temos o PDF em cache
        if os.path.exists(cache_filename):
            try:
                pdf_file = fitz.open(cache_filename)
                pdf_text = "\n".join(page.get_text() for page in pdf_file)
                pdf_file.close()
                return pdf_text
            except Exception:
                pass
        
        try:
            pdf_response = requests.get(pdf_url, timeout=10, headers=HEADERS, verify=False)
            pdf_response.raise_for_status()

            with open(cache_filename, 'wb') as f:
                f.write(pdf_response.content)
            
            pdf_file = fitz.open(cache_filename)
            pdf_text = "\n".join(page.get_text() for page in pdf_file)
            pdf_file.close()
            return pdf_text
        except requests.RequestException as e:
            print(f"Erro ao acessar o PDF: {e}")
        except Exception as e:
            print(f"Erro ao processar o PDF: {e}")
            if os.path.exists(cache_filename):
                os.remove(cache_filename)
        return None

    def extrair_conteudo(self, url, url_pai=None):
        """Função para extrair conteúdo HTML de uma URL"""
        global resultados, urls_visitadas
        
        if url in urls_visitadas:
            return  
        urls_visitadas.add(url)  
        
        try:
            response = requests.get(url, timeout=10, headers=HEADERS, verify=False)
            response.raise_for_status()
            if "text/html" not in response.headers.get("Content-Type", ""):
                print(f"Ignorando {url}, pois não é uma página HTML.")
                return
            response.encoding = "utf-8"
        except requests.RequestException as e:
            print(f"Erro ao acessar {url}: {e}")
            return

        soup = BeautifulSoup(response.text, "html.parser")
        itens = soup.find_all("div", class_="search-result")

        if not itens:
            print(f"Nenhuma div com class='search-result' encontrada em {url}")
            return
        
        for div in itens:
            h5 = div.find("h5")
            link = div.find("a", href=True)
            if h5 and link:
                titulo = h5.text.strip()
                link_url = urljoin(url, link["href"])
                resultados.append({"titulo": titulo, "link": link_url})
        
        navbar = soup.find("div", class_="navbar")
        if navbar:
            for link in navbar.find_all("a", href=True):
                link_url = urljoin(url, link["href"])
                if link_url not in urls_visitadas:
                    self.extrair_conteudo(link_url)

    def formatar_texto(self, elemento):
        """Função para formatar o conteúdo HTML"""
        if elemento.name in {"h1", "h2", "h3", "h4", "h5", "a", "p"}:
            return elemento.get_text(strip=True)
        return None

    def encontrar_link_pdf(self, soup, url):
        """Função para encontrar o link do PDF corretamente"""
        pdf_tag = soup.find("a", href=True, target="_blank")
        if pdf_tag and pdf_tag.find("span", class_="fa-file-pdf-o"):
            return urljoin(url, pdf_tag["href"])
        return None

    def formatar_conteudo_pdf(self, texto):
        """Função melhorada para formatar o conteúdo do PDF"""
        if not texto:
            return []

        texto_limpo = texto

        # Remover cabeçalhos e rodapés
        texto_limpo = re.sub(r"\nDireção Geral de Alimentação e Veterinária – DGAMV.*?Página \d+ de \d+ \n", "", texto_limpo, flags=re.DOTALL)
        texto_limpo = re.sub(r"\n\d+\.\d+ \n", "--", texto_limpo)
        texto_limpo = re.sub(r"\n\d+\.\d+  \n", "--", texto_limpo)

        # Remover tudo após "FOLHETO INFORMATIVO" (case-insensitive)
        partes_folheto = re.split(r"(FOLHETO INFORMATIVO)", texto_limpo, flags=re.IGNORECASE)
        if len(partes_folheto) > 1:
            texto_limpo = partes_folheto[0]

        # Dividir o texto
        partes = re.split(r"\n \n\d+\. \n", texto_limpo)

        partes_formatadas = []
        for parte in partes:
            parte_limpa = parte.strip()
            parte_limpa = re.sub(r"\n(?!\n)", " ", parte_limpa)
            parte_limpa = re.sub(r"\n\n+", "\n\n", parte_limpa)
            partes_formatadas.append(parte_limpa)

        return partes_formatadas

    def processar_link(self, link):
        """Função para processar um único link"""
        global resultados
        
        try:
            response = requests.get(link, timeout=15, headers=HEADERS, verify=False)
            response.raise_for_status()
            if "text/html" not in response.headers.get("Content-Type", ""):
                print(f"Ignorando {link}, pois não é uma página HTML.")
                return None
            response.encoding = "utf-8"
        except requests.RequestException as e:
            print(f"Erro ao acessar {link}: {e}")
            return None
        
        soup = BeautifulSoup(response.text, "html.parser")
        tags_permitidas = {"h1", "h2", "h3", "h4", "h5", "p", "a"}
        conteudo = {"url": link, "conteudo": ""}
        
        # Extrair o conteúdo HTML
        encontrou_titulo = False
        conteudo_str = ""
        for element in soup.body.find_all(tags_permitidas, recursive=True):
            texto_formatado = self.formatar_texto(element)
            if texto_formatado:
                if element.name in {"h1", "h2", "h3", "h4", "h5"}:
                    if any(texto_formatado.strip('"- ') == resultado["titulo"] for resultado in resultados):
                        encontrou_titulo = True
                if encontrou_titulo:
                    if element.name in {"h1", "h2", "h3", "h4", "h5"}:
                        conteudo_str += f"\n## {texto_formatado}\n"
                    else:
                        conteudo_str += texto_formatado + " "
        
        conteudo["conteudo"] = conteudo_str.strip()
        
        # Extrair o link do PDF
        pdf_url = self.encontrar_link_pdf(soup, link)
        if pdf_url:
            pdf_text = self.extrair_conteudo_pdf(pdf_url)
            if pdf_text:
                conteudo["pdf_conteudo"] = self.formatar_conteudo_pdf(pdf_text)
                print(f"PDF encontrado e extraído: {pdf_url}")
            else:
                print(f"Erro ao extrair conteúdo do PDF: {pdf_url}")
        else:
            print(f"Nenhum PDF encontrado para {link}")
        
        if not encontrou_titulo:
            return None
            
        return conteudo

    def extrair_conteudo_completo(self, links_selecionados):
        """Função para extrair conteúdo completo (HTML e PDF) com processamento paralelo"""
        conteudo_extraido = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futuros = {executor.submit(self.processar_link, link): link for link in links_selecionados}
            for futuro in tqdm(concurrent.futures.as_completed(futuros), total=len(links_selecionados), desc="Processando links"):
                link = futuros[futuro]
                try:
                    resultado = futuro.result()
                    if resultado:
                        conteudo_extraido.append(resultado)
                except Exception as e:
                    print(f"Erro ao processar {link}: {e}")
        
        # Salvar em um arquivo JSON
        with open(ARQUIVO_JSON, "w", encoding="utf-8") as json_file:
            json.dump(conteudo_extraido, json_file, ensure_ascii=False, indent=4)
        
        print(f"Conteúdo completo (HTML + PDF) salvo em {ARQUIVO_JSON} ({len(conteudo_extraido)} links processados)")
        return conteudo_extraido

    def fazer_webscraping(self):
        """Função principal para fazer o web scraping"""
        global resultados, urls_visitadas
        
        # Resetar variáveis globais
        resultados = []
        urls_visitadas = set()
        
        termo_busca = input("Digite o termo de busca: ")
        
        # Configurar Chrome para ser mais rápido e headless
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--no-sandbox")
        
        driver = webdriver.Chrome(options=chrome_options)
        nova_url = ''
        try:
            print("Acessando o site...")
            driver.get("https://medvet.dgav.pt/")
            
            wait = WebDriverWait(driver, 10)
            input_box = wait.until(EC.presence_of_element_located((By.TAG_NAME, "input")))
            
            print(f"Buscando por: '{termo_busca}'")
            input_box.send_keys(termo_busca)
            input_box.send_keys(Keys.RETURN)
            
            time.sleep(2)
            nova_url = driver.current_url
        finally:
            driver.quit()

        print(f"Extraindo resultados de: {nova_url}")
        self.extrair_conteudo(nova_url)
        
        if not resultados:
            print("Nenhum resultado encontrado para a busca.")
            return None
        
        print("\nResultados encontrados:")
        for idx, item in enumerate(resultados, start=1):
            print(f"{idx} - {item['titulo']}")

        while True:
            try:
                escolhas = input("\nDigite os números das opções desejadas (separados por vírgula ou 'todos' para selecionar todos): ")
                
                if escolhas.lower() == 'todos':
                    links_selecionados = [item['link'] for item in resultados]
                else:
                    escolhas = [int(x.strip()) for x in escolhas.split(",") if x.strip().isdigit()]
                    links_selecionados = [resultados[escolha - 1]['link'] for escolha in escolhas if 1 <= escolha <= len(resultados)]
                
                if not links_selecionados:
                    print("Nenhuma opção válida selecionada.")
                    continue
                    
                print(f"Processando {len(links_selecionados)} links selecionados...")
                conteudo_extraido = self.extrair_conteudo_completo(links_selecionados)
                
                if conteudo_extraido:
                    print("\nProcesso de extração concluído!")
                    return conteudo_extraido
                else:
                    print("Nenhum conteúdo foi extraído. Tente novamente.")
            except Exception as e:
                print(f"Erro ao processar escolhas: {e}")
                print("Tente novamente.")

    # ========== FUNÇÕES DE CONSULTA COM OLLAMA ==========
    
    def gerar_hash(self, texto):
        """Gera um hash único para uma consulta"""
        return hashlib.md5(texto.encode('utf-8')).hexdigest()

    def carregar_cache(self, hash_consulta):
        """Tenta carregar uma resposta do cache"""
        arquivo_cache = os.path.join(CACHE_DIR, f"{hash_consulta}.json")
        if os.path.exists(arquivo_cache):
            try:
                with open(arquivo_cache, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
                    return cache.get('resposta')
            except:
                return None
        return None

    def salvar_cache(self, hash_consulta, resposta):
        """Salva uma resposta no cache"""
        arquivo_cache = os.path.join(CACHE_DIR, f"{hash_consulta}.json")
        with open(arquivo_cache, 'w', encoding='utf-8') as f:
            json.dump({'resposta': resposta}, f, ensure_ascii=False, indent=2)

    def preparar_contexto(self, dados, pergunta):
        """Prepara um contexto reduzido relevante para a pergunta"""
        palavras_chave = set(palavra.lower() for palavra in pergunta.split() if len(palavra) > 3)
        contexto_relevante = []
        
        for item in dados:
            conteudo_relevante = False
            trecho_relevante = {}
            
            # Verificar conteúdo HTML
            if "conteudo" in item and item["conteudo"]:
                texto = item["conteudo"].lower()
                if any(palavra in texto for palavra in palavras_chave):
                    conteudo_relevante = True
                    trecho_relevante["conteudo"] = item["conteudo"]
            
            # Verificar conteúdo PDF
            if "pdf_conteudo" in item and item["pdf_conteudo"]:
                pdf_relevante = []
                for secao in item["pdf_conteudo"]:
                    texto_secao = secao.lower()
                    if any(palavra in texto_secao for palavra in palavras_chave):
                        pdf_relevante.append(secao)
                
                if pdf_relevante:
                    conteudo_relevante = True
                    trecho_relevante["pdf_conteudo"] = pdf_relevante
            
            # Se encontrou conteúdo relevante, adicionar à lista
            if conteudo_relevante:
                if "url" in item:
                    trecho_relevante["url"] = item["url"]
                contexto_relevante.append(trecho_relevante)
        
        # Se não encontrou nada relevante, retornar o contexto completo
        if not contexto_relevante:
            return dados
        
        return contexto_relevante

    def consultar_ollama(self, prompt):
        """Consulta o Ollama com um prompt"""
        try:
            resposta = ollama.chat(
                model=self.modelo,
                messages=[
                    {
                        'role': 'system',
                        'content': 'Você é um assistente médico veterinário que fornece informações precisas baseadas apenas no contexto fornecido.'
                    },
                    {
                        'role': 'user',
                        'content': prompt,
                    }
                ],
                options={
                    'temperature': self.temperatura
                }
            )
            return resposta['message']['content']
        except Exception as e:
            return f"Erro ao consultar o modelo: {str(e)}"
    
    def consultar_com_ollama(self, arquivo):
        """Carrega um arquivo específico e inicia uma conversa com o Ollama"""
        global ARQUIVO_JSON
        arquivo_original = ARQUIVO_JSON  # Salva o arquivo padrão
        try:
            # Define o novo arquivo como padrão
            ARQUIVO_JSON = arquivo
            
            # Carrega os dados do novo arquivo
            if not self.carregar_dados(arquivo):
                print(colored(f"Erro ao carregar o arquivo {arquivo}.", "red"))
                return
            
            # Inicia a consulta com o Ollama
            print(colored(f"Iniciando consulta com o arquivo {arquivo}...", "cyan"))
            self.fazer_consultas()
        finally:
            # Restaura o arquivo padrão
            ARQUIVO_JSON = arquivo_original
            print(colored(f"Arquivo padrão restaurado: {ARQUIVO_JSON}", "green"))

    def carregar_dados(self, arquivo=None):
        """Carrega os dados do arquivo JSON"""
        arquivo_usar = arquivo or ARQUIVO_JSON
        
        if not os.path.exists(arquivo_usar):
            print(colored(f"Erro: O arquivo {arquivo_usar} não foi encontrado.", "red"))
            return False
        
        try:
            with open(arquivo_usar, "r", encoding="utf-8") as f:
                self.dados = json.load(f)
            print(colored(f"Arquivo carregado com sucesso! ({len(self.dados)} entradas)", "green"))
            return True
        except Exception as e:
            print(colored(f"Erro ao carregar o arquivo JSON: {e}", "red"))
            return False

    def fazer_consultas(self, sem_cache=False):
        """Loop principal de consultas"""
        if not self.dados:
            print(colored("Nenhum dado carregado. Execute o web scraping primeiro ou carregue um arquivo JSON.", "red"))
            return
        
        print(colored(f"\nMODO CONSULTA ATIVADO", "cyan"))
        print(colored(f"Modelo: {self.modelo}", "cyan"))
        print(colored(f"Temperatura: {self.temperatura}", "cyan"))
        print(colored(f"Dados carregados: {len(self.dados)} entradas\n", "cyan"))
        print(colored("Digite suas perguntas sobre os dados extraídos.", "white"))
        print(colored("Comandos especiais: 'sair', 'menu', 'info'", "yellow"))
        
        while True:
            pergunta = input(colored("\nSua pergunta: ", "cyan"))
            
            if pergunta.lower() in ['sair', 'exit', 'quit']:
                break
            elif pergunta.lower() == 'menu':
                return  # Volta ao menu principal
            elif pergunta.lower() == 'info':
                print(colored(f"\nInformações atuais:", "cyan"))
                print(f"Modelo: {self.modelo}")
                print(f"Temperatura: {self.temperatura}")
                print(f"Entradas carregadas: {len(self.dados)}")
                continue
            
            if not pergunta.strip():
                continue
            
            start_time = time.perf_counter()
            
            # Verificar cache primeiro
            hash_consulta = self.gerar_hash(f"{pergunta}_{self.modelo}_{self.temperatura}")
            if not sem_cache:
                resposta_cache = self.carregar_cache(hash_consulta)
                if resposta_cache:
                    print(colored("\nResposta (cache):", "green"))
                    print(resposta_cache)
                    end_time = time.perf_counter()
                    print(colored(f"\nTempo: {(end_time - start_time):.3f}s (cache)", "yellow"))
                    continue
            
            # Preparar contexto relevante para a pergunta
            print(colored("Analisando dados relevantes...", "yellow"))
            contexto_relevante = self.preparar_contexto(self.dados, pergunta)
            
            # Limitar o contexto para não exceder limites do modelo
            contexto_json = json.dumps(contexto_relevante, ensure_ascii=False)
            print(colored(f"Contexto: {len(contexto_json)} caracteres", "yellow"))
            
            # Preparar prompt
            prompt = f"""
                Com base APENAS no seguinte contexto sobre medicamentos veterinários:

                ```
                {contexto_json}
                ```

                Responda à pergunta: "{pergunta}"

                Se a informação não estiver no contexto fornecido, responda 'Não encontrei informações sobre isso no material disponível'.
                Cite as fontes (URLs) se disponíveis no material.
                """
            
            # Consultar o Ollama
            print(colored("Consultando modelo...", "yellow"))
            resposta = self.consultar_ollama(prompt)
            
            # Salvar no cache
            if not sem_cache:
                self.salvar_cache(hash_consulta, resposta)
            
            # Exibir a resposta
            print(colored("\nResposta:", "green"))
            print(resposta)
            
            end_time = time.perf_counter()
            print(colored(f"\nTempo: {(end_time - start_time):.3f}s", "yellow"))

    def executar(self, modo="completo", arquivo_json=None, sem_cache=False):
        """Função principal que executa o programa"""
        print(colored("=== Sistema Unificado de Web Scraping e Consulta Veterinária ===", "magenta"))
        
        if modo == "completo":
            print(colored("\n1. Iniciando Web Scraping...", "cyan"))
            dados_extraidos = self.fazer_webscraping()
            
            if dados_extraidos:
                self.dados = dados_extraidos
                print(colored("\n2. Dados extraídos com sucesso! Iniciando modo de consulta.", "green"))
                self.fazer_consultas(sem_cache)
            else:
                print(colored("Web scraping não foi concluído com sucesso.", "red"))
                
        elif modo == "consulta":
            if self.carregar_dados(arquivo_json):
                self.fazer_consultas(sem_cache)

def limpar_cache():
    """Limpa os caches de PDF e respostas"""
    import shutil
    
    try:
        # Limpar cache de PDFs
        if os.path.exists(PDF_CACHE_DIR):
            shutil.rmtree(PDF_CACHE_DIR)
            os.makedirs(PDF_CACHE_DIR, exist_ok=True)
        
        # Limpar cache de respostas
        if os.path.exists(CACHE_DIR):
            shutil.rmtree(CACHE_DIR)
            os.makedirs(CACHE_DIR, exist_ok=True)
            
        print(colored("Cache limpo com sucesso!", "green"))
    except Exception as e:
        print(colored(f"Erro ao limpar cache: {e}", "red"))

def mostrar_menu():
    """Mostra o menu principal"""
    print(colored("\n" + "="*60, "magenta"))
    print(colored("SISTEMA DE CONSULTA VETERINÁRIA", "magenta"))
    print(colored("="*60, "magenta"))
    print(colored("\nMENU PRINCIPAL:", "cyan"))
    print("1. Fazer perguntas sobre dados existentes")
    print("2. Nova pesquisa (Web Scraping + Consultas)")
    print("3. Limpar cache")
    print("4. Consultar legislação com Ollama (dados_dgav_final.json)")
    print("5. Sair")
    print(colored("-"*60, "cyan"))

def main():
    modelo_atual = MODELO_PADRAO
    temperatura_atual = 0.2
    
    while True:
        mostrar_menu()
        
        try:
            opcao = input(colored("Escolha uma opção (1-5): ", "yellow")).strip()
            
            if opcao == "1":
                # Fazer perguntas sobre dados existentes
                print(colored("\nCarregando dados existentes...", "cyan"))
                consultor = MedicineScraperConsultor(modelo=modelo_atual, temperatura=temperatura_atual)
                if consultor.carregar_dados():
                    consultor.fazer_consultas()
                else:
                    input(colored("Pressione Enter para continuar...", "yellow"))
                    
            elif opcao == "2":
                # Nova pesquisa completa
                print(colored("\nIniciando nova pesquisa...", "cyan"))
                consultor = MedicineScraperConsultor(modelo=modelo_atual, temperatura=temperatura_atual)
                dados_extraidos = consultor.fazer_webscraping()
                
                if dados_extraidos:
                    consultor.dados = dados_extraidos
                    print(colored("\nDados extraídos! Iniciando consultas...", "green"))
                    consultor.fazer_consultas()
                else:
                    print(colored("Web scraping não foi concluído.", "red"))
                    input(colored("Pressione Enter para continuar...", "yellow"))
                    
            elif opcao == "3":
                # Limpar cache
                confirmacao = input(colored("Tem certeza que deseja limpar todo o cache? (s/N): ", "yellow")).strip().lower()
                if confirmacao in ['s', 'sim', 'yes', 'y']:
                    limpar_cache()
                else:
                    print(colored("Operação cancelada.", "yellow"))
                input(colored("Pressione Enter para continuar...", "yellow"))
            
            elif opcao == "4":
                # Consultar Ollama com 'dados_dgav_final.json'
                print(colored("\nIniciando consulta com Ollama usando 'dados_dgav_final.json'...", "cyan"))
                consultor = MedicineScraperConsultor(modelo=modelo_atual, temperatura=temperatura_atual)
                consultor.consultar_com_ollama("dados_dgav_final.json")
                input(colored("Pressione Enter para continuar...", "yellow"))
                
            elif opcao == "5":
                # Sair
                print(colored("Obrigado por usar o sistema! Até logo!", "green"))
                break
                
            else:
                print(colored("Opção inválida. Escolha um número de 1 a 5.", "red"))
                input(colored("Pressione Enter para continuar...", "yellow"))
                
        except KeyboardInterrupt:
            print(colored("\nPrograma interrompido pelo usuário. Até logo!", "yellow"))
            break
        except Exception as e:
            print(colored(f"Erro inesperado: {e}", "red"))
            input(colored("Pressione Enter para continuar...", "yellow"))

if __name__ == "__main__":
    main()