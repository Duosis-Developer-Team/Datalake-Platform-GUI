from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable


class PlatformAdapter(ABC):
    def __init__(self, get_connection: Callable, run_value: Callable, run_row: Callable, run_rows: Callable):
        self._get_connection = get_connection
        self._run_value = run_value
        self._run_row = run_row
        self._run_rows = run_rows

    @abstractmethod
    def fetch_single_dc(self, cursor, dc_param: str, start_ts, end_ts) -> dict[str, Any]:
        ...

    @abstractmethod
    def fetch_batch_queries(
        self, dc_list: list[str], pattern_list: list[str], start_ts, end_ts
    ) -> list[tuple[str, str, tuple]]:
        ...
