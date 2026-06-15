"""P6: gunicorn runs with >=8 threads and exactly 1 worker (single in-process cache)."""
from pathlib import Path


def test_gunicorn_threads_and_single_worker():
    cmd = Path("Dockerfile").read_text(encoding="utf-8")
    assert '"--workers", "1"' in cmd, "must stay single-worker (in-process cache)"
    assert '"--threads", "8"' in cmd, "threads should be raised to 8"
