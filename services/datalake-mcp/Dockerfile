FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY services/datalake-tools-core /app/services/datalake-tools-core
COPY services/datalake-mcp /app/services/datalake-mcp

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir /app/services/datalake-tools-core \
    && pip install --no-cache-dir -r /app/services/datalake-mcp/requirements.txt

ENV PYTHONPATH=/app/services/datalake-mcp

EXPOSE 8010

WORKDIR /app/services/datalake-mcp

CMD ["python", "-m", "datalake_mcp", "--transport", "http", "--port", "8010"]
