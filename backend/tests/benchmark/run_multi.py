"""Benchmark multi-modelo do golden set.

Roda as N perguntas de ``data/perguntas_exemplo.txt`` sequencialmente em
cada modelo passado. Entre modelos faz CLEAN SLATE (apaga todo o cache:
respostas, HTML, PDFs, embeddings, índice vector store) — garante que
cada modelo é avaliado em condições idênticas, do zero.

# Uso

    python -m backend.tests.benchmark.run_multi \\
        --models gemma3:27b aya-expanse:32b qwen3:32b gemma3n:e4b \\
        --output data/benchmarks/run_2026-05-26.json

Atalhos via Makefile:

    make bench-multi MODELS="gemma3:27b aya-expanse:32b"
    make bench-multi MODELS="gemma3:27b" LIMIT=5

# Output

Único ficheiro JSON acumulativo. Schema:

    {
      "started_at": "2026-05-26T09:30:00+00:00",
      "finished_at": "...",
      "total_duration_s": 8123.4,
      "config": {...},
      "runs": [
        {
          "modelo": "gemma3:27b",
          "started_at": "...",
          "duration_s": ...,
          "perguntas": [
            {"pergunta": "...", "resposta": "...", "tempo_total_s": 18.4}
          ],
          "summary": {"n_ok": 35, "n_falha": 0, "tempo_medio_s": 22.3}
        }
      ]
    }

# Resistência a falhas

- Modelo inexistente no Ollama → tenta ``ollama pull``; se falhar, regista
  ``erro_inicial`` no run e passa para o próximo modelo.
- Excepção numa pergunta → captura traceback, regista, continua para a
  próxima pergunta.
- Save incremental: o JSON é gravado APÓS cada modelo terminar — interromper
  a meio com Ctrl+C ainda preserva os modelos já completados.

# Clean slate (cache scope)

Apaga, antes de cada modelo:
    data/cache/                 (todos os subdirs: responses, html, search,
                                 embeddings, intent, ...)
    pdf_cache_otimizado/        (PDFs baixados do MedVet)
    data/index/                 (índice ChromaDB)

NÃO toca em:
    data/perguntas_exemplo.txt  (golden set — só leitura)
    data/results/, data/benchmarks/  (saídas)
    backend/, frontend/, etc.   (código)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.config import get_settings
from backend.intent import IntentClassifier
from backend.llm import OllamaClient
from backend.observability import configure_logging, get_logger
from backend.orchestrator import Pipeline

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Carregamento das perguntas
# ---------------------------------------------------------------------------

def load_questions(path: Path) -> list[str]:
    """Lê perguntas do golden set.

    Critério: linha tem que terminar em '?'. Filtra a tabela markdown de
    benchmarks anteriores, separadores ("1-", "2-") e notas finais.
    """
    out: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if not line.endswith("?"):
            continue
        if line.startswith(("|", "#", "//", "--")):
            continue
        out.append(line)
    return out


# ---------------------------------------------------------------------------
# Ollama: presence + pull
# ---------------------------------------------------------------------------

def ollama_list_local() -> set[str]:
    """Lista modelos locais via `ollama list`."""
    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            log.warning("ollama list falhou: %s", result.stderr)
            return set()
        models: set[str] = set()
        for line in result.stdout.splitlines()[1:]:  # skip header
            parts = line.split()
            if parts:
                models.add(parts[0])
        return models
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        log.warning("Não consegui executar 'ollama list': %s", exc)
        return set()


def ensure_pulled(model: str) -> bool:
    """Garante que o modelo está disponível localmente."""
    local = ollama_list_local()
    if model in local:
        log.info("Modelo %s já presente localmente", model)
        return True
    log.info("Modelo %s não local — executando 'ollama pull %s' (pode demorar)", model, model)
    try:
        # Pull pode demorar muito para modelos grandes (20 GB → 5-10 min)
        result = subprocess.run(
            ["ollama", "pull", model],
            check=False, timeout=3600,
        )
        if result.returncode != 0:
            log.error("Pull falhou (rc=%d) para %s", result.returncode, model)
            return False
        return True
    except subprocess.TimeoutExpired:
        log.error("Pull excedeu 1h timeout para %s", model)
        return False
    except FileNotFoundError:
        log.error("Comando 'ollama' não encontrado no PATH")
        return False


# ---------------------------------------------------------------------------
# Clean slate (limpeza total de cache entre modelos)
# ---------------------------------------------------------------------------

def clean_slate(settings) -> dict:
    """Apaga TODOS os caches e índices. Devolve contagem para log."""
    targets = [
        ("cache_dir", settings.cache_dir),
        ("pdf_cache_dir", settings.pdf_cache_dir),
        ("index_dir", settings.index_dir),
    ]
    removed = {}
    for name, p in targets:
        if p.exists():
            try:
                files_before = sum(1 for _ in p.rglob("*") if _.is_file())
            except OSError:
                files_before = 0
            shutil.rmtree(p, ignore_errors=True)
            p.mkdir(parents=True, exist_ok=True)
            removed[name] = files_before
            log.info("Limpou %s (%d ficheiros)", p, files_before)
        else:
            p.mkdir(parents=True, exist_ok=True)
            removed[name] = 0
    return removed


# ---------------------------------------------------------------------------
# Captura de info do host (GPU, versão)
# ---------------------------------------------------------------------------

def host_info() -> dict:
    info = {"hostname": socket.gethostname()}
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            info["gpu"] = result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    try:
        result = subprocess.run(
            ["ollama", "--version"], capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            info["ollama_version"] = result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return info


# ---------------------------------------------------------------------------
# Run de um modelo
# ---------------------------------------------------------------------------

def run_one_model(
    model: str,
    questions: list[str],
    *,
    limit: Optional[int] = None,
) -> dict:
    """Executa todas as perguntas com o modelo dado."""
    qs = questions[:limit] if limit else questions
    started = time.time()

    print(f"\n{'='*72}")
    print(f"MODELO: {model}")
    print(f"Perguntas: {len(qs)}")
    print(f"{'='*72}")

    # 1. Garante que o modelo está presente
    if not ensure_pulled(model):
        return {
            "modelo": model,
            "started_at": datetime.fromtimestamp(started, timezone.utc).isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "duration_s": time.time() - started,
            "erro_inicial": f"falha a obter modelo {model}",
            "perguntas": [],
            "summary": {"n_ok": 0, "n_falha": len(qs), "tempo_medio_s": 0.0},
        }

    # 2. Clean slate: limpa todos os caches do modelo anterior
    settings = get_settings()
    cleanup_stats = clean_slate(settings)

    # 3. Re-inicializa get_settings (cache LRU) e cria pipeline novo
    #    Passamos o modelo explicitamente para garantir que vai onde queremos.
    os.environ["OLLAMA_MODEL"] = model
    get_settings.cache_clear()

    llm = OllamaClient(model=model)
    classifier = IntentClassifier(llm=llm)
    pipeline = Pipeline(llm=llm, classifier=classifier)

    # 4. Loop das perguntas
    results: list[dict] = []
    n_ok = 0
    n_falha = 0

    for i, q in enumerate(qs, 1):
        print(f"\n[{i}/{len(qs)}] {q}")
        start = time.perf_counter()
        try:
            r = pipeline.run(q, session_id=f"bench-{model}-{i}")
            elapsed = time.perf_counter() - start
            results.append({
                "pergunta": q,
                "resposta": r.response,
                "tempo_total_s": round(elapsed, 3),
            })
            n_ok += 1
            print(f"  ✓ {elapsed:.1f}s")
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            elapsed = time.perf_counter() - start
            log.exception("Falha em Q%d", i)
            results.append({
                "pergunta": q,
                "resposta": f"[ERRO] {exc}",
                "tempo_total_s": round(elapsed, 3),
            })
            n_falha += 1
            print(f"  ✗ erro ({elapsed:.1f}s): {exc}")

    finished = time.time()
    media = (sum(r["tempo_total_s"] for r in results) / max(len(results), 1))

    return {
        "modelo": model,
        "started_at": datetime.fromtimestamp(started, timezone.utc).isoformat(),
        "finished_at": datetime.fromtimestamp(finished, timezone.utc).isoformat(),
        "duration_s": round(finished - started, 3),
        "cleanup_stats": cleanup_stats,
        "perguntas": results,
        "summary": {
            "n_questions": len(qs),
            "n_ok": n_ok,
            "n_falha": n_falha,
            "tempo_medio_s": round(media, 3),
            "tempo_total_s": round(finished - started, 3),
        },
    }


# ---------------------------------------------------------------------------
# Save incremental
# ---------------------------------------------------------------------------

def save_results(output: Path, payload: dict) -> None:
    """Escrita atómica: ficheiro completo só aparece quando o save termina."""
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(output)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark multi-modelo do golden set, com clean slate entre modelos.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplos:\n"
            "  python -m backend.tests.benchmark.run_multi \\\n"
            "    --models gemma3:27b aya-expanse:32b qwen3:32b\n\n"
            "  make bench-multi MODELS=\"gemma3:27b mistral-small:24b\" LIMIT=5\n"
        ),
    )
    parser.add_argument("--models", nargs="+", required=True,
                        help="Lista de tags Ollama (espaço-separadas)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limita o nº de perguntas por modelo (útil em dev)")
    parser.add_argument("--output", type=Path, default=None,
                        help="Caminho do JSON de saída (default: data/benchmarks/run_TS.json)")
    parser.add_argument("--questions", type=Path, default=None,
                        help="Ficheiro de perguntas (default: data/perguntas_exemplo.txt)")
    args = parser.parse_args()

    configure_logging()
    settings = get_settings()

    questions_file = args.questions or settings.project_root / "data" / "perguntas_exemplo.txt"
    if not questions_file.exists():
        print(f"✗ Ficheiro não encontrado: {questions_file}", file=sys.stderr)
        return 1
    questions = load_questions(questions_file)
    if not questions:
        print(f"✗ Sem perguntas válidas em {questions_file}", file=sys.stderr)
        return 1
    log.info("Carregadas %d perguntas de %s", len(questions), questions_file)

    output = args.output or (
        settings.data_dir / "benchmarks" /
        f"run_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.json"
    )

    overall_start = time.time()
    n_used = len(questions[: args.limit] if args.limit else questions)

    payload = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "total_duration_s": None,
        "config": {
            "questions_count": n_used,
            "questions_file": str(questions_file),
            "cache_scope": "clean_slate",
            "models_planned": list(args.models),
            "host": host_info(),
            "settings_snapshot": {
                "retriever_top_k": settings.retriever_top_k,
                "retriever_use_embeddings": settings.retriever_use_embeddings,
                "context_chars_limit": settings.context_chars_limit,
                "answer_min_confidence": settings.answer_min_confidence,
                "ollama_embed_model": settings.ollama_embed_model,
            },
        },
        "runs": [],
    }

    # Save inicial (vazio) — assim se Ctrl+C antes do 1º modelo, há sinal
    save_results(output, payload)

    try:
        for model in args.models:
            run = run_one_model(model, questions, limit=args.limit)
            payload["runs"].append(run)
            # Save incremental APÓS cada modelo
            save_results(output, payload)
            print(f"\n→ Resultado parcial gravado em {output}")
    except KeyboardInterrupt:
        log.warning("Interrompido pelo utilizador (Ctrl+C)")
    finally:
        payload["finished_at"] = datetime.now(timezone.utc).isoformat()
        payload["total_duration_s"] = round(time.time() - overall_start, 3)
        save_results(output, payload)

    # Sumário final
    print(f"\n{'='*72}")
    print(f"RESULTADOS GRAVADOS EM: {output}")
    print(f"Duração total: {payload['total_duration_s']:.1f}s "
          f"({payload['total_duration_s'] / 60:.1f} min)")
    print(f"{'='*72}")
    for r in payload["runs"]:
        s = r.get("summary", {})
        if "erro_inicial" in r:
            print(f"  ✗ {r['modelo']:32}  ERRO INICIAL: {r['erro_inicial']}")
            continue
        n_ok = s.get("n_ok", 0)
        n_total = s.get("n_questions", 0)
        media = s.get("tempo_medio_s", 0)
        print(f"  - {r['modelo']:32}  {n_ok}/{n_total} ok  |  média {media:.1f}s/pergunta")

    return 0


if __name__ == "__main__":
    sys.exit(main())
