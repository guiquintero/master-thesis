# api_vet_cors.py - Configuração para acesso público
from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS
import json
import sys
import threading
import queue
import time
import traceback
import os

from temporario import SistemaConsultaVetOtimizado

app = Flask(__name__)

# CORS configurado para permitir acesso de qualquer origem
CORS(app, 
     origins="*",  # Permite qualquer origem
     allow_headers=["Content-Type"],
     methods=["GET", "POST", "OPTIONS"],
     supports_credentials=False)


class APIVeterinaria:
    def __init__(self):
        self.sistema = SistemaConsultaVetOtimizado()
        
    def processar_com_logs(self, pergunta, log_queue):
        """Processa a pergunta capturando todos os logs"""
        try:
            # Enviar log inicial
            log_queue.put({
                'type': 'log',
                'message': '🚀 Iniciando processamento da pergunta...',
                'timestamp': time.time()
            })
            
            log_queue.put({
                'type': 'log',
                'message': f'🔍 Pergunta recebida: {pergunta}',
                'timestamp': time.time()
            })
            
            # Processar a pergunta
            resposta = self.sistema.processar_pergunta_unica(pergunta)
            
            log_queue.put({
                'type': 'log',
                'message': '✅ Processamento concluído com sucesso!',
                'timestamp': time.time()
            })
            
            log_queue.put({
                'type': 'response',
                'message': resposta,
                'timestamp': time.time()
            })
            
            # Sinalizar fim do processamento
            log_queue.put({'type': 'end'})
            
        except Exception as e:
            error_msg = f"❌ Erro ao processar pergunta: {str(e)}\n{traceback.format_exc()}"
            
            log_queue.put({
                'type': 'error',
                'message': error_msg,
                'timestamp': time.time()
            })
            log_queue.put({'type': 'end'})

# Instância global da API
api_vet = APIVeterinaria()

@app.route('/api/consulta/stream', methods=['POST', 'OPTIONS'])
def consulta_stream():
    """
    Endpoint com streaming de logs via Server-Sent Events
    """
    # Handle preflight
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        data = request.json
        pergunta = data.get('pergunta')
        
        if not pergunta:
            return jsonify({
                'success': False,
                'error': 'Campo "pergunta" é obrigatório'
            }), 400
        
        def generate():
            log_queue = queue.Queue(maxsize=1000)
            
            # Enviar confirmação de início
            yield f"data: {json.dumps({'type': 'start', 'message': 'Iniciando processamento...', 'timestamp': time.time()})}\n\n"
            
            # Iniciar processamento em thread separada
            thread = threading.Thread(
                target=api_vet.processar_com_logs,
                args=(pergunta, log_queue),
                daemon=True
            )
            thread.start()
            
            # Enviar logs conforme vão chegando
            timeout_count = 0
            max_timeout_count = 60
            
            while True:
                try:
                    item = log_queue.get(timeout=3)
                    timeout_count = 0
                    
                    if item['type'] == 'end':
                        yield f"data: {json.dumps(item)}\n\n"
                        break
                    
                    yield f"data: {json.dumps(item)}\n\n"
                    
                except queue.Empty:
                    timeout_count += 1
                    
                    if timeout_count % 10 == 0:
                        yield f"data: {json.dumps({'type': 'heartbeat', 'message': f'Processando... ({timeout_count * 3}s)', 'timestamp': time.time()})}\n\n"
                    
                    if timeout_count >= max_timeout_count:
                        yield f"data: {json.dumps({'type': 'timeout', 'message': 'Timeout na operação (3 minutos)', 'timestamp': time.time()})}\n\n"
                        yield f"data: {json.dumps({'type': 'end'})}\n\n"
                        break
                    
                    if not thread.is_alive() and log_queue.empty():
                        yield f"data: {json.dumps({'type': 'error', 'message': 'Thread de processamento encerrou inesperadamente', 'timestamp': time.time()})}\n\n"
                        yield f"data: {json.dumps({'type': 'end'})}\n\n"
                        break
            
            thread.join(timeout=10)
        
        return Response(
            generate(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no',
                'Content-Type': 'text/event-stream',
                'Access-Control-Allow-Origin': '*'
            }
        )
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/limpar_contexto', methods=['POST', 'OPTIONS'])
def limpar_contexto():
    """Endpoint para limpar o contexto da conversa"""
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        api_vet.sistema.limpar_contexto_manual()
        return jsonify({
            'success': True,
            'message': 'Contexto limpo com sucesso'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/status', methods=['GET', 'OPTIONS'])
def status():
    """Endpoint para verificar status da API"""
    if request.method == 'OPTIONS':
        return '', 204
        
    return jsonify({
        'status': 'online',
        'modelo': api_vet.sistema.modelo_ollama,
        'timestamp': time.time()
    })

@app.route('/', methods=['GET'])
def home():
    """Servir a página do chat diretamente"""
    if os.path.exists('/opt/veterinaria-api/chat-novavet.html'):
        return send_from_directory('/opt/veterinaria-api', 'chat-novavet.html')
    else:
        return """
        <html>
            <head>
                <title>API Sistema Veterinário</title>
                <style>
                    body { font-family: Arial; margin: 40px; }
                    h1 { color: #333; }
                    .endpoint { background: #f5f5f5; padding: 15px; margin: 20px 0; border-radius: 5px; }
                    code { background: #e0e0e0; padding: 2px 5px; border-radius: 3px; }
                </style>
            </head>
            <body>
                <h1>🏥 API Sistema de Consulta Veterinária</h1>
                
                <div class="endpoint">
                    <h2>Chat Interface</h2>
                    <p>Acesse: <a href="/chat-novavet.html">/chat-novavet.html</a></p>
                </div>
                
                <div class="endpoint">
                    <h2>POST /api/consulta/stream</h2>
                    <p>Retorna stream de eventos (SSE) com logs em tempo real</p>
                    <code>{"pergunta": "Qual a dose do Animeloxan para suínos?"}</code>
                </div>
                
                <div class="endpoint">
                    <h2>POST /api/limpar_contexto</h2>
                    <p>Limpa o contexto da conversa</p>
                </div>
                
                <div class="endpoint">
                    <h2>GET /api/status</h2>
                    <p>Verifica o status da API</p>
                </div>
            </body>
        </html>
        """

@app.route('/chat-novavet.html')
def chat_page():
    """Servir a página do chat"""
    return send_from_directory('/opt/veterinaria-api', 'chat-novavet.html')

if __name__ == '__main__':
    print("🚀 Iniciando API Sistema Veterinário...")
    print("📍 Acesse: http://193.136.195.43:8000")
    print("💬 Chat: http://193.136.195.43:8000/chat-novavet.html")
    app.run(debug=False, host='0.0.0.0', port=8000, threaded=True)