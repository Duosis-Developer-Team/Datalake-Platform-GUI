FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set at build time so you can confirm the running image (e.g. git sha):
#   APP_BUILD_ID=$(git rev-parse --short HEAD) docker compose build app
ARG APP_BUILD_ID=local
ENV APP_BUILD_ID=${APP_BUILD_ID}

# Platform versioning (TASK-64): recorded per deployment via self-registration.
ARG APP_VERSION=local
ARG GIT_SHA=local
ENV APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA}

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN pip install --no-cache-dir -e dash_globe_component/
RUN pip install --no-cache-dir -e dash_hmdl_flow/

EXPOSE 8050

# gthread: threads actually handle concurrent requests (sync worker ignores --threads).
# Higher timeout avoids false WORKER TIMEOUT on slow first loads / many API calls.
# workers 2: a --max-requests recycle takes ~196 s to come back (measured), and
#   with one worker that is a full outage — the page a user is watching just
#   stops updating. The second worker keeps serving through it. Safe because the
#   cache is shared (RedisBackend + SET NX EX single-flight), not per-process.
# max-requests 20000/jitter 2000: still bounds the memory growth this was added
#   for, but recycles ~10x less often and never lines the two workers up.
#   The underlying leak is a separate piece of work; keep a mem_limit on the
#   container until it is fixed.
# graceful-timeout 30: 120 s of drain sits on top of the recycle window. An
#   interrupted warm fetch is retried by the next request.
# worker-tmp-dir: use shared memory for heartbeat files (Linux).
CMD ["gunicorn", "app:server", "--bind", "0.0.0.0:8050", "--worker-class", "gthread", "--workers", "2", "--threads", "8", "--timeout", "300", "--graceful-timeout", "30", "--keep-alive", "5", "--max-requests", "20000", "--max-requests-jitter", "2000", "--worker-tmp-dir", "/dev/shm"]

