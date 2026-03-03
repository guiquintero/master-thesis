# 🚀 Instruções para Executar o Sistema Veterinário

## 📋 Estrutura do Sistema

```
Testes/
├── site.html                    # Página principal da Novavet
├── consulta.html                # Interface do assistente (conecta à API)
├── api_vet.py                   # API Flask (backend)
├── temporario_MV.py             # Sistema de consulta veterinária
├── query_classifier.py          # Classificador de perguntas
├── ollama_wrapper.py            # Wrapper para Ollama
├── cao.png                      # Ícone do assistente
└── requirements.txt             # Dependências Python
```

---

## ⚙️ Configuração

### **1. Instalar Dependências**

```bash
# Criar ambiente virtual (recomendado)
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows

# Instalar dependências
pip install -r requirements.txt
```

### **2. Instalar e Configurar Ollama**

```bash
# Instalar Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Baixar o modelo (verifique qual está configurado no temporario_MV.py)
ollama pull qwen2.5:14b

# Iniciar o servidor Ollama
ollama serve
```

---

## 🚀 Executando o Sistema

### **Passo 1: Iniciar o Ollama**

Em um terminal:
```bash
ollama serve
```

Deixe este terminal aberto.

---

### **Passo 2: Iniciar a API Flask**

Em outro terminal:
```bash
cd /home/guilherme-quintero/Documents/IPB/Tese/Testes
source venv/bin/activate  # Se estiver usando venv
python api_vet.py
```

Você verá:
```
🚀 Iniciando API Sistema Veterinário...
📍 Acesse: http://localhost:5000
 * Running on http://127.0.0.1:5000
```

---

### **Passo 3: Abrir o Frontend**

Abra o navegador e acesse:
```
file:///home/guilherme-quintero/Documents/IPB/Tese/Testes/site.html
```

Ou abra o arquivo `site.html` diretamente no navegador.

---

## 🧪 Testando o Sistema

### **Teste 1: Verificar Status da API**

Acesse no navegador:
```
http://localhost:5000/api/status
```

Deve retornar:
```json
{
  "status": "online",
  "modelo": "qwen2.5:14b",
  "timestamp": 1733347200.0
}
```

---

### **Teste 2: Usar o Assistente**

1. Abra `site.html` no navegador
2. Clique no **ícone do cachorro** (canto inferior direito)
3. Você será redirecionado para `consulta.html`
4. Digite uma pergunta, por exemplo:
   - "Qual a dose do Animeloxan para suínos?"
   - "Medicamentos alternativos ao Dolocarp?"
   - "Como armazenar o Trocoxil?"

---

## 📡 Endpoints da API

### **GET `/api/status`**
Verifica se a API está online.

**Resposta:**
```json
{
  "status": "online",
  "modelo": "qwen2.5:14b",
  "timestamp": 1733347200.0
}
```

---

### **POST `/api/consulta/stream`**
Envia uma pergunta e recebe resposta via Server-Sent Events (SSE).

**Request:**
```json
{
  "pergunta": "Qual a dose do Animeloxan para suínos?"
}
```

**Response (Stream):**
```
data: {"type":"start","message":"Iniciando processamento...","timestamp":1733347200.0}

data: {"type":"log","message":"📝 Pergunta recebida: Qual a dose...","timestamp":1733347201.0}

data: {"type":"log","message":"🔍 Classificando pergunta...","timestamp":1733347202.0}

data: {"type":"response","message":"A dose do Animeloxan...","timestamp":1733347210.0}

data: {"type":"end"}
```

---

### **POST `/api/limpar_contexto`**
Limpa o histórico da conversa.

**Response:**
```json
{
  "success": true,
  "message": "Contexto limpo com sucesso"
}
```

---

## 🔧 Configurações

### **Mudar o Modelo de IA**

Edite `temporario_MV.py` (linha 48):
```python
MODELO_OLLAMA_PADRAO = "qwen2.5:14b"  # Altere aqui
```

Modelos disponíveis:
- `qwen2.5:7b` (mais rápido, menos preciso)
- `qwen2.5:14b` (balanceado - **PADRÃO**)
- `gemma3:latest`
- `deepseek-r1:8b`

---

### **Mudar a Porta da API**

