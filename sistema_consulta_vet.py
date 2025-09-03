# ...existing code...

class SistemaConsultaVet:
    # ...existing code...

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

    def processar_pergunta_unica(self, pergunta_usuario):
        # Normalizar espécies animais na pergunta antes de processar
        pergunta_normalizada = self._normalizar_especies_texto(pergunta_usuario)
        
        if pergunta_normalizada != pergunta_usuario:
            print(colored(f"Pergunta normalizada: '{pergunta_normalizada}'", "cyan"))
        
        print(colored(f"\nProcessando pergunta: '{pergunta_normalizada}'", "cyan"))
        classificacao = self.query_classifier.classify_and_extract(pergunta_normalizada)

        # ...existing code...

        elif categoria == "comparacao":
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

        # ...existing code...
