import re

frase = "\n \n6. \nINFORMAÇÕES FARMACÊUTICAS \n6.1 \nLista de excipientes \nÁcido cítrico anidro \n6.2 \nIncompatibilidades principais \nNa ausência de estudos \n \n7. \nINFORMAÇÕES FARMACÊUTICAS \n7.1 \nLista de excipientes \nÁcido cítrico anidro \n7.2 \nIncompatibilidades principais \nNa ausência de estudos"
palavras = re.split(r"\n \n\d+\. \n", frase)
palavras = re.sub(r"\n\d+\.d+ \n", "444", palavras)
print(f"Palavras: {palavras}")




