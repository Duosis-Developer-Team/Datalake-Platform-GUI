FROM python:3.11-slim

WORKDIR /app

# curl: docker healthcheck için zorunlu (python:3.11-slim içermiyor)
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Layer cache optimizasyonu: bağımlılıklar koddan önce kopyalanır
COPY services/gui-service/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Paylaşılan şemalar (shared/schemas/) imaja bake edilir
COPY shared/ ./shared/

# Servis kodu
COPY services/gui-service/ .

EXPOSE 8050

CMD ["python", "app.py"]
