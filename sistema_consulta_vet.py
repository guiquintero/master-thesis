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
            palavras_chave = [palavra for palavra in pergunta.split() if len(palavra) > 4][:5]  # Top 5 palavras relevantes
            key_parts = [categoria] + sorted(palavras_chave)
        else:
            key_parts = [categoria, texto.lower()]
        
        # Remover partes vazias e criar hash
        key_parts = [part for part in key_parts if part]
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
                
                return self._consultar_ollama_com_contexto(
                    pergunta_para_ollama, 
                    dados_raspados, 
                    tipo_consulta="comparacao",
                    classificacao=classificacao,
                    pergunta_original=pergunta_normalizada
                )

        # ...existing code...
