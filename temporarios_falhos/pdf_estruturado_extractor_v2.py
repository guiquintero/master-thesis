# pdf_estruturado_extractor_v2.py - VERSÃO MELHORADA
import re
import fitz
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from enum import Enum
import json
from termcolor import colored
from collections import OrderedDict

class SecaoPDF(Enum):
    """Mapeamento das seções padrão de bulas veterinárias DGAV"""
    NOME_COMPOSICAO = "1"
    FORMA_FARMACEUTICA = "2"
    INFORMACOES_CLINICAS = "3"
    ESPECIES_ALVO = "4.1"
    INDICACOES = "4.2"
    CONTRAINDICACOES = "4.3"
    ADVERTENCIAS = "4.4"
    PRECAUCOES = "4.5"
    REACOES_ADVERSAS = "4.6"
    GRAVIDEZ_LACTACAO = "4.7"
    INTERACOES = "4.8"
    POSOLOGIA_ADMINISTRACAO = "4.9"
    SOBREDOSAGEM = "4.10"
    TEMPO_ESPERA = "4.11"
    PROPRIEDADES_FARMACOLOGICAS = "5"
    COMPOSICAO_QUALITATIVA = "6.1"
    INCOMPATIBILIDADES = "6.2"
    VALIDADE = "6.3"
    PRECAUCOES_CONSERVACAO = "6.4"
    NATUREZA_EMBALAGEM = "6.5"
    TITULAR_AUTORIZACAO = "7"

@dataclass
class InformacaoExtraida:
    """Estrutura para informação extraída com metadados"""
    conteudo: str
    secao: str
    confianca: float  # 0.0 a 1.0
    pagina: int
    metodo_extracao: str
    contexto: str = ""

