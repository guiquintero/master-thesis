# api_vet.py - CORRIGIDO
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import json
import sys
import threading
import queue
import time
from contextlib import redirect_stdout, redirect_stderr
import traceback
import io

# Importar o sistema principal
from temporario import SistemaConsultaVetOtimizado

app = Flask(__name__)
CORS(app)

class LogCapture:
    """Captura TODOS os prints e outputs do sistema"""
    def __init__(self, log_queue):
        self.log_queue = log_queue
        self.terminal = sys.stdout
        self.buffer = []
        
    def write(self, text):
        if text and text.strip():  # Ignorar linhas vazias
            # Enviar para a fila IMEDIATAMENTE
            try:
                self.log_queue.put({
                    'type': 'log',
                    'message': text.strip(),
                    'timestamp': time.time()
                }, block=False)
            except queue.Full:
                pass  # Se a fila estiver cheia, ignora
        
        # Também imprimir no terminal
        self.terminal.write(text)
        
    def flush(self):
        self.terminal.flush()

class APIVeterinaria:
    def __init__(self):
        self.sistema = SistemaConsultaVetOtimizado()
        
    def processar_com_logs(self, pergunta, log_queue):
        """Processa a pergunta capturando todos os logs"""
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        
        try:
            # Enviar log inicial
            log_queue.put({
                'type': 'log',
                'message': '🚀 Iniciando processamento da pergunta...',
                'timestamp': time.time()
            })
            
            # Capturar stdout E stderr
            sys.stdout = LogCapture(log_queue)
            sys.stderr = LogCapture(log_queue)
            
            # Adicionar callback para monitorar progresso
            def progress_callback(message):
                log_queue.put({
                    'type': 'log',
                    'message': message,
                    'timestamp': time.time()
                })
            
            # Processar a pergunta
            log_queue.put({
                'type': 'log',
                'message': f'📝 Pergunta recebida: {pergunta}',
                'timestamp': time.time()
            })
            
            resposta = self.sistema.processar_pergunta_unica(pergunta)
            
            # Restaurar stdout/stderr
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            
            # Enviar resposta final
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
            # Restaurar stdout/stderr em caso de erro
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            
            error_msg = f"❌ Erro ao processar pergunta: {str(e)}\n{traceback.format_exc()}"
            
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
            log_queue = queue.Queue(maxsize=1000)  # Fila maior
            
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
            max_timeout_count = 60  # 60 * 3 = 180 segundos
            
            while True:
                try:
                    # Timeout menor para verificações mais frequentes
                    item = log_queue.get(timeout=3)
                    
                    # Reset timeout counter quando recebe dados
                    timeout_count = 0
                    
                    if item['type'] == 'end':
                        yield f"data: {json.dumps(item)}\n\n"
                        break
                    
                    # Enviar log imediatamente
                    yield f"data: {json.dumps(item)}\n\n"
                    
                except queue.Empty:
                    timeout_count += 1
                    
                    # Enviar heartbeat para manter conexão viva
                    if timeout_count % 10 == 0:  # A cada 30 segundos
                        yield f"data: {json.dumps({'type': 'heartbeat', 'message': f'Processando... ({timeout_count * 3}s)', 'timestamp': time.time()})}\n\n"
                    
                    # Timeout final após 180 segundos
                    if timeout_count >= max_timeout_count:
                        yield f"data: {json.dumps({'type': 'timeout', 'message': 'Timeout na operação (3 minutos)', 'timestamp': time.time()})}\n\n"
                        yield f"data: {json.dumps({'type': 'end'})}\n\n"
                        break
                    
                    # Verificar se a thread ainda está viva
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
                'Content-Type': 'text/event-stream'
            }
        )
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/limpar_contexto', methods=['POST'])
def limpar_contexto():
    """Endpoint para limpar o contexto da conversa"""
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
    """Endpoint para verificar status da API"""
    return jsonify({
        'status': 'online',
        'modelo': api_vet.sistema.modelo_ollama,
        'timestamp': time.time()
    })

@app.route('/', methods=['GET'])
def home():
    """Página inicial com documentação básica"""
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
    app.run(debug=False, port=5000, threaded=True)  # debug=False para produção