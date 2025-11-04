import ollama
from termcolor import colored

print(colored("="*60, "cyan"))
print(colored("🧪 TESTE ISOLADO DO MODELO", "cyan", attrs=['bold']))
print(colored("="*60, "cyan"))

# Teste 1: Modelo Gemma3
print(colored("\n📊 Testando Gemma3:", "yellow"))
for i in range(5):
    try:
        response = ollama.chat(
            model="gemma3:latest",
            messages=[
                {'role': 'system', 'content': 'RESPONDA APENAS EM PORTUGUÊS. NUNCA use inglês.'},
                {'role': 'user', 'content': 'Qual a capital de Portugal? Responda em uma palavra.'}
            ],
            options={'temperature': 0.0}
        )
        
        content = response['message']['content']
        tem_ingles = any(w in content.lower() for w in ['lisbon', 'the', 'is', 'capital'])
        
        if tem_ingles:
            print(colored(f"  {i+1}. ❌ INGLÊS: {content}", "red"))
        else:
            print(colored(f"  {i+1}. ✅ PORTUGUÊS: {content}", "green"))
    except Exception as e:
        print(colored(f"  {i+1}. ❌ ERRO: {e}", "red"))

# Teste 2: Modelo Qwen (se disponível)
print(colored("\n📊 Testando Qwen2.5 (se instalado):", "yellow"))
try:
    response = ollama.chat(
        model="qwen2.5:7b",
        messages=[
            {'role': 'system', 'content': 'RESPONDA APENAS EM PORTUGUÊS.'},
            {'role': 'user', 'content': 'Qual a capital de Portugal?'}
        ],
        options={'temperature': 0.0}
    )
    print(colored(f"  ✅ Qwen2.5: {response['message']['content']}", "green"))
except:
    print(colored("  ⚠️ Qwen2.5 não instalado", "yellow"))
    print(colored("  💡 Instale: ollama pull qwen2.5:7b", "cyan"))

print(colored("\n" + "="*60, "cyan"))