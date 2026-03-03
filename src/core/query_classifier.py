# query_classifier.py - Versão melhorada COM SUPORTE A ALTERNATIVAS
import json
import re
import ollama
from termcolor import colored
from src.utils.ollama_wrapper import OllamaWrapperSeguro

class QueryClassifier:
    def __init__(self, model="gemma3:latest"):
        self.model = model
        self.ollama_seguro = OllamaWrapperSeguro(model=model)

    def _extrair_medicamento_referencia_completo(self, query):
        """
        Extrai o medicamento de referência de perguntas sobre alternativas/substitutos
        VERSÃO MELHORADA - Suporta nomes compostos com números, dosagens e símbolos
        """
        query_lower = query.lower()
        
        # Padrões específicos para alternativas/substitutos
        # ATUALIZADO: Aceita números, %, hífens, pontos
        padroes_alternativa = [
            # "alternativo ao MEDICAMENTO" (com dosagem/número)
            r'alternativ[oa]s?\s+(?:ao|para|do)\s+((?:[A-Z][a-zà-ú]+(?:\s+|-))*[A-Z][A-Z\-]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+)*(?:\s+\d+(?:\.\d+)?%?(?:\s*(?:mg|ml|g|%|PÓ))?)*)',
            
            # "substituto do MEDICAMENTO"
            r'substitut[oa]s?\s+(?:ao|para|do)\s+((?:[A-Z][a-zà-ú]+(?:\s+|-))*[A-Z][A-Z\-]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+)*(?:\s+\d+(?:\.\d+)?%?(?:\s*(?:mg|ml|g|%|PÓ))?)*)',
            
            # "equivalente ao MEDICAMENTO"
            r'equivalente\s+(?:ao|para|do)\s+((?:[A-Z][a-zà-ú]+(?:\s+|-))*[A-Z][A-Z\-]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+)*(?:\s+\d+(?:\.\d+)?%?(?:\s*(?:mg|ml|g|%|PÓ))?)*)',
            
            # "medicamento alternativo ao MEDICAMENTO"
            r'medicamento\s+alternativ[oa]\s+(?:ao|para|do)\s+((?:[A-Z][a-zà-ú]+(?:\s+|-))*[A-Z][A-Z\-]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+)*(?:\s+\d+(?:\.\d+)?%?(?:\s*(?:mg|ml|g|%|PÓ))?)*)',
            
            # "MEDICAMENTO alternativo" (inverte ordem)
            r'((?:[A-Z][a-zà-ú]+(?:\s+|-))*[A-Z][A-Z\-]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+)*(?:\s+\d+(?:\.\d+)?%?(?:\s*(?:mg|ml|g|%|PÓ))?)*)\s+alternativ[oa]',
        ]
        
        # Tentar cada padrão em ordem de prioridade
        for padrao in padroes_alternativa:
            match = re.search(padrao, query, re.IGNORECASE)
            if match:
                medicamento = match.group(1).strip()
                print(colored(f"   ✓ Medicamento de referência extraído: '{medicamento}'", "green"))
                return medicamento
        
        # Fallback melhorado: procurar sequência com maiúsculas, números, hífens, %
        # Padrão: Uma ou mais palavras começando com maiúscula + opcionalmente números/símbolos
        padrao_geral = r'\b([A-ZÀ-Ú][A-ZÀ-Úa-zà-ú\-]+(?:\s+[A-ZÀ-Ú][A-ZÀ-Úa-zà-ú\-]+)*(?:\s+(?:PÓ|SOLUÇÃO|COMPRIMIDO|INJETÁVEL))?(?:\s+\d+(?:\.\d+)?%?(?:\s*(?:mg|ml|g|%))?)*)'
        
        matches = re.findall(padrao_geral, query)
        
        # Filtrar palavras comuns
        palavras_ignorar = ['Que', 'Qual', 'Para', 'Como', 'Quais', 'Onde', 'Quando', 'Espécie', 'Espécies']
        
        for match in matches:
            if match not in palavras_ignorar and len(match) > 2:
                print(colored(f"   ✓ Medicamento genérico extraído: '{match}'", "green"))
                return match
        
        return None

    def classify_and_extract(self, query):
        
        # ========== PRÉ-PROCESSAMENTO: DETECTAR ALTERNATIVAS ==========
        query_lower = query.lower()
        
        # Palavras-chave que indicam ALTERNATIVA/SUBSTITUTO
        palavras_alternativa = ['alternativ', 'substitut', 'equivalente', 'similar']
        
        is_pergunta_alternativa = any(palavra in query_lower for palavra in palavras_alternativa)
        
        if is_pergunta_alternativa:
            print(colored("🔍 Pergunta sobre ALTERNATIVA/SUBSTITUTO detectada!", "yellow"))
            
            # Extrair medicamento de referência
            medicamento_ref = self._extrair_medicamento_referencia_completo(query)
            
            if medicamento_ref:
                print(colored(f"   ✓ Medicamento de referência: {medicamento_ref}", "green"))
                
                # Extrair espécie (se houver)
                especie = self._extrair_especie_query(query)
                
                # Construir termo de busca otimizado
                termo_busca = medicamento_ref
                if especie:
                    termo_busca = f"{medicamento_ref} {especie}"
                
                # RETORNAR DIRETAMENTE (pular Ollama para evitar confusão)
                resultado = {
                    "categoria": "comparacao",
                    "entidades": {
                        "termo_busca": medicamento_ref,  # Medicamento de referência
                        "pergunta_ollama": query,
                        "substancia_ativa": medicamento_ref,  # Será usado para extração do princípio ativo
                        "especie_alvo": especie,
                        "forma_farmaceutica": self._extrair_forma_farmaceutica_query(query)
                    }
                }
                
                print(colored(f"   ✅ Classificação direta como comparação", "green"))
                print(colored(f"   📋 Termo busca: {termo_busca}", "cyan"))
                
                return resultado
            else:
                print(colored("   ⚠️ Não conseguiu extrair medicamento de referência", "yellow"))
                # Continuar com fluxo normal do Ollama
        
        # ========== FLUXO NORMAL (quando não é alternativa OU não conseguiu extrair) ==========
        
        prompt = f"""
        ANALISE ESTA PERGUNTA SOBRE MEDICAMENTOS VETERINÁRIOS:

        ⚠️ OBRIGATÓRIO: Responda APENAS em PORTUGUÊS (pt-PT ou pt-BR)

        PERGUNTA: "{query}"

        CATEGORIAS:
        - 'medicamento': Perguntas sobre informações ESPECÍFICAS de UM ÚNICO medicamento
        - 'comparacao': Perguntas sobre COMPARAR ou LISTAR VÁRIOS medicamentos

        REGRAS IMPORTANTES:
        1. Se pergunta tem "o medicamento NOME" ou "do medicamento NOME" -> SEMPRE é 'medicamento'
        2. Se a pergunta contém "mesmo princípio ativo" -> SEMPRE é 'comparacao'
        3. ⚠️ CRÍTICO: Se a pergunta contém "alternativo", "alternativa", "substituto", "equivalente" -> SEMPRE é 'comparacao'
        4. ⚠️ Para perguntas de alternativa: termo_busca DEVE ser o NOME DO MEDICAMENTO DE REFERÊNCIA (aquele que o usuário quer substituir)
        5. ⚠️ NUNCA use "alternativo" ou "alternativa" como termo_busca - use o NOME DO MEDICAMENTO
        6. ⚠️ IMPORTANTE: "Para que espécies o medicamento X" é 'medicamento', mas "Que medicamentos para espécie Y" é 'comparacao'

        EXEMPLOS CORRETOS:

        Pergunta: "Que medicamentos alternativos ao Trocoxil 75 mg para cães?"
        {{
            "categoria": "comparacao",
            "entidades": {{
                "termo_busca": "Trocoxil 75 mg cães",  ← CORRETO: nome do medicamento
                "pergunta_ollama": "Medicamentos alternativos ao Trocoxil 75 mg para cães",
                "substancia_ativa": "Trocoxil 75 mg",
                "especie_alvo": "cães",
                "forma_farmaceutica": ""
            }}
        }}

        Pergunta: "Medicamento alternativo ao Rimadyl?"
        {{
            "categoria": "comparacao",
            "entidades": {{
                "termo_busca": "Rimadyl",  ← CORRETO: nome do medicamento
                "pergunta_ollama": "Medicamento alternativo ao Rimadyl",
                "substancia_ativa": "Rimadyl",
                "especie_alvo": "",
                "forma_farmaceutica": ""
            }}
        }}

        EXEMPLOS ERRADOS (NÃO FAÇA ISSO):

        ❌ "termo_busca": "alternativo"  ← ERRADO
        ❌ "termo_busca": "medicamento alternativo"  ← ERRADO
        ❌ "substancia_ativa": "alternativo"  ← ERRADO

        PARA A PERGUNTA ACIMA, analise e responda APENAS com JSON no formato:

        {{
            "categoria": "medicamento|comparacao|erro",
            "entidades": {{
                "termo_busca": "string (NOME DO MEDICAMENTO ou SUBSTÂNCIA ATIVA, NUNCA 'alternativo' + ESPECIE ALVO + ESPECIE ALVO)",
                "pergunta_ollama": "pergunta específica para o Ollama",
                "substancia_ativa": "string (se aplicável)",
                "especie_alvo": "string (se aplicável)", 
                "forma_farmaceutica": "string (se aplicável)"
            }}
        }}

        AGORA ANALISE ESTA PERGUNTA: "{query}"
        """

        try:
            response = self.ollama_seguro.chat(
                messages=[
                    {
                        'role': 'system',
                        'content': 'Você é um classificador de perguntas veterinárias. Responda SEMPRE em português. Para perguntas sobre alternativas/substitutos, o termo_busca DEVE ser o NOME DO MEDICAMENTO, nunca a palavra "alternativo".'
                    },
                    {
                        'role': 'user',
                        'content': prompt
                    }
                ],
                options={'temperature': 0.0}
            )
            
            # Extrair resposta
            content = None
            if isinstance(response, dict):
                if 'message' in response and isinstance(response['message'], dict):
                    content = response['message'].get('content')
                elif 'content' in response:
                    content = response['content']
            elif isinstance(response, str):
                content = response
            
            if not content:
                print(colored(f"❌ Estrutura inesperada do classificador", "red"))
                return self._classificacao_fallback(query)
            
            # Extrair JSON
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                result = json.loads(json_str)
                
                # ========== VALIDAÇÃO ESPECIAL PARA ALTERNATIVAS ==========
                if is_pergunta_alternativa:
                    termo_busca = result.get('entidades', {}).get('termo_busca', '').lower()
                    
                    # Se termo_busca é "alternativo" ou similar, CORRIGIR
                    if termo_busca in ['alternativo', 'alternativa', 'substituto', 'equivalente']:
                        print(colored(f"⚠️ Ollama retornou termo_busca errado: '{termo_busca}'", "yellow"))
                        print(colored(f"   🔧 Corrigindo...", "cyan"))
                        
                        # Tentar extrair medicamento manualmente
                        medicamento_correto = self._extrair_medicamento_referencia_completo(query)
                        
                        if medicamento_correto:
                            result['entidades']['termo_busca'] = medicamento_correto
                            result['entidades']['substancia_ativa'] = medicamento_correto
                            result['categoria'] = 'comparacao'
                            print(colored(f"   ✅ Corrigido para: {medicamento_correto}", "green"))
                        else:
                            print(colored(f"   ❌ Não conseguiu corrigir - usando fallback", "red"))
                            return self._classificacao_fallback(query)
                
                # Validação geral
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
        
        # ========== PRIORIDADE 0: ALTERNATIVAS/SUBSTITUTOS ==========
        palavras_alternativa = ['alternativ', 'substitut', 'equivalente', 'similar']
        
        if any(palavra in query_lower for palavra in palavras_alternativa):
            print(colored("🔧 Fallback: Detectada pergunta sobre alternativa", "yellow"))
            
            medicamento_ref = self._extrair_medicamento_referencia_completo(query)
            
            if medicamento_ref:
                especie = self._extrair_especie_query(query)
                
                return {
                    "categoria": "comparacao",
                    "entidades": {
                        "termo_busca": medicamento_ref,
                        "pergunta_ollama": query,
                        "substancia_ativa": medicamento_ref,
                        "especie_alvo": especie,
                        "forma_farmaceutica": self._extrair_forma_farmaceutica_query(query)
                    }
                }
        
        # ========== FLUXO NORMAL (mantido igual) ==========
        
        # PRIORIDADE 1: Verificar se é pergunta sobre medicamento ESPECÍFICO
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
        
        # PRIORIDADE 2: Palavras-chave FORTES para comparação
        palavras_comparacao_fortes = [
            "que medicamentos", "quais medicamentos", "liste medicamentos",
            "medicamentos com", "medicamentos contendo", "medicamentos que",
            "mesmo princípio ativo", "mesma substância"
        ]
        
        tem_comparacao = any(palavra in query_lower for palavra in palavras_comparacao_fortes)
        
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
        
        # PRIORIDADE 3: Perguntas específicas
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
        
        # Fallback final
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
        """
        Tenta extrair o nome do medicamento da query
        VERSÃO MELHORADA - Suporta nomes compostos complexos
        """
        
        # Padrão: Começa com maiúscula, pode ter hífens, espaços, números, %
        padrao_medicamento = r'\b([A-ZÀ-Ú][A-ZÀ-Úa-zà-ú\-]+(?:\s+[A-ZÀ-Ú][A-ZÀ-Úa-zà-ú\-]+)*(?:\s+(?:PÓ|SOLUÇÃO|COMPRIMIDO|INJETÁVEL))?(?:\s+\d+(?:\.\d+)?%?(?:\s*(?:mg|ml|g|%))?)*)'
        
        matches = re.findall(padrao_medicamento, query)
        
        # Filtrar palavras comuns
        palavras_ignorar = ['Para', 'Com', 'Que', 'Qual', 'Como', 'Quais', 'Onde', 'Quando', 
                        'Espécie', 'Espécies', 'Animal', 'Animais', 'Medicamento', 'Medicamentos']
        
        for match in matches:
            if match not in palavras_ignorar and len(match) > 2:
                print(colored(f"   ✓ Medicamento extraído: '{match}'", "cyan"))
                return match
        
        # Fallback antigo (mais simples)
        palavras = query.split()
        for palavra in palavras:
            if (palavra and palavra[0].isupper() and 
                len(palavra) > 2 and palavra not in palavras_ignorar):
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
