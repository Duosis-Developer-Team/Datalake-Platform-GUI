FROM python:3.11-slim

WORKDIR /app

# Layer cache optimizasyonu: bağımlılıklar koddan önce kopyalanır
COPY services/query-service/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Paylaşılan şemalar (shared/schemas/) imaja bake edilir
COPY shared/ ./shared/

# Servis kodu
COPY services/query-service/ .

EXPOSE 8002

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8002"]
