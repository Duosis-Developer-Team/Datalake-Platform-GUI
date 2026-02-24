FROM python:3.11-slim

WORKDIR /app

# System deps: asyncpg için libpq gerekli
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Layer cache optimizasyonu: bağımlılıklar koddan önce kopyalanır
COPY services/db-service/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Paylaşılan şemalar (shared/schemas/) imaja bake edilir
COPY shared/ ./shared/

# Servis kodu
COPY services/db-service/ .

EXPOSE 8001

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]
