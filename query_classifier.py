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

        Exemplos:
        Pergunta: "Qual a dose recomendada para patos do Maxyl 500 mg/g"
        {{"categoria": "medicamento", "entidades": {{"termo_busca": "Maxyl 500 mg/g patos", "pergunta_ollama": "Qual a dose recomendada para patos?"}}}}

        Pergunta: "O que diz a legislação sobre a venda de antibióticos sem receita?"
        {{"categoria": "legislacao", "entidades": {{"pergunta_ollama": "O que diz a legislação sobre a venda de antibióticos sem receita?"}}}}

        Pergunta: "Preciso de uma alternativa para o Maxyl 500 mg/g que seja para cães e tenha a mesma substância ativa"
        {{"categoria": "comparacao", "entidades": {{"substancia_ativa": "Maxyl", "especie_alvo": "cães", "forma_farmaceutica": "", "pergunta_ollama": "Encontre alternativas para o Maxyl 500mg/g para cães com a mesma substância ativa."}}}}

        Pergunta: "Quais medicamentos para gatos com substância ativa 'Amoxicilina' e forma farmacêutica 'comprimido'?"
        {{"categoria": "comparacao", "entidades": {{"substancia_ativa": "Amoxicilina", "especie_alvo": "gatos", "forma_farmaceutica": "comprimido", "pergunta_ollama": "Quais medicamentos para gatos com substância ativa 'Amoxicilina' e forma farmacêutica 'comprimido'?"}}}}

        Pergunta: "Quais são os requisitos para importação de medicamentos veterinários em Portugal?"
        {{"categoria": "legislacao", "entidades": {{"pergunta_ollama": "Quais são os requisitos para importação de medicamentos veterinários em Portugal?"}}}}

        Pergunta: "Informações sobre o medicamento 'Vetmedin' para cães"
        {{"categoria": "medicamento", "entidades": {{"termo_busca": "Vetmedin cães", "pergunta_ollama": "Informações sobre o medicamento 'Vetmedin' para cães"}}}}

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
    
    # Testes
    queries = [
        "Qual a dose recomendada para patos do Maxyl 500mg/g",
        "O que diz a legislação sobre a venda de antibióticos sem receita?",
        "Preciso de uma alternativa para o Maxyl 500mg/g que seja para cães e tenha a mesma substância ativa",
        "Quais medicamentos para gatos com substância ativa 'Amoxicilina' e forma farmacêutica 'comprimido'?",
        "Quais são os requisitos para importação de medicamentos veterinários em Portugal?",
        "Informações sobre o medicamento 'Vetmedin' para cães"
    ]

    for q in queries:
        print(f"\nPergunta: {q}")
        result = classifier.classify_and_extract(q)
        print(f"Resultado: {json.dumps(result, indent=2, ensure_ascii=False)}")


