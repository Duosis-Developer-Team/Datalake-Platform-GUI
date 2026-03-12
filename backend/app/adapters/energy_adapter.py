from __future__ import annotations

from typing import Callable

from app.db.queries import energy as eq


class EnergyAdapter:
    def __init__(self, get_connection: Callable, run_value: Callable):
        self._get_connection = get_connection
        self._run_value = run_value

    def fetch_single_dc(self, cursor, dc_code_exact: str, dc_code_like: str, start_ts, end_ts) -> dict:
        return {
            "ibm_w": self._run_value(cursor, eq.IBM, (dc_code_like, start_ts, end_ts)),
            "vcenter_w": self._run_value(cursor, eq.VCENTER, (dc_code_exact, start_ts, end_ts)),
            "ibm_kwh": self._run_value(cursor, eq.IBM_KWH, (dc_code_like, start_ts, end_ts)),
            "vcenter_kwh": self._run_value(cursor, eq.VCENTER_KWH, (dc_code_exact, start_ts, end_ts)),
        }

    def fetch_batch_queries(self, dc_list, pattern_list, start_ts, end_ts) -> list:
        return [
            ("e_ibm",      eq.BATCH_IBM,         (start_ts, end_ts, dc_list)),
            ("e_vcenter",  eq.BATCH_VCENTER,     (dc_list, pattern_list, start_ts, end_ts)),
            ("e_ibm_kwh",  eq.BATCH_IBM_KWH,     (start_ts, end_ts, dc_list)),
            ("e_vctr_kwh", eq.BATCH_VCENTER_KWH, (dc_list, pattern_list, start_ts, end_ts)),
        ]
