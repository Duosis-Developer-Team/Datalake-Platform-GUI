from __future__ import annotations

from app.adapters.base import PlatformAdapter
from app.db.queries import nutanix as nq


class NutanixAdapter(PlatformAdapter):
    def fetch_single_dc(self, cursor, dc_param: str, start_ts, end_ts) -> dict:
        return {
            "host_count": self._run_value(cursor, nq.HOST_COUNT, (dc_param, start_ts, end_ts)),
            "vm_count": self._run_value(cursor, nq.VM_COUNT, (dc_param, start_ts, end_ts)),
            "memory": self._run_row(cursor, nq.MEMORY, (dc_param, start_ts, end_ts)),
            "storage": self._run_row(cursor, nq.STORAGE, (dc_param, start_ts, end_ts)),
            "cpu": self._run_row(cursor, nq.CPU, (dc_param, start_ts, end_ts)),
        }

    def fetch_batch_queries(self, dc_list, pattern_list, start_ts, end_ts) -> list:
        params = (dc_list, pattern_list, start_ts, end_ts)
        return [
            ("n_host",     nq.BATCH_HOST_COUNT,     params),
            ("n_vm",       nq.BATCH_VM_COUNT,       params),
            ("n_mem",      nq.BATCH_MEMORY,         params),
            ("n_stor",     nq.BATCH_STORAGE,        params),
            ("n_cpu",      nq.BATCH_CPU,            params),
            ("n_platform", nq.BATCH_PLATFORM_COUNT, params),
        ]
