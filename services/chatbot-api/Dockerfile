FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY services/datalake-tools-core /build/datalake-tools-core
COPY services/chatbot-api/requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --prefix=/install /build/datalake-tools-core \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Platform versioning (TASK-64): baked per build, recorded via self-registration.
ARG APP_VERSION=local
ARG GIT_SHA=local
ENV APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA}

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
COPY services/chatbot-api/app/ ./app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
