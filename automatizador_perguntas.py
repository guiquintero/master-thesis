#!/usr/bin/env python3
"""
Automatizador de Perguntas - Sistema de Consulta Veterinária
Permite submeter uma lista de perguntas e registrar respostas e tempos de execução
"""

import json
import time
import sys
from datetime import datetime
from termcolor import colored
from temporario_MV import SistemaConsultaVetOtimizado
import asyncio
import os


class AutomatizadorPerguntas:
    """Classe para automatizar o processamento de múltiplas perguntas"""
    
    def __init__(self, arquivo_saida="resultados/resultados_automatizados.txt"):
        """
        Inicializa o automatizador
        
        Args:
            arquivo_saida: Caminho do arquivo onde serão salvos os resultados
        """
        self.arquivo_saida = arquivo_saida
        self.resultados = []
        self.sistema = None
        
        # Criar diretório de resultados se não existir
        diretorio = os.path.dirname(arquivo_saida)
        if diretorio:  # Só cria se houver um diretório no caminho
            os.makedirs(diretorio, exist_ok=True)
    
    def carregar_perguntas_do_arquivo(self, arquivo_perguntas):
        """
        Carrega perguntas de um arquivo de texto (uma pergunta por linha)
        
        Args:
            arquivo_perguntas: Caminho do arquivo com as perguntas
            
        Returns:
            Lista de perguntas
        """
        try:
            with open(arquivo_perguntas, 'r', encoding='utf-8') as f:
                perguntas = [linha.strip() for linha in f.readlines() if linha.strip()]
            print(colored(f"✓ Carregadas {len(perguntas)} perguntas do arquivo '{arquivo_perguntas}'", "green"))
            return perguntas
        except FileNotFoundError:
            print(colored(f"✗ Arquivo '{arquivo_perguntas}' não encontrado!", "red"))
            return []
        except Exception as e:
            print(colored(f"✗ Erro ao carregar perguntas: {e}", "red"))
            return []
    
    def processar_perguntas(self, perguntas):
        """
        Processa uma lista de perguntas e registra os resultados
        
        Args:
            perguntas: Lista de perguntas a serem processadas
        """
        if not perguntas:
            print(colored("Nenhuma pergunta para processar!", "yellow"))
            return
        
        print(colored(f"\n{'='*80}", "cyan"))
        print(colored(f"Iniciando processamento de {len(perguntas)} perguntas", "cyan", attrs=["bold"]))
        print(colored(f"{'='*80}\n", "cyan"))
        
        # Criar instância do sistema
        self.sistema = SistemaConsultaVetOtimizado()
        
        for idx, pergunta in enumerate(perguntas, 1):
            print(colored(f"\n{'─'*80}", "blue"))
            print(colored(f"Pergunta {idx}/{len(perguntas)}: {pergunta}", "yellow", attrs=["bold"]))
            print(colored(f"{'─'*80}", "blue"))
            
            resultado = self._processar_pergunta_individual(pergunta, idx)
            self.resultados.append(resultado)
            
            # Salvar resultados parciais após cada pergunta
            self._salvar_resultados_parciais()
            
            # Pausa entre perguntas para não sobrecarregar o sistema
            if idx < len(perguntas):
                time.sleep(2)
        
        # Fechar sessão do sistema
        self._fechar_sistema()
        
        # Salvar resultados finais
        self._salvar_resultados_finais()
        self._exibir_resumo()
    
    def _processar_pergunta_individual(self, pergunta, numero):
        """
        Processa uma pergunta individual e registra o resultado
        
        Args:
            pergunta: Pergunta a ser processada
            numero: Número da pergunta na sequência
            
        Returns:
            Dicionário com os resultados
        """
        tempo_inicio = time.perf_counter()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        resultado = {
            "numero": numero,
            "pergunta": pergunta,
            "timestamp": timestamp,
            "resposta": "",
            "tempo_total_segundos": 0,
            "sucesso": False,
            "erro": None
        }
        
        try:
            # Processar pergunta usando o sistema
            resposta = self.sistema.processar_pergunta_unica(pergunta)
            tempo_total = time.perf_counter() - tempo_inicio
            
            resultado["resposta"] = resposta
            resultado["tempo_total_segundos"] = round(tempo_total, 2)
            resultado["sucesso"] = True
            
            print(colored(f"\n✓ Resposta obtida em {tempo_total:.2f}s", "green"))
            
        except Exception as e:
            tempo_total = time.perf_counter() - tempo_inicio
            resultado["tempo_total_segundos"] = round(tempo_total, 2)
            resultado["erro"] = str(e)
            print(colored(f"\n✗ Erro ao processar pergunta: {e}", "red"))
        
        return resultado
    
    def _fechar_sistema(self):
        """Fecha a sessão do sistema de forma adequada"""
        if self.sistema and hasattr(self.sistema, 'session') and self.sistema.session:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.sistema.session.close())
                loop.close()
                print(colored("\n✓ Sistema fechado corretamente", "green"))
            except Exception as e:
                print(colored(f"\n✗ Erro ao fechar sistema: {e}", "red"))
    
    def _salvar_resultados_parciais(self):
        """Salva resultados parciais após cada pergunta"""
        try:
            # Criar diretório se não existir
            diretorio = os.path.dirname(self.arquivo_saida)
            if diretorio:
                os.makedirs(diretorio, exist_ok=True)
            
            with open(self.arquivo_saida + ".tmp", 'w', encoding='utf-8') as f:
                f.write(self._formatar_resultados())
        except Exception as e:
            print(colored(f"Aviso: Não foi possível salvar resultados parciais: {e}", "yellow"))
    
    def _salvar_resultados_finais(self):
        """Salva os resultados finais no arquivo de saída"""
        try:
            # Criar diretório se não existir
            diretorio = os.path.dirname(self.arquivo_saida)
            if diretorio:
                os.makedirs(diretorio, exist_ok=True)
            
            with open(self.arquivo_saida, 'w', encoding='utf-8') as f:
                f.write(self._formatar_resultados())
            
            # Remover arquivo temporário se existir
            if os.path.exists(self.arquivo_saida + ".tmp"):
                os.remove(self.arquivo_saida + ".tmp")
            
            print(colored(f"\n✓ Resultados salvos em: {self.arquivo_saida}", "green", attrs=["bold"]))
            
            # Salvar também em formato JSON
            arquivo_json = self.arquivo_saida.replace('.txt', '.json')
            with open(arquivo_json, 'w', encoding='utf-8') as f:
                json.dump(self.resultados, f, ensure_ascii=False, indent=2)
            print(colored(f"✓ Resultados JSON salvos em: {arquivo_json}", "green"))
            
        except Exception as e:
            print(colored(f"✗ Erro ao salvar resultados: {e}", "red"))
    
    def _formatar_resultados(self):
        """
        Formata os resultados para salvamento em arquivo
        
        Returns:
            String formatada com todos os resultados
        """
        linhas = []
        linhas.append("=" * 100)
        linhas.append("RESULTADOS DO PROCESSAMENTO AUTOMATIZADO DE PERGUNTAS")
        linhas.append(f"Data/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        linhas.append(f"Total de Perguntas: {len(self.resultados)}")
        linhas.append("=" * 100)
        linhas.append("")
        
        for resultado in self.resultados:
            linhas.append("-" * 100)
            linhas.append(f"PERGUNTA #{resultado['numero']}")
            linhas.append(f"Timestamp: {resultado['timestamp']}")
            linhas.append("-" * 100)
            linhas.append(f"Pergunta: {resultado['pergunta']}")
            linhas.append("")
            
            if resultado['sucesso']:
                linhas.append(f"Resposta:")
                linhas.append(resultado['resposta'])
                linhas.append("")
                linhas.append(f"⏱️  Tempo Total: {resultado['tempo_total_segundos']} segundos")
                linhas.append(f"✓ Status: SUCESSO")
            else:
                linhas.append(f"✗ Status: ERRO")
                linhas.append(f"Erro: {resultado['erro']}")
                linhas.append(f"⏱️  Tempo até erro: {resultado['tempo_total_segundos']} segundos")
            
            linhas.append("")
        
        linhas.append("=" * 100)
        linhas.append("RESUMO ESTATÍSTICO")
        linhas.append("=" * 100)
        
        total = len(self.resultados)
        
        if total == 0:
            linhas.append("Nenhuma pergunta foi processada.")
        else:
            sucessos = sum(1 for r in self.resultados if r['sucesso'])
            erros = total - sucessos
            tempo_total = sum(r['tempo_total_segundos'] for r in self.resultados)
            tempo_medio = tempo_total / total
            
            linhas.append(f"Total de perguntas: {total}")
            linhas.append(f"Sucessos: {sucessos} ({sucessos/total*100:.1f}%)")
            linhas.append(f"Erros: {erros} ({erros/total*100:.1f}%)")
            linhas.append(f"Tempo total: {tempo_total:.2f} segundos ({tempo_total/60:.2f} minutos)")
            linhas.append(f"Tempo médio por pergunta: {tempo_medio:.2f} segundos")
        
        linhas.append("=" * 100)
        
        return "\n".join(linhas)
    
    def _exibir_resumo(self):
        """Exibe um resumo dos resultados no console"""
        print(colored(f"\n{'='*80}", "cyan"))
        print(colored("RESUMO DO PROCESSAMENTO", "cyan", attrs=["bold"]))
        print(colored(f"{'='*80}", "cyan"))
        
        total = len(self.resultados)
        
        if total == 0:
            print(colored("Nenhuma pergunta foi processada.", "yellow"))
        else:
            sucessos = sum(1 for r in self.resultados if r['sucesso'])
            erros = total - sucessos
            tempo_total = sum(r['tempo_total_segundos'] for r in self.resultados)
            tempo_medio = tempo_total / total
            
            print(colored(f"Total de perguntas: {total}", "white"))
            print(colored(f"✓ Sucessos: {sucessos} ({sucessos/total*100:.1f}%)", "green"))
            if erros > 0:
                print(colored(f"✗ Erros: {erros} ({erros/total*100:.1f}%)", "red"))
            print(colored(f"⏱️  Tempo total: {tempo_total:.2f}s ({tempo_total/60:.2f} min)", "yellow"))
            print(colored(f"⏱️  Tempo médio: {tempo_medio:.2f}s por pergunta", "yellow"))
        
        print(colored(f"{'='*80}\n", "cyan"))


def main():
    """Função principal do automatizador"""
    print(colored("=" * 80, "green"))
    print(colored("AUTOMATIZADOR DE PERGUNTAS - SISTEMA VETERINÁRIO", "green", attrs=["bold"]))
    print(colored("=" * 80, "green"))
    
    # Verificar argumentos
    if len(sys.argv) > 1:
        arquivo_perguntas = sys.argv[1]
        arquivo_saida = sys.argv[2] if len(sys.argv) > 2 else "resultados/resultados_automatizados.txt"
    else:
        print(colored("\nModo de uso:", "yellow"))
        print(colored("  python automatizador_perguntas.py <arquivo_perguntas.txt> [arquivo_saida.txt]", "white"))
        print(colored("\nOu use o modo interativo:", "yellow"))
        
        arquivo_perguntas = input(colored("\nDigite o caminho do arquivo com as perguntas: ", "cyan")).strip()
        arquivo_saida = input(colored("Digite o caminho do arquivo de saída (Enter para padrão): ", "cyan")).strip()
        
        if not arquivo_saida:
            arquivo_saida = "resultados/resultados_automatizados.txt"
    
    # Criar automatizador
    automatizador = AutomatizadorPerguntas(arquivo_saida)
    
    # Carregar perguntas
    perguntas = automatizador.carregar_perguntas_do_arquivo(arquivo_perguntas)
    
    if not perguntas:
        print(colored("\nNenhuma pergunta válida encontrada. Encerrando...", "red"))
        return
    
    # Confirmar processamento
    print(colored(f"\nSerão processadas {len(perguntas)} perguntas.", "yellow"))
    print(colored(f"Resultados serão salvos em: {arquivo_saida}", "yellow"))
    
    confirmar = input(colored("\nDeseja continuar? (s/n): ", "cyan")).strip().lower()
    
    if confirmar not in ['s', 'sim', 'y', 'yes']:
        print(colored("\nOperação cancelada pelo usuário.", "yellow"))
        return
    
    # Processar perguntas
    try:
        automatizador.processar_perguntas(perguntas)
        print(colored("\n✓ Processamento concluído com sucesso!", "green", attrs=["bold"]))
    except KeyboardInterrupt:
        print(colored("\n\n✗ Processamento interrompido pelo usuário!", "red"))
        automatizador._salvar_resultados_finais()
    except Exception as e:
        print(colored(f"\n✗ Erro durante processamento: {e}", "red"))
        automatizador._salvar_resultados_finais()


if __name__ == "__main__":
    main()
