# api_vet.py
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import json
import sys
import threading
import queue
import time
from contextlib import redirect_stdout, redirect_stderr
import traceback

# Importar o sistema principal
from temporario import SistemaConsultaVetOtimizado

app = Flask(__name__)
CORS(app)  # Habilitar CORS para permitir requisições de diferentes origens

class LogCapture:
    """Captura todos os prints e outputs do sistema"""
    def __init__(self, log_queue):
        self.log_queue = log_queue
        self.terminal = sys.stdout
        
    def write(self, text):
        if text.strip():  # Ignorar linhas vazias
            # Enviar para a fila
            self.log_queue.put({
                'type': 'log',
                'message': text.strip(),
                'timestamp': time.time()
            })
        # Também imprimir no terminal (opcional)
        self.terminal.write(text)
        
    def flush(self):
        self.terminal.flush()

class APIVeterinaria:
    def __init__(self):
        self.sistema = SistemaConsultaVetOtimizado()
        
    def processar_com_logs(self, pergunta, log_queue):
        """Processa a pergunta capturando todos os logs"""
        try:
            # Capturar stdout
            old_stdout = sys.stdout
            sys.stdout = LogCapture(log_queue)
            
            # Processar a pergunta
            resposta = self.sistema.processar_pergunta_unica(pergunta)
            
            # Restaurar stdout
            sys.stdout = old_stdout
            
            # Enviar resposta final
            log_queue.put({
                'type': 'response',
                'message': resposta,
                'timestamp': time.time()
            })
            
            # Sinalizar fim do processamento
            log_queue.put({'type': 'end'})
            
        except Exception as e:
            sys.stdout = old_stdout
            error_msg = f"Erro ao processar pergunta: {str(e)}\n{traceback.format_exc()}"
            log_queue.put({
                'type': 'error',
                'message': error_msg,
                'timestamp': time.time()
            })
            log_queue.put({'type': 'end'})

# Instância global da API
api_vet = APIVeterinaria()

@app.route('/api/consulta/stream', methods=['POST'])
def consulta_stream():
    """
    Endpoint com streaming de logs via Server-Sent Events
    
    Exemplo de requisição:
    POST /api/consulta/stream
    {
        "pergunta": "Qual a dose do Animeloxan para suínos?"
    }
    
    Retorna stream de eventos com formato:
    data: {"type": "log", "message": "Processando...", "timestamp": 1234567890}
    data: {"type": "response", "message": "Resposta final...", "timestamp": 1234567891}
    data: {"type": "end"}
    """
    try:
        data = request.json
        pergunta = data.get('pergunta')
        
        if not pergunta:
            return jsonify({
                'success': False,
                'error': 'Campo "pergunta" é obrigatório'
            }), 400
        
        def generate():
            log_queue = queue.Queue()
            
            # Enviar confirmação de início
            yield f"data: {json.dumps({'type': 'start', 'message': 'Iniciando processamento...', 'timestamp': time.time()})}\n\n"
            
            # Iniciar processamento em thread separada
            thread = threading.Thread(
                target=api_vet.processar_com_logs,
                args=(pergunta, log_queue)
            )
            thread.start()
            
            # Enviar logs conforme vão chegando
            while True:
                try:
                    item = log_queue.get(timeout=180)  # Timeout de 180 segundos (3 minutos)
                    
                    if item['type'] == 'end':
                        yield f"data: {json.dumps(item)}\n\n"
                        break
                    
                    # Enviar log imediatamente
                    yield f"data: {json.dumps(item)}\n\n"
                    
                except queue.Empty:
                    # Enviar timeout e encerrar
                    yield f"data: {json.dumps({'type': 'timeout', 'message': 'Timeout na operação (3 minutos)', 'timestamp': time.time()})}\n\n"
                    yield f"data: {json.dumps({'type': 'end'})}\n\n"
                    break
            
            thread.join(timeout=10)  # Aguardar thread terminar
        
        return Response(
            generate(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no'
            }
        )
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/limpar_contexto', methods=['POST'])
def limpar_contexto():
    """
    Endpoint para limpar o contexto da conversa
    """
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

@app.route('/api/status', methods=['GET'])
def status():
    """
    Endpoint para verificar status da API
    """
    return jsonify({
        'status': 'online',
        'modelo': api_vet.sistema.modelo_ollama,
        'timestamp': time.time()
    })

@app.route('/', methods=['GET'])
def home():
    """
    Página inicial com documentação básica
    """
    return """
    <html>
        <head>
            <title>API Sistema Veterinário</title>
            <style>
                body { font-family: Arial; margin: 40px; }
                h1 { color: #333; }
                .endpoint { background: #f5f5f5; padding: 15px; margin: 20px 0; border-radius: 5px; }
                code { background: #e0e0e0; padding: 2px 5px; border-radius: 3px; }
                pre { background: #2d2d2d; color: #f8f8f2; padding: 15px; border-radius: 5px; overflow-x: auto; }
            </style>
        </head>
        <body>
            <h1>🏥 API Sistema de Consulta Veterinária</h1>
            
            <div class="endpoint">
                <h2>POST /api/consulta/stream</h2>
                <p>Retorna stream de eventos (SSE) com logs em tempo real</p>
                <pre>{
    "pergunta": "Qual a dose do Animeloxan para suínos?"
}</pre>
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

if __name__ == '__main__':
    print("🚀 Iniciando API Sistema Veterinário...")
    print("📍 Acesse: http://localhost:5000")
    app.run(debug=True, port=5000, threaded=True)