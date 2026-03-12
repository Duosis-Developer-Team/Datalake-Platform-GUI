from __future__ import annotations

from app.adapters.base import PlatformAdapter
from app.db.queries import vmware as vq


class VMwareAdapter(PlatformAdapter):
    def fetch_single_dc(self, cursor, dc_param: str, start_ts, end_ts) -> dict:
        return {
            "counts": self._run_row(cursor, vq.COUNTS, (dc_param, start_ts, end_ts)),
            "memory": self._run_row(cursor, vq.MEMORY, (dc_param, start_ts, end_ts)),
            "storage": self._run_row(cursor, vq.STORAGE, (dc_param, start_ts, end_ts)),
            "cpu": self._run_row(cursor, vq.CPU, (dc_param, start_ts, end_ts)),
        }

    def fetch_batch_queries(self, dc_list, pattern_list, start_ts, end_ts) -> list:
        params = (dc_list, pattern_list, start_ts, end_ts)
        return [
            ("v_cnt",      vq.BATCH_COUNTS,         params),
            ("v_mem",      vq.BATCH_MEMORY,         params),
            ("v_stor",     vq.BATCH_STORAGE,        params),
            ("v_cpu",      vq.BATCH_CPU,            params),
            ("v_platform", vq.BATCH_PLATFORM_COUNT, params),
        ]
