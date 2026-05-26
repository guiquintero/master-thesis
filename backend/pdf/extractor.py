"""Extração de texto de PDFs de bula (MedVet/DGAV).

Versão v2.1: usa ``SemanticChunker`` (chunking em 3 níveis) em vez do antigo
``SectionSplitter`` mono-nível. O `extract()` continua a devolver
``list[PDFSection]`` para compatibilidade, mas agora cada secção pode ser
posteriormente expandida em chunks atómicos via ``extract_chunks()``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import fitz  # PyMuPDF

from backend.observability import get_logger
from backend.pdf.chunker import Chunk, SemanticChunker
from backend.pdf.section_splitter import SectionSplitter  # mantido p/ compat
from backend.pdf.table_extractor import TableExtractor

log = get_logger(__name__)

# Cabeçalho/rodapé recorrente da DGAV — removido para reduzir ruído.
_HEADER_FOOTER = re.compile(
    r"\nDireção Geral de Alimentação e Veterinária.*?Página \d+ de \d+ \n",
    re.DOTALL,
)
# Rodapé "Página X de Y" isolado.
_PAGE_FOOTER = re.compile(r"^\s*Página \d+ de \d+\s*$", re.MULTILINE)


@dataclass
class PDFSection:
    """Compatibilidade com v2.0. Para novo código usar ``Chunk``."""

    number: str
    title: str
    body: str
    has_table: bool = False

    def to_text(self) -> str:
        header = f"{self.number} {self.title}".strip()
        if header:
            return f"{header}\n{self.body}".strip()
        return self.body.strip()


class PDFExtractor:
    """Pipeline: PDF → texto limpo → secções (compat) ou chunks atómicos."""

    def __init__(
        self,
        max_pages: int = 20,
        chunker: Optional[SemanticChunker] = None,
    ) -> None:
        self.max_pages = max_pages
        self._tables = TableExtractor()
        self._splitter = SectionSplitter()
        self._chunker = chunker or SemanticChunker()

    # ----------------------------------------------------------------- core

    def _extract_text(self, pdf_path: Path) -> str:
        try:
            pages_text: list[str] = []
            with fitz.open(pdf_path) as doc:
                for idx, page in enumerate(doc):
                    if idx >= self.max_pages:
                        break
                    text = page.get_text()
                    tables = self._tables.extract_from_page(page)
                    if tables:
                        text = self._merge_tables(text, tables, idx + 1)
                    pages_text.append(text)
        except Exception as exc:  # noqa: BLE001
            log.error("Erro ao processar PDF %s: %s", pdf_path, exc)
            return ""
        full = "\n\n".join(pages_text)
        return self._clean(full)

    # ----------------------------------------------------------------- API antiga (compat)

    def extract(self, pdf_path: Path | str) -> list[PDFSection]:
        path = Path(pdf_path)
        if not path.exists():
            log.error("PDF não encontrado: %s", path)
            return []
        text = self._extract_text(path)
        if not text:
            return []
        return self._splitter.split(text)

    # ----------------------------------------------------------------- API nova (chunks)

    def extract_chunks(
        self,
        pdf_path: Path | str,
        *,
        medicamento: Optional[str] = None,
    ) -> list[Chunk]:
        """Extrai PDF e devolve já em formato de chunks atómicos."""
        path = Path(pdf_path)
        if not path.exists():
            log.error("PDF não encontrado: %s", path)
            return []
        text = self._extract_text(path)
        if not text:
            return []
        return self._chunker.chunk(text, source_pdf=str(path), medicamento=medicamento)

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _clean(text: str) -> str:
        text = _HEADER_FOOTER.sub("", text)
        text = _PAGE_FOOTER.sub("", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        return text.strip()

    @staticmethod
    def _merge_tables(text: str, tables: Iterable[str], page_num: int) -> str:
        suffix = ""
        for tbl in tables:
            suffix += f"\n\n[Tabela página {page_num}]\n{tbl}\n[/Tabela]\n"
        return text + suffix
