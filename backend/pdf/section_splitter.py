"""Divisor por secções SmPC.

Os PDFs MedVet seguem o template oficial (RCM/SmPC):
  1. Nome
  2. Composição
  3. Forma farmacêutica
  4.1 Espécies-alvo
  4.2 Indicações
  4.3 Contra-indicações
  4.4 Advertências especiais
  4.5 Precauções
  4.6 Reações adversas
  4.7 Gravidez/lactação
  4.8 Interações
  4.9 Posologia / Administração
  4.10 Sobredosagem
  4.11 Intervalos de segurança
  5. Propriedades farmacológicas
  6.1 Excipientes
  6.4 Conservação
  ...

Esse split estrutural permite retrieval por secção, que é muito mais preciso
que filtragem por palavra-chave em texto contínuo.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.pdf.extractor import PDFSection

_SECTION_HEADER = re.compile(
    r"^(?P<num>\d+(?:\.\d+)*)\.\s+(?P<title>[^\n]{2,120})$",
    re.MULTILINE,
)


class SectionSplitter:
    def split(self, text: str) -> list["PDFSection"]:
        from backend.pdf.extractor import PDFSection  # local to avoid cycle

        matches = list(_SECTION_HEADER.finditer(text))
        if not matches:
            # PDF não-estruturado: devolve uma única secção.
            return [PDFSection(number="", title="", body=text.strip(), has_table="[Tabela" in text)]

        sections: list[PDFSection] = []
        for idx, m in enumerate(matches):
            start = m.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            sections.append(
                PDFSection(
                    number=m.group("num"),
                    title=m.group("title").strip(),
                    body=body,
                    has_table="[Tabela" in body,
                )
            )
        return sections
