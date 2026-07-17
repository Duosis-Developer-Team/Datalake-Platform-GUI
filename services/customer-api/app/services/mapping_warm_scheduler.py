"""Debounced background warm for customers whose mapping just changed."""
from __future__ import annotations

import logging
import threading
from typing import Callable, Iterable

logger = logging.getLogger(__name__)

DEFAULT_WARM_DELAY_SECONDS = 10.0


class MappingWarmScheduler:
    """Warm a customer once, shortly after their mapping settles.

    Debounced per name: a rollout that corrects the same customer several times
    in a row should fire one warm, not one per save. Process-local by design —
    customer-api runs as a single uvicorn process, and if that ever changes the
    worst case is a duplicate warm, which is idempotent.
    """

    def __init__(
        self,
        warm_fn: Callable[[str], None],
        delay_seconds: float = DEFAULT_WARM_DELAY_SECONDS,
    ) -> None:
        self._warm_fn = warm_fn
        self._delay = delay_seconds
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def schedule(self, names: Iterable[str]) -> None:
        for raw in names or []:
            name = str(raw or "").strip()
            if not name:
                continue
            with self._lock:
                existing = self._timers.pop(name, None)
                if existing is not None:
                    existing.cancel()
                timer = threading.Timer(self._delay, self._run, args=(name,))
                timer.daemon = True
                self._timers[name] = timer
                timer.start()

    def _run(self, name: str) -> None:
        with self._lock:
            self._timers.pop(name, None)
        try:
            self._warm_fn(name)
        except Exception as exc:  # noqa: BLE001
            # Warming is an optimisation. A failure leaves the cache empty, and
            # the next read recomputes it — correctness is unaffected.
            logger.warning("Mapping warm failed for customer=%s: %s", name, exc)

    def cancel_all(self) -> None:
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()
