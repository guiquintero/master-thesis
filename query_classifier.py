# query_classifier.py - Versão melhorada
import json
import re
import ollama
from termcolor import colored

class QueryClassifier:
    def __init__(self, model="phi3:mini"):
        self.model = model

    def classify_and_extract(self, query):
        prompt = f"""
        ANALISE ESTA PERGUNTA SOBRE MEDICAMENTOS VETERINÁRIOS:

        PERGUNTA: "{query}"

        CATEGORIAS:
        - 'medicamento': Perguntas sobre informações ESPECÍFICAS de UM ÚNICO medicamento
        - 'comparacao': Perguntas sobre COMPARAR ou LISTAR VÁRIOS medicamentos

        EXEMPLOS DE 'medicamento':
        - Informações sobre dose, administração, armazenamento, composição, fabricante
        - Perguntas sobre características específicas de um medicamento
        - Ex: "Qual a dose do X?", "Como armazenar Y?", "Para que serve Z?"

        EXEMPLOS DE 'comparacao':
        - Perguntas sobre "mesmo princípio ativo", "alternativas", "medicamentos similares"
        - Listagem de medicamentos com determinada substância, forma farmacêutica ou espécie
        - Ex: "Que medicamentos com princípio ativo X?", "Alternativas ao medicamento Y?"

        REGRAS IMPORTANTES:
        1. Se a pergunta contém "mesmo princípio ativo" -> SEMPRE é 'comparacao'
        2. Se a pergunta contém "alternativo" ou "alternativa" -> SEMPRE é 'comparacao'  
        3. Se pergunta sobre características de UM medicamento -> 'medicamento'
        4. Se pergunta sobre LISTAR/COMPARAR VÁRIOS medicamentos -> 'comparacao'
        5. Os únicos termos que podem ser usados como 'termo_busca' são as substancia ativa, nome dos medicamentos, especie de animais e forma farmaceutica

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
                "pergunta_ollama": "Quais são as espécies alvo do medicamento Animeloxan",
                "substancia_ativa": "Animeloxan",
                "especie_alvo": "",
                "forma_farmaceutica": ""
            }}
        }}

        {{
            "categoria": "medicamento", 
            "entidades": {{
                "termo_busca": "Meloxicam",
                "pergunta_ollama": "Medicamento contendo Meloxicam indicado para suínos",
                "substancia_ativa": "Meloxicam", 
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
            "categoria": "medicamento",
            "entidades": {{
                "termo_busca": "Dexinjet 2 mg/ml",
                "pergunta_ollama": "Dose indicada do medicamento Dexinjet 2 mg/ml em suínos (ou outra espécie pecuária)",
                "substancia_ativa": "Dexinjet 2 mg/ml",
                "especie_alvo": "Suínos",
                "forma_farmaceutica": ""
            }}
        }}

        {{
            "categoria": "medicamento",
            "entidades": {{
                "termo_busca": "Acuimix",
                "pergunta_ollama": "Armazenamento do medicamento Acuimix",
                "substancia_ativa": "Acuimix",
                "especie_alvo": "",
                "forma_farmaceutica": ""
            }}
        }}

        AGORA ANALISE ESTA PERGUNTA: "{query}"
        """

        try:
            response = ollama.chat(
                model=self.model,
                messages=[{'role': 'user', 'content': prompt}],
                options={'temperature': 0.0}
            )
            content = response['message']['content']
            
            # Extrair JSON
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                result = json.loads(json_str)
                
                # Validação básica
                if not self._validar_resposta(result, query):
                    return self._classificacao_fallback(query)
                    
                return result
            else:
                return self._classificacao_fallback(query)
                
        except Exception as e:
            print(colored(f"Erro ao classificar: {e}", "red"))
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
            
        # Verificar regras específicas
        query_lower = query.lower()
        
        # Se a pergunta tem "mesmo princípio ativo" deve ser comparação
        if "mesmo princípio ativo" in query_lower and categoria != "comparacao":
            return False
            
        # Se a pergunta tem "alternativ" deve ser comparação
        if "alternativ" in query_lower and categoria != "comparacao":
            return False
            
        return True

    def _classificacao_fallback(self, query):
        """Classificação fallback quando o modelo falha"""
        query_lower = query.lower()
        
        # Palavras-chave para comparação
        palavras_comparacao = [
            "mesmo princípio ativo", "mesma substância", "alternativ",
            "quais medicamentos", "liste medicamentos", "outros medicamentos", 
            "medicamentos com", "medicamentos que", "comparar"
        ]
        
        # Palavras-chave para medicamento
        palavras_medicamento = [
            "dose", "armazenamento", "composição", "fabricante", "reações",
            "administração", "intervalos", "validade", "indicado para",
            "para que serve", "como usar"
        ]
        
        # Verificar se é comparação
        if any(palavra in query_lower for palavra in palavras_comparacao):
            # Tentar extrair a substância ativa
            substancia = self._extrair_substancia_query(query)
            return {
                "categoria": "comparacao",
                "entidades": {
                    "termo_busca": substancia,
                    "pergunta_ollama": query,
                    "substancia_ativa": substancia,
                    "especie_alvo": self._extrair_especie_query(query),
                    "forma_farmaceutica": self._extrair_forma_farmaceutica_query(query)
                }
            }
        
        # Se não, assume medicamento
        medicamento = self._extrair_medicamento_query(query)
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

    def _extrair_medicamento_query(self, query):
        """Tenta extrair o nome do medicamento da query"""
        # Padrões para encontrar medicamentos (palavras com maiúscula)
        palavras = query.split()
        for palavra in palavras:
            if (palavra and palavra[0].isupper() and 
                len(palavra) > 2 and not palavra.lower() in ['para', 'com', 'que', 'qual']):
                return palavra
        return "medicamento"

    def _extrair_substancia_query(self, query):
        """Tenta extrair substância ativa da query"""
        # Padrões comuns
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
                   'galinhas', 'caprinos', 'ovelhas', 'ovinos', 'coelhos']
        
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

if __name__ == "__main__":
    classifier = QueryClassifier()
    
    # Testes
    test_queries = [
        "Que medicamentos existem com o mesmo princípio ativo que o medicamento Vetmedin?",
        "Qual a dose do Animeloxan para suínos?",
        "Que medicamentos com butorfanol existem para gatos?",
        "Como armazenar o Maxy?",
        "Alternativas ao Trocoxil para cães"
    ]
    
    for query in test_queries:
        print(f"\n{'='*50}")
        print(f"Pergunta: {query}")
        resultado = classifier.classify_and_extract(query)
        print(f"Resultado: {json.dumps(resultado, indent=2, ensure_ascii=False)}")