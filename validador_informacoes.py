# validador_informacoes.py - Sistema de validação e correção
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

class TipoErro(Enum):
    """Tipos de erros detectáveis"""
    UNIDADE_INCORRETA = "unidade_incorreta"
    VALOR_FORA_RANGE = "valor_fora_range"
    FORMATO_INVALIDO = "formato_invalido"
    INCONSISTENCIA = "inconsistencia"
    CONTEXTO_ERRADO = "contexto_errado"

@dataclass
class ErroDetectado:
    """Estrutura para erros detectados"""
    tipo: TipoErro
    valor_original: str
    valor_sugerido: Optional[str]
    confianca_erro: float
    descricao: str

class ValidadorInformacoes:
    """Valida e corrige informações extraídas de PDFs veterinários"""
    
    def __init__(self):
        # 🆕 Ranges ajustados para serem mais permissivos
        self.ranges_validos = {
            'dose_mg_kg': (0.001, 200.0),  # Era 0.01-100
            'dose_ml_kg': (0.001, 100.0),  # Era 0.01-50
            'temperatura': (-20, 40),
            'validade_anos': (1, 10),
            'validade_meses': (3, 120),
            'intervalo_dias': (0, 365),
        }
        
        self.conversoes_unidades = {
            'mcg': 'μg',
            'ug': 'μg',
            'microgramas': 'μg',
            'miligramas': 'mg',
            'mililitros': 'ml',
            'graus': '°C',
        }
        
        self.padroes_nome_medicamento = [
            r'\b\d+\s*mg/ml\b',
            r'\b\d+\s*mg\s*comprimido\b',
            r'\b\d+\s*mg\s*\/\s*comprimido\b',
        ]
        
        self.especies_validas = {
            'suínos', 'suino', 'porcos', 'leitões',
            'bovinos', 'bovino', 'vacas', 'gado',
            'equinos', 'equino', 'cavalos', 'égua',
            'cães', 'caes', 'cão', 'cao', 'cachorros',
            'gatos', 'gato', 'felinos',
            'aves', 'galinhas', 'frangos', 'perus',
            'ovinos', 'ovelhas', 'carneiros',
            'caprinos', 'cabras', 'bodes',
            'coelhos', 'coelho'
        }

    def validar_dose(self, dose_texto: str, contexto: str = "") -> Tuple[bool, Optional[ErroDetectado], Optional[str]]:
        """
        Valida uma dose extraída
        
        Returns:
            (é_valida, erro_detectado, dose_corrigida)
        """
        dose_original = dose_texto
        dose_norm = dose_texto.lower().strip()
        contexto_norm = contexto.lower()
        
        # Verificar se é concentração de nome de medicamento (falso positivo comum)
        for padrao in self.padroes_nome_medicamento:
            if re.search(padrao, dose_norm):
                erro = ErroDetectado(
                    tipo=TipoErro.CONTEXTO_ERRADO,
                    valor_original=dose_texto,
                    valor_sugerido=None,
                    confianca_erro=0.9,
                    descricao="Parece ser concentração do produto, não dosagem por peso"
                )
                return False, erro, None
        
        # Extrair valor numérico e unidade
        match_dose = re.search(
            r'(\d+(?:[.,]\d+)?)\s*(\w+)\s*(?:\/|por)\s*(\w+)',
            dose_norm
        )
        
        if not match_dose:
            match_dose = re.search(r'(\d+(?:[.,]\d+)?)\s*(\w+)', dose_norm)
            
            if not match_dose:
                erro = ErroDetectado(
                    tipo=TipoErro.FORMATO_INVALIDO,
                    valor_original=dose_texto,
                    valor_sugerido=None,
                    confianca_erro=0.8,
                    descricao="Formato de dose não reconhecido"
                )
                return False, erro, None
        
        valor_str = match_dose.group(1).replace(',', '.')
        unidade = match_dose.group(2)
        unidade_peso = match_dose.group(3) if len(match_dose.groups()) >= 3 else 'kg'
        
        try:
            valor = float(valor_str)
        except ValueError:
            erro = ErroDetectado(
                tipo=TipoErro.FORMATO_INVALIDO,
                valor_original=dose_texto,
                valor_sugerido=None,
                confianca_erro=0.95,
                descricao="Valor numérico inválido"
            )
            return False, erro, None
        
        # Normalizar unidade
        unidade_norm = self.conversoes_unidades.get(unidade, unidade)
        
        # Validar range
        if unidade_norm in ['mg', 'ml']:
            range_key = f'dose_{unidade_norm}_kg'
            
            if range_key in self.ranges_validos:
                min_val, max_val = self.ranges_validos[range_key]
                
                if not (min_val <= valor <= max_val):
                    # Verificar se pode ser erro de unidade
                    if valor > max_val and valor / 1000 >= min_val:
                        dose_corrigida = f"{valor/1000} mg/kg"
                        erro = ErroDetectado(
                            tipo=TipoErro.UNIDADE_INCORRETA,
                            valor_original=dose_texto,
                            valor_sugerido=dose_corrigida,
                            confianca_erro=0.7,
                            descricao=f"Dose muito alta ({valor} {unidade_norm}/kg), pode ser {valor/1000} mg/kg"
                        )
                        return False, erro, dose_corrigida
                    
                    # 🆕 Se valor muito baixo, apenas avisar (não bloquear)
                    if valor < min_val:
                        erro = ErroDetectado(
                            tipo=TipoErro.VALOR_FORA_RANGE,
                            valor_original=dose_texto,
                            valor_sugerido=None,
                            confianca_erro=0.5,  # Baixa confiança - apenas aviso
                            descricao=f"Dose baixa ({valor} {unidade_norm}/kg), pode ser correta para casos específicos"
                        )
                        return True, erro, None  # ✅ Válida com aviso
                    
                    erro = ErroDetectado(
                        tipo=TipoErro.VALOR_FORA_RANGE,
                        valor_original=dose_texto,
                        valor_sugerido=None,
                        confianca_erro=0.85,
                        descricao=f"Dose fora do range esperado ({min_val}-{max_val} {unidade_norm}/kg)"
                    )
                    return False, erro, None
        
        # Normalizar formato da dose
        dose_corrigida = f"{valor} {unidade_norm}/kg"
        
        if dose_corrigida != dose_original:
            return True, None, dose_corrigida
        
        return True, None, None

    def validar_temperatura(self, temp_texto: str) -> Tuple[bool, Optional[ErroDetectado], Optional[str]]:
        """Valida temperatura de armazenamento"""
        temp_norm = temp_texto.lower()
        
        match = re.search(r'(\d+)\s*(?:-\s*(\d+))?\s*°?\s*c', temp_norm)
        
        if not match:
            erro = ErroDetectado(
                tipo=TipoErro.FORMATO_INVALIDO,
                valor_original=temp_texto,
                valor_sugerido=None,
                confianca_erro=0.8,
                descricao="Formato de temperatura não reconhecido"
            )
            return False, erro, None
        
        temp1 = int(match.group(1))
        temp2 = int(match.group(2)) if match.group(2) else temp1
        
        min_temp, max_temp = self.ranges_validos['temperatura']
        
        if not (min_temp <= temp1 <= max_temp and min_temp <= temp2 <= max_temp):
            erro = ErroDetectado(
                tipo=TipoErro.VALOR_FORA_RANGE,
                valor_original=temp_texto,
                valor_sugerido=None,
                confianca_erro=0.9,
                descricao=f"Temperatura fora do range esperado ({min_temp} a {max_temp}°C)"
            )
            return False, erro, None
        
        # Normalizar formato
        if temp1 == temp2:
            temp_corrigida = f"{temp1}°C"
        else:
            temp_corrigida = f"{temp1}-{temp2}°C"
        
        if temp_corrigida != temp_texto:
            return True, None, temp_corrigida
        
        return True, None, None

    def validar_intervalo_seguranca(self, intervalo_texto: str) -> Tuple[bool, Optional[ErroDetectado], Optional[str]]:
        """Valida intervalo de segurança/tempo de espera"""
        intervalo_norm = intervalo_texto.lower()
        
        match = re.search(r'(\d+)\s*(dia|dias|hora|horas)', intervalo_norm)
        
        if not match:
            erro = ErroDetectado(
                tipo=TipoErro.FORMATO_INVALIDO,
                valor_original=intervalo_texto,
                valor_sugerido=None,
                confianca_erro=0.8,
                descricao="Formato de intervalo não reconhecido"
            )
            return False, erro, None
        
        valor = int(match.group(1))
        unidade = match.group(2)
        
        # Converter horas para dias se necessário
        if 'hora' in unidade:
            valor_dias = valor / 24
            
            if valor_dias > 1:
                intervalo_corrigido = f"{valor_dias:.1f} dias"
                return True, None, intervalo_corrigido
        
        # 🆕 Validação mais permissiva para intervalos
        min_dias, max_dias = self.ranges_validos['intervalo_dias']
        
        if 'dia' in unidade and not (min_dias <= valor <= max_dias):
            # Apenas aviso, não erro fatal
            erro = ErroDetectado(
                tipo=TipoErro.VALOR_FORA_RANGE,
                valor_original=intervalo_texto,
                valor_sugerido=None,
                confianca_erro=0.5,  # Baixa confiança
                descricao=f"Intervalo atípico (0-{max_dias} dias é comum)"
            )
            return True, erro, None  # ✅ Válido com aviso
        
        return True, None, None

    def validar_conjunto_informacoes(self, informacoes: Dict) -> Dict:
        """
        Valida um conjunto completo de informações extraídas
        
        Returns:
            Dict com informações validadas e erros detectados
        """
        resultado = {
            'informacoes_validadas': {},
            'erros_detectados': [],
            'avisos': [],
            'correcoes_aplicadas': []
        }
        
        # Validar doses
        if 'doses' in informacoes:
            doses_validadas = []
            
            for info_dose in informacoes['doses']:
                dose_texto = info_dose.conteudo
                contexto = info_dose.contexto
                
                valida, erro, corrigida = self.validar_dose(dose_texto, contexto)
                
                if erro:
                    if erro.confianca_erro >= 0.8:
                        resultado['erros_detectados'].append({
                            'tipo': 'dose',
                            'erro': erro,
                            'info_original': info_dose
                        })
                    else:
                        resultado['avisos'].append({
                            'tipo': 'dose',
                            'erro': erro,
                            'info_original': info_dose
                        })
                
                if valida:
                    if corrigida:
                        info_dose.conteudo = corrigida
                        resultado['correcoes_aplicadas'].append({
                            'tipo': 'dose',
                            'original': dose_texto,
                            'corrigida': corrigida
                        })
                    
                    doses_validadas.append(info_dose)
            
            resultado['informacoes_validadas']['doses'] = doses_validadas
        
        # Validar temperaturas
        if 'armazenamento' in informacoes:
            temps_validadas = []
            
            for info_temp in informacoes['armazenamento']:
                temp_texto = info_temp.conteudo
                
                valida, erro, corrigida = self.validar_temperatura(temp_texto)
                
                if erro:
                    resultado['erros_detectados'].append({
                        'tipo': 'temperatura',
                        'erro': erro,
                        'info_original': info_temp
                    })
                
                if valida:
                    if corrigida:
                        info_temp.conteudo = corrigida
                        resultado['correcoes_aplicadas'].append({
                            'tipo': 'temperatura',
                            'original': temp_texto,
                            'corrigida': corrigida
                        })
                    
                    temps_validadas.append(info_temp)
            
            resultado['informacoes_validadas']['armazenamento'] = temps_validadas
        
        # Validar intervalos
        if 'intervalos_seguranca' in informacoes:
            intervalos_validados = []
            
            for info_intervalo in informacoes['intervalos_seguranca']:
                intervalo_texto = info_intervalo.conteudo
                
                valida, erro, corrigida = self.validar_intervalo_seguranca(intervalo_texto)
                
                if erro:
                    resultado['avisos'].append({
                        'tipo': 'intervalo',
                        'erro': erro,
                        'info_original': info_intervalo
                    })
                
                if valida:
                    if corrigida:
                        info_intervalo.conteudo = corrigida
                        resultado['correcoes_aplicadas'].append({
                            'tipo': 'intervalo',
                            'original': intervalo_texto,
                            'corrigida': corrigida
                        })
                    
                    intervalos_validados.append(info_intervalo)
            
            resultado['informacoes_validadas']['intervalos_seguranca'] = intervalos_validados
        
        # Copiar demais informações não validadas
        for chave in ['administracao', 'composicao', 'reacoes_adversas', 'receita', 'especies']:
            if chave in informacoes:
                resultado['informacoes_validadas'][chave] = informacoes[chave]
        
        return resultado

    def gerar_relatorio_validacao(self, resultado_validacao: Dict) -> str:
        """Gera relatório legível da validação"""
        linhas = []
        linhas.append("=" * 80)
        linhas.append("RELATÓRIO DE VALIDAÇÃO")
        linhas.append("=" * 80)
        
        if resultado_validacao['correcoes_aplicadas']:
            linhas.append("\n✅ CORREÇÕES APLICADAS:")
            for correcao in resultado_validacao['correcoes_aplicadas']:
                linhas.append(f"\n  • Tipo: {correcao['tipo']}")
                linhas.append(f"    Original: {correcao['original']}")
                linhas.append(f"    Corrigida: {correcao['corrigida']}")
        
        if resultado_validacao['erros_detectados']:
            linhas.append("\n❌ ERROS DETECTADOS:")
            for erro_info in resultado_validacao['erros_detectados']:
                erro = erro_info['erro']
                linhas.append(f"\n  • Tipo: {erro_info['tipo']}")
                linhas.append(f"    Valor: {erro.valor_original}")
                linhas.append(f"    Erro: {erro.descricao}")
                linhas.append(f"    Confiança: {erro.confianca_erro*100:.0f}%")
                if erro.valor_sugerido:
                    linhas.append(f"    Sugestão: {erro.valor_sugerido}")
        
        if resultado_validacao['avisos']:
            linhas.append("\n⚠️  AVISOS:")
            for aviso_info in resultado_validacao['avisos']:
                aviso = aviso_info['erro']
                linhas.append(f"\n  • Tipo: {aviso_info['tipo']}")
                linhas.append(f"    Valor: {aviso.valor_original}")
                linhas.append(f"    Aviso: {aviso.descricao}")
        
        linhas.append("\n" + "=" * 80)
        linhas.append("RESUMO:")
        linhas.append(f"  • Correções: {len(resultado_validacao['correcoes_aplicadas'])}")
        linhas.append(f"  • Erros: {len(resultado_validacao['erros_detectados'])}")
        linhas.append(f"  • Avisos: {len(resultado_validacao['avisos'])}")
        linhas.append("=" * 80)
        
        return "\n".join(linhas)