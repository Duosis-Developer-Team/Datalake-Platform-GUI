FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set at build time so you can confirm the running image (e.g. git sha):
#   APP_BUILD_ID=$(git rev-parse --short HEAD) docker compose build app
ARG APP_BUILD_ID=local
ENV APP_BUILD_ID=${APP_BUILD_ID}

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8050

# gthread: threads actually handle concurrent requests (sync worker ignores --threads).
# Higher timeout avoids false WORKER TIMEOUT on slow first loads / many API calls.
# max-requests: recycle worker to limit long-lived memory growth (mitigate OOM).
# worker-tmp-dir: use shared memory for heartbeat files (Linux).
CMD ["gunicorn", "app:server", "--bind", "0.0.0.0:8050", "--worker-class", "gthread", "--workers", "1", "--threads", "4", "--timeout", "300", "--graceful-timeout", "120", "--keep-alive", "5", "--max-requests", "2000", "--max-requests-jitter", "200", "--worker-tmp-dir", "/dev/shm"]

