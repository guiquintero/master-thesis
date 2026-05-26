"""Medição de tempo por etapa, sem o overhead de OpenTelemetry."""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, Iterator

from backend.observability.logger import get_logger

log = get_logger(__name__)


@dataclass
class TimingReport:
    """Registro acumulado de durações por etapa do pipeline."""

    steps: Dict[str, float] = field(default_factory=dict)
    started_at: float = field(default_factory=time.perf_counter)

    def add(self, name: str, duration_s: float) -> None:
        self.steps[name] = self.steps.get(name, 0.0) + duration_s

    @property
    def total(self) -> float:
        return time.perf_counter() - self.started_at

    def to_dict(self) -> Dict[str, float]:
        out = dict(self.steps)
        out["total"] = self.total
        return out

    def log_summary(self) -> None:
        total = max(self.total, 1e-6)
        log.info("===== Tempos de execução =====")
        for step, dur in sorted(self.steps.items(), key=lambda kv: -kv[1]):
            pct = dur / total * 100
            log.info("  %-22s %6.2fs (%5.1f%%)", step, dur, pct)
        log.info("  %-22s %6.2fs", "TOTAL", total)


class StepTimer:
    """Context manager + decorator para medir etapas.

    >>> report = TimingReport()
    >>> with StepTimer(report, "classificacao"):
    ...     ...
    """

    def __init__(self, report: TimingReport, name: str) -> None:
        self._report = report
        self._name = name
        self._start = 0.0

    def __enter__(self) -> "StepTimer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._report.add(self._name, time.perf_counter() - self._start)


@contextmanager
def step(report: TimingReport, name: str) -> Iterator[None]:
    with StepTimer(report, name):
        yield
