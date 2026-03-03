# Sistema de Consulta Veterinária

Sistema de IA para consultas veterinárias usando Ollama + web scraping do portal MedVet.

Sistema de IA para consultas veterinárias usando Ollama + web scraping do portal MedVet.

## Instalação

```bash
# Instalar dependências
pip install -r requirements.txt

# Instalar e iniciar Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama serve
ollama pull qwen2.5:14b
```

## Uso

### CLI Interativo
```bash
python src/core/sistema_consulta.py
```

### API REST
```bash
python src/api/api_vet.py
# Acesse: http://localhost:5000
```

### Interface Web
```bash
./scripts/iniciar_web.sh
# Abrir: http://localhost:8000/frontend/site.html
```

## Estrutura

```
src/
  core/           # Sistema principal
  api/            # API Flask
  utils/          # Utilitários
  tests/          # Testes
frontend/         # Interface web
data/             # Cache e resultados
scripts/          # Scripts auxiliares
```

## Licença

MIT
