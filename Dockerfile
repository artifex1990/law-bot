FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-client \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 120 -r requirements.txt

COPY . .

# Сборка на Windows: CRLF в .sh ломает exec (kernel ищет /bin/sh\r)
RUN mkdir -p logs backups \
    && sed -i 's/\r$//' scripts/docker-entrypoint.sh \
    && chmod +x scripts/docker-entrypoint.sh

# HEALTHCHECK задайте в docker-compose (зависит от API_ENABLED и вебхуков)

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
