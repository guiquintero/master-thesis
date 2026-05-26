# DEPRECATED — substituído por backend/tests/golden/run_golden.py
# Mantido apenas para referência histórica.
# Use: python -m backend.tests.golden.run_golden
raise SystemExit(
    "Este script foi substituído. Execute:\n"
    "  python -m backend.tests.golden.run_golden\n"
    "ou:\n"
    "  make bench"
)
# ---- código legado abaixo (não executável) ----

import sys
import time
import json
from datetime import datetime
from termcolor import colored
from pathlib import Path
from src.core.sistema_consulta import SistemaConsultaVetOtimizado

class TestadorAutomatico:
    def __init__(self):
        self.sistema = SistemaConsultaVetOtimizado()
        self.resultados = []
        self.tempo_total = 0

        # Criar pasta de resultados se não existir
        self.pasta_resultados = Path("resultados")
        self.pasta_resultados.mkdir(exist_ok=True)
        print(colored(f"📁 Pasta de resultados: {self.pasta_resultados.absolute()}", "cyan"))
        
    def executar_testes(self, perguntas):
        """
        Executa lista de perguntas sequencialmente
        """
        print(colored("="*80, "cyan"))
        print(colored("🧪 INICIANDO TESTES AUTOMATIZADOS", "cyan", attrs=['bold']))
        print(colored("="*80, "cyan"))
        print(colored(f"📋 Total de perguntas: {len(perguntas)}", "yellow"))
        print(colored(f"🕐 Início: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "yellow"))
        print(colored("="*80 + "\n", "cyan"))
        
        inicio_total = time.time()
        
        for i, pergunta in enumerate(perguntas, 1):
            self._executar_teste_individual(i, pergunta, len(perguntas))
            
            # Pequena pausa entre perguntas para não sobrecarregar
            if i < len(perguntas):
                time.sleep(1)
        
        self.tempo_total = time.time() - inicio_total
        
        # Gerar relatório final
        self._gerar_relatorio()
    
    def _executar_teste_individual(self, numero, pergunta, total):
        """
        Executa uma pergunta individual e registra resultado
        """
        print(colored("\n" + "="*80, "blue"))
        print(colored(f"📝 TESTE {numero}/{total}", "blue", attrs=['bold']))
        print(colored("="*80, "blue"))
        print(colored(f"❓ Pergunta: {pergunta}", "white"))
        print(colored("-"*80, "blue"))
        
        # Classificar a pergunta ANTES de processar
        classificacao = None
        try:
            classificacao = self.sistema.query_classifier.classify_and_extract(pergunta)
            print(colored(f"📊 Categoria: {classificacao.get('categoria', 'N/A')}", "cyan"))
            print(colored(f"🏷️  Entidades: {json.dumps(classificacao.get('entidades', {}), ensure_ascii=False)}", "cyan"))
        except Exception as e:
            print(colored(f"⚠️  Erro ao classificar: {e}", "yellow"))
        
        resultado = {
            'numero': numero,
            'pergunta': pergunta,
            'categoria': classificacao.get('categoria') if classificacao else None,
            'entidades': classificacao.get('entidades') if classificacao else None,
            'resposta': None,
            'tempo_total': 0,
            'tempo_classificacao': 0,
            'tempo_processamento': 0,
            'sucesso': False,
            'erro': None,
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            inicio = time.time()
            
            # Executar pergunta
            resposta = self.sistema.processar_pergunta_unica(pergunta)
            
            tempo_execucao = time.time() - inicio
            
            # Registrar resultado
            resultado['resposta'] = resposta
            resultado['tempo'] = tempo_execucao
            resultado['sucesso'] = True
            
            # Exibir resposta
            print(colored("\n✅ RESPOSTA:", "green", attrs=['bold']))
            print(colored("-"*80, "green"))
            print(resposta)
            print(colored("-"*80, "green"))
            print(colored(f"⏱️  Tempo: {tempo_execucao:.2f}s", "yellow"))
            
        except Exception as e:
            tempo_execucao = time.time() - inicio
            resultado['tempo'] = tempo_execucao
            resultado['erro'] = str(e)
            
            print(colored(f"\n❌ ERRO: {e}", "red", attrs=['bold']))
            print(colored(f"⏱️  Tempo até erro: {tempo_execucao:.2f}s", "yellow"))
        
        self.resultados.append(resultado)
    
    def _gerar_relatorio(self):
        """
        Gera relatório completo dos testes
        """
        print(colored("\n" + "="*80, "cyan"))
        print(colored("📊 RELATÓRIO FINAL DOS TESTES", "cyan", attrs=['bold']))
        print(colored("="*80, "cyan"))
        
        # Estatísticas gerais
        total_testes = len(self.resultados)
        sucessos = sum(1 for r in self.resultados if r['sucesso'])
        falhas = total_testes - sucessos
        tempo_medio = self.tempo_total / total_testes if total_testes > 0 else 0
        
        print(colored(f"\n📈 ESTATÍSTICAS:", "yellow", attrs=['bold']))
        print(colored(f"  Total de testes: {total_testes}", "white"))
        print(colored(f"  ✅ Sucessos: {sucessos} ({sucessos/total_testes*100:.1f}%)", "green"))
        print(colored(f"  ❌ Falhas: {falhas} ({falhas/total_testes*100:.1f}%)", "red"))
        print(colored(f"  ⏱️  Tempo total: {self.tempo_total:.2f}s", "yellow"))
        print(colored(f"  ⏱️  Tempo médio: {tempo_medio:.2f}s/pergunta", "yellow"))
        
        # Testes mais rápidos e mais lentos
        if self.resultados:
            resultados_ordenados = sorted(self.resultados, key=lambda x: x['tempo'])
            mais_rapido = resultados_ordenados[0]
            mais_lento = resultados_ordenados[-1]
            
            print(colored(f"\n⚡ TESTE MAIS RÁPIDO:", "green"))
            print(colored(f"  #{mais_rapido['numero']}: {mais_rapido['pergunta'][:60]}...", "white"))
            print(colored(f"  Tempo: {mais_rapido['tempo']:.2f}s", "yellow"))
            
            print(colored(f"\n🐌 TESTE MAIS LENTO:", "red"))
            print(colored(f"  #{mais_lento['numero']}: {mais_lento['pergunta'][:60]}...", "white"))
            print(colored(f"  Tempo: {mais_lento['tempo']:.2f}s", "yellow"))
        
        # Listar falhas (se houver)
        if falhas > 0:
            print(colored(f"\n❌ TESTES QUE FALHARAM:", "red", attrs=['bold']))
            for r in self.resultados:
                if not r['sucesso']:
                    print(colored(f"  #{r['numero']}: {r['pergunta']}", "white"))
                    print(colored(f"    Erro: {r['erro']}", "red"))
        
        # Salvar resultados em arquivo
        self._salvar_resultados_arquivo()
        
        print(colored("\n" + "="*80, "cyan"))
        print(colored("🎉 TESTES CONCLUÍDOS!", "green", attrs=['bold']))
        print(colored("="*80 + "\n", "cyan"))
    
    def _salvar_resultados_arquivo(self):
        """
        Salva resultados em arquivo JSON e TXT na pasta 'resultados'
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Salvar JSON (dados completos)
        arquivo_json = self.pasta_resultados / f"teste_resultados_{timestamp}.json"
        with open(arquivo_json, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'tempo_total': self.tempo_total,
                'total_testes': len(self.resultados),
                'sucessos': sum(1 for r in self.resultados if r['sucesso']),
                'resultados': self.resultados
            }, f, ensure_ascii=False, indent=2)
        
        print(colored(f"\n💾 Resultados salvos em: {arquivo_json}", "cyan"))
        
        # Salvar TXT (relatório legível)
        arquivo_txt = self.pasta_resultados / f"teste_relatorio_{timestamp}.txt"
        with open(arquivo_txt, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write("RELATÓRIO DE TESTES - Sistema de Consulta Veterinária\n")
            f.write("="*80 + "\n\n")
            f.write(f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total de testes: {len(self.resultados)}\n")
            f.write(f"Tempo total: {self.tempo_total:.2f}s\n\n")
            
            for r in self.resultados:
                f.write(f"\n{'='*80}\n")
                f.write(f"TESTE #{r['numero']}\n")
                f.write(f"{'='*80}\n")
                f.write(f"Pergunta: {r['pergunta']}\n")
                f.write(f"Status: {'✅ SUCESSO' if r['sucesso'] else '❌ FALHA'}\n")
                f.write(f"Tempo: {r['tempo']:.2f}s\n")
                
                if r['sucesso']:
                    f.write(f"\nResposta:\n{'-'*80}\n")
                    f.write(f"{r['resposta']}\n")
                    f.write(f"{'-'*80}\n")
                else:
                    f.write(f"\nErro: {r['erro']}\n")
        
        print(colored(f"📄 Relatório legível salvo em: {arquivo_txt}", "cyan"))



def main():
    """
    Função principal para executar testes
    """
    
    # Lista de perguntas de teste
    test_queries = [
        "Para que espécies está indicado o medicamento Simparica?",
        "Qual a dose indicada do medicamento Senvelgo 15 mg/ml em gatos?",
        "Qual a forma de administração do medicamento Pathozone 250 mg em bovinos?",
        "Como deve ser armazenado, depois de aberto o medicamento Flevox?",
        "Quais os intervalos de segurança do medicamento Felpreva?",
        "O medicamentos Maxy é usado para que?",
        "Que medicamentos/marcas existem com o princípio ativo altrenogest indicado para porcos?",
        "Que medicamentos existem com o mesmo princípio ativo que o medicamento/marca Terramicina 55 mg/g?",
        "Para que espécies está indicado o medicamento Animeloxan?",
        "Que medicamentos contendo o princípio ativo Meloxicam pode ser administrado a suínos?",
        "Qual a dose indicada do medicamento Dexinjet 2 mg/ml em suínos?",
        "Qual a forma de administração do medicamento Hidrocol em suínos?",
        "E perus?", 
        "Qual a dose que deve ser administrada do medicamento Domtor em gatos?",
        "Como deve ser armazenado o medicamento Acuimix?",
        "Como deve ser armazenado, depois de aberto o medicamento Calcibel?",
        "Quais os intervalos de segurança do medicamento Maxy?",
        "Para que é usado o medicamentos Apilife?",
        "Qual é a composição do medicamento Genestran?",
        "Em que espécies pode ser usado o medicamento Terramicina 500 mg?",
        "Que reações adversas pode apresentar o medicamento Suispirin?",
        "O medicamento Colombovac PMV/POX é sujeito a receita médica veterinária?",
        "Que medicamentos/marcas existem com o princípio ativo butorfanol indicado para gatos?",
        "Que medicamentos/marcas existem com o princípio ativo doramectina?",
        "Que medicamentos/marcas existem em comprimidos com o princípio ativo ácido tolfenâmico?",
        "Que medicamentos existem com o mesmo princípio ativo que o medicamento/marca Animeloxan?",
        "Qual o medicamento alternativo para Trocoxil 75 para cães?",
    ]
    
    # Criar testador e executar
    testador = TestadorAutomatico()
    
    try:
        testador.executar_testes(test_queries)
    except KeyboardInterrupt:
        print(colored("\n\n⚠️  Testes interrompidos pelo usuário", "yellow"))
        print(colored("📊 Gerando relatório parcial...\n", "yellow"))
        testador._gerar_relatorio()
    except Exception as e:
        print(colored(f"\n\n❌ Erro fatal: {e}", "red"))
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()