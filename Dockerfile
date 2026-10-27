FROM python:3.12-slim

WORKDIR /app


# Instala dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia código fonte
COPY src/ ./src/
COPY .env .env

# Cria diretório de logs
RUN mkdir -p /app/logs

# Configura variável de ambiente para unbuffered output
ENV PYTHONUNBUFFERED=1

# Healthcheck interno do Docker (verifica se o processo está vivo)
HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD pgrep -f "python -m src" || exit 1

# Inicia o bot
CMD ["python", "-m", "src"]
