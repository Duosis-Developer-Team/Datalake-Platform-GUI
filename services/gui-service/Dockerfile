FROM python:3.11-slim

WORKDIR /app

# Layer cache optimizasyonu: bağımlılıklar koddan önce kopyalanır
COPY services/gui-service/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Paylaşılan şemalar (shared/schemas/) imaja bake edilir
COPY shared/ ./shared/

# Servis kodu
COPY services/gui-service/ .

EXPOSE 8050

CMD ["python", "app.py"]
