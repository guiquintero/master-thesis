# cliente_api_vet.py - CORRIGIDO
from flask import Flask, render_template_string, request, jsonify, Response
from flask_cors import CORS
import requests
import json
import time

app = Flask(__name__)
CORS(app)

class ClienteAPIVeterinaria:
    def __init__(self, base_url="http://localhost:5000"):
        self.base_url = base_url
    
    def consulta_stream_proxy(self, pergunta):
        """Proxy MELHORADO para o endpoint de streaming da API principal"""
        url = f"{self.base_url}/api/consulta/stream"
        payload = {"pergunta": pergunta}
        
        def generate():
            try:
                # Configurar timeout maior e stream
                response = requests.post(
                    url, 
                    json=payload, 
                    stream=True,
                    timeout=(10, 600),  # 10s para conectar, 600s (10 min) para dados
                    headers={'Accept': 'text/event-stream'}
                )
                
                if response.status_code == 200:
                    # Processar linha por linha do stream
                    for line in response.iter_lines(decode_unicode=True):
                        if line:
                            # SSE envia linhas no formato "data: {json}"
                            if line.startswith('data: '):
                                # Remover o prefixo "data: " e enviar
                                yield line + '\n\n'
                            else:
                                # Se não tiver o prefixo, adicionar
                                yield f"data: {line}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'error', 'message': f'Erro na API: Status {response.status_code}'})}\n\n"
                    yield f"data: {json.dumps({'type': 'end'})}\n\n"
                    
            except requests.exceptions.Timeout:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Timeout na conexão com API principal (10 minutos)'})}\n\n"
                yield f"data: {json.dumps({'type': 'end'})}\n\n"
            except requests.exceptions.ConnectionError as e:
                yield f"data: {json.dumps({'type': 'error', 'message': f'Erro de conexão: {str(e)}'})}\n\n"
                yield f"data: {json.dumps({'type': 'end'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': f'Erro inesperado: {str(e)}'})}\n\n"
                yield f"data: {json.dumps({'type': 'end'})}\n\n"
        
        return Response(
            generate(), 
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no',
                'Content-Type': 'text/event-stream'
            }
        )
    
    def limpar_contexto(self):
        """Limpa o contexto via API"""
        url = f"{self.base_url}/api/limpar_contexto"
        try:
            response = requests.post(url, timeout=10)
            return response.json() if response.status_code == 200 else None
        except:
            return None
    
    def verificar_status(self):
        """Verifica status da API"""
        url = f"{self.base_url}/api/status"
        try:
            response = requests.get(url, timeout=5)
            return response.json() if response.status_code == 200 else None
        except:
            return None

# Instância do cliente
cliente = ClienteAPIVeterinaria()

HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sistema Veterinário - Chat</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #f0f2f5;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        
        .header {
            background: #2c3e50;
            color: white;
            padding: 1rem;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        .container {
            display: flex;
            flex: 1;
            overflow: hidden;
        }
        
        .chat-section {
            flex: 1;
            display: flex;
            flex-direction: column;
            background: white;
            border-right: 2px solid #e0e0e0;
        }
        
        .terminal-section {
            flex: 1;
            display: flex;
            flex-direction: column;
            background: #1e1e1e;
        }
        
        .chat-header, .terminal-header {
            padding: 1rem;
            border-bottom: 1px solid #e0e0e0;
            font-weight: bold;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .terminal-header {
            background: #333;
            color: #00ff00;
            border-bottom: 1px solid #444;
        }
        
        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 1rem;
            background: #fafafa;
        }
        
        .terminal-content {
            flex: 1;
            overflow-y: auto;
            padding: 1rem;
            font-family: 'Courier New', monospace;
            font-size: 14px;
            color: #00ff00;
            background: #000;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        
        .message {
            margin-bottom: 1rem;
            display: flex;
            flex-direction: column;
        }
        
        .message.user {
            align-items: flex-end;
        }
        
        .message.bot {
            align-items: flex-start;
        }
        
        .message-bubble {
            max-width: 70%;
            padding: 0.75rem 1rem;
            border-radius: 20px;
            word-wrap: break-word;
            white-space: pre-wrap;
        }
        
        .message.user .message-bubble {
            background: #007bff;
            color: white;
        }
        
        .message.bot .message-bubble {
            background: #e9ecef;
            color: #333;
        }
        
        .message-time {
            font-size: 0.75rem;
            color: #888;
            margin-top: 0.25rem;
        }
        
        .chat-input {
            display: flex;
            padding: 1rem;
            background: white;
            border-top: 1px solid #e0e0e0;
        }
        
        .chat-input input {
            flex: 1;
            padding: 0.75rem;
            border: 1px solid #ddd;
            border-radius: 25px;
            outline: none;
            font-size: 16px;
        }
        
        .chat-input button {
            margin-left: 0.5rem;
            padding: 0.75rem 1.5rem;
            background: #007bff;
            color: white;
            border: none;
            border-radius: 25px;
            cursor: pointer;
            font-size: 16px;
        }
        
        .chat-input button:hover {
            background: #0056b3;
        }
        
        .chat-input button:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        
        .status {
            padding: 0.25rem 0.5rem;
            border-radius: 12px;
            font-size: 0.75rem;
        }
        
        .status.online {
            background: #d4edda;
            color: #155724;
        }
        
        .status.offline {
            background: #f8d7da;
            color: #721c24;
        }
        
        .log-line {
            margin-bottom: 0.25rem;
            font-family: 'Courier New', monospace;
        }
        
        .loading {
            display: flex;
            align-items: center;
            color: #007bff;
            font-style: italic;
        }
        
        .loading::after {
            content: '';
            width: 20px;
            height: 20px;
            margin-left: 10px;
            border: 2px solid #f3f3f3;
            border-top: 2px solid #007bff;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .clear-btn {
            background: #dc3545;
            color: white;
            border: none;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.75rem;
        }
        
        .clear-btn:hover {
            background: #c82333;
        }
        
        /* Estilos para links e fontes */
        .fonte-badge {
            display: inline-block;
            background: #007bff;
            color: white;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.75rem;
            margin: 0 2px;
            cursor: help;
            transition: all 0.2s;
        }
        
        .fonte-badge:hover {
            background: #0056b3;
            transform: scale(1.05);
        }
        
        .link-externo {
            color: #007bff;
            text-decoration: none;
            padding: 2px 6px;
            border-radius: 4px;
            background: #e7f3ff;
            transition: all 0.2s;
            font-size: 0.9rem;
            display: inline-block;
            margin: 2px;
        }
        
        .link-externo:hover {
            background: #007bff;
            color: white;
            text-decoration: none;
        }
        
        .message-bubble a {
            word-break: break-all;
        }
        
        .message-bubble strong {
            font-weight: 600;
            color: #2c3e50;
        }
        
        .message.bot .message-bubble strong {
            color: #1a1a1a;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🏥 Sistema de Consulta Veterinária</h1>
    </div>
    
    <div class="container">
        <!-- Seção do Chat -->
        <div class="chat-section">
            <div class="chat-header">
                <span>💬 Chat</span>
                <div>
                    <span id="api-status" class="status offline">🔴 Verificando...</span>
                    <button class="clear-btn" onclick="limparContexto()" title="Limpar apenas mensagens visíveis">🧹 Limpar Chat</button>
                    <button class="clear-btn" style="background: #ff6b6b;" onclick="limparContextoCompleto()" title="Limpar contexto completo da API">🗑️ Reset Total</button>
                </div>
            </div>
            
            <div class="chat-messages" id="chat-messages">
                <div class="message bot">
                    <div class="message-bubble">
                        Olá! Sou seu assistente veterinário. Faça uma pergunta sobre medicamentos ou tratamentos.
                    </div>
                    <div class="message-time" id="welcome-time"></div>
                </div>
            </div>
            
            <div class="chat-input">
                <input type="text" id="message-input" placeholder="Digite sua pergunta..." disabled>
                <button id="send-button" onclick="enviarMensagem()" disabled>Enviar</button>
            </div>
        </div>
        
        <!-- Seção do Terminal -->
        <div class="terminal-section">
            <div class="terminal-header">
                <span>🖥️ Terminal de Logs</span>
                <button class="clear-btn" onclick="limparTerminal()">🧹 Limpar</button>
            </div>
            
            <div class="terminal-content" id="terminal-content">
                <div class="log-line" style="color: #00ff00;">> Sistema iniciado...</div>
                <div class="log-line" style="color: #ffff00;">> Aguardando conexão com API...</div>
            </div>
        </div>
    </div>

    <script>
        let isProcessing = false;
        let currentEventSource = null;
        
        // Verificar status da API ao carregar
        window.onload = function() {
            verificarStatus();
            document.getElementById('welcome-time').textContent = new Date().toLocaleTimeString();
            
            // Enter para enviar
            document.getElementById('message-input').addEventListener('keypress', function(e) {
                if (e.key === 'Enter' && !isProcessing) {
                    enviarMensagem();
                }
            });
        }
        
        function verificarStatus() {
            fetch('/api/status')
                .then(response => response.json())
                .then(data => {
                    const statusEl = document.getElementById('api-status');
                    const messageInput = document.getElementById('message-input');
                    const sendButton = document.getElementById('send-button');
                    
                    if (data && data.status === 'online') {
                        statusEl.textContent = '🟢 Online';
                        statusEl.className = 'status online';
                        messageInput.disabled = false;
                        sendButton.disabled = false;
                        adicionarLogTerminal('✅ API conectada - Modelo: ' + data.modelo, '#00ff00');
                    } else {
                        statusEl.textContent = '🔴 Offline';
                        statusEl.className = 'status offline';
                        messageInput.disabled = true;
                        sendButton.disabled = true;
                        adicionarLogTerminal('❌ API desconectada', '#ff0000');
                    }
                })
                .catch(() => {
                    const statusEl = document.getElementById('api-status');
                    statusEl.textContent = '🔴 Erro';
                    statusEl.className = 'status offline';
                    adicionarLogTerminal('❌ Erro ao conectar com API', '#ff0000');
                });
        }
        
        function enviarMensagem() {
            if (isProcessing) return;
            
            const input = document.getElementById('message-input');
            const pergunta = input.value.trim();
            
            if (!pergunta) return;
            
            // Adicionar mensagem do usuário
            adicionarMensagem('user', pergunta);
            input.value = '';
            isProcessing = true;
            
            // Desabilitar input
            input.disabled = true;
            document.getElementById('send-button').disabled = true;
            
            // Adicionar indicador de carregamento
            const loadingMsg = adicionarMensagem('bot', '<div class="loading">Processando sua pergunta...</div>');
            
            // Limpar terminal para nova consulta
            adicionarLogTerminal('📤 Nova consulta: ' + pergunta, '#00ffff');
            adicionarLogTerminal('🔄 Conectando com API...', '#ffff00');
            
            // Fechar conexão anterior se existir
            if (currentEventSource) {
                currentEventSource.close();
            }
            
            // Fazer streaming com EventSource
            const eventSource = new EventSource('/stream?pergunta=' + encodeURIComponent(pergunta));
            currentEventSource = eventSource;
            let respostaFinal = '';
            let lastActivity = Date.now();
            let logCount = 0;
            
            // Timeout manual (10 minutos)
            const timeoutId = setTimeout(() => {
                adicionarLogTerminal('⏰ Timeout - Processo demorou mais de 10 minutos', '#ffaa00');
                eventSource.close();
                finalizarProcessamento(loadingMsg, input, '⏰ A consulta demorou mais que o esperado.');
            }, 600000); // 10 minutos
            
            eventSource.onopen = function() {
                adicionarLogTerminal('🔗 Conexão estabelecida com sucesso', '#00ff00');
            };
            
            eventSource.onmessage = function(event) {
                lastActivity = Date.now();
                
                try {
                    const data = JSON.parse(event.data);
                    
                    if (data.type === 'start') {
                        adicionarLogTerminal('🚀 ' + data.message, '#00ffff');
                    } else if (data.type === 'log') {
                        logCount++;
                        adicionarLogTerminal(`[${logCount}] ${data.message}`, '#00ff00');
                    } else if (data.type === 'heartbeat') {
                        adicionarLogTerminal('💓 ' + data.message, '#888888');
                    } else if (data.type === 'response') {
                        respostaFinal = data.message;
                        adicionarLogTerminal('📄 Resposta recebida (' + respostaFinal.length + ' caracteres)', '#00ffff');
                    } else if (data.type === 'error') {
                        clearTimeout(timeoutId);
                        adicionarLogTerminal('❌ Erro: ' + data.message, '#ff0000');
                        finalizarProcessamento(loadingMsg, input, '❌ Erro: ' + data.message);
                        eventSource.close();
                    } else if (data.type === 'timeout') {
                        clearTimeout(timeoutId);
                        adicionarLogTerminal('⏰ ' + data.message, '#ffaa00');
                        finalizarProcessamento(loadingMsg, input, '⏰ Timeout na API principal.');
                        eventSource.close();
                    } else if (data.type === 'end') {
                        clearTimeout(timeoutId);
                        loadingMsg.remove();
                        
                        if (respostaFinal) {
                            adicionarMensagem('bot', respostaFinal);
                            adicionarLogTerminal(`✅ Processamento concluído (${logCount} logs)`, '#00ff00');
                        } else {
                            adicionarMensagem('bot', '❌ Não foi possível obter resposta');
                            adicionarLogTerminal('❌ Resposta vazia', '#ff0000');
                        }
                        
                        input.disabled = false;
                        document.getElementById('send-button').disabled = false;
                        input.focus();
                        isProcessing = false;
                        currentEventSource = null;
                        eventSource.close();
                    }
                } catch (e) {
                    console.error('Erro ao processar evento:', e);
                    adicionarLogTerminal('❌ Erro ao processar dados: ' + e.message, '#ff0000');
                }
            };
            
            eventSource.onerror = function(error) {
                clearTimeout(timeoutId);
                console.error('EventSource error:', error);
                
                const timeSinceLastActivity = Date.now() - lastActivity;
                adicionarLogTerminal(`❌ Erro de conexão (${Math.floor(timeSinceLastActivity/1000)}s)`, '#ff0000');
                
                if (logCount === 0) {
                    finalizarProcessamento(loadingMsg, input, '❌ Erro de conexão inicial. Verifique a API.');
                } else {
                    finalizarProcessamento(loadingMsg, input, '❌ Conexão perdida durante processamento.');
                }
                
                currentEventSource = null;
                eventSource.close();
            };
        }
        
        function finalizarProcessamento(loadingMsg, input, mensagemErro) {
            if (loadingMsg && loadingMsg.parentNode) {
                loadingMsg.innerHTML = '<div style="color: #dc3545;">' + mensagemErro + '</div>';
            }
            input.disabled = false;
            document.getElementById('send-button').disabled = false;
            input.focus();
            isProcessing = false;
            currentEventSource = null;
        }
        
        function formatarConteudoComLinks(conteudo) {
            try {
                // Converter [Fonte N] em badges clicáveis
                conteudo = conteudo.replace(/\[Fonte (\d+)\]/g, 
                    '<span class="fonte-badge" data-fonte="$1">📖 Fonte $1</span>');
                
                // Converter URLs em links clicáveis (REGEX SIMPLIFICADA)
                conteudo = conteudo.replace(/(https?:\/\/[^\s]+)/g, function(url) {
                    let nomeCurto = url.split('/').pop() || 'Link';
                    if (nomeCurto.length > 30) {
                        nomeCurto = nomeCurto.substring(0, 30) + '...';
                    }
                    return '<a href="' + url + '" target="_blank" class="link-externo" title="' + url + '">🔗 ' + nomeCurto + '</a>';
                });
                
                // Converter **texto** em negrito
                conteudo = conteudo.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
                
                // Converter quebras de linha em <br>
                conteudo = conteudo.replace(/\n/g, '<br>');
                
                return conteudo;
            } catch (e) {
                console.error('Erro ao formatar conteúdo:', e);
                return conteudo;
            }
        }
        
        function adicionarMensagem(tipo, conteudo) {
            const messagesDiv = document.getElementById('chat-messages');
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${tipo}`;
            
            // Formatar conteúdo com links elegantes apenas para mensagens do bot
            let conteudoFormatado = conteudo;
            if (tipo === 'bot') {
                try {
                    conteudoFormatado = formatarConteudoComLinks(conteudo);
                } catch (e) {
                    console.error('Erro ao formatar links:', e);
                    conteudoFormatado = conteudo;
                }
            }
            
            messageDiv.innerHTML = `
                <div class="message-bubble">${conteudoFormatado}</div>
                <div class="message-time">${new Date().toLocaleTimeString()}</div>
            `;
            
            messagesDiv.appendChild(messageDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
            
            return messageDiv.querySelector('.message-bubble');
        }
        
        function adicionarLogTerminal(texto, cor = '#00ff00') {
            const terminal = document.getElementById('terminal-content');
            const logDiv = document.createElement('div');
            logDiv.className = 'log-line';
            logDiv.style.color = cor;
            logDiv.textContent = `[${new Date().toLocaleTimeString()}] ${texto}`;
            
            terminal.appendChild(logDiv);
            terminal.scrollTop = terminal.scrollHeight;
        }
        
        function limparContexto() {
            // Fechar stream se estiver ativo
            if (currentEventSource) {
                currentEventSource.close();
                currentEventSource = null;
                isProcessing = false;
                document.getElementById('message-input').disabled = false;
                document.getElementById('send-button').disabled = false;
            }
            
            // Limpar apenas as mensagens visuais do chat
            const chatMessages = document.getElementById('chat-messages');
            chatMessages.innerHTML = `
                <div class="message bot">
                    <div class="message-bubble">
                        Chat limpo. O contexto da conversa foi mantido para continuidade.
                    </div>
                    <div class="message-time">${new Date().toLocaleTimeString()}</div>
                </div>
            `;
            
            adicionarLogTerminal('🧹 Mensagens do chat limpas (contexto mantido)', '#ffff00');
        }
        
        function limparContextoCompleto() {
            // Esta função limpa o contexto real da API (use com cuidado)
            if (currentEventSource) {
                currentEventSource.close();
                currentEventSource = null;
                isProcessing = false;
                document.getElementById('message-input').disabled = false;
                document.getElementById('send-button').disabled = false;
            }
            
            fetch('/api/limpar_contexto', {method: 'POST'})
                .then(response => response.json())
                .then(data => {
                    if (data && data.success) {
                        adicionarLogTerminal('🗑️ Contexto da API limpo completamente', '#ffaa00');
                        
                        // Limpar chat também
                        const chatMessages = document.getElementById('chat-messages');
                        chatMessages.innerHTML = `
                            <div class="message bot">
                                <div class="message-bubble">
                                    Contexto da conversa foi totalmente limpo. Nova sessão iniciada.
                                </div>
                                <div class="message-time">${new Date().toLocaleTimeString()}</div>
                            </div>
                        `;
                    } else {
                        adicionarLogTerminal('❌ Erro ao limpar contexto da API', '#ff0000');
                    }
                })
                .catch(error => {
                    adicionarLogTerminal('❌ Erro ao limpar contexto: ' + error.message, '#ff0000');
                });
        }
        
        function limparTerminal() {
            document.getElementById('terminal-content').innerHTML = '<div class="log-line" style="color: #00ff00;">> Terminal limpo</div>';
        }
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/stream')
def stream():
    pergunta = request.args.get('pergunta')
    if not pergunta:
        return "Pergunta não fornecida", 400
    
    return cliente.consulta_stream_proxy(pergunta)

@app.route('/api/limpar_contexto', methods=['POST'])
def limpar_contexto():
    resultado = cliente.limpar_contexto()
    if resultado:
        return jsonify(resultado)
    else:
        return jsonify({'success': False, 'error': 'Erro ao limpar contexto'}), 500

@app.route('/api/status')
def status():
    resultado = cliente.verificar_status()
    if resultado:
        return jsonify(resultado)
    else:
        return jsonify({'status': 'offline'}), 503

if __name__ == "__main__":
    print("🚀 Iniciando Cliente Web...")
    print("📍 Acesse: http://localhost:3030")
    print("⚠️  Certifique-se que a API principal está rodando em localhost:5000")
    app.run(debug=False, port=3030, threaded=True)  # debug=False para produção