import json
import ollama
import time
import os
import hashlib
from termcolor import colored
import argparse

# Configurações
MODELO_PADRAO = "llama3.2-vision:latest"  # Modelo mais rápido e ainda eficiente
CACHE_DIR = "resposta_cache"

# Criar diretório de cache para respostas
os.makedirs(CACHE_DIR, exist_ok=True)

def gerar_hash(texto):
    """Gera um hash único para uma consulta"""
    return hashlib.md5(texto.encode('utf-8')).hexdigest()

def carregar_cache(hash_consulta):
    """Tenta carregar uma resposta do cache"""
    arquivo_cache = os.path.join(CACHE_DIR, f"{hash_consulta}.json")
    if os.path.exists(arquivo_cache):
        try:
            with open(arquivo_cache, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                return cache.get('resposta')
        except:
            return None
    return None

def salvar_cache(hash_consulta, resposta):
    """Salva uma resposta no cache"""
    arquivo_cache = os.path.join(CACHE_DIR, f"{hash_consulta}.json")
    with open(arquivo_cache, 'w', encoding='utf-8') as f:
        json.dump({'resposta': resposta}, f, ensure_ascii=False, indent=2)

def preparar_contexto(dados, pergunta):
    """Prepara um contexto reduzido relevante para a pergunta"""
    # Esta função analisa o conteúdo e extrai apenas partes relevantes
    # para reduzir o tamanho do contexto enviado para o modelo
    
    palavras_chave = set(palavra.lower() for palavra in pergunta.split() if len(palavra) > 3)
    contexto_relevante = []
    
    for item in dados:
        conteudo_relevante = False
        trecho_relevante = {}
        
        # Verificar conteúdo HTML
        if "conteudo" in item and item["conteudo"]:
            texto = item["conteudo"].lower()
            if any(palavra in texto for palavra in palavras_chave):
                conteudo_relevante = True
                trecho_relevante["conteudo"] = item["conteudo"]
        
        # Verificar conteúdo PDF
        if "pdf_conteudo" in item and item["pdf_conteudo"]:
            pdf_relevante = []
            for secao in item["pdf_conteudo"]:
                texto_secao = secao.lower()
                if any(palavra in texto_secao for palavra in palavras_chave):
                    pdf_relevante.append(secao)
            
            if pdf_relevante:
                conteudo_relevante = True
                trecho_relevante["pdf_conteudo"] = pdf_relevante
        
        # Se encontrou conteúdo relevante, adicionar à lista
        if conteudo_relevante:
            if "url" in item:
                trecho_relevante["url"] = item["url"]
            contexto_relevante.append(trecho_relevante)
    
    # Se não encontrou nada relevante, retornar o contexto completo
    if not contexto_relevante:
        return dados
    
    return contexto_relevante

def consultar_ollama(prompt, modelo=MODELO_PADRAO, temperatura=0.2):
    """Consulta o Ollama com um prompt"""
    try:
        resposta = ollama.chat(
            model=modelo,
            messages=[
                {
                    'role': 'system',
                    'content': 'Você é um assistente médico veterinário que fornece informações precisas baseadas apenas no contexto fornecido.'
                },
                {
                    'role': 'user',
                    'content': prompt,
                }
            ],
            options={
                'temperature': temperatura
            }
        )
        return resposta['message']['content']
    except Exception as e:
        return f"Erro ao consultar o modelo: {str(e)}"

def main():
    # Configurar argumentos de linha de comando
    parser = argparse.ArgumentParser(description="Consulta informações veterinárias usando LLM local.")
    parser.add_argument("--arquivo", default="conteudo_completo.json", help="Arquivo JSON com os dados")
    parser.add_argument("--modelo", default=MODELO_PADRAO, help=f"Modelo Ollama a ser usado (padrão: {MODELO_PADRAO})")
    parser.add_argument("--temperatura", type=float, default=0.2, help="Temperatura para geração de resposta (0.0-1.0)")
    parser.add_argument("--sem-cache", action="store_true", help="Ignorar o cache de respostas")
    args = parser.parse_args()
    
    # Verificar se o arquivo existe
    if not os.path.exists(args.arquivo):
        print(colored(f"Erro: O arquivo {args.arquivo} não foi encontrado.", "red"))
        return
    
    # Carregar o arquivo JSON
    try:
        with open(args.arquivo, "r", encoding="utf-8") as f:
            dados = json.load(f)
    except Exception as e:
        print(colored(f"Erro ao carregar o arquivo JSON: {e}", "red"))
        return
    
    print(colored(f"Arquivo carregado com sucesso! ({len(dados)} entradas)", "green"))
    
    # Loop de perguntas
    while True:
        pergunta = input(colored("\nDigite sua pergunta (ou 'sair' para encerrar): ", "cyan"))
        
        if pergunta.lower() in ['sair', 'exit', 'quit']:
            break
        
        if not pergunta.strip():
            continue
        
        start_time = time.perf_counter()
        
        # Verificar cache primeiro
        hash_consulta = gerar_hash(f"{pergunta}_{args.modelo}_{args.temperatura}")
        if not args.sem_cache:
            resposta_cache = carregar_cache(hash_consulta)
            if resposta_cache:
                print(colored("\nResposta (do cache):\n", "green"))
                print(resposta_cache)
                end_time = time.perf_counter()
                print(colored(f"\nTempo decorrido: {(end_time - start_time):.4f} segundos (cache)", "yellow"))
                continue
        
        # Preparar contexto relevante para a pergunta
        print(colored("Analisando dados relevantes...", "yellow"))
        contexto_relevante = preparar_contexto(dados, pergunta)
        
        # Limitar o contexto para não exceder limites do modelo
        contexto_json = json.dumps(contexto_relevante, ensure_ascii=False)
        print(colored(f"Contexto preparado: {len(contexto_json)} caracteres", "yellow"))
        
        # Preparar prompt
        prompt = f"""
Com base APENAS no seguinte contexto sobre medicamentos veterinários:

```
{contexto_json}
```

Responda à pergunta: "{pergunta}"

Se a informação não estiver no contexto fornecido, responda 'Não encontrei informações sobre isso no material disponível'.
Cite as fontes (URLs) se disponíveis no material.
"""
        
        # Consultar o Ollama
        print(colored("Consultando modelo...", "yellow"))
        resposta = consultar_ollama(prompt, modelo=args.modelo, temperatura=args.temperatura)
        
        # Salvar no cache
        if not args.sem_cache:
            salvar_cache(hash_consulta, resposta)
        
        # Exibir a resposta
        print(colored("\nResposta:\n", "green"))
        print(resposta)
        
        end_time = time.perf_counter()
        print(colored(f"\nTempo decorrido: {(end_time - start_time):.4f} segundos", "yellow"))

if __name__ == "__main__":
    main()