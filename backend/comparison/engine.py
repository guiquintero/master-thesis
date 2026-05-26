"""Lógica de comparação e busca de alternativas.

Substitui `_realizar_consulta_dupla`, `_realizar_busca_comparacao_simples` e
seus formatadores na god-class antiga.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.entities import Entities
from backend.medvet import (
    ListingResult,
    MedVetSearch,
    parse_substancias_ativas,
)
from backend.observability import get_logger

log = get_logger(__name__)


@dataclass
class ComparisonEngine:
    search: MedVetSearch

    def find_alternatives(self, entities: Entities, *, tipo_pergunta: str = "alternativo") -> str:
        if not entities.medicamento:
            return "Não foi possível identificar o medicamento de referência."

        log.info("Comparison: %s (tipo=%s)", entities.medicamento, tipo_pergunta)

        # Fase 1: busca o medicamento de referência
        ref_results = self.search.search(entities.medicamento)
        if not ref_results:
            return f"Não foi possível encontrar informações sobre '{entities.medicamento}'."

        ref = ref_results[0]
        substancias = ref.substancias_ativas
        if not substancias:
            substancias = parse_substancias_ativas(ref.informacoes_visiveis)
        if not substancias:
            return f"Não foi possível identificar substâncias activas de '{entities.medicamento}'."

        if len(substancias) == 1:
            return self._format_single(
                ref=entities.medicamento,
                principio=substancias[0],
                results=self._search_filter(substancias[0], entities, exclude=entities.medicamento),
                tipo=tipo_pergunta,
                especie=entities.especie_alvo,
            )

        per_subst = {}
        for s in substancias:
            res = self._search_filter(s, entities, exclude=entities.medicamento)
            if res:
                per_subst[s] = res

        if not per_subst:
            return (
                f"Não foram encontrados medicamentos alternativos para nenhuma das "
                f"substâncias de '{entities.medicamento}'."
            )

        return self._format_multi(
            ref=entities.medicamento,
            substancias=substancias,
            per_subst=per_subst,
            tipo=tipo_pergunta,
            especie=entities.especie_alvo,
        )

    # ----------------------------------------------------------------- helpers

    def _search_filter(self, term: str, entities: Entities, *, exclude: str) -> list[ListingResult]:
        query = term
        if entities.especie_alvo:
            query += f" {entities.especie_alvo}"
        results = self.search.search(query)
        return [r for r in results if exclude.lower() not in r.nome.lower()]

    @staticmethod
    def _header(tipo: str, ref: str) -> str:
        labels = {
            "alternativo": f"Medicamentos alternativos ao {ref}",
            "substituto": f"Medicamentos substitutos do {ref}",
            "equivalente": f"Medicamentos equivalentes ao {ref}",
        }
        return labels.get(tipo, f"Medicamentos com mesmo princípio activo que {ref}")

    def _format_single(
        self,
        ref: str,
        principio: str,
        results: list[ListingResult],
        tipo: str,
        especie: Optional[str],
    ) -> str:
        if not results:
            return f"Apenas '{ref}' foi encontrado com '{principio}'."

        lines = [f"**{self._header(tipo, ref)}:**\n"]
        lines.append(f"Princípio activo: {principio}")
        if especie:
            lines.append(f"Espécie: {especie}")
        lines.append(f"\nMedicamentos encontrados ({len(results)}):\n")
        for i, item in enumerate(results, 1):
            lines.append(self._format_item(i, item, indent=""))
        lines.append(f"\nTotal: {len(results)} medicamentos alternativos.")
        return "\n".join(lines)

    def _format_multi(
        self,
        ref: str,
        substancias: list[str],
        per_subst: dict[str, list[ListingResult]],
        tipo: str,
        especie: Optional[str],
    ) -> str:
        lines = [f"**{self._header(tipo, ref)}:**\n"]
        lines.append(f"{ref} contém múltiplas substâncias activas:")
        for s in substancias:
            lines.append(f"  - {s}")
        if especie:
            lines.append(f"\nEspécie-alvo: {especie}")

        total = 0
        for i, s in enumerate(substancias, 1):
            lines.append(f"\n## {i}. {s}")
            results = per_subst.get(s, [])
            if not results:
                lines.append("Nenhum medicamento adicional encontrado.")
                continue
            total += len(results)
            lines.append(f"{len(results)} medicamento(s):")
            for j, item in enumerate(results, 1):
                lines.append(self._format_item(j, item, indent="  "))

        lines.append(f"\nTotal: {total} medicamentos alternativos em {len(per_subst)} substância(s).")
        return "\n".join(lines)

    @staticmethod
    def _format_item(i: int, item: ListingResult, *, indent: str) -> str:
        out = [f"{indent}{i}. **{item.nome}**"]
        if item.especies:
            out.append(f"{indent}   - Espécies: {item.especies}")
        if item.forma_farmaceutica:
            out.append(f"{indent}   - Forma: {item.forma_farmaceutica}")
        if item.link:
            out.append(f"{indent}   - Link: {item.link}")
        return "\n".join(out)
