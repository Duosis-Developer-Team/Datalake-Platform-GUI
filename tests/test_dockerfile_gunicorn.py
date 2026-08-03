"""gunicorn must survive a worker recycle without taking the app down.

This file used to assert `--workers 1`, on the reasoning that a second worker
would mean a second in-process cache. That reasoning no longer holds: with
REDIS_URL set (which every deployment sets) cache_service selects RedisBackend,
so the cache — and the single-flight lock that guards it (SET NX EX, see
RedisBackend.try_acquire) — is shared across processes.

What single-worker did guarantee is that every `--max-requests` recycle is a
full outage: one process exits, and until it has re-imported the app nothing
serves. Measured on the running container, that window is ~196 s, during which
requests hang and the page a user is looking at stops updating. Two workers make
the recycle invisible.
"""

import json
import re
from pathlib import Path


def _gunicorn_argv() -> list[str]:
    text = Path("Dockerfile").read_text(encoding="utf-8")
    match = re.search(r"^CMD (\[.*\])\s*$", text, re.MULTILINE)
    assert match, "Dockerfile must end with an exec-form CMD"
    return json.loads(match.group(1))


def _flag(name: str) -> str:
    argv = _gunicorn_argv()
    assert name in argv, f"{name} missing from the gunicorn CMD"
    return argv[argv.index(name) + 1]


def test_more_than_one_worker():
    """A recycle must never leave zero processes serving."""
    assert int(_flag("--workers")) >= 2


def test_threads_stay_at_eight():
    assert int(_flag("--threads")) == 8


def test_worker_class_is_gthread():
    """The sync worker ignores --threads, so the thread count would be a lie."""
    assert _flag("--worker-class") == "gthread"


def test_recycle_is_rare_and_staggered():
    """Jitter is what keeps two workers from recycling on the same request count."""
    max_requests = int(_flag("--max-requests"))
    jitter = int(_flag("--max-requests-jitter"))

    assert max_requests >= 20000, "recycling every 2000 requests is far too often"
    assert jitter >= max_requests // 20, "too little jitter: workers recycle together"


def test_graceful_timeout_is_short_enough_to_matter():
    """120 s of graceful drain on top of the boot time widens the recycle window;
    an interrupted warm fetch is retried by the next request anyway."""
    assert int(_flag("--graceful-timeout")) <= 30


def test_request_timeout_survives_slow_first_loads():
    assert int(_flag("--timeout")) >= 300
