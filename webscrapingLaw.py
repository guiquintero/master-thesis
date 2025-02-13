import requests
import json
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URLS = [
    "https://www.dgav.pt/animais/",
    "https://www.dgav.pt/plantas/",
    "https://www.dgav.pt/alimentos/",
    "https://www.dgav.pt/vaiviajar/",
    "https://www.dgav.pt/comerciointernacional/",
    "https://www.dgav.pt/medicamentos/",
    ]

urls_visitadas = set()
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
}

dados_extraidos = []  # Lista global para armazenar todas as páginas encontradas

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

    titulos = {
        "h1": [h.text.strip() for div in readable_divs for h in div.find_all("h1")],
        "h2": [h.text.strip() for div in readable_divs for h in div.find_all("h2")],
        "h3": [h.text.strip() for div in readable_divs for h in div.find_all("h3")],
        "h4": [h.text.strip() for div in readable_divs for h in div.find_all("h4")],
    }

    # Criar lista única mantendo a ordem dos elementos no HTML
    conteudo_ordenado = []
    for div in readable_divs:
        for elemento in div.find_all(["p", "ul"]):  # Mantém a ordem original
            if elemento.name == "p" and elemento.text.strip():
                conteudo_ordenado.append(elemento.text.strip())
            elif elemento.name == "ul":
                lista = [li.text.strip() for li in elemento.find_all("li") if li.text.strip()]
                if lista:
                    conteudo_ordenado.append(lista)

    if any([titulos["h1"], titulos["h2"], titulos["h3"], titulos["h4"], conteudo_ordenado]):
        dados_extraidos.append({
            "url": url,
            "titulos": titulos,
            "conteudo": conteudo_ordenado,  # Parágrafos e listas juntos
        })

    # Buscar links internos apenas dentro da div id="readable"
    for div in readable_divs:
        for link in div.find_all("a", href=True):
            link_url = urljoin(url, link["href"])
            # Filtrar apenas links que são continuação da URL atual
            if link_url.startswith(url) and link_url not in urls_visitadas:
                extrair_conteudo(link_url, url, profundidade + 1, max_profundidade)

for url in BASE_URLS:
    extrair_conteudo(url)  # Agora todas as páginas encontradas serão salvas na lista global

with open("dados_dgav_final.json", "w", encoding="utf-8") as f:
    json.dump(dados_extraidos, f, ensure_ascii=False, indent=4)

print("Scraping concluído! Dados salvos em 'dados_dgav.json'.")
