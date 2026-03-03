import ollama
from termcolor import colored
import re

class OllamaWrapperSeguro:
    """
    Wrapper que FORÇA todas as respostas do Ollama em PORTUGUÊS
    Protege contra respostas em mandarim, japonês, hindu, árabe, etc.
    """
    
    def __init__(self, model="qwen2.5:7b"):
        self.model = model
        self.tentativas_maximas = 3
        
    def chat(self, messages, options=None):
        """
        Wrapper do ollama.chat que GARANTE resposta em português
        """
        if options is None:
            options = {}
        
        # FORÇAR temperatura 0 SEMPRE
        options['temperature'] = 0.0
        
        # Adicionar instrução FORTE no system prompt
        messages_protegidos = self._proteger_mensagens(messages)
        
        for tentativa in range(self.tentativas_maximas):
            try:
                response = ollama.chat(
                    model=self.model,
                    messages=messages_protegidos,
                    options=options
                )
                
                # Extrair conteúdo (compatível 0.12.9)
                content = self._extrair_conteudo(response)
                
                if not content:
                    print(colored(f"⚠️ Tentativa {tentativa+1}: Resposta vazia", "yellow"))
                    continue
                
                # VALIDAR IDIOMA
                idioma_detectado = self._detectar_idioma(content)
                
                if idioma_detectado == "portugues":
                    print(colored(f"✅ Resposta em português (tentativa {tentativa+1})", "green"))
                    return response
                else:
                    print(colored(f"❌ Tentativa {tentativa+1}: Resposta em {idioma_detectado}", "red"))
                    print(colored(f"   Amostra: {content[:100]}", "yellow"))
                    
                    # Se não é a última tentativa, tentar traduzir
                    if tentativa < self.tentativas_maximas - 1:
                        print(colored("   🔄 Tentando forçar português...", "cyan"))
                        messages_protegidos = self._mensagens_mais_forte(messages)
                    else:
                        # Última tentativa: tentar traduzir
                        print(colored("   🔄 Forçando tradução...", "cyan"))
                        content_traduzido = self._forcar_traducao(content)
                        
                        # Substituir conteúdo na resposta
                        if isinstance(response, dict) and 'message' in response:
                            response['message']['content'] = content_traduzido
                        
                        return response
                        
            except Exception as e:
                print(colored(f"❌ Erro na tentativa {tentativa+1}: {e}", "red"))
                if tentativa == self.tentativas_maximas - 1:
                    raise
        
        # Se chegou aqui, todas as tentativas falharam
        raise Exception("Não foi possível obter resposta em português após múltiplas tentativas")
    
    def _proteger_mensagens(self, messages):
        """
        Adiciona proteção FORTE contra outros idiomas
        """
        messages_protegidos = []
        
        # Substituir ou adicionar system message
        tem_system = False
        
        for msg in messages:
            if msg.get('role') == 'system':
                tem_system = True
                # Adicionar proteção ao system existente
                content_original = msg.get('content', '')
                msg['content'] = f"""🚨 OBRIGATÓRIO - LEIA COM ATENÇÃO:

1. Você DEVE responder APENAS em PORTUGUÊS (Portugal ou Brasil)
2. NUNCA use: inglês, espanhol, mandarim, japonês, hindu, árabe ou qualquer outro idioma
3. Se você responder em QUALQUER outro idioma, sua resposta será REJEITADA
4. Se não souber responder em português, diga: "Não consigo processar esta pergunta"

{content_original}

⚠️ LEMBRE-SE: APENAS PORTUGUÊS! Nenhuma palavra em outro idioma é aceitável."""
            
            messages_protegidos.append(msg)
        
        # Se não tinha system, adicionar
        if not tem_system:
            messages_protegidos.insert(0, {
                'role': 'system',
                'content': """🚨 REGRA ABSOLUTA: Responda APENAS em PORTUGUÊS (pt-PT ou pt-BR)
                
IDIOMAS PROIBIDOS:
❌ Inglês (English)
❌ Espanhol (Español)  
❌ Mandarim (中文)
❌ Japonês (日本語)
❌ Hindu (हिन्दी)
❌ Árabe (العربية)
❌ Qualquer outro idioma

✅ APENAS PORTUGUÊS é permitido.

Se você responder em outro idioma, será considerado ERRO GRAVE."""
            })
        
        return messages_protegidos
    
    def _mensagens_mais_forte(self, messages):
        """
        Versão AINDA MAIS FORTE das mensagens
        """
        messages_super_forte = []
        
        for msg in messages:
            if msg.get('role') == 'system':
                msg['content'] = """🔴🔴🔴 ATENÇÃO CRÍTICA 🔴🔴🔴

Você está configurado para responder EXCLUSIVAMENTE em PORTUGUÊS.

IDIOMAS COMPLETAMENTE PROIBIDOS:
- Inglês / English
- Espanhol / Español
- Chinês / 中文 / Chinese / Mandarim
- Japonês / 日本語 / Japanese
- Hindu / हिन्दी / Hindi
- Árabe / العربية / Arabic
- Coreano / 한국어 / Korean
- Russo / Русский / Russian
- Francês / Français / French
- Alemão / Deutsch / German

✅ ÚNICO IDIOMA PERMITIDO: PORTUGUÊS (Portugal ou Brasil)

Se você não conseguir responder em português, diga apenas:
"Desculpe, não consigo processar esta solicitação em português."

NÃO USE NENHUMA PALAVRA EM OUTRO IDIOMA."""
            
            messages_super_forte.append(msg)
        
        return messages_super_forte
    
    def _extrair_conteudo(self, response):
        """
        Extrai conteúdo da resposta (compatível 0.12.9)
        """
        if isinstance(response, dict):
            if 'message' in response and isinstance(response['message'], dict):
                return response['message'].get('content')
            elif 'content' in response:
                return response['content']
        elif isinstance(response, str):
            return response
        
        return None
    
    def _detectar_idioma(self, texto):
        """
        Detecta idioma da resposta - VERSÃO MELHORADA
        """
        # Caracteres não-latinos (CJK - Chinês/Japonês/Coreano)
        if re.search(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]', texto):
            if re.search(r'[\u4e00-\u9fff]', texto):
                return "mandarim/chines"
            elif re.search(r'[\u3040-\u309f\u30a0-\u30ff]', texto):
                return "japones"
            elif re.search(r'[\uac00-\ud7af]', texto):
                return "coreano"
        
        # Árabe
        if re.search(r'[\u0600-\u06ff]', texto):
            return "arabe"
        
        # Devanagari (Hindi/Hindu)
        if re.search(r'[\u0900-\u097f]', texto):
            return "hindi"
        
        # Cirílico (Russo)
        if re.search(r'[\u0400-\u04ff]', texto):
            return "russo"
        
        texto_lower = texto.lower()
        palavras = texto_lower.split()
        
        # Inglês
        palavras_ingles = ['the', 'is', 'are', 'was', 'were', 'have', 'has', 'had', 
                           'will', 'would', 'should', 'could', 'can', 'may', 'might',
                           'this', 'that', 'these', 'those', 'what', 'where', 'when',
                           'according', 'document', 'information', 'dose', 'species']
        ingles_count = sum(1 for p in palavras_ingles if p in palavras)
        
        # Espanhol
        palavras_espanhol = ['el', 'la', 'los', 'las', 'es', 'está', 'son', 'del', 
                             'según', 'documento', 'información', 'debe', 'puede']
        espanhol_count = sum(1 for p in palavras_espanhol if p in palavras)
        
        # Francês
        palavras_frances = ['le', 'la', 'les', 'est', 'sont', 'du', 'de', 'selon', 
                           'avec', 'dans', 'pour', 'sur']
        frances_count = sum(1 for p in palavras_frances if p in palavras)
        
        # Alemão
        palavras_alemao = ['der', 'die', 'das', 'ist', 'sind', 'und', 'mit', 
                          'nach', 'für', 'von', 'auf']
        alemao_count = sum(1 for p in palavras_alemao if p in palavras)
        
        total_palavras = len(palavras)
        if total_palavras == 0:
            return "indefinido"
        
        # Se mais de 15% são palavras estrangeiras
        if ingles_count / total_palavras > 0.15:
            return "ingles"
        if espanhol_count / total_palavras > 0.15:
            return "espanhol"
        if frances_count / total_palavras > 0.15:
            return "frances"
        if alemao_count / total_palavras > 0.15:
            return "alemao"
        
        # Verificar português
        palavras_portugues = ['o', 'a', 'os', 'as', 'de', 'do', 'da', 'dos', 'das',
                             'em', 'para', 'com', 'por', 'que', 'não', 'é', 'são',
                             'está', 'segundo', 'medicamento', 'dose']
        portugues_count = sum(1 for p in palavras_portugues if p in palavras)
        
        if portugues_count / total_palavras > 0.10:
            return "portugues"
        
        # Se chegou aqui, idioma desconhecido
        return "desconhecido"
    
    def _forcar_traducao(self, texto_estrangeiro):
        """
        Força tradução para português como último recurso
        """
        try:
            response = ollama.chat(
                model=self.model,
                messages=[
                    {
                        'role': 'system',
                        'content': 'Você é um tradutor. Traduza TUDO para PORTUGUÊS. Não adicione comentários.'
                    },
                    {
                        'role': 'user',
                        'content': f"Traduza este texto para português:\n\n{texto_estrangeiro}"
                    }
                ],
                options={'temperature': 0.0}
            )
            
            content = self._extrair_conteudo(response)
            
            # Verificar se tradução funcionou
            if self._detectar_idioma(content) == "portugues":
                print(colored("   ✅ Tradução bem-sucedida", "green"))
                return content
            else:
                print(colored("   ⚠️ Tradução falhou, usando original", "yellow"))
                return texto_estrangeiro
                
        except Exception as e:
            print(colored(f"   ❌ Erro na tradução: {e}", "red"))
            return texto_estrangeiro