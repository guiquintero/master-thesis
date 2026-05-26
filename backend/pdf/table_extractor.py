"""Detecção de tabelas via análise de layout do PyMuPDF.

Simplificação do `PDFProcessor._extrair_tabelas_estruturadas` legado.
Sem emojis no output (que poluíam contexto da LLM).
"""

from __future__ import annotations

from typing import Iterable


class TableExtractor:
    """Extrai tabelas de uma página fitz.Page por agrupamento de spans."""

    def extract_from_page(self, page) -> list[str]:  # page: fitz.Page
        try:
            blocks = page.get_text("dict").get("blocks", [])
        except Exception:  # noqa: BLE001
            return []

        rows: list[list[tuple[str, float]]] = []
        current: list[tuple[str, float]] = []
        y_prev = None

        for block in blocks:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if not text:
                        continue
                    bbox = span.get("bbox", (0, 0, 0, 0))
                    y, x = bbox[1], bbox[0]
                    if y_prev is not None and abs(y - y_prev) > 5:
                        if len(current) > 1:
                            rows.append(sorted(current, key=lambda t: t[1]))
                        current = []
                    current.append((text, x))
                    y_prev = y

        if len(current) > 1:
            rows.append(sorted(current, key=lambda t: t[1]))

        if len(rows) < 2:
            return []

        # Verifica consistência (variação no nº de colunas)
        col_counts = {len(r) for r in rows}
        if len(col_counts) > 3:
            return []

        return [self._format(rows)]

    @staticmethod
    def _format(rows: Iterable[list[tuple[str, float]]]) -> str:
        rows = list(rows)
        header = " | ".join(t[0] for t in rows[0])
        out = [header, "-" * len(header)]
        for r in rows[1:]:
            out.append(" | ".join(t[0] for t in r))
        return "\n".join(out)