Edite `api_vet.py` (última linha):
```python
app.run(debug=False, port=5000, threaded=True)  # Mude a porta aqui
```

Se mudar a porta, **atualize também** em `consulta.html`:
```javascript
const API_BASE_URL = 'http://localhost:5000';  // Mude aqui também
```

---

## 🐛 Resolução de Problemas

### **Erro: "API Offline"**

**Causa:** A API Flask não está rodando.

**Solução:**
```bash
cd /home/guilherme-quintero/Documents/IPB/Tese/Testes
python api_vet.py
```

---

### **Erro: "Ollama não encontrado"**

**Causa:** Ollama não está instalado ou não está rodando.

**Solução:**
```bash
# Instalar Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Iniciar servidor
ollama serve

# Em outro terminal, baixar modelo
ollama pull qwen2.5:14b
```

---

### **Erro: "ModuleNotFoundError: No module named 'flask'"**

**Causa:** Dependências não instaladas.

**Solução:**
```bash
pip install -r requirements.txt
```

---

### **Erro: "CORS blocked"**

**Causa:** Frontend e backend em origens diferentes.

**Solução:** Já configurado com `flask-cors`. Se persistir, use uma extensão do navegador como "CORS Unblock".

---

### **Erro: "Timeout na operação"**

**Causa:** Pergunta muito complexa ou Ollama lento.

**Solução:**
1. Use um modelo mais rápido (`qwen2.5:7b`)
2. Simplifique a pergunta
3. Aumente o timeout em `api_vet.py` (linha 195):
   ```python
   max_timeout_count = 120  # Aumentar de 60 para 120
   ```

---

## 📊 Fluxo de Dados

```
┌─────────────┐
│  site.html  │  (Página principal)
└──────┬──────┘
       │
       │ Clique no cachorro
       ▼
┌──────────────┐
│consulta.html │  (Interface do chat)
└──────┬───────┘
       │
       │ HTTP POST /api/consulta/stream
       ▼
┌──────────────┐
│  api_vet.py  │  (API Flask)
└──────┬───────┘
       │
       │ Chama métodos
       ▼
┌────────────────────┐
│ temporario_MV.py   │  (Lógica de consulta)
└──────┬─────────────┘
       │
       │ Web scraping + Ollama
       ▼
┌─────────────────┐
│   Resposta      │
└─────────────────┘
```

---

## 🌐 Para Produção (Servidor Remoto)

Se quiser rodar em um servidor remoto:

1. **Edite `api_vet.py`** (última linha):
   ```python
   app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
   ```

2. **Atualize `consulta.html`**:
   ```javascript
   const API_BASE_URL = 'http://SEU_IP_PUBLICO:5000';
   ```

3. **Configure firewall**:
   ```bash
   sudo ufw allow 5000/tcp
   ```

4. **Use Gunicorn** (mais robusto):
   ```bash
   pip install gunicorn
   gunicorn -w 4 -b 0.0.0.0:5000 api_vet:app
   ```

---

## ✅ Checklist de Funcionamento

- [ ] Ollama está rodando (`ollama serve`)
- [ ] Modelo está baixado (`ollama list`)
- [ ] API Flask está rodando (`python api_vet.py`)
- [ ] Status da API retorna "online" (`http://localhost:5000/api/status`)
- [ ] `site.html` abre no navegador
- [ ] Clique no cachorro redireciona para `consulta.html`
- [ ] `consulta.html` mostra status "API Online"
- [ ] Perguntas são enviadas e respostas aparecem

---

## 📝 Logs Úteis

### **Logs da API:**
Aparecem no terminal onde você executou `python api_vet.py`

### **Logs do Frontend:**
Aparecem no **Terminal de Logs** dentro do `consulta.html` (painel direito)

### **Logs do Ollama:**
```bash
journalctl -u ollama -f  # Se instalado como serviço
```

---

## 🎯 Próximos Passos

1. **Deploy em servidor remoto** (ver seção "Para Produção")
2. **Adicionar autenticação** (se necessário)
3. **Configurar HTTPS** com certificado SSL
4. **Adicionar rate limiting** para proteger a API
5. **Monitoramento** com ferramentas como Sentry

---

**Desenvolvido por:** Guilherme Quintero  
**Data:** Dezembro 2025  
**Versão:** 1.0
