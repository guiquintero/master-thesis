"""Templates de prompt por tipo de consulta.

Substituem os 5 montadores espalhados pelo código antigo
(`_gerar_prompt_otimizado`, `_gerar_prompt_direto`, `_gerar_prompt_especializado_pdf`,
`_gerar_prompt_super_restritivo_dose`, inline no wrapper).

v2.1 (P5): prompts pedem output JSON estruturado.
Schema:
    {
      "resposta": "texto em pt-PT",
      "encontrada_no_documento": true|false,
      "fontes": [{"secao": "4.9", "trecho": "..."}],
      "confianca": 0.0..1.0
    }
"""

from __future__ import annotations

from typing import Iterable, Optional


JSON_SCHEMA_HINT = (
    "Responde APENAS com um objecto JSON válido, sem texto adicional, "
    "no formato:\n"
    "{\n"
    '  "resposta": "<texto em pt-PT, conciso, citando valores do documento>",\n'
    '  "encontrada_no_documento": <true|false>,\n'
    '  "fontes": [{"secao": "<ex. 4.9>", "trecho": "<excerto relevante>"}],\n'
    '  "confianca": <0.0 a 1.0>\n'
    "}\n"
    "Se a informação não estiver no contexto, define encontrada_no_documento=false, "
    "resposta=\"Informação não encontrada no documento.\" e confianca<=0.3."
)


def build_rag_prompt(
    pergunta: str,
    *,
    medicamento: str,
    secoes: Iterable[str],
    especie: Optional[str] = None,
    tipo_info: Optional[str] = None,
) -> str:
    """Prompt principal — síntese baseada em trechos recuperados."""
    secoes_txt = "\n\n---\n\n".join(s.strip() for s in secoes if s and s.strip())

    foco = ""
    if tipo_info:
        focos = {
            "dose": "Procura a dose por peso (mg/kg, ml/kg) e a frequência, idealmente específicas para a espécie indicada.",
            "armazenamento": "Procura a temperatura, condições e prazo de validade.",
            "especies": "Lista as espécies-alvo.",
            "composicao": "Lista a(s) substância(s) activa(s) e respectivas concentrações.",
            "indicacao": "Lista as indicações terapêuticas.",
            "contraindicacoes": "Lista as contra-indicações.",
            "reacoes": "Lista reações adversas / efeitos indesejáveis.",
            "intervalos": "Indica o intervalo de segurança / tempo de espera.",
        }
        if tipo_info in focos:
            foco = f"Foco: {focos[tipo_info]}\n\n"

    especie_txt = f"\nEspécie-alvo: {especie}" if especie else ""

    return (
        f"Medicamento: {medicamento}{especie_txt}\n\n"
        f"{foco}"
        f"Contexto (excertos do documento oficial):\n{secoes_txt}\n\n"
        f"Pergunta: {pergunta}\n\n"
        f"{JSON_SCHEMA_HINT}"
    )


def build_dose_prompt(
    pergunta: str,
    *,
    medicamento: str,
    secoes: Iterable[str],
    doses_extraidas: list[str],
    especie: Optional[str] = None,
) -> str:
    """Prompt restritivo para perguntas de dose, com doses pré-extraídas."""
    secoes_txt = "\n\n---\n\n".join(s.strip() for s in secoes if s and s.strip())
    doses_txt = "\n".join(f"- {d}" for d in doses_extraidas) or "- (nenhuma identificada)"
    especie_txt = f"\nEspécie-alvo: {especie}" if especie else ""

    return (
        f"Medicamento: {medicamento}{especie_txt}\n\n"
        f"Doses identificadas no documento (usa apenas estas):\n{doses_txt}\n\n"
        f"Contexto:\n{secoes_txt}\n\n"
        f"Pergunta: {pergunta}\n\n"
        "Regras:\n"
        "- Usa apenas valores da lista \"Doses identificadas\" acima.\n"
        "- Não confundas concentração do produto (ex.: 15 mg/ml no nome) com dose por peso (mg/kg).\n"
        "- Se houver dose específica para a espécie indicada, prioriza-a.\n"
        "- Se não houver dose para essa espécie, encontrada_no_documento=false.\n\n"
        f"{JSON_SCHEMA_HINT}"
    )


def build_classification_prompt(query: str) -> str:
    """Prompt JSON-mode para classificação (usado apenas como fallback)."""
    return (
        "Classifica a pergunta em uma de duas categorias:\n"
        "- \"medicamento\": pergunta sobre UM medicamento específico\n"
        "- \"comparacao\": comparar/listar VÁRIOS medicamentos "
        "(inclui \"alternativo\", \"substituto\", \"equivalente\", \"mesmo princípio ativo\")\n\n"
        "Responde estritamente em JSON com este formato:\n"
        "{\n"
        "  \"categoria\": \"medicamento\" | \"comparacao\",\n"
        "  \"termo_busca\": \"string (nome do medicamento ou substância)\",\n"
        "  \"substancia_ativa\": \"string\",\n"
        "  \"especie_alvo\": \"string\",\n"
        "  \"forma_farmaceutica\": \"string\"\n"
        "}\n\n"
        f"Pergunta: {query}"
    )


def build_comparison_prompt(
    pergunta: str,
    *,
    medicamentos: Iterable[dict],
) -> str:
    """Prompt para resumir/comparar lista de medicamentos recuperados."""
    import json

    lista_txt = json.dumps(list(medicamentos), ensure_ascii=False, indent=2)
    return (
        f"Lista de medicamentos disponíveis:\n```json\n{lista_txt}\n```\n\n"
        f"Pergunta: {pergunta}\n\n"
        "Compara apenas os medicamentos presentes na lista. "
        "Organiza por tópicos: princípio ativo, espécies, forma farmacêutica. "
        "Se a lista estiver vazia, responde \"Nenhum medicamento encontrado.\""
    )
