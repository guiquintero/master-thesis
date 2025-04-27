import requests
import json
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URLS = [
    "https://www.dgav.pt/medicamentos/",
]

urls_visitadas = set()
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
}

dados_extraidos = []

def extrair_conteudo(url, url_pai=None, profundidade=0, max_profundidade=3):
    """Extrai conteúdo apenas das divs com id='readable', seguindo links internos de forma hierárquica."""
    
    if url in urls_visitadas or profundidade > max_profundidade:
        return
    
    print(f"Extraindo: {url}")
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
    readable_divs = soup.find_all("div", id="readable")
    
    if not readable_divs:
        print(f"Nenhuma div com id='readable' encontrada em {url}")
        return

    conteudo_completo = ""
    
    apenas_h2 = True
    
    for div in readable_divs:
        for elemento in div.find_all(["h2", "p", "ul"]):
            if elemento.name == "h2" and elemento.text.strip():
                conteudo_completo += f"## {elemento.text.strip()}: "  
            elif elemento.name == "p" and elemento.text.strip():
                conteudo_completo += f"{elemento.text.strip()}."
                apenas_h2 = False  
            elif elemento.name == "ul":
                lista_items = elemento.find_all("li")
                if lista_items:
                    apenas_h2 = False  
                    conteudo_completo += "\n"
                    for li in lista_items:
                        if li.text.strip():
                            conteudo_completo += f"- {li.text.strip()};"
                    conteudo_completo += "\n"

    conteudo_limpo = conteudo_completo.strip()
    if conteudo_limpo and not apenas_h2:
        dados_extraidos.append({
            "url": url,
            "conteudo": conteudo_limpo
        })
    elif apenas_h2:
        print(f"URL {url} contém apenas cabeçalhos h2, ignorando.")
    
    # Buscar links internos apenas dentro da div id="readable"
    for div in readable_divs:
        for link in div.find_all("a", href=True):
            link_url = urljoin(url, link["href"])
            # Filtrar apenas links que são continuação da URL atual
            if link_url.startswith(url) and link_url not in urls_visitadas:
                extrair_conteudo(link_url, url, profundidade + 1, max_profundidade)

for url in BASE_URLS:
    extrair_conteudo(url)

# Salvar apenas as URLs com conteúdo
with open("dados_dgav_final.json", "w", encoding="utf-8") as f:
    json.dump(dados_extraidos, f, ensure_ascii=False, indent=4)

print(f"Scraping concluído! Dados salvos em 'dados_dgav_final.json'. Total de páginas com conteúdo: {len(dados_extraidos)}")