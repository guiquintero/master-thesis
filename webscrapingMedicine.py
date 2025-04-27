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

# Desativar alertas de aviso de SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
}

resultados = []
urls_visitadas = set()
PDF_CACHE_DIR = "pdf_cache"

# Criar diretório de cache para PDFs
os.makedirs(PDF_CACHE_DIR, exist_ok=True)

# Função para extrair conteúdo do PDF com cache
def extrair_conteudo_pdf(pdf_url):
    # Criar um nome de arquivo baseado na URL
    cache_filename = os.path.join(PDF_CACHE_DIR, pdf_url.split('/')[-1].replace('?', '_').replace('&', '_'))
    
    # Verificar se já temos o PDF em cache
    if os.path.exists(cache_filename):
        try:
            pdf_file = fitz.open(cache_filename)
            pdf_text = "\n".join(page.get_text() for page in pdf_file)
            pdf_file.close()
            return pdf_text
        except Exception:
            # Se houver erro ao ler do cache, continuar com download
            pass
    
    try:
        # Fazer download do PDF
        pdf_response = requests.get(pdf_url, timeout=10, headers=HEADERS, verify=False)
        pdf_response.raise_for_status()

        # Salvar o PDF em cache
        with open(cache_filename, 'wb') as f:
            f.write(pdf_response.content)
        
        # Extrair texto
        pdf_file = fitz.open(cache_filename)
        pdf_text = "\n".join(page.get_text() for page in pdf_file)
        pdf_file.close()
        return pdf_text
    except requests.RequestException as e:
        print(f"Erro ao acessar o PDF: {e}")
    except Exception as e:
        print(f"Erro ao processar o PDF: {e}")
        # Remover arquivo de cache corrompido se existir
        if os.path.exists(cache_filename):
            os.remove(cache_filename)
    return None

# Função para extrair conteúdo HTML de uma URL
def extrair_conteudo(url, url_pai=None):
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
                extrair_conteudo(link_url)

# Função para formatar o conteúdo HTML
def formatar_texto(elemento):
    if elemento.name in {"h1", "h2", "h3", "h4", "h5", "a", "p"}:
        return elemento.get_text(strip=True)
    return None

# Função para encontrar o link do PDF corretamente
def encontrar_link_pdf(soup, url):
    pdf_tag = soup.find("a", href=True, target="_blank")
    if pdf_tag and pdf_tag.find("span", class_="fa-file-pdf-o"):
        return urljoin(url, pdf_tag["href"])
    return None

# Função melhorada para formatar o conteúdo do PDF
def formatar_conteudo_pdf(texto):
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
        texto_limpo = partes_folheto[0] # Pegar apenas a parte antes do "FOLHETO INFORMATIVO"

    # Dividir o texto
    partes = re.split(r"\n \n\d+\. \n", texto_limpo)

    partes_formatadas = []
    for parte in partes:
        # Remover espaços em branco no início e fim da parte
        parte_limpa = parte.strip()
        # Remover quebras de linha desnecessárias mas preservar estrutura de parágrafos
        parte_limpa = re.sub(r"\n(?!\n)", " ", parte_limpa)  # Substituir quebras de linha únicas por espaços
        parte_limpa = re.sub(r"\n\n+", "\n\n", parte_limpa)  # Manter apenas uma quebra de parágrafo
        partes_formatadas.append(parte_limpa)

    return partes_formatadas

# Função para processar um único link
def processar_link(link):
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
        texto_formatado = formatar_texto(element)
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
    pdf_url = encontrar_link_pdf(soup, link)
    if pdf_url:
        pdf_text = extrair_conteudo_pdf(pdf_url)
        if pdf_text:
            conteudo["pdf_conteudo"] = formatar_conteudo_pdf(pdf_text)
            print(f"PDF encontrado e extraído: {pdf_url}")
        else:
            print(f"Erro ao extrair conteúdo do PDF: {pdf_url}")
    else:
        print(f"Nenhum PDF encontrado para {link}")
    
    if not encontrou_titulo:
        return None
        
    return conteudo

# Função para extrair conteúdo completo (HTML e PDF) com processamento paralelo
def extrair_conteudo_completo(links_selecionados):
    conteudo_extraido = []
    
    # Usar processamento paralelo para extrair conteúdo
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        # Usar tqdm para mostrar progresso
        futuros = {executor.submit(processar_link, link): link for link in links_selecionados}
        for futuro in tqdm(concurrent.futures.as_completed(futuros), total=len(links_selecionados), desc="Processando links"):
            link = futuros[futuro]
            try:
                resultado = futuro.result()
                if resultado:
                    conteudo_extraido.append(resultado)
            except Exception as e:
                print(f"Erro ao processar {link}: {e}")
    
    # Salvar em um arquivo JSON
    with open("conteudo_completo.json", "w", encoding="utf-8") as json_file:
        json.dump(conteudo_extraido, json_file, ensure_ascii=False, indent=4)
    
    print(f"Conteúdo completo (HTML + PDF) salvo em conteudo_completo.json ({len(conteudo_extraido)} links processados)")
    return len(conteudo_extraido) > 0

# Função principal
def main():
    termo_busca = input("Digite o termo de busca: ")
    
    # Configurar Chrome para ser mais rápido e headless
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Executar em modo headless (sem interface gráfica)
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    
    driver = webdriver.Chrome(options=chrome_options)
    nova_url = ''
    try:
        print("Acessando o site...")
        driver.get("https://medvet.dgav.pt/")
        
        # Esperar pelo carregamento da página usando WebDriverWait
        wait = WebDriverWait(driver, 10)
        input_box = wait.until(EC.presence_of_element_located((By.TAG_NAME, "input")))
        
        print(f"Buscando por: '{termo_busca}'")
        input_box.send_keys(termo_busca)
        input_box.send_keys(Keys.RETURN)
        
        # Esperar pela navegação
        time.sleep(2)
        nova_url = driver.current_url
    finally:
        driver.quit()

    print(f"Extraindo resultados de: {nova_url}")
    extrair_conteudo(nova_url)
    
    if not resultados:
        print("Nenhum resultado encontrado para a busca.")
        return
    
    print("\nResultados encontrados:")
    for idx, item in enumerate(resultados, start=1):
        print(f"{idx} - {item['titulo']}")

    while True:
        try:
            # Escolher os links para extrair o conteúdo completo
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
            if extrair_conteudo_completo(links_selecionados):
                print("\nProcesso de extração concluído!")
                break
            else:
                print("Nenhum conteúdo foi extraído. Tente novamente.")
        except Exception as e:
            print(f"Erro ao processar escolhas: {e}")
            print("Tente novamente.")

if __name__ == "__main__":
    main()