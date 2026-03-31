"""Run independent API-bound callables in parallel (ThreadPoolExecutor)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, TypeVar

T = TypeVar("T")


def parallel_execute(tasks: dict[str, Callable[[], T]]) -> dict[str, T]:
    """Execute each task in a thread pool; propagates the first exception like sequential code."""
    results: dict[str, T] = {}
    if not tasks:
        return results
    max_workers = min(8, len(tasks))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_key = {pool.submit(fn): key for key, fn in tasks.items()}
        for fut in as_completed(future_to_key):
            key = future_to_key[fut]
            results[key] = fut.result()
    return results
