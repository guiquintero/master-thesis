from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time
import requests
import json
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# Lista de URLs visitadas para evitar duplicatas
urls_visitadas = set()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
}

# Lista para armazenar os dados extraídos
dados_extraidos = []

def extrair_conteudo(url):
    """Acessa a URL, extrai os títulos dos resultados e segue a paginação."""
    
    if url in urls_visitadas:
        return  # Evita visitar a mesma página várias vezes
    
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

    # Encontra todas as divs com classe "search-result"
    itens = soup.find_all(class_="search-result")

    if not itens:
        print(f"Nenhuma div com class='search-result' encontrada em {url}")
        return

    # Extrai os títulos h5 dentro dessas divs
    titulos = [h.text.strip() for div in itens for h in div.find_all("h5")]

    if titulos:
        dados_extraidos.append({
            "url": url,
            "titulos": titulos,
        })
    
    # ---- TRATANDO PAGINAÇÃO ---- #
    # Coleta os links dentro da div "navbar" (que contém a paginação)
    nav_bar = soup.find(class_="navbar")
    if nav_bar:
        for link in nav_bar.find_all("a", href=True):
            link_url = urljoin(url, link["href"])
            
            # Se o link ainda não foi visitado e pertence ao mesmo site, visitar
            if link_url not in urls_visitadas and "medvet.dgav.pt" in link_url:
                extrair_conteudo(link_url)

# ---- USANDO SELENIUM PARA SUBMETER O INPUT ---- #
termo_busca = input("Digite o termo de busca: ")

driver = webdriver.Chrome()
new_url = ''
try:
    driver.get("https://medvet.dgav.pt/")
    time.sleep(2)

    input_box = driver.find_element(By.TAG_NAME, "input")  # Ajuste se necessário
    input_box.send_keys(termo_busca)
    input_box.send_keys(Keys.RETURN)

    time.sleep(3)

    # Obtém a URL da página com os resultados
    new_url = driver.current_url

finally:
    driver.quit()

# ---- CHAMA A FUNÇÃO PARA EXTRAIR OS DADOS DA URL OBTIDA ---- #
extrair_conteudo(new_url)

# ---- SALVA OS DADOS EXTRAÍDOS EM UM JSON ---- #
with open("dados_dgav.json", "w", encoding="utf-8") as f:
    json.dump(dados_extraidos, f, ensure_ascii=False, indent=4)

print("Scraping concluído! Dados salvos em 'dados_dgav.json'.")
