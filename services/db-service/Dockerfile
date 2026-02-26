# ── Stage 1: Builder (derleme araçları + asyncpg binary) ──────────────────────
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY services/db-service/requirements.txt requirements.txt
RUN pip install --user --no-cache-dir -r requirements.txt

# ── Stage 2: Production (sadece runtime bağımlılıkları) ─────────────────────
FROM python:3.11-slim AS production

# asyncpg binary için libpq5 (runtime), healthcheck için curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Builder'dan derlenmiş paketleri kopyala
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

WORKDIR /app

# Paylaşılan şemalar (shared/schemas/) imaja bake edilir
COPY shared/ ./shared/

# Servis kodu
COPY services/db-service/ .

EXPOSE 8001

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "2"]