class PDFEstruturadoExtractorV2:
    """
    Extrator avançado MELHORADO com foco em intervalos de segurança e precisão
    """
    
    def __init__(self):
        self.secoes_mapeadas = {}
        self.tabelas_detectadas = []
        self.metadados = {}
        
        # 🆕 PADRÕES MELHORADOS - Especialmente para intervalos
        self.padroes_extracao = {
            'dose': [
                r'(\d+(?:[.,]\d+)?)\s*(?:mg|ml|g|mcg|μg|UI)\s*(?:\/|por)\s*kg',
                r'(\d+(?:[.,]\d+)?)\s*(?:mg|ml|g|mcg|μg|UI)\s*por\s+(?:kg|quilograma)',
                r'dose\s+(?:de|:)?\s*(\d+(?:[.,]\d+)?)\s*(?:mg|ml|g)',
                r'(\d+(?:[.,]\d+)?)\s*(?:mg|ml|g)\/kg\s+(?:de\s+)?peso(?:\s+vivo)?',
                r'(\d+(?:[.,]\d+)?)\s*a\s*(\d+(?:[.,]\d+)?)\s*(?:mg|ml)\/kg',  # Range
            ],
            'via_administracao': [
                r'via\s+(oral|intramuscular|intravenosa|subcutânea|subcutanea|tópica|topica|im|iv|sc|cutânea|cutanea)',
                r'administra[çc][ãa]o\s+(oral|intramuscular|intravenosa|subcutânea|subcutanea|tópica|topica)',
                r'por\s+via\s+(oral|intramuscular|intravenosa|subcutânea|subcutanea|tópica|topica)',
                r'uso\s+(oral|tópico|topico|cutâneo|cutaneo|injetável|injetavel)',
            ],
            'temperatura': [
                r'(?:conservar|armazenar|manter)\s+(?:a|entre|abaixo de)?\s*(\d+)\s*°?\s*[Cc]',
                r'temperatura\s+(?:de\s+)?(?:até|inferior a|não superior a|abaixo de)?\s*(\d+)\s*°?\s*[Cc]',
                r'(\d+)\s*-\s*(\d+)\s*°?\s*[Cc]',
                r'(?:entre\s+)?(\d+)\s*°?\s*[Cc]\s+(?:e|a)\s+(\d+)\s*°?\s*[Cc]',
                r'(?:não\s+)?(?:exceder|ultrapassar)\s+(\d+)\s*°?\s*[Cc]',
            ],
            'validade': [
                r'(?:prazo de )?validade[:\s]+(\d+)\s+(ano|anos|mês|meses)',
                r'(\d+)\s+(?:ano|anos|mês|meses)\s+(?:de\s+)?validade',
                r'válido\s+(?:por\s+)?(\d+)\s+(ano|anos|mês|meses)',
            ],
            # 🆕 PADRÕES EXPANDIDOS PARA INTERVALOS DE SEGURANÇA
            'intervalo_seguranca': [
                # Padrão 1: "Tempo de espera: X dias"
                r'tempo\s+de\s+espera[:\s]+(\d+)\s+(dia|dias|hora|horas)',
                
                # Padrão 2: "Intervalo de segurança: X dias"
                r'intervalo\s+de\s+seguran[çc]a[:\s]+(\d+)\s+(dia|dias|hora|horas)',
                
                # Padrão 3: "Carência: X dias"
                r'car[êe]ncia[:\s]+(\d+)\s+(dia|dias|hora|horas)',
                
                # Padrão 4: Específico para carne
                r'carne[:\s]+(\d+)\s+(dia|dias|hora|horas)',
                r'carne\s+e\s+v[íi]sceras[:\s]+(\d+)\s+(dia|dias)',
                
                # Padrão 5: Específico para leite
                r'leite[:\s]+(\d+)\s+(dia|dias|hora|horas)',
                
                # Padrão 6: Específico para ovos
                r'ovos[:\s]+(\d+)\s+(dia|dias|hora|horas)',
                
                # Padrão 7: Formato "X dias de tempo de espera"
                r'(\d+)\s+dias?\s+(?:de\s+)?(?:tempo\s+de\s+espera|car[êe]ncia)',
                
                # Padrão 8: "Não utilizar em animais destinados..."
                r'não\s+utilizar.*?(\d+)\s+dias?\s+(?:antes|do\s+abate)',
                
                # Padrão 9: Tabelas (formato comum em PDFs)
                r'(?:carne|leite|ovos)\s+(\d+)\s*\n',
                
                # Padrão 10: "Zero dias" ou "Nulo"
                r'(?:tempo\s+de\s+espera|intervalo)[:\s]+(?:zero|nulo|0)\s+dias?',
            ],
            'receita': [
                r'(?:sujeito a|requer|necessita)\s+receita\s+(?:médica\s+)?veterinária',
                r'venda\s+(?:sob|com)\s+receita',
                r'medicamento\s+sujeito\s+a\s+receita',
                r'receita\s+médica\s+veterinária\s+obrigatória',
                r'(?:MNSRM|MSRM)',  # Siglas portuguesas
            ]
        }
        
        # Palavras-chave para identificação de contexto
        self.palavras_chave_secoes = {
            'dose': ['posologia', 'dose', 'dosagem', 'administração'],
            'armazenamento': ['conservação', 'armazenamento', 'armazenar', 'temperatura'],
            'especies': ['espécies-alvo', 'espécies alvo', 'animais'],
            'composicao': ['composição', 'princípio ativo', 'substância ativa'],
            'reacoes': ['reações adversas', 'efeitos indesejáveis', 'efeitos colaterais'],
            'intervalos': ['tempo de espera', 'intervalo de segurança', 'carência', 'abate', 'consumo'],
            'receita': ['receita', 'prescrição', 'venda', 'MNSRM', 'MSRM'],
        }

    def processar_pdf_completo(self, pdf_path: str) -> Dict:
        """
        Processa o PDF completo e extrai todas as informações estruturadas
        """
        print(colored(f"📄 Processando PDF estruturado: {pdf_path}", "cyan"))
        
        try:
            with fitz.open(pdf_path) as pdf_doc:
                # Fase 1: Mapear estrutura do documento
                self._mapear_estrutura_documento(pdf_doc)
                
                # Fase 2: Detectar e processar tabelas
                self._detectar_tabelas(pdf_doc)
                
                # Fase 3: Extrair informações específicas
                informacoes = self._extrair_informacoes_especificas(pdf_doc)
                
                # 🆕 Fase 4: Extração adicional de intervalos (busca global)
                informacoes['intervalos_seguranca'] = self._extrair_intervalos_melhorado(pdf_doc)
                
                return {
                    'metadados': self.metadados,
                    'secoes_mapeadas': self.secoes_mapeadas,
                    'tabelas': self.tabelas_detectadas,
                    'informacoes_extraidas': informacoes,
                    'sucesso': True
                }
                
        except Exception as e:
            print(colored(f"❌ Erro ao processar PDF: {e}", "red"))
            return {'sucesso': False, 'erro': str(e)}

    def _mapear_estrutura_documento(self, pdf_doc):
        """Mapeia a estrutura do documento identificando seções numeradas"""
        print(colored("🗺️  Mapeando estrutura do documento...", "yellow"))
        
        padrao_secao = r'^(\d+(?:\.\d+)?)\.\s+(.+)$'
        
        for page_num, page in enumerate(pdf_doc):
            texto = page.get_text()
            linhas = texto.split('\n')
            
            for i, linha in enumerate(linhas):
                linha_limpa = linha.strip()
                match = re.match(padrao_secao, linha_limpa)
                
                if match:
                    numero_secao = match.group(1)
                    titulo_secao = match.group(2).strip()
                    
                    # Capturar contexto expandido (30 linhas para seção 4.11)
                    num_linhas_contexto = 30 if numero_secao == '4.11' else 20
                    contexto = '\n'.join(linhas[i:i+num_linhas_contexto])
                    
                    self.secoes_mapeadas[numero_secao] = {
                        'titulo': titulo_secao,
                        'pagina': page_num + 1,
                        'contexto': contexto,
                        'linha_inicio': i
                    }
        
        print(colored(f"   ✓ Encontradas {len(self.secoes_mapeadas)} seções", "green"))

    def _detectar_tabelas(self, pdf_doc):
        """Detecta e extrai tabelas estruturadas do documento"""
        print(colored("📊 Detectando tabelas...", "yellow"))
        
        for page_num, page in enumerate(pdf_doc):
            # Método 1: Análise de layout
            tabelas_layout = self._extrair_tabelas_por_layout(page, page_num)
            
            # Método 2: Análise de texto (padrões tabulares)
            tabelas_texto = self._extrair_tabelas_por_texto(page, page_num)
            
            self.tabelas_detectadas.extend(tabelas_layout)
            self.tabelas_detectadas.extend(tabelas_texto)
        
        print(colored(f"   ✓ Detectadas {len(self.tabelas_detectadas)} tabelas", "green"))

    def _extrair_tabelas_por_layout(self, page, page_num: int) -> List[Dict]:
        """Extrai tabelas usando análise de coordenadas"""
        tabelas = []
        
        try:
            blocos = page.get_text("dict")["blocks"]
            linhas_agrupadas = {}
            
            for bloco in blocos:
                if "lines" not in bloco:
                    continue
                
                for linha in bloco["lines"]:
                    for span in linha["spans"]:
                        y = round(span["bbox"][1], 1)
                        x = span["bbox"][0]
                        texto = span["text"].strip()
                        
                        if texto:
                            if y not in linhas_agrupadas:
                                linhas_agrupadas[y] = []
                            linhas_agrupadas[y].append((x, texto))
            
            linhas_ordenadas = sorted(linhas_agrupadas.items())
            
            for i in range(len(linhas_ordenadas) - 1):
                y_atual, celulas_atual = linhas_ordenadas[i]
                y_proxima, celulas_proxima = linhas_ordenadas[i + 1]
                
                if len(celulas_atual) >= 2 and len(celulas_proxima) >= 2:
                    x_coords_atual = [c[0] for c in celulas_atual]
                    x_coords_proxima = [c[0] for c in celulas_proxima]
                    
                    if self._verificar_alinhamento(x_coords_atual, x_coords_proxima):
                        tabela_candidata = {
                            'pagina': page_num + 1,
                            'tipo': 'layout',
                            'linhas': [
                                sorted(celulas_atual, key=lambda x: x[0]),
                                sorted(celulas_proxima, key=lambda x: x[0])
                            ]
                        }
                        
                        if not any(self._tabelas_similares(t, tabela_candidata) for t in tabelas):
                            tabelas.append(tabela_candidata)
        
        except Exception as e:
            print(colored(f"   ⚠️ Erro na extração por layout: {e}", "yellow"))
        
        return tabelas

    def _extrair_tabelas_por_texto(self, page, page_num: int) -> List[Dict]:
        """Detecta tabelas por padrões textuais"""
        tabelas = []
        texto = page.get_text()
        linhas = texto.split('\n')
        
        i = 0
        while i < len(linhas):
            linha = linhas[i]
            
            if self._e_linha_tabular(linha):
                tabela_linhas = [linha]
                j = i + 1
                
                while j < len(linhas) and (self._e_linha_tabular(linhas[j]) or linhas[j].strip() == ''):
                    if linhas[j].strip():
                        tabela_linhas.append(linhas[j])
                    j += 1
                
                if len(tabela_linhas) >= 2:
                    tabela = {
                        'pagina': page_num + 1,
                        'tipo': 'texto',
                        'conteudo_bruto': '\n'.join(tabela_linhas),
                        'interpretada': self._interpretar_tabela_texto(tabela_linhas)
                    }
                    tabelas.append(tabela)
                
                i = j
            else:
                i += 1
        
        return tabelas

    def _e_linha_tabular(self, linha: str) -> bool:
        """Verifica se uma linha tem características tabulares"""
        tem_espacos_multiplos = bool(re.search(r'\s{3,}', linha))
        tem_pipes = '|' in linha
        tem_dados_numericos = len(re.findall(r'\d+(?:[.,]\d+)?', linha)) >= 2
        
        return (tem_espacos_multiplos or tem_pipes) and tem_dados_numericos

    def _interpretar_tabela_texto(self, linhas: List[str]) -> Dict:
        """Interpreta o conteúdo de uma tabela textual"""
        interpretacao = {
            'cabecalhos': [],
            'dados': []
        }
        
        if linhas:
            primeira_linha = linhas[0]
            
            if '|' in primeira_linha:
                colunas = [c.strip() for c in primeira_linha.split('|') if c.strip()]
            else:
                colunas = re.split(r'\s{3,}', primeira_linha)
            
            interpretacao['cabecalhos'] = [c.strip() for c in colunas if c.strip()]
        
        for linha in linhas[1:]:
            if '|' in linha:
                valores = [v.strip() for v in linha.split('|') if v.strip()]
            else:
                valores = re.split(r'\s{3,}', linha)
            
            valores_limpos = [v.strip() for v in valores if v.strip()]
            if valores_limpos:
                interpretacao['dados'].append(valores_limpos)
        
        return interpretacao

    def _extrair_informacoes_especificas(self, pdf_doc) -> Dict[str, List[InformacaoExtraida]]:
        """Extrai informações específicas usando padrões e contexto"""
        print(colored("🔍 Extraindo informações específicas...", "yellow"))
        
        informacoes = {
            'doses': [],
            'administracao': [],
            'armazenamento': [],
            'intervalos_seguranca': [],
            'composicao': [],
            'reacoes_adversas': [],
            'receita': [],
            'especies': []
        }
        
        informacoes['doses'] = self._extrair_doses(pdf_doc)
        informacoes['administracao'] = self._extrair_administracao(pdf_doc)
        informacoes['armazenamento'] = self._extrair_armazenamento(pdf_doc)
        informacoes['composicao'] = self._extrair_composicao(pdf_doc)
        informacoes['reacoes_adversas'] = self._extrair_reacoes(pdf_doc)
        informacoes['receita'] = self._extrair_info_receita(pdf_doc)
        informacoes['especies'] = self._extrair_especies(pdf_doc)
        
        return informacoes

    # 🆕 MÉTODO MELHORADO PARA INTERVALOS
    def _extrair_intervalos_melhorado(self, pdf_doc) -> List[InformacaoExtraida]:
        """
        Extração MELHORADA de intervalos de segurança com múltiplas estratégias
        """
        intervalos_encontrados = []
        
        print(colored("   🔍 Buscando intervalos de segurança...", "cyan"))
        
        # ESTRATÉGIA 1: Buscar na seção 4.11 (Tempo de Espera)
        secao_tempo_espera = self.secoes_mapeadas.get('4.11')
        
        if secao_tempo_espera:
            print(colored("      → Buscando na seção 4.11...", "blue"))
            contexto = secao_tempo_espera['contexto']
            pagina = secao_tempo_espera['pagina']
            
            for padrao in self.padroes_extracao['intervalo_seguranca']:
                matches = re.finditer(padrao, contexto, re.IGNORECASE | re.MULTILINE)
                
                for match in matches:
                    intervalo_valor = match.group(0)
                    
                    # Extrair contexto local
                    inicio = max(0, match.start() - 100)
                    fim = min(len(contexto), match.end() + 100)
                    contexto_local = contexto[inicio:fim]
                    
                    info = InformacaoExtraida(
                        conteudo=intervalo_valor,
                        secao='4.11',
                        confianca=0.95,
                        pagina=pagina,
                        metodo_extracao='regex_secao_4.11',
                        contexto=contexto_local
                    )
                    intervalos_encontrados.append(info)
                    print(colored(f"         ✓ Encontrado: {intervalo_valor}", "green"))
        
        # ESTRATÉGIA 2: Buscar em tabelas
        print(colored("      → Buscando em tabelas...", "blue"))
        for tabela in self.tabelas_detectadas:
            if tabela['tipo'] == 'texto' and 'interpretada' in tabela:
                interpretacao = tabela['interpretada']
                cabecalhos = interpretacao.get('cabecalhos', [])
                dados = interpretacao.get('dados', [])
                
                # Procurar colunas relacionadas a tempo de espera
                palavras_chave_intervalo = ['tempo', 'espera', 'carência', 'carne', 'leite', 'ovos']
                
                indices_relevantes = []
                for i, cab in enumerate(cabecalhos):
                    if any(palavra in cab.lower() for palavra in palavras_chave_intervalo):
                        indices_relevantes.append(i)
                
                if indices_relevantes:
                    for linha_dados in dados:
                        for idx in indices_relevantes:
                            if idx < len(linha_dados):
                                valor = linha_dados[idx]
                                
                                # Validar se parece intervalo (número + unidade)
                                if re.search(r'\d+\s*(?:dia|hora)', valor, re.IGNORECASE):
                                    info = InformacaoExtraida(
                                        conteudo=valor,
                                        secao='tabela',
                                        confianca=0.90,
                                        pagina=tabela['pagina'],
                                        metodo_extracao='tabela_estruturada',
                                        contexto=tabela['conteudo_bruto'][:200]
                                    )
                                    intervalos_encontrados.append(info)
                                    print(colored(f"         ✓ Encontrado em tabela: {valor}", "green"))
        
        # ESTRATÉGIA 3: Busca global em todo o documento (se nada encontrado)
        if not intervalos_encontrados:
            print(colored("      → Buscando em todo o documento...", "blue"))
            for page_num, page in enumerate(pdf_doc):
                texto = page.get_text()
                
                # Focar em regiões que mencionam "tempo de espera"
                if any(termo in texto.lower() for termo in ['tempo de espera', 'carência', 'intervalo']):
                    for padrao in self.padroes_extracao['intervalo_seguranca']:
                        matches = re.finditer(padrao, texto, re.IGNORECASE | re.MULTILINE)
                        
                        for match in matches:
                            intervalo_valor = match.group(0)
                            
                            inicio = max(0, match.start() - 80)
                            fim = min(len(texto), match.end() + 80)
                            contexto_local = texto[inicio:fim]
                            
                            info = InformacaoExtraida(
                                conteudo=intervalo_valor,
                                secao='documento_global',
                                confianca=0.70,
                                pagina=page_num + 1,
                                metodo_extracao='regex_global',
                                contexto=contexto_local
                            )
                            intervalos_encontrados.append(info)
                            print(colored(f"         ✓ Encontrado globalmente: {intervalo_valor}", "green"))
        
        # Remover duplicatas
        intervalos_unicos = self._remover_duplicatas_intervalos(intervalos_encontrados)
        
        print(colored(f"   ✓ Total de intervalos encontrados: {len(intervalos_unicos)}", "green"))
        return intervalos_unicos

    def _remover_duplicatas_intervalos(self, intervalos: List[InformacaoExtraida]) -> List[InformacaoExtraida]:
        """Remove intervalos duplicados mantendo o de maior confiança"""
        intervalos_dict = {}
        
        for info in intervalos:
            # Normalizar para comparação
            conteudo_norm = re.sub(r'\s+', ' ', info.conteudo.lower()).strip()
            
            if conteudo_norm not in intervalos_dict:
                intervalos_dict[conteudo_norm] = info
            else:
                # Manter o de maior confiança
                if info.confianca > intervalos_dict[conteudo_norm].confianca:
                    intervalos_dict[conteudo_norm] = info
        
        return list(intervalos_dict.values())

    def _extrair_doses(self, pdf_doc) -> List[InformacaoExtraida]:
        """Extração especializada de doses"""
        doses_encontradas = []
        
        # Estratégia 1: Seção 4.9
        secao_posologia = self.secoes_mapeadas.get('4.9')
        
        if secao_posologia:
            contexto = secao_posologia['contexto']
            pagina = secao_posologia['pagina']
            
            for padrao in self.padroes_extracao['dose']:
                matches = re.finditer(padrao, contexto, re.IGNORECASE)
                
                for match in matches:
                    dose_valor = match.group(0)
                    
                    inicio = max(0, match.start() - 50)
                    fim = min(len(contexto), match.end() + 50)
                    contexto_local = contexto[inicio:fim]
                    
                    info = InformacaoExtraida(
                        conteudo=dose_valor,
                        secao='4.9',
                        confianca=0.9,
                        pagina=pagina,
                        metodo_extracao='regex_secao_especifica',
                        contexto=contexto_local
                    )
                    doses_encontradas.append(info)
        
        # Estratégia 2: Tabelas
        for tabela in self.tabelas_detectadas:
            if tabela['tipo'] == 'texto' and 'interpretada' in tabela:
                interpretacao = tabela['interpretada']
                cabecalhos = interpretacao.get('cabecalhos', [])
                dados = interpretacao.get('dados', [])
                
                idx_dose = None
                for i, cab in enumerate(cabecalhos):
                    if any(palavra in cab.lower() for palavra in ['dose', 'dosagem', 'posologia']):
                        idx_dose = i
                        break
                
                if idx_dose is not None:
                    for linha_dados in dados:
                        if idx_dose < len(linha_dados):
                            dose_valor = linha_dados[idx_dose]
                            
                            if re.search(r'\d+(?:[.,]\d+)?\s*(?:mg|ml|g)', dose_valor, re.IGNORECASE):
                                info = InformacaoExtraida(
                                    conteudo=dose_valor,
                                    secao='tabela',
                                    confianca=0.95,
                                    pagina=tabela['pagina'],
                                    metodo_extracao='tabela_estruturada',
                                    contexto=tabela['conteudo_bruto'][:200]
                                )
                                doses_encontradas.append(info)
        
        print(colored(f"   ✓ Encontradas {len(doses_encontradas)} doses", "green"))
        return doses_encontradas

    def _extrair_administracao(self, pdf_doc) -> List[InformacaoExtraida]:
        """Extrai formas de administração"""
        admins = []
        
        secao = self.secoes_mapeadas.get('4.9')
        if secao:
            for padrao in self.padroes_extracao['via_administracao']:
                matches = re.finditer(padrao, secao['contexto'], re.IGNORECASE)
                
                for match in matches:
                    info = InformacaoExtraida(
                        conteudo=match.group(0),
                        secao='4.9',
                        confianca=0.9,
                        pagina=secao['pagina'],
                        metodo_extracao='regex_secao',
                        contexto=match.group(0)
                    )
                    admins.append(info)
        
        return admins

    def _extrair_armazenamento(self, pdf_doc) -> List[InformacaoExtraida]:
        """Extrai condições de armazenamento"""
        armazenamento = []
        
        secao = self.secoes_mapeadas.get('6.4')
        if secao:
            for padrao in self.padroes_extracao['temperatura']:
                matches = re.finditer(padrao, secao['contexto'], re.IGNORECASE)
                
                for match in matches:
                    info = InformacaoExtraida(
                        conteudo=match.group(0),
                        secao='6.4',
                        confianca=0.95,
                        pagina=secao['pagina'],
                        metodo_extracao='regex_secao',
                        contexto=secao['contexto'][:200]
                    )
                    armazenamento.append(info)
        
        return armazenamento

    def _extrair_composicao(self, pdf_doc) -> List[InformacaoExtraida]:
        """Extrai composição do medicamento"""
        composicao = []
        
        secoes_relevantes = ['1', '6.1']
        
        for num_secao in secoes_relevantes:
            secao = self.secoes_mapeadas.get(num_secao)
            if secao:
                info = InformacaoExtraida(
                    conteudo=secao['contexto'][:500],
                    secao=num_secao,
                    confianca=0.95,
                    pagina=secao['pagina'],
                    metodo_extracao='secao_completa',
                    contexto=secao['titulo']
                )
                composicao.append(info)
        
        return composicao

    def _extrair_reacoes(self, pdf_doc) -> List[InformacaoExtraida]:
        """Extrai reações adversas"""
        reacoes = []
        
        secao = self.secoes_mapeadas.get('4.6')
        if secao:
            info = InformacaoExtraida(
                conteudo=secao['contexto'],
                secao='4.6',
                confianca=0.95,
                pagina=secao['pagina'],
                metodo_extracao='secao_completa',
                contexto=secao['titulo']
            )
            reacoes.append(info)
        
        return reacoes

    def _extrair_info_receita(self, pdf_doc) -> List[InformacaoExtraida]:
        """Verifica se medicamento requer receita"""
        receita_info = []
        
        for page_num, page in enumerate(pdf_doc):
            texto = page.get_text()
            
            for padrao in self.padroes_extracao['receita']:
                if re.search(padrao, texto, re.IGNORECASE):
                    info = InformacaoExtraida(
                        conteudo="Requer receita médica veterinária",
                        secao='global',
                        confianca=0.9,
                        pagina=page_num + 1,
                        metodo_extracao='regex_global',
                        contexto=''
                    )
                    receita_info.append(info)
                    break
        
        return receita_info

    def _extrair_especies(self, pdf_doc) -> List[InformacaoExtraida]:
        """Extrai espécies-alvo"""
        especies = []
        
        secao = self.secoes_mapeadas.get('4.1')
        if secao:
            especies_conhecidas = [
                'suínos', 'suino', 'porcos', 'leitões',
                'bovinos', 'bovino', 'vacas', 'gado',
                'equinos', 'equino', 'cavalos', 'égua',
                'cães', 'caes', 'cão', 'cao', 'cachorros',
                'gatos', 'gato', 'felinos',
                'aves', 'galinhas', 'frangos', 'perus',
                'ovinos', 'ovelhas', 'carneiros',
                'caprinos', 'cabras', 'bodes',
                'coelhos', 'coelho'
            ]
            
            especies_encontradas = []
            contexto_lower = secao['contexto'].lower()
            
            for especie in especies_conhecidas:
                if especie in contexto_lower:
                    especies_encontradas.append(especie.capitalize())
            
            if especies_encontradas:
                # Remover duplicatas mantendo ordem
                especies_unicas = list(OrderedDict.fromkeys(especies_encontradas))
                
                info = InformacaoExtraida(
                    conteudo=', '.join(especies_unicas),
                    secao='4.1',
                    confianca=0.95,
                    pagina=secao['pagina'],
                    metodo_extracao='lista_especies',
                    contexto=secao['contexto'][:200]
                )
                especies.append(info)
        
        return especies

    def _verificar_alinhamento(self, coords1: List[float], coords2: List[float], 
                               tolerancia: float = 5.0) -> bool:
        """Verifica se duas listas de coordenadas estão alinhadas"""
        if len(coords1) != len(coords2):
            return False
        
        for c1, c2 in zip(sorted(coords1), sorted(coords2)):
            if abs(c1 - c2) > tolerancia:
                return False
        
        return True

    def _tabelas_similares(self, tabela1: Dict, tabela2: Dict, 
                           tolerancia: float = 10.0) -> bool:
        """Verifica se duas tabelas são similares"""
        if tabela1.get('pagina') != tabela2.get('pagina'):
            return False
        
        if 'conteudo_bruto' in tabela1 and 'conteudo_bruto' in tabela2:
            conteudo1 = tabela1['conteudo_bruto'][:100].lower()
            conteudo2 = tabela2['conteudo_bruto'][:100].lower()
            
            palavras1 = set(conteudo1.split())
            palavras2 = set(conteudo2.split())
            
            if palavras1 and palavras2:
                intersecao = palavras1.intersection(palavras2)
                similaridade = len(intersecao) / max(len(palavras1), len(palavras2))
                
                return similaridade > 0.8
        
        return False

    def buscar_informacao_especifica(self, tipo_info: str, 
                                     especie: Optional[str] = None) -> List[InformacaoExtraida]:
        """
        Busca informação específica já extraída
        """
        if not hasattr(self, 'informacoes_extraidas'):
            return []
        
        # Mapear tipo_info para chave interna
        mapeamento = {
            'dosagem': 'doses',
            'dose': 'doses',
            'intervalos': 'intervalos_seguranca',
            'armazenamento': 'armazenamento',
        }
        
        chave = mapeamento.get(tipo_info, tipo_info)
        info_list = self.informacoes_extraidas.get(chave, [])
        
        if especie and info_list:
            especie_lower = especie.lower()
            info_filtrada = []
            
            for info in info_list:
                contexto_lower = info.contexto.lower()
                if especie_lower in contexto_lower or especie_lower in info.conteudo.lower():
                    info_filtrada.append(info)
            
            return info_filtrada if info_filtrada else info_list
        
        return info_list

    def gerar_resumo_estruturado(self) -> str:
        """Gera um resumo estruturado de todas as informações extraídas"""
        if not hasattr(self, 'informacoes_extraidas'):
            return "Nenhuma informação extraída ainda."
        
        resumo = []
        resumo.append("=" * 80)
        resumo.append("RESUMO ESTRUTURADO DO MEDICAMENTO")
        resumo.append("=" * 80)
        
        if self.metadados:
            resumo.append("\n📋 METADADOS:")
            for chave, valor in self.metadados.items():
                resumo.append(f"  • {chave}: {valor}")
        
        mapeamento_titulos = {
            'doses': '💉 DOSAGEM',
            'administracao': '📌 ADMINISTRAÇÃO',
            'armazenamento': '🌡️ ARMAZENAMENTO',
            'intervalos_seguranca': '⏰ INTERVALOS DE SEGURANÇA',
            'composicao': '🧪 COMPOSIÇÃO',
            'reacoes_adversas': '⚠️ REAÇÕES ADVERSAS',
            'receita': '📝 RECEITA',
            'especies': '🐾 ESPÉCIES-ALVO'
        }
        
        for tipo, titulo in mapeamento_titulos.items():
            info_list = self.informacoes_extraidas.get(tipo, [])
            
            if info_list:
                resumo.append(f"\n{titulo}:")
                
                for i, info in enumerate(info_list[:3], 1):
                    confianca_pct = int(info.confianca * 100)
                    resumo.append(f"  {i}. {info.conteudo}")
                    resumo.append(f"     (Confiança: {confianca_pct}%, Seção: {info.secao}, Pág: {info.pagina})")
        
        resumo.append("\n" + "=" * 80)
        
        return "\n".join(resumo)


