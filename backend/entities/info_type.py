"""Tipos de informação que o utilizador pode pedir. Fonte única.

Substitui as 4 versões espalhadas no código antigo
(`_identificar_tipo_informacao`, blocos inline em `_consultar_ollama_otimizado`,
`_buscar_informacao_direta_pdf`, `_gerar_prompt_especializado_pdf`).

Cada tipo associa-se a:
- palavras-chave (regex word-boundary)
- número(s) da secção SmPC (Resumo das Características do Medicamento) onde
  tipicamente vive a informação no PDF da MedVet
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class InfoType(str, Enum):
    DOSE = "dose"
    ARMAZENAMENTO = "armazenamento"
    ADMINISTRACAO = "administracao"
    COMPOSICAO = "composicao"
    INDICACAO = "indicacao"
    ESPECIES = "especies"
    REACOES = "reacoes"
    INTERVALOS = "intervalos"
    CONTRAINDICACOES = "contraindicacoes"
    RECEITA = "receita"
    FABRICANTE = "fabricante"
    APRESENTACAO = "apresentacao"
    GERAL = "geral"


@dataclass(frozen=True)
class InfoTypeSpec:
    info_type: InfoType
    keywords: tuple[str, ...]
    smpc_sections: tuple[str, ...]  # 4.1, 4.9, 6.4, etc


SPECS: tuple[InfoTypeSpec, ...] = (
    InfoTypeSpec(InfoType.DOSE, ("dose", "dosagem", "posologia", "quanto administrar"), ("4.9", "4.2")),
    InfoTypeSpec(InfoType.ARMAZENAMENTO, ("armazenamento", "armazenar", "armazenado", "conservar", "conservação", "guardar", "validade"), ("6.4", "6.3")),
    InfoTypeSpec(InfoType.ADMINISTRACAO, ("administração", "administrar", "via de administração", "como usar", "forma de administração"), ("4.9",)),
    InfoTypeSpec(InfoType.COMPOSICAO, ("composição", "princípio ativo", "principio ativo", "substância ativa", "substancia ativa", "componentes"), ("2.", "6.1")),
    InfoTypeSpec(InfoType.INDICACAO, ("indicação", "indicado", "usado para", "serve para", "para que serve", "utilização"), ("4.2",)),
    InfoTypeSpec(InfoType.ESPECIES, ("espécies", "espécie", "espécies-alvo", "espécies alvo", "para que espécies"), ("4.1",)),
    InfoTypeSpec(InfoType.REACOES, ("reações adversas", "efeitos colaterais", "efeitos indesejáveis", "reações"), ("4.6",)),
    InfoTypeSpec(InfoType.INTERVALOS, ("intervalos", "intervalo de segurança", "tempo de espera", "carência"), ("4.11",)),
    InfoTypeSpec(InfoType.CONTRAINDICACOES, ("contraindicações", "contraindicação", "contra-indicações", "não deve ser usado"), ("4.3",)),
    InfoTypeSpec(InfoType.RECEITA, ("receita médica", "receita veterinária", "prescrição"), ("9.", "10.")),
    InfoTypeSpec(InfoType.FABRICANTE, ("fabricante", "laboratório", "titular"), ("7.",)),
    InfoTypeSpec(InfoType.APRESENTACAO, ("apresentação", "embalagem", "forma farmacêutica"), ("3.", "6.5")),
)


_WORD = lambda kw: re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
_COMPILED = [(spec, [_WORD(kw) for kw in spec.keywords]) for spec in SPECS]


def identify_info_type(query: str) -> InfoType:
    for spec, patterns in _COMPILED:
        if any(p.search(query) for p in patterns):
            return spec.info_type
    return InfoType.GERAL


def smpc_sections_for(info_type: InfoType) -> tuple[str, ...]:
    for spec in SPECS:
        if spec.info_type == info_type:
            return spec.smpc_sections
    return ()
