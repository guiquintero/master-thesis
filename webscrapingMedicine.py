from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import urllib3
import json
import fitz  # PyMuPDF
import re

# Desativar alertas de aviso de SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
}

resultados = []
urls_visitadas = set()

# Função para extrair conteúdo do PDF
def extrair_conteudo_pdf(pdf_url):
    try:
        pdf_response = requests.get(pdf_url, timeout=10, headers=HEADERS, verify=False)
        pdf_response.raise_for_status()

        pdf_file = fitz.open(stream=pdf_response.content, filetype="pdf")
        pdf_text = "\n".join(page.get_text() for page in pdf_file)
        pdf_file.close()
        return pdf_text
    except requests.RequestException as e:
        print(f"Erro ao acessar o PDF: {e}")
    except Exception as e:
        print(f"Erro ao processar o PDF: {e}")
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
    if elemento.name == "h1":
        return f'{elemento.get_text(strip=True)}'
    elif elemento.name == "h2":
        return f'{elemento.get_text(strip=True)}'
    elif elemento.name == "h3":
        return f'{elemento.get_text(strip=True)}'
    elif elemento.name == "h4":
        return f'{elemento.get_text(strip=True)}'
    elif elemento.name == "h5":
        return f'{elemento.get_text(strip=True)}'
    elif elemento.name == "a":
        return elemento.get_text(strip=True)
    elif elemento.name == "p":
        return elemento.get_text(strip=True)
    return None

# Função para encontrar o link do PDF corretamente
def encontrar_link_pdf(soup, url):
    pdf_tag = soup.find("a", href=True, target="_blank")
    if pdf_tag and pdf_tag.find("span", class_="fa-file-pdf-o"):
        return urljoin(url, pdf_tag["href"])
    return None

# Função para formatar o conteúdo do PDF
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
        # Remover todas as quebras de linha dentro da parte
        parte_limpa = re.sub(r"\n", "", parte_limpa)
        partes_formatadas.append(parte_limpa)

    return partes_formatadas

# Função para extrair conteúdo completo (HTML e PDF)
def extrair_conteudo_completo(links_selecionados):
    conteudo_extraido = []
    for link in links_selecionados:
        try:
            response = requests.get(link, timeout=10, headers=HEADERS, verify=False)
            response.raise_for_status()
            if "text/html" not in response.headers.get("Content-Type", ""):
                print(f"Ignorando {link}, pois não é uma página HTML.")
                continue
            response.encoding = "utf-8"
        except requests.RequestException as e:
            print(f"Erro ao acessar {link}: {e}")
            continue
        
        soup = BeautifulSoup(response.text, "html.parser")
        tags_permitidas = {"h1", "h2", "h3", "h4", "h5", "p", "a"}
        conteudo = {"link": link, "conteudo": []}
        
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
                    conteudo_str += texto_formatado + " "
        conteudo["conteudo"] = conteudo_str.strip()

        
        # Extrair o link do PDF corretamente
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
        
        if encontrou_titulo:
            conteudo_extraido.append(conteudo)
    
    # Salvar em um arquivo JSON
    with open("conteudo_completo.json", "w", encoding="utf-8") as json_file:
        json.dump(conteudo_extraido, json_file, ensure_ascii=False, indent=4)
    
    print("Conteúdo completo (HTML + PDF) salvo em conteudo_completo.json")

# Processo para buscar e coletar as URLs
termo_busca = input("Digite o termo de busca: ")
driver = webdriver.Chrome()
nova_url = ''
try:
    driver.get("https://medvet.dgav.pt/")
    time.sleep(2)
    
    input_box = driver.find_element(By.TAG_NAME, "input")
    input_box.send_keys(termo_busca)
    input_box.send_keys(Keys.RETURN)
    
    time.sleep(2)
    nova_url = driver.current_url
finally:
    driver.quit()

extrair_conteudo(nova_url)
print("\nResultados encontrados:")
for idx, item in enumerate(resultados, start=1):
    print(f"{idx} - {item['titulo']}")

# Escolher os links para extrair o conteúdo completo
escolhas = input("\nDigite os números das opções desejadas (separados por vírgula): ")
escolhas = [int(x.strip()) for x in escolhas.split(",") if x.strip().isdigit()]
links_selecionados = [resultados[escolha - 1]['link'] for escolha in escolhas if 1 <= escolha <= len(resultados)]
extrair_conteudo_completo(links_selecionados)
print("\nProcesso concluído!")
