# query_classifier.py - Versão melhorada COM SUPORTE A ALTERNATIVAS
import json
import re
import ollama
from termcolor import colored
from ollama_wrapper import OllamaWrapperSeguro

class QueryClassifier:
    def __init__(self, model="gemma3:latest"):
        self.model = model
        self.ollama_seguro = OllamaWrapperSeguro(model=model)

    def classify_and_extract(self, query):
        prompt = f"""
        ANALISE ESTA PERGUNTA SOBRE MEDICAMENTOS VETERINÁRIOS:

        ⚠️ OBRIGATÓRIO: Responda APENAS em PORTUGUÊS (pt-PT ou pt-BR)
        ⚠️ NUNCA use inglês, espanhol ou outros idiomas
        ⚠️ Se você responder em outro idioma, será considerado ERRO


        PERGUNTA: "{query}"

        CATEGORIAS:
        - 'medicamento': Perguntas sobre informações ESPECÍFICAS de UM ÚNICO medicamento
        - 'comparacao': Perguntas sobre COMPARAR ou LISTAR VÁRIOS medicamentos

        EXEMPLOS DE 'medicamento':
        - Informações sobre dose, administração, armazenamento, composição, fabricante DE UM MEDICAMENTO ESPECÍFICO nomeado
        - Perguntas sobre características, espécies-alvo, reações adversas de um medicamento JÁ IDENTIFICADO pelo nome
        - Ex: "Qual a dose do Animeloxan?", "Para que espécies está indicado o medicamento Rimadyl?", "Como armazenar o Vetmedin?"
        - Ex: "Quais os intervalos de segurança do Maxy?", "Que reações adversas pode apresentar o Suispirin?"

        EXEMPLOS DE 'comparacao':
        - Perguntas sobre "mesmo princípio ativo", "alternativas", "medicamentos similares"
        - Perguntas sobre "medicamento alternativo", "substituto", "equivalente"
        - LISTAGEM/BUSCA de medicamentos (PLURAL) com determinada substância, forma farmacêutica ou espécie
        - Perguntas que começam com "Que medicamentos..." (PLURAL), "Quais medicamentos...", "Liste medicamentos..."
        - Ex: "Que medicamentos com princípio ativo X?", "Quais medicamentos para suínos?", "Medicamentos contendo Meloxicam"

        REGRAS IMPORTANTES:
        1. Se pergunta tem "o medicamento NOME" ou "do medicamento NOME" -> SEMPRE é 'medicamento' (pergunta sobre medicamento específico)
        2. Se a pergunta contém "mesmo princípio ativo" -> SEMPRE é 'comparacao'
        3. Se a pergunta contém "alternativo", "alternativa", "substituto", "equivalente" -> SEMPRE é 'comparacao'  
        4. Se pergunta começa com "Que medicamentos" (PLURAL), "Quais medicamentos", "Liste medicamentos" -> SEMPRE é 'comparacao'
        5. Se pergunta sobre "medicamentos contendo X", "medicamentos com X" (PLURAL) -> SEMPRE é 'comparacao'
        6. Se pergunta é sobre dose, armazenamento, composição, espécies-alvo, reações DE UM medicamento nomeado -> 'medicamento'
        7. Se pergunta sobre LISTAR/COMPARAR/BUSCAR VÁRIOS medicamentos -> 'comparacao'
        8. Os únicos termos que podem ser usados como 'termo_busca' são: substancia ativa, nome dos medicamentos, espécie de animais e forma farmacêutica
        9. IMPORTANTE: "Para que espécies o medicamento X" é 'medicamento', mas "Que medicamentos para espécie Y" é 'comparacao'

        PARA A PERGUNTA ACIMA, analise e responda APENAS com JSON no formato:

        {{
            "categoria": "medicamento|comparacao|erro",
            "entidades": {{
                "termo_busca": "string para busca no site (mais relevante)",
                "pergunta_ollama": "pergunta específica para o Ollama",
                "substancia_ativa": "string (se aplicável)",
                "especie_alvo": "string (se aplicável)", 
                "forma_farmaceutica": "string (se aplicável)"
            }}
        }}

        EXEMPLOS DE RESPOSTA:

        {{
            "categoria": "medicamento",
            "entidades": {{
                "termo_busca": "Animeloxan",
                "pergunta_ollama": "Para que espécies está indicado o medicamento Animeloxan",
                "substancia_ativa": "Animeloxan",
                "especie_alvo": "",
                "forma_farmaceutica": ""
            }}
        }}

        {{
            "categoria": "comparacao",
            "entidades": {{
                "termo_busca": "Meloxicam suínos",
                "pergunta_ollama": "Que medicamento contendo o princípio ativo Meloxicam podem ser administrados a suínos",
                "substancia_ativa": "Meloxicam",
                "especie_alvo": "Suínos",
                "forma_farmaceutica": ""
            }}
        }}

        {{
            "categoria": "comparacao",
            "entidades": {{
                "termo_busca": "Animeloxan",
                "pergunta_ollama": "Que medicamentos com o mesmo princípio ativo que o Animeloxan",
                "substancia_ativa": "Animeloxan",
                "especie_alvo": "",
                "forma_farmaceutica": ""
            }}
        }}

        {{
            "categoria": "comparacao",
            "entidades": {{
                "termo_busca": "Trocoxil 75",
                "pergunta_ollama": "Medicamentos alternativos ao Trocoxil 75 para cães",
                "substancia_ativa": "Trocoxil 75",
                "especie_alvo": "cães",
                "forma_farmaceutica": ""
            }}
        }}

        {{
            "categoria": "medicamento",
            "entidades": {{
                "termo_busca": "Animeloxan",
                "pergunta_ollama": "Qual a dose do medicamento Animeloxan para suínos",
                "substancia_ativa": "Animeloxan",
                "especie_alvo": "Suínos",
                "forma_farmaceutica": ""
            }}
        }}

        {{
            "categoria": "comparacao",
            "entidades": {{
                "termo_busca": "Butorfanol gatos",
                "pergunta_ollama": "Que medicamentos com princípio ativo butorfanol indicado para gatos",
                "substancia_ativa": "Butorfanol",
                "especie_alvo": "Gatos", 
                "forma_farmaceutica": ""
            }}
        }}
        
        {{
            "categoria": "medicamento",
            "entidades": {{
                "termo_busca": "Dexinjet 2 mg/ml",
                "pergunta_ollama": "Dose indicada do medicamento Dexinjet 2 mg/ml em suínos",
                "substancia_ativa": "Dexinjet 2 mg/ml",
                "especie_alvo": "Suínos",
                "forma_farmaceutica": ""
            }}
        }}

        AGORA ANALISE ESTA PERGUNTA: "{query}"
        """

        try:
            # SUBSTITUIR: ollama.chat -> self.ollama_seguro.chat
            response = self.ollama_seguro.chat(
                messages=[
                    {
                        'role': 'system',
                        'content': 'Você é um classificador de perguntas veterinárias. Responda SEMPRE em português. NUNCA em outra língua.'
                    },
                    {
                        'role': 'user',
                        'content': prompt
                    }
                ],
                options={'temperature': 0.0}
            )
            
            # VALIDAR RESPOSTA (compatível 0.12.9)
            content = None
            
            if isinstance(response, dict):
                if 'message' in response and isinstance(response['message'], dict):
                    content = response['message'].get('content')
                elif 'content' in response:
                    content = response['content']
            elif isinstance(response, str):
                content = response
            
            if not content:
                print(colored(f"❌ Estrutura inesperada do classificador: {type(response)}", "red"))
                return self._classificacao_fallback(query)
            
            # Extrair JSON
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                result = json.loads(json_str)
                
                if not self._validar_resposta(result, query):
                    return self._classificacao_fallback(query)
                    
                return result
            else:
                return self._classificacao_fallback(query)
                
        except Exception as e:
            print(colored(f"Erro ao classificar: {e}", "red"))
            import traceback
            traceback.print_exc()
            return self._classificacao_fallback(query)

    def _validar_resposta(self, resultado, query):
        """Valida se a resposta do classificador faz sentido"""
        if not resultado or 'categoria' not in resultado:
            return False
            
        categoria = resultado.get('categoria')
        entidades = resultado.get('entidades', {})
        
        # Verificar se a categoria é válida
        if categoria not in ['medicamento', 'comparacao', 'erro']:
            return False
            
        # Verificar se termo_busca existe
        if not entidades.get('termo_busca'):
            return False
            
        query_lower = query.lower()
        
        # REGRA 1: Se tem "o medicamento NOME" ou "do medicamento NOME" -> DEVE ser medicamento
        padrao_medicamento_especifico = r'\b(?:o|do|no|ao)\s+medicamento\s+\w+'
        if re.search(padrao_medicamento_especifico, query_lower) and categoria != "medicamento":
            print(colored(f"⚠️ Tem 'o medicamento X' mas foi classificado como {categoria}", "yellow"))
            return False
        
        # REGRA 2: Palavras FORTES que indicam COMPARAÇÃO (busca de múltiplos)
        palavras_comparacao_fortes = [
            "que medicamentos", "quais medicamentos", "liste medicamentos",
            "medicamentos com", "medicamentos contendo", "medicamentos que",
            "mesmo princípio ativo", "alternativ", "substitut", "equivalente"
        ]
        
        tem_palavra_comparacao = any(palavra in query_lower for palavra in palavras_comparacao_fortes)
        
        # EXCEÇÃO: "que medicamento" (singular) não é comparação
        if "que medicamento " in query_lower and "que medicamentos" not in query_lower:
            tem_palavra_comparacao = False
        
        if tem_palavra_comparacao and categoria != "comparacao":
            print(colored(f"⚠️ Tem palavra de comparação mas foi classificado como {categoria}", "yellow"))
            return False
        
        # REGRA 3: Perguntas sobre características de medicamento específico
        perguntas_medicamento_especifico = [
            "qual a dose", "como armazenar", "como deve ser armazenado",
            "quais os intervalos", "qual é a composição", "para que é usado",
            "que reações adversas", "em que espécies pode ser usado",
            "para que espécies", "qual a forma de administração"
        ]
        
        tem_pergunta_especifica = any(palavra in query_lower for palavra in perguntas_medicamento_especifico)
        
        # Se tem medicamento nomeado E pergunta específica, DEVE ser medicamento
        if tem_pergunta_especifica and re.search(r'\b[A-Z]\w+', query) and categoria != "medicamento":
            # Exceto se também tem palavra forte de comparação
            if not tem_palavra_comparacao:
                print(colored(f"⚠️ Pergunta específica sobre medicamento mas foi classificado como {categoria}", "yellow"))
                return False
            
        return True

    def _classificacao_fallback(self, query):
        """Classificação fallback quando o modelo falha"""
        query_lower = query.lower()
        
        # PRIORIDADE 1: Verificar se é pergunta sobre medicamento ESPECÍFICO
        # Padrões: "o medicamento X", "do medicamento Y", "medicamento Z"
        padrao_medicamento_especifico = r'\b(?:o|do|no|ao)\s+medicamento\s+(\w+)'
        match_medicamento = re.search(padrao_medicamento_especifico, query_lower)
        
        if match_medicamento:
            medicamento = match_medicamento.group(1).capitalize()
            return {
                "categoria": "medicamento",
                "entidades": {
                    "termo_busca": medicamento,
                    "pergunta_ollama": query,
                    "substancia_ativa": medicamento,
                    "especie_alvo": self._extrair_especie_query(query),
                    "forma_farmaceutica": self._extrair_forma_farmaceutica_query(query)
                }
            }
        
        # PRIORIDADE 2: Palavras-chave FORTES para comparação (PLURAL)
        palavras_comparacao_fortes = [
            "que medicamentos", "quais medicamentos", "liste medicamentos",
            "medicamentos com", "medicamentos contendo", "medicamentos que",
            "mesmo princípio ativo", "mesma substância", "alternativ",
            "substitut", "equivalente", "similar"
        ]
        
        # Se tem QUALQUER palavra forte (e não é "que medicamento" singular), É COMPARAÇÃO
        tem_comparacao = any(palavra in query_lower for palavra in palavras_comparacao_fortes)
        
        # EXCEÇÃO: "que medicamento" (singular) não é comparação
        if "que medicamento " in query_lower and "que medicamentos" not in query_lower:
            tem_comparacao = False
        
        if tem_comparacao:
            substancia = self._extrair_medicamento_referencia(query)
            especie = self._extrair_especie_query(query)
            
            termo_busca = substancia
            if especie and substancia:
                termo_busca = f"{substancia} {especie}"
            
            return {
                "categoria": "comparacao",
                "entidades": {
                    "termo_busca": termo_busca,
                    "pergunta_ollama": query,
                    "substancia_ativa": substancia,
                    "especie_alvo": especie,
                    "forma_farmaceutica": self._extrair_forma_farmaceutica_query(query)
                }
            }
        
        # PRIORIDADE 3: Perguntas específicas sobre características de medicamento
        palavras_medicamento_especifico = [
            "qual a dose", "dose indicada", "dose que deve",
            "como armazenar", "como deve ser armazenado", "armazenamento",
            "qual a forma de administração", "forma de administração",
            "quais os intervalos", "intervalos de segurança",
            "qual é a composição", "composição do",
            "para que é usado", "para que serve",
            "que reações adversas", "reações adversas",
            "em que espécies pode ser usado", "para que espécies"
        ]
        
        tem_pergunta_especifica = any(palavra in query_lower for palavra in palavras_medicamento_especifico)
        
        # Se tem pergunta específica E medicamento com maiúscula, é medicamento
        if tem_pergunta_especifica:
            medicamento = self._extrair_medicamento_query(query)
            if medicamento and medicamento != "medicamento":
                return {
                    "categoria": "medicamento",
                    "entidades": {
                        "termo_busca": medicamento,
                        "pergunta_ollama": query,
                        "substancia_ativa": medicamento,
                        "especie_alvo": self._extrair_especie_query(query),
                        "forma_farmaceutica": self._extrair_forma_farmaceutica_query(query)
                    }
                }
        
        # Fallback final: se tem medicamento com maiúscula, assumir medicamento específico
        medicamento = self._extrair_medicamento_query(query)
        if medicamento and medicamento != "medicamento":
            return {
                "categoria": "medicamento",
                "entidades": {
                    "termo_busca": medicamento,
                    "pergunta_ollama": query,
                    "substancia_ativa": medicamento,
                    "especie_alvo": self._extrair_especie_query(query),
                    "forma_farmaceutica": self._extrair_forma_farmaceutica_query(query)
                }
            }
        
        # Último recurso: comparação
        return {
            "categoria": "comparacao",
            "entidades": {
                "termo_busca": medicamento,
                "pergunta_ollama": query,
                "substancia_ativa": medicamento,
                "especie_alvo": self._extrair_especie_query(query),
                "forma_farmaceutica": self._extrair_forma_farmaceutica_query(query)
            }
        }

    def _extrair_medicamento_referencia(self, query):
        """
        Extrai o medicamento de referência ou substância para perguntas de comparação/lista
        """
        query_lower = query.lower()
        
        # Padrões para extrair substância/medicamento de referência
        padroes = [
            r"alternativ[oa]?\s+(?:ao|para|do|de)\s+([\w\s\d]+?)(?:\s+para|\s+em|\s+indicado|$)",
            r"substitut[oa]?\s+(?:ao|para|do|de)\s+([\w\s\d]+?)(?:\s+para|\s+em|\s+indicado|$)",
            r"equivalente\s+(?:ao|para|do|de)\s+([\w\s\d]+?)(?:\s+para|\s+em|\s+indicado|$)",
            r"similar\s+(?:ao|para|do)\s+([\w\s\d]+?)(?:\s+para|\s+em|\s+indicado|$)",
            r"mesmo princípio ativo\s+que\s+(?:o\s+)?(?:medicamento\s+)?([\w\s\d]+?)(?:\s+para|\s+em|\s+indicado|$)",
            r"medicamentos?\s+(?:com|contendo)\s+(?:o\s+)?(?:princípio ativo\s+)?([\w\s\d]+?)(?:\s+para|\s+podem?|\s+indicado|\s+a\s+|$)",
            r"que medicamentos?\s+(?:com|contendo)\s+([\w\s\d]+?)(?:\s+para|\s+podem?|\s+indicado|$)"
        ]
        
        for padrao in padroes:
            match = re.search(padrao, query_lower, re.IGNORECASE)
            if match:
                medicamento = match.group(1).strip()
                medicamento = re.sub(r'\s+(para|podem?|ser|indicado|a)$', '', medicamento, flags=re.IGNORECASE)
                return medicamento.strip().title()
        
        return self._extrair_medicamento_query(query)

    def _extrair_medicamento_query(self, query):
        """Tenta extrair o nome do medicamento da query"""
        palavras = query.split()
        for palavra in palavras:
            if (palavra and palavra[0].isupper() and 
                len(palavra) > 2 and not palavra.lower() in ['para', 'com', 'que', 'qual']):
                return palavra
        return "medicamento"

    def _extrair_substancia_query(self, query):
        """Tenta extrair substância ativa da query"""
        padroes = [
            r"princípio ativo\s+([\w\s]+)",
            r"substância ativa\s+([\w\s]+)", 
            r"contendo\s+([\w\s]+)",
            r"com\s+([\w\s]+)\s+princípio",
            r"com\s+([\w\s]+)\s+substância"
        ]
        
        for padrao in padroes:
            match = re.search(padrao, query, re.IGNORECASE)
            if match:
                return match.group(1).strip()
                
        return self._extrair_medicamento_query(query)

    def _extrair_especie_query(self, query):
        """Tenta extrair espécie alvo da query"""
        especies = ['suínos', 'suino', 'porcos', 'bovinos', 'vacas', 'equinos', 
                   'cavalos', 'cães', 'caes', 'cachorros', 'gatos', 'aves', 
                   'galinhas', 'caprinos', 'ovelhas', 'ovinos', 'coelhos', 'peru', 'perus']
        
        query_lower = query.lower()
        for especie in especies:
            if especie in query_lower:
                return especie.capitalize()
        return ""

    def _extrair_forma_farmaceutica_query(self, query):
        """Tenta extrair forma farmacêutica da query"""
        formas = ['comprimidos', 'comprimido', 'injetável', 'injetavel', 'solução',
                 'solucao', 'pó', 'po', 'pomada', 'creme', 'spray', 'gotas']
        
        query_lower = query.lower()
        for forma in formas:
            if forma in query_lower:
                return forma.capitalize()
        return ""

    def _classificar_automaticamente(self, query):
        """Classifica automaticamente uma query usando heurísticas simples"""
        query_lower = query.lower()
        
        # Verificar padrões de medicamento específico
        padrao_medicamento_especifico = r'\b(?:o|do|no|ao)\s+medicamento\s+\w+'
        if re.search(padrao_medicamento_especifico, query_lower):
            return "medicamento"
        
        # Palavras-chave fortes para comparação
        palavras_comparacao = [
            "que medicamentos", "quais medicamentos", "liste medicamentos",
            "medicamentos com", "medicamentos contendo", "medicamentos que",
            "mesmo princípio ativo", "alternativ", "substitut", "equivalente"
        ]
        
        if any(palavra in query_lower for palavra in palavras_comparacao):
            # Exceção: "que medicamento" (singular) não é comparação
            if "que medicamento " in query_lower and "que medicamentos" not in query_lower:
                return "medicamento"
            return "comparacao"
        
        # Perguntas específicas sobre características de medicamento
        perguntas_especificas = [
            "qual a dose", "como armazenar", "como deve ser armazenado",
            "quais os intervalos", "qual é a composição", "para que é usado",
            "que reações adversas", "em que espécies pode ser usado",
            "para que espécies", "qual a forma de administração"
        ]
        
        tem_pergunta_especifica = any(palavra in query_lower for palavra in perguntas_especificas)
        
        # Se tem pergunta específica E medicamento com maiúscula, é medicamento
        if tem_pergunta_especifica and re.search(r'\b[A-Z]\w+', query):
            return "medicamento"
        
        # Default: se menciona um medicamento específico, é medicamento
        if re.search(r'\b[A-Z][a-z]{2,}', query):
            return "medicamento"
        
        return "comparacao"
