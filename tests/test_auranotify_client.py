"""Tests for AuraNotify HTTP client thread-local setup."""
from __future__ import annotations

import threading

from src.services import auranotify_client as aura


def test_get_client_is_thread_local():
    clients: list = []

    def worker() -> None:
        clients.append(aura._get_client())

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(clients) == 3
    assert len({id(c) for c in clients}) == 3
