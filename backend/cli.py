"""CLI interactivo — substitui o `main()` do `sistema_consulta.py`."""

from __future__ import annotations

import argparse
import sys
import uuid

from backend.observability import configure_logging, get_logger
from backend.orchestrator import Pipeline

log = get_logger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sistema de Consulta Veterinária — CLI")
    parser.add_argument("--question", "-q", help="Pergunta única (não interativo)")
    parser.add_argument("--session", "-s", default=None, help="Identificador de sessão")
    args = parser.parse_args()

    configure_logging()
    pipe = Pipeline()
    session_id = args.session or str(uuid.uuid4())

    if args.question:
        result = pipe.run(args.question, session_id=session_id)
        print(result.response)
        return

    print("Sistema de Consulta Veterinária. 'sair' para encerrar, 'reset' para limpar contexto.")
    while True:
        try:
            pergunta = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not pergunta:
            continue
        if pergunta.lower() in {"sair", "exit", "quit"}:
            break
        if pergunta.lower() == "reset":
            pipe.conversations.reset(session_id)
            print("(contexto limpo)")
            continue
        result = pipe.run(pergunta, session_id=session_id)
        print("\n" + result.response)


if __name__ == "__main__":
    sys.exit(main())
