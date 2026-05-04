# crm-engine — dedicated container for CRM/sellable computation.
# Reuses customer-api shared modules (services, db queries, models, core, utils,
# adapters, telemetry, config) by copying them in first; then layers crm-engine
# specific main.py and routers/ on top.
FROM python:3.11-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*
COPY services/crm-engine/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /install /usr/local
COPY shared/ ./shared/
# Shared customer-api modules (services, db, models, core, utils, adapters, config, telemetry).
COPY services/customer-api/app/ ./app/
# Layer crm-engine specific main.py + routers/ on top.
COPY services/crm-engine/app/ ./app/
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
