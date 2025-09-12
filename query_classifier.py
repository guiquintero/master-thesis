#Que medicamentos existem com o mesmo princípio ativo que o medicamento Mavacoxib 75.0 mg?
#qual o medicamento alternativo para Trocoxil 75 para cães?

import json
import re
import ollama
from termcolor import colored

class QueryClassifier:
    def __init__(self, model="phi3:mini"):
        self.model = model

    def classify_and_extract(self, query):
        prompt = f"""
        Analise a seguinte pergunta do usuário e classifique-a em uma das categorias:
        - 'medicamento': Se a pergunta busca informações sobre um medicamento específico que pode precisar de web scraping.
        - 'legislacao': Se a pergunta busca informações sobre legislação ou regulamentação.
        - 'comparacao': Se a pergunta busca comparar medicamentos ou encontrar alternativas com base em especificações.
        - 'erro': Se a pergunta não se encaixa em nenhuma das categorias acima ou não é possível classificar.

        Além da classificação, extraia as seguintes entidades relevantes para cada categoria:

        Para 'medicamento':
        - 'termo_busca': O nome do medicamento, substância ativa ou espécie alvo para buscar no site.
        - 'pergunta_ollama': A pergunta específica a ser feita ao Ollama sobre o conteúdo raspado.

        Para 'legislacao':
        - 'pergunta_ollama': A pergunta específica a ser feita ao Ollama sobre a legislação.

        Para 'comparacao':
        - 'substancia_ativa': A substância ativa desejada (pode ser vazia).
        - 'especie_alvo': A espécie alvo desejada (pode ser vazia).
        - 'forma_farmaceutica': A forma farmacêutica desejada (pode ser vazia).
        - 'pergunta_ollama': A pergunta específica a ser feita ao Ollama para a comparação.

        Formato de saída JSON:
        {{
            "categoria": "[medicamento|legislacao|comparacao]",
            "entidades": {{
                "termo_busca": "string",
                "pergunta_ollama": "string",
                "substancia_ativa": "string",
                "especie_alvo": "string",
                "forma_farmaceutica": "string"
            }}
        }}

        Exemplos de Medicamentos:
        Pergunta: "Para que espécies está indicado o medicamento Animedazon?"
        {{"categoria": "medicamento", "entidades": {{"termo_busca": "Animedazon", "pergunta_ollama": "Para que espécies está indicado o medicamento Animedazon?"}}}}

        Pergunta: "Que medicamento contendo o princípio ativo amoxicilina pode ser administrado a suínos?"
        {{"categoria": "medicamento", "entidades": {{"termo_busca": "amoxicilina suínos", "pergunta_ollama": "Que medicamento contendo o princípio ativo amoxicilina pode ser administrado a suínos?"}}}}

        Pergunta: "Qual a dose indicada do medicamento Belaflor em suínos?"
        {{"categoria": "medicamento", "entidades": {{"termo_busca": "Belaflor suínos", "pergunta_ollama": "Qual a dose indicada do medicamento Belaflor em suínos?"}}}}

        Pergunta: "Qual a forma de administração do medicamento Vetmedin em cães?"
        {{"categoria": "medicamento", "entidades": {{"termo_busca": "Vetmedin cães", "pergunta_ollama": "Qual a forma de administração do medicamento Vetmedin em cães?"}}}}

        Pergunta: "Como deve ser armazenado o medicamento Synulox?"
        {{"categoria": "medicamento", "entidades": {{"termo_busca": "Synulox", "pergunta_ollama": "Como deve ser armazenado o medicamento Synulox?"}}}}

        Pergunta: "Como deve ser armazenado, depois de aberto o medicamento Iberzoon?"
        {{"categoria": "medicamento", "entidades": {{"termo_busca": "Iberzoon", "pergunta_ollama": "Como deve ser armazenado, depois de aberto o medicamento Iberzoon?"}}}}

        Pergunta: "Que medicamentos podem ser usado em ovinos para mastite?*****"
        {{"categoria": "medicamento", "entidades": {{"termo_busca": "mastite ovinos", "pergunta_ollama": "Que medicamentos podem ser usado em ovinos para mastite?"}}}}

        Pergunta: "Quais os intervalos de segurança do medicamento Maxyl?"
        {{"categoria": "medicamento", "entidades": {{"termo_busca": "Maxyl", "pergunta_ollama": "Quais os intervalos de segurança do medicamento Maxyl?"}}}}

        Pergunta: "Quem é o fabricante do medicamento Zoetis?"
        {{"categoria": "medicamento", "entidades": {{"termo_busca": "Zoetis", "pergunta_ollama": "Quem é o fabricante do medicamento Zoetis?"}}}}

        Pergunta: "Para que é usado o medicamento Enrofloxacina?"
        {{"categoria": "medicamento", "entidades": {{"termo_busca": "Enrofloxacina", "pergunta_ollama": "Para que é usado o medicamento Enrofloxacina?"}}}}

        Pergunta: "Qual é a composição do medicamento Pengetol?"
        {{"categoria": "medicamento", "entidades": {{"termo_busca": "Pengetol", "pergunta_ollama": "Qual é a composição do medicamento Pengetol?"}}}}

        Pergunta: "Em que espécies pode ser usado o medicamento Terramicina?"
        {{"categoria": "medicamento", "entidades": {{"termo_busca": "Terramicina", "pergunta_ollama": "Em que espécies pode ser usado o medicamento Terramicina?"}}}}

        Pergunta: "Que reações adversas pode apresentar o medicamento Metacam?"
        {{"categoria": "medicamento", "entidades": {{"termo_busca": "Metacam", "pergunta_ollama": "Que reações adversas pode apresentar o medicamento Metacam?"}}}}

        Pergunta: "O medicamento Convenia é sujeito a receita médica veterinária?"
        {{"categoria": "medicamento", "entidades": {{"termo_busca": "Convenia", "pergunta_ollama": "O medicamento Convenia é sujeito a receita médica veterinária?"}}}}

        Exemplos de Comparação:
        Pergunta: "Que medicamentos/marcas existem com o princípio ativo amoxicilina indicado para bovinos?"
        {{"categoria": "comparacao", "entidades": {{"substancia_ativa": "amoxicilina", "especie_alvo": "bovinos", "forma_farmaceutica": "", "pergunta_ollama": "Que medicamentos/marcas existem com o princípio ativo amoxicilina indicado para bovinos?"}}}}

        Pergunta: "Que medicamentos/marcas existem com o princípio ativo enrofloxacina?"
        {{"categoria": "comparacao", "entidades": {{"substancia_ativa": "enrofloxacina", "especie_alvo": "", "forma_farmaceutica": "", "pergunta_ollama": "Que medicamentos/marcas existem com o princípio ativo enrofloxacina?"}}}}

        Pergunta: "Que medicamentos/marcas existem em comprimidos com o princípio ativo meloxicam?"
        {{"categoria": "comparacao", "entidades": {{"substancia_ativa": "meloxicam", "especie_alvo": "", "forma_farmaceutica": "comprimidos", "pergunta_ollama": "Que medicamentos/marcas existem em comprimidos com o princípio ativo meloxicam?"}}}}

        Pergunta: "Que medicamentos existem com o mesmo princípio ativo que o medicamento Vetmedin?"
        {{"categoria": "comparacao", "entidades": {{"substancia_ativa": "Vetmedin", "especie_alvo": "", "forma_farmaceutica": "", "pergunta_ollama": "Que medicamentos existem com o mesmo princípio ativo que o medicamento Vetmedin?"}}}}

        Pergunta: "Quais medicamentos têm a mesma substância ativa do Convenia?"
        {{"categoria": "comparacao", "entidades": {{"substancia_ativa": "Convenia", "especie_alvo": "", "forma_farmaceutica": "", "pergunta_ollama": "Quais medicamentos têm a mesma substância ativa do Convenia?"}}}}

        Pergunta: "Que alternativas existem ao medicamento Metacam?"
        {{"categoria": "comparacao", "entidades": {{"substancia_ativa": "Metacam", "especie_alvo": "", "forma_farmaceutica": "", "pergunta_ollama": "Que alternativas existem ao medicamento Metacam?"}}}}

        Exemplos de Legislação:
        Pergunta: "O que é necessário para licenciar um centro de atendimento médico veterinário?"
        {{"categoria": "legislacao", "entidades": {{"pergunta_ollama": "O que é necessário para licenciar um centro de atendimento médico veterinário?"}}}}

        Pergunta: "O que é necessário para licenciar um Posto de Venda de Medicamentos Veterinários?"
        {{"categoria": "legislacao", "entidades": {{"pergunta_ollama": "O que é necessário para licenciar um Posto de Venda de Medicamentos Veterinários?"}}}}

        Pergunta: "O que é necessário para licenciar um Local de Venda de Medicamentos Veterinários Não Sujeitos a Receita Médica?"
        {{"categoria": "legislacao", "entidades": {{"pergunta_ollama": "O que é necessário para licenciar um Local de Venda de Medicamentos Veterinários Não Sujeitos a Receita Médica?"}}}}

        Pergunta: "Qual o procedimento para pedir um medicamento sujeito a uma Autorização de Utilização Especial?"
        {{"categoria": "legislacao", "entidades": {{"pergunta_ollama": "Qual o procedimento para pedir um medicamento sujeito a uma Autorização de Utilização Especial?"}}}}

        Pergunta: "Os centros de atendimento médico veterinário podem comercializar medicamentos sujeitos a receita médica veterinária?"
        {{"categoria": "legislacao", "entidades": {{"pergunta_ollama": "Os centros de atendimento médico veterinário podem comercializar medicamentos sujeitos a receita médica veterinária?"}}}}

        Pergunta: "Os centros de atendimento médico veterinário podem comercializar medicamentos psicotrópicos e estupefacientes?"
        {{"categoria": "legislacao", "entidades": {{"pergunta_ollama": "Os centros de atendimento médico veterinário podem comercializar medicamentos psicotrópicos e estupefacientes?"}}}}

        Pergunta: "Os postos de venda a retalho de medicamentos veterinários podem comercializar medicamentos psicotrópicos e estupefacientes?"
        {{"categoria": "legislacao", "entidades": {{"pergunta_ollama": "Os postos de venda a retalho de medicamentos veterinários podem comercializar medicamentos psicotrópicos e estupefacientes?"}}}}

        Pergunta: "Qual a validade de uma receita médico veterinária?"
        {{"categoria": "legislacao", "entidades": {{"pergunta_ollama": "Qual a validade de uma receita médico veterinária?"}}}}

        Pergunta: "É possível adquirir um medicamento sujeito a receita médica com uma receita fora de validade?"
        {{"categoria": "legislacao", "entidades": {{"pergunta_ollama": "É possível adquirir um medicamento sujeito a receita médica com uma receita fora de validade?"}}}}

        Pergunta: "Para adquirir um medicamento é obrigatório a apresentação de uma receita médico-veterinária?"
        {{"categoria": "legislacao", "entidades": {{"pergunta_ollama": "Para adquirir um medicamento é obrigatório a apresentação de uma receita médico-veterinária?"}}}}

        Pergunta: "É possível dispensar/vender um produto equivalente ao que consta na receita médico veterinária?"
        {{"categoria": "legislacao", "entidades": {{"pergunta_ollama": "É possível dispensar/vender um produto equivalente ao que consta na receita médico veterinária?"}}}}

        Pergunta: "{query}"
        """
        try:
            response = ollama.chat(
                model=self.model,
                messages=[
                    {
                        'role': 'user',
                        'content': prompt,
                    }
                ],
                options={
                    'temperature': 0.0  # Queremos respostas determinísticas para classificação
                }
            )
            content = response['message']['content']
            # Tentar extrair o JSON do texto da resposta
            json_match = re.search(r'```json\n(.*?)```', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = content # Se não encontrar o bloco de código, assume que a resposta é o JSON direto
            
            return json.loads(json_str)
        except Exception as e:
            print(colored(f"Erro ao classificar a pergunta com Ollama: {e}", "red"))
            return {"categoria": "erro", "entidades": {}}

if __name__ == "__main__":
    classifier = QueryClassifier()
    
    # Testes com os novos exemplos
    queries = [
        "Para que espécies está indicado o medicamento Animedazon?",
        "Que medicamento contendo o princípio ativo amoxicilina pode ser administrado a suínos?",
        "Qual a dose indicada do medicamento Belaflor em bovinos?",
        "Que medicamentos/marcas existem com o princípio ativo enrofloxacina indicado para bovinos?",
        "O que é necessário para licenciar um centro de atendimento médico veterinário?",
        "Qual a validade de uma receita médico veterinária?",
        "Que medicamentos existem com o mesmo princípio ativo que o medicamento Vetmedin?",
        "Como deve ser armazenado o medicamento Synulox?"
    ]

    for q in queries:
        print(f"\nPergunta: {q}")
        result = classifier.classify_and_extract(q)
        print(f"Resultado: {json.dumps(result, indent=2, ensure_ascii=False)}")


