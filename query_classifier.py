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

        - 'comparacao': Se a pergunta busca comparar medicamentos ou encontrar alternativas com base em especificações.
        - 'erro': Se a pergunta não se encaixa em nenhuma das categorias acima ou não é possível classificar.

        Além da classificação, extraia as seguintes entidades relevantes para cada categoria:

        Para 'medicamento':
        - 'termo_busca': O nome do medicamento, substância ativa ou espécie alvo para buscar no site.
        - 'pergunta_ollama': A pergunta específica a ser feita ao Ollama sobre o conteúdo raspado.



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

        Pergunta: "Que medicamento contendo o princípio ativo amoxicilina pode ser administrado a suínos?*****"
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



