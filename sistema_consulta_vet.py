# ...existing code...

class SistemaConsultaVet:
    # ...existing code...

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
        elif categoria == "legislacao":
            # Para legislação, usar palavras-chave da pergunta
            pergunta = entidades.get("pergunta_ollama", "").lower()
            palavras_chave = [palavra para palavra em pergunta.split() se len(palavra) > 4][:5]  # Top 5 palavras relevantes
            key_parts = [categoria] + sorted(palavras_chave)
        else:
            key_parts = [categoria, entidades.get("pergunta_ollama", "").lower()]
        
        # Remover partes vazias e criar hash
        key_parts = [part para part em key_parts se part]
        cache_key = "_".join(key_parts)
        return hashlib.md5(cache_key.encode('utf-8')).hexdigest()

    def _verificar_intencao_similar(self, pergunta_atual, pergunta_cache):
        """Usa IA para verificar se duas perguntas têm intenção similar"""
        prompt = f"""
        Analise se as duas perguntas abaixo têm a mesma intenção/objetivo, mesmo que sejam formuladas de forma diferente.
        
        Pergunta 1: "{pergunta_atual}"
        Pergunta 2: "{pergunta_cache}"
        
        Responda apenas "SIM" se as perguntas têm a mesma intenção ou "NAO" se têm intenções diferentes.
        
        Exemplos de perguntas com mesma intenção:
        - "Qual a dose do medicamento X?" e "Que dose devo dar do X?"
        - "Como armazenar Y?" e "Qual a forma de armazenamento do Y?"
        - "Para que serve Z?" e "Qual a indicação do Z?"
        
        Resposta:
        """
        
        try:
            response = ollama.chat(
                model=self.modelo_ollama,
                messages=[
                    {
                        'role': 'system',
                        'content': 'Você é um analisador de intenções de perguntas. Responda apenas SIM ou NAO.'
                    },
                    {
                        'role': 'user',
                        'content': prompt,
                    }
                ],
                options={'temperature': 0.0}  # Determinístico
            )
            resposta = response['message']['content'].strip().upper()
            return resposta == "SIM"
        except Exception as e:
            print(colored(f"Erro ao verificar intenção: {e}", "red"))
            return False

    def _carregar_resposta_cache_inteligente(self, classificacao, pergunta_atual):
        """Carrega resposta do cache inteligente verificando entidades e intenção"""
        cache_key = self._gerar_cache_key_inteligente(classificacao)
        arquivo_cache = os.path.join(CACHE_DIR_RESPOSTAS, f"smart_{cache_key}.json")
        
        if not os.path.exists(arquivo_cache):
            return None
        
        try:
            with open(arquivo_cache, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Verificar se as entidades batem
            entidades_cache = cache_data.get('entidades', {})
            entidades_atual = classificacao.get('entidades', {})
            
            # Comparar entidades principais baseado na categoria
            categoria = classificacao.get('categoria')
            
            if categoria == "medicamento":
                if (entidades_cache.get('termo_busca', '').lower().strip() != 
                    entidades_atual.get('termo_busca', '').lower().strip()):
                    return None
                    
            elif categoria == "comparacao":
                campos_comparacao = ['substancia_ativa', 'especie_alvo', 'forma_farmaceutica']
                for campo in campos_comparacao:
                    if (entidades_cache.get(campo, '').lower().strip() != 
                        entidades_atual.get(campo, '').lower().strip()):
                        return None
                        
            elif categoria == "legislacao":
                # Para legislação, verificar se as palavras-chave principais coincidem
                pergunta_cache = entidades_cache.get('pergunta_ollama', '').lower()
                pergunta_atual_text = entidades_atual.get('pergunta_ollama', '').lower()
                
                # Extrair palavras-chave importantes
                palavras_cache = set([p for p in pergunta_cache.split() if len(p) > 4])
                palavras_atual = set([p for p in pergunta_atual_text.split() if len(p) > 4])
                
                # Verificar se há sobreposição significativa (pelo menos 60%)
                if len(palavras_cache & palavras_atual) / max(len(palavras_cache), len(palavras_atual), 1) < 0.6:
                    return None
            
            # Se chegou até aqui, as entidades batem. Agora verificar intenção
            pergunta_cache = cache_data.get('pergunta_original', '')
            
            print(colored("Entidades coincidem. Verificando intenção com IA...", "yellow"))
            
            if self._verificar_intencao_similar(pergunta_atual, pergunta_cache):
                print(colored("Intenção similar encontrada! Usando cache inteligente.", "green"))
                return cache_data.get('resposta')
            else:
                print(colored("Intenção diferente. Cache não será usado.", "yellow"))
                return None
                
        except Exception as e:
            print(colored(f"Erro ao carregar cache inteligente: {e}", "red"))
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

    def _consultar_ollama_com_contexto(self, pergunta_ollama, contexto_dados, tipo_consulta="medicamento", classificacao=None, pergunta_original=None):
        # Tentar carregar do cache inteligente primeiro
        if classificacao and pergunta_original:
            resposta_cache = self._carregar_resposta_cache_inteligente(classificacao, pergunta_original)
            if resposta_cache:
                return resposta_cache

        # ...existing code para processamento normal...

        try:
            print(colored("Consultando Ollama...", "yellow"))
            start_time = time.perf_counter()
            # ...existing code para chamada do ollama...
            
            # Salvar no cache inteligente
            if classificacao and pergunta_original:
                self._salvar_resposta_cache_inteligente(classificacao, pergunta_original, resposta_ollama)
            
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

        # ...existing code...

        if categoria == "medicamento":
            # ...existing code...
            return self._consultar_ollama_com_contexto(
                pergunta_para_ollama, 
                dados_raspados, 
                tipo_consulta="medicamento",
                classificacao=classificacao,
                pergunta_original=pergunta_normalizada
            )

        elif categoria == "legislacao":
            # ...existing code...
            return self._consultar_ollama_com_contexto(
                pergunta_para_ollama, 
                self.dados_legislacao, 
                tipo_consulta="legislacao",
                classificacao=classificacao,
                pergunta_original=pergunta_normalizada
            )

        elif categoria == "comparacao":
            # Verificar se é uma consulta dupla
            if self._detectar_consulta_dupla(classificacao):
                print(colored("Detectada consulta dupla (medicamento + comparação)", "yellow"))
                return self._realizar_consulta_dupla(classificacao, pergunta_normalizada)
            
            # TODAS as comparações agora usam web scraping simples (sem IA)
            substancia = entidades.get("substancia_ativa", "")
            especie = entidades.get("especie_alvo", "")
            forma = entidades.get("forma_farmaceutica", "")
            termo_busca_comparacao = f"{substancia} {especie} {forma}".strip()
            
            if not termo_busca_comparacao:
                return "Para comparação, por favor, forneça pelo menos uma substância ativa, espécie alvo ou forma farmacêutica."

            # Sempre realizar busca simples sem IA para comparações
            print(colored("Realizando busca de comparação com web scraping simples (sem IA).", "blue"))
            resultados_simples = self._realizar_busca_comparacao_simples(termo_busca_comparacao)
            if not resultados_simples:
                return f"Não foram encontrados resultados na busca para: '{termo_busca_comparacao}'."
            
            return self._formatar_resultados_comparacao_simples(resultados_simples, pergunta_normalizada)

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

    # ...existing code...
