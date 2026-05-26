# syntax=docker/dockerfile:1.6
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Dependências do sistema para PyMuPDF, Selenium e chromium-driver
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    chromium \
    chromium-driver \
    libglib2.0-0 \
    libnss3 \
    libgconf-2-4 \
    libxss1 \
    libasound2 \
    fonts-liberation \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Camada de deps cacheável
COPY pyproject.toml requirements.txt ./
RUN pip install -r requirements.txt

# Código
COPY backend ./backend
COPY frontend ./frontend
COPY data/perguntas_exemplo.txt ./data/perguntas_exemplo.txt
COPY scripts ./scripts

ENV CHROME_BIN=/usr/bin/chromium \
    PATH=/usr/lib/chromium:$PATH \
    APP_MODE=docker

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -fsS http://localhost:5000/api/status || exit 1

# Em produção usar gunicorn; em dev (APP_DEBUG=true) cair no app.py
CMD ["sh", "-c", "if [ \"$APP_DEBUG\" = \"true\" ]; then python -m backend.api.app; else gunicorn -b 0.0.0.0:5000 -w ${API_WORKERS:-2} -k gthread --threads 4 --timeout 180 'backend.api.app:create_app()'; fi"]