# Classe wrapper para compatibilidade
class PDFProcessorAvancadoV2:
    """
    Wrapper MELHORADO que integra o extrator v2
    """
    
    def __init__(self):
        self.extrator = PDFEstruturadoExtractorV2()
        self.cache_processados = {}
    
    def extrair_e_processar_pdf(self, pdf_path: str) -> List[str]:
        """Método compatível com interface original"""
        resultado = self.extrator.processar_pdf_completo(pdf_path)
        
        if not resultado.get('sucesso'):
            return []
        
        self.extrator.informacoes_extraidas = resultado['informacoes_extraidas']
        self.extrator.metadados = resultado['metadados']
        
        secoes_formatadas = []
        
        # Resumo estruturado
        resumo = self.extrator.gerar_resumo_estruturado()
        secoes_formatadas.append(resumo)
        
        # Seções mapeadas
        for num_secao, dados_secao in sorted(resultado['secoes_mapeadas'].items()):
            secao_texto = f"\n{'='*80}\n"
            secao_texto += f"SEÇÃO {num_secao}: {dados_secao['titulo']}\n"
            secao_texto += f"{'='*80}\n\n"
            secao_texto += dados_secao['contexto']
            
            secoes_formatadas.append(secao_texto)
        
        # Tabelas interpretadas
        for i, tabela in enumerate(resultado['tabelas'], 1):
            if tabela.get('tipo') == 'texto' and 'interpretada' in tabela:
                tabela_texto = f"\n{'='*80}\n"
                tabela_texto += f"📊 TABELA {i} (Página {tabela['pagina']})\n"
                tabela_texto += f"{'='*80}\n\n"
                
                interpretacao = tabela['interpretada']
                
                if interpretacao.get('cabecalhos'):
                    tabela_texto += "CABEÇALHOS: " + " | ".join(interpretacao['cabecalhos']) + "\n\n"
                
                if interpretacao.get('dados'):
                    for j, linha in enumerate(interpretacao['dados'], 1):
                        tabela_texto += f"Linha {j}: " + " | ".join(linha) + "\n"
                
                secoes_formatadas.append(tabela_texto)
        
        return secoes_formatadas
    
    def buscar_informacao_direta(self, tipo_info: str, 
                                 especie: Optional[str] = None) -> Optional[Dict]:
        """Busca direta de informação específica"""
        mapeamento = {
            'dosagem': 'doses',
            'dose': 'doses',
            'armazenamento': 'armazenamento',
            'especies': 'especies',
            'administracao': 'administracao',
            'reacoes': 'reacoes_adversas',
            'intervalos': 'intervalos_seguranca',
            'receita': 'receita',
            'composicao': 'composicao'
        }
        
        tipo_interno = mapeamento.get(tipo_info.lower(), tipo_info)
        
        info_list = self.extrator.buscar_informacao_especifica(tipo_interno, especie)
        
        if not info_list:
            return {
                'encontrado': False,
                'tipo': tipo_info,
                'mensagem': f'Informação sobre {tipo_info} não encontrada'
            }
        
        info_extraida = []
        secoes_relevantes = []
        
        for info in info_list:
            info_extraida.append({
                'conteudo': info.conteudo,
                'confianca': info.confianca,
                'secao': info.secao,
                'pagina': info.pagina
            })
            
            secoes_relevantes.append(info.contexto)
        
        return {
            'encontrado': True,
            'tipo': tipo_info,
            'info_extraida': info_extraida,
            'secoes_relevantes': secoes_relevantes,
            'melhor_resultado': info_list[0].conteudo if info_list else None,
            'confianca_media': sum(i.confianca for i in info_list) / len(info_list)
        }