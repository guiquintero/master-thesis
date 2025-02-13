import ollama

response = ollama.chat(
    model='llama3.2-vision',
    messages=[{
        'role': 'user',
        'content': 'Apenas diga o nome do animal da foto?',
        'images': ['imagem.jpg']
    }]
)

print(response.message.content)