"""Chunking semântico em 3 níveis (P1 — Sprint v2.1).

Substitui o `SectionSplitter` mono-nível antigo, que devolvia secções SmPC
inteiras (frequentemente 4 000–8 000 chars) e degradava o retrieval para
"tudo-ou-nada".

# Estratégia

Cada PDF de bula é decomposto em ``Chunk`` atómicos. Há 3 níveis:

  Nível 1: SECÇÃO SmPC (4.1, 4.9, 6.4...)  ──► dá o contexto estrutural
  Nível 2: PARÁGRAFO dentro da secção        ──► granularidade fina
  Nível 3: TABELA (cada tabela = 1 chunk)    ──► autocontido

# Overlap

Para evitar que informação atravessando a fronteira entre dois parágrafos se
perca, aplicamos overlap configurável (default ``overlap_tokens=80``).
Cada chunk leva consigo a "cauda" do anterior + a "cabeça" do próximo.

# Robustez do splitter SmPC

A regex de header agora tolera:
- header em maiúsculas: ``"4.9 POSOLOGIA"``
- múltiplos espaços
- ausência do ponto final no número (``"4.9 Posologia"`` vs ``"4.9. Posologia"``)
- linhas concatenadas pelo PyMuPDF

Se mesmo assim falhar, devolve UMA secção com o texto inteiro e o chunker de
nível 2 (parágrafos) garante que ainda há chunks utilizáveis.

# ANTES vs DEPOIS

Antes (`SectionSplitter`):
    PDF de 12 páginas → 6 PDFSection (uma por secção SmPC) → cada uma com
    4 000–8 000 chars → retrieval devolve secção inteira

Depois (`SemanticChunker`):
    PDF de 12 páginas → 6 secções → 35 Chunk de ~500 tokens (com overlap) +
    3 Chunk de tabela → retrieval devolve top-k atómicos
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields
from typing import Iterable, Optional

from backend.observability import get_logger

log = get_logger(__name__)


# Regex tolerante: aceita "4.9", "4.9.", maiúsculas, hifens, espaços múltiplos.
_SECTION_HEADER = re.compile(
    r"(?m)^\s*(?P<num>\d{1,2}(?:\.\d{1,2}){0,2})\.?\s+(?P<title>[^\n]{2,200})$"
)

# Marcadores de tabela inseridos pelo PDFExtractor (extractor.py).
_TABLE_OPEN = re.compile(r"\[Tabela página (\d+)\]\n", re.IGNORECASE)
_TABLE_CLOSE = "[/Tabela]"


@dataclass
class Chunk:
    """Unidade atómica de retrieval.

    Metadata rica permite filtro pré-retrieval no vector store
    (ex.: ``where={"section_num": "4.9", "is_table": false}``).
    """

    text: str
    section_num: str = ""       # "4.9" ou ""
    section_title: str = ""     # "Posologia e via de administração"
    paragraph_idx: int = 0      # 0, 1, 2... dentro da secção
    is_table: bool = False
    page: Optional[int] = None  # nº da página (se conhecido — tabelas têm-no)
    source_pdf: Optional[str] = None  # path/url do PDF
    medicamento: Optional[str] = None
    char_count: int = 0

    def __post_init__(self) -> None:
        if self.char_count == 0:
            self.char_count = len(self.text)

    def to_text(self) -> str:
        """Texto pronto a colocar no prompt do LLM, com header de secção."""
        prefix = ""
        if self.section_num or self.section_title:
            prefix = f"[Secção {self.section_num} {self.section_title}".strip() + "]\n"
        if self.is_table:
            prefix = (prefix or "") + "[Tabela]\n"
        return f"{prefix}{self.text.strip()}"

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, data: dict) -> "Chunk":
        valid = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in valid})


@dataclass
class SemanticChunker:
    """Chunker em 3 níveis (secção → parágrafo → tabela), com overlap.

    Parâmetros calibrados para bulas SmPC (texto técnico, secções pequenas).
    Para corpus diferente, ajustar ``target_tokens`` e ``overlap_tokens``.
    """

    target_tokens: int = 350         # tamanho-alvo do chunk de parágrafo
    overlap_tokens: int = 80          # sobreposição entre chunks consecutivos
    min_chunk_tokens: int = 40        # abaixo disto, agrega com o vizinho
    chars_per_token: float = 4.0      # aproximação grosseira pt-PT

    @property
    def target_chars(self) -> int:
        return int(self.target_tokens * self.chars_per_token)

    @property
    def overlap_chars(self) -> int:
        return int(self.overlap_tokens * self.chars_per_token)

    @property
    def min_chunk_chars(self) -> int:
        return int(self.min_chunk_tokens * self.chars_per_token)

    # ----------------------------------------------------------------- API

    def chunk(self, text: str, *, source_pdf: Optional[str] = None,
              medicamento: Optional[str] = None) -> list[Chunk]:
        """Divide um PDF inteiro (texto bruto) em Chunks atómicos."""
        sections = self._split_by_section(text)
        out: list[Chunk] = []
        for sec_num, sec_title, sec_body in sections:
            out.extend(self._chunk_section(
                sec_num, sec_title, sec_body,
                source_pdf=source_pdf, medicamento=medicamento,
            ))
        log.debug("Chunker: %d secções → %d chunks", len(sections), len(out))
        return out

    # ----------------------------------------------------------------- Nível 1

    def _split_by_section(self, text: str) -> list[tuple[str, str, str]]:
        """Devolve list[(section_num, section_title, body)].

        Se não houver headers SmPC reconhecíveis, devolve uma única tupla
        ("", "", text) — o nível 2 ainda produz chunks utilizáveis.
        """
        matches = list(_SECTION_HEADER.finditer(text))
        if not matches:
            return [("", "", text.strip())]

        sections = []
        for i, m in enumerate(matches):
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            sections.append((m.group("num"), m.group("title").strip(), body))
        return sections

    # ----------------------------------------------------------------- Níveis 2 + 3

    def _chunk_section(
        self,
        section_num: str,
        section_title: str,
        body: str,
        *,
        source_pdf: Optional[str],
        medicamento: Optional[str],
    ) -> list[Chunk]:
        out: list[Chunk] = []

        # Nível 3: tabelas saem como chunks independentes.
        non_table_text, tables = self._extract_tables(body)
        for page, tbl_text in tables:
            out.append(Chunk(
                text=tbl_text,
                section_num=section_num,
                section_title=section_title,
                paragraph_idx=-1,  # convenção: tabelas usam -1
                is_table=True,
                page=page,
                source_pdf=source_pdf,
                medicamento=medicamento,
            ))

        # Nível 2: parágrafos do texto não-tabular.
        paragraphs = self._paragraph_split(non_table_text)
        # Junta parágrafos pequenos até atingir target_chars; aplica overlap.
        for idx, para in enumerate(self._pack_with_overlap(paragraphs)):
            out.append(Chunk(
                text=para,
                section_num=section_num,
                section_title=section_title,
                paragraph_idx=idx,
                is_table=False,
                source_pdf=source_pdf,
                medicamento=medicamento,
            ))
        return out

    @staticmethod
    def _extract_tables(body: str) -> tuple[str, list[tuple[int, str]]]:
        """Separa tabelas marcadas [Tabela página N]...[/Tabela] do texto."""
        tables: list[tuple[int, str]] = []
        cursor = 0
        out = []
        while True:
            m = _TABLE_OPEN.search(body, cursor)
            if not m:
                out.append(body[cursor:])
                break
            out.append(body[cursor:m.start()])
            page = int(m.group(1))
            close = body.find(_TABLE_CLOSE, m.end())
            if close == -1:
                # tabela sem fecho — agrega o resto e termina
                tables.append((page, body[m.end():].strip()))
                cursor = len(body)
                break
            tables.append((page, body[m.end():close].strip()))
            cursor = close + len(_TABLE_CLOSE)
        return ("".join(out).strip(), tables)

    @staticmethod
    def _paragraph_split(text: str) -> list[str]:
        """Quebra por linhas em branco; depois por sentenças longas se necessário."""
        if not text.strip():
            return []
        # Quebra primária: linhas em branco
        paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        # Quebra secundária para parágrafos demasiado longos: por sentença
        out: list[str] = []
        for p in paras:
            if len(p) <= 2000:
                out.append(p)
                continue
            # Sentenças (.! ?) preservando o terminador.
            sentences = re.split(r"(?<=[\.!?])\s+", p)
            buf = ""
            for s in sentences:
                if len(buf) + len(s) + 1 <= 1500:
                    buf = (buf + " " + s).strip() if buf else s
                else:
                    if buf:
                        out.append(buf)
                    buf = s
            if buf:
                out.append(buf)
        return out

    def _pack_with_overlap(self, paragraphs: list[str]) -> list[str]:
        """Junta parágrafos pequenos até ~target_chars com overlap do anterior."""
        if not paragraphs:
            return []
        packed: list[str] = []
        current = ""
        for para in paragraphs:
            if not current:
                current = para
                continue
            if len(current) + len(para) + 1 <= self.target_chars:
                current = current + "\n\n" + para
            else:
                packed.append(current)
                # Overlap: leva cauda do current para o próximo
                overlap = current[-self.overlap_chars:] if self.overlap_chars > 0 else ""
                current = (overlap + "\n\n" + para).strip() if overlap else para
        if current:
            packed.append(current)

        # Remove chunks demasiado pequenos (agrega com vizinho)
        return self._merge_tiny(packed)

    def _merge_tiny(self, chunks: list[str]) -> list[str]:
        if not chunks:
            return []
        out = [chunks[0]]
        for c in chunks[1:]:
            if len(c) < self.min_chunk_chars and out:
                out[-1] = out[-1] + "\n\n" + c
            else:
                out.append(c)
        return out


__all__ = ["Chunk", "SemanticChunker"]
