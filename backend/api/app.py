"""Flask app factory.

Diferenças vs. API antiga:
- Sem hijack global de `sys.stdout`/`stderr`
- Logs streamados via callback do logger (`observability.capture_logs`)
- Sessões isoladas por `session_id` (header `X-Session-Id`, gerado se ausente)
- CORS configurável por env (`CORS_ORIGINS`)
"""

from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from typing import Iterable

from flask import Flask, Response, jsonify, request
from flask_cors import CORS

from backend.config import get_settings
from backend.observability import configure_logging, get_logger
from backend.observability.logger import capture_logs
from backend.orchestrator import Pipeline

log = get_logger(__name__)


def create_app(pipeline: Pipeline | None = None) -> Flask:
    settings = get_settings()
    configure_logging(level="DEBUG" if settings.debug else "INFO")

    app = Flask(__name__)
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()] or "*"
    CORS(app, origins=origins, allow_headers=["Content-Type", "X-Session-Id"], methods=["GET", "POST", "OPTIONS"])

    pipe = pipeline or Pipeline()

    @app.route("/api/status", methods=["GET"])
    def status():
        return jsonify({
            "status": "online",
            "modelo": pipe.llm.model,
            "embed_model": pipe.llm.embed_model,
            "mode": settings.mode,
            "version": "2.0.0",
            "timestamp": time.time(),
        })

    @app.route("/api/limpar_contexto", methods=["POST"])
    def reset_context():
        session_id = request.headers.get("X-Session-Id") or (request.json or {}).get("session_id", "default")
        pipe.conversations.reset(session_id)
        return jsonify({"success": True, "session_id": session_id})

    @app.route("/api/consulta", methods=["POST"])
    def consulta_simples():
        body = request.get_json(silent=True) or {}
        pergunta = (body.get("pergunta") or "").strip()
        if not pergunta:
            return jsonify({"success": False, "error": "Campo 'pergunta' é obrigatório"}), 400
        session_id = request.headers.get("X-Session-Id") or body.get("session_id") or str(uuid.uuid4())
        result = pipe.run(pergunta, session_id=session_id)
        return jsonify({
            "success": True,
            "resposta": result.response,
            "categoria": result.category,
            "entidades": result.entities,
            "via": result.via,
            "timings": result.timings,
            "session_id": result.session_id,
        })

    @app.route("/api/consulta/stream", methods=["POST", "OPTIONS"])
    def consulta_stream():
        if request.method == "OPTIONS":
            return ("", 204)

        body = request.get_json(silent=True) or {}
        pergunta = (body.get("pergunta") or "").strip()
        if not pergunta:
            return jsonify({"success": False, "error": "Campo 'pergunta' é obrigatório"}), 400
        session_id = request.headers.get("X-Session-Id") or body.get("session_id") or str(uuid.uuid4())

        def generate() -> Iterable[bytes]:
            q: "queue.Queue[dict]" = queue.Queue(maxsize=2000)
            yield _sse({"type": "start", "session_id": session_id, "timestamp": time.time()})

            def log_callback(level: str, msg: str) -> None:
                try:
                    q.put_nowait({"type": "log", "level": level, "message": msg, "timestamp": time.time()})
                except queue.Full:
                    pass

            def worker() -> None:
                try:
                    with capture_logs(log_callback):
                        result = pipe.run(pergunta, session_id=session_id)
                    q.put({
                        "type": "response",
                        "message": result.response,
                        "categoria": result.category,
                        "entidades": result.entities,
                        "timings": result.timings,
                        "via": result.via,
                        "timestamp": time.time(),
                    })
                except Exception as exc:  # noqa: BLE001
                    log.exception("Erro no pipeline")
                    q.put({"type": "error", "message": str(exc), "timestamp": time.time()})
                finally:
                    q.put({"type": "end"})

            thread = threading.Thread(target=worker, daemon=True)
            thread.start()

            heartbeats = 0
            while True:
                try:
                    item = q.get(timeout=3)
                    if item["type"] == "end":
                        yield _sse(item)
                        break
                    yield _sse(item)
                    heartbeats = 0
                except queue.Empty:
                    heartbeats += 1
                    if heartbeats % 10 == 0:
                        yield _sse({"type": "heartbeat", "timestamp": time.time()})
                    if not thread.is_alive() and q.empty():
                        yield _sse({"type": "end"})
                        break

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.route("/", methods=["GET"])
    def root():
        return jsonify({
            "name": "Sistema de Consulta Veterinária — API",
            "version": "2.0.0",
            "endpoints": [
                "GET  /api/status",
                "POST /api/consulta",
                "POST /api/consulta/stream",
                "POST /api/limpar_contexto",
            ],
        })

    return app


def _sse(payload: dict) -> bytes:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")


def main() -> None:
    settings = get_settings()
    app = create_app()
    log.info("API ouvindo em %s:%d (modo=%s)", settings.api_host, settings.api_port, settings.mode)
    app.run(host=settings.api_host, port=settings.api_port, debug=settings.debug, threaded=True)


if __name__ == "__main__":
    main()
