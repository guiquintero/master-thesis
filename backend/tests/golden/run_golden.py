"""Runner do golden set.

Executa `data/perguntas_exemplo.txt`, grava latências/respostas e produz um
relatório JSON em `data/results/golden_<modelo>_<timestamp>.json`.

Uso:
    python -m backend.tests.golden.run_golden
    python -m backend.tests.golden.run_golden --limit 5
    python -m backend.tests.golden.run_golden --model gemma2:9b
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable

from backend.config import get_settings
from backend.llm import OllamaClient
from backend.observability import configure_logging, get_logger
from backend.orchestrator import Pipeline

log = get_logger(__name__)


def iter_questions(path: Path) -> Iterable[str]:
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("|") or s.startswith("-") or s.startswith("#") or s.endswith("-"):
            continue
        if "Modelo" in s and "Assertividade" in s:
            continue
        yield s


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Quantas perguntas executar")
    parser.add_argument("--model", default=None, help="Modelo Ollama (sobrescreve .env)")
    parser.add_argument("--out", type=Path, default=None, help="Caminho do JSON de saída")
    args = parser.parse_args()

    configure_logging()
    settings = get_settings()

    questions_file = settings.project_root / "data" / "perguntas_exemplo.txt"
    if not questions_file.exists():
        raise SystemExit(f"Arquivo não encontrado: {questions_file}")

    questions = list(iter_questions(questions_file))
    if args.limit:
        questions = questions[: args.limit]

    llm = OllamaClient(model=args.model) if args.model else OllamaClient()
    pipe = Pipeline(llm=llm)

    results = []
    total_start = time.time()

    for i, q in enumerate(questions, 1):
        log.info("=" * 70)
        log.info("[%d/%d] %s", i, len(questions), q)
        start = time.perf_counter()
        try:
            r = pipe.run(q, session_id=f"golden-{i}")
            elapsed = time.perf_counter() - start
            results.append({
                "n": i,
                "question": q,
                "category": r.category,
                "entities": r.entities,
                "via": r.via,
                "response": r.response,
                "timings": r.timings,
                "elapsed": elapsed,
                "ok": True,
            })
            log.info("OK %s | %.2fs", r.category, elapsed)
        except Exception as exc:  # noqa: BLE001
            log.exception("Falha na pergunta %d", i)
            results.append({
                "n": i,
                "question": q,
                "error": str(exc),
                "ok": False,
            })

    elapsed_total = time.time() - total_start
    success = sum(1 for r in results if r.get("ok"))

    report = {
        "timestamp": datetime.now().isoformat(),
        "model": llm.model,
        "n_questions": len(questions),
        "n_success": success,
        "elapsed_total": elapsed_total,
        "elapsed_avg": elapsed_total / max(len(questions), 1),
        "results": results,
    }

    out = args.out or settings.data_dir / "results" / f"golden_{llm.model.replace(':', '_')}_{int(time.time())}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Relatório: %s", out)
    log.info("Sucesso: %d/%d  |  Tempo médio: %.2fs", success, len(questions), report["elapsed_avg"])


if __name__ == "__main__":
    main()
