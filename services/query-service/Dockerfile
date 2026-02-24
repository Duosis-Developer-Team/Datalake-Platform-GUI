FROM python:3.11-slim

WORKDIR /app

# System deps: curl healthcheck için zorunlu
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Layer cache optimizasyonu: bağımlılıklar koddan önce kopyalanır
COPY services/query-service/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Paylaşılan şemalar (shared/schemas/) imaja bake edilir
COPY shared/ ./shared/

# Servis kodu
COPY services/query-service/ .

EXPOSE 8002

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8002"]
