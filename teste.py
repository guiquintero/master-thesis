import json
import ollama
import time

# Carregar o arquivo JSON
with open("dados_dgav_final.json", "r", encoding="utf-8") as f:
    dados = json.load(f)

# Criar um prompt
pergunta = input("Digite sua pergunta: ")
start_time = time.perf_counter()
contexto = json.dumps(dados, ensure_ascii=False)

prompt = f"Com base somente em: {contexto}, seja direto e responda {pergunta}. Se a informação não estiver no conteúdo, responda 'Resposta não encontrada'."

# Interagir com o Ollama
resposta = ollama.chat(model='llama3.2-vision:latest', messages=[
  {
    'role': 'user',
    'content': prompt,
  },
])

# Processar a resposta
print(resposta['message']['content'])
print(resposta['content'])

end_time = time.perf_counter()
print(f"Tempo decorrido: {(end_time - start_time):.4f} segundos")