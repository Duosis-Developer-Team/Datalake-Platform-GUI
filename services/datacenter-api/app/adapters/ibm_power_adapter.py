from __future__ import annotations

import re

from app.adapters.base import PlatformAdapter
from app.db.queries import ibm as iq

_DC_CODE_RE = re.compile(r'(DC\d+|AZ\d+|ICT\d+|UZ\d+|DH\d+)', re.IGNORECASE)


def _extract_dc(server_name: str, dc_set_upper: set[str]) -> str | None:
    if not server_name:
        return None
    m = _DC_CODE_RE.search(server_name.upper())
    if m and m.group(1) in dc_set_upper:
        return m.group(1)
    return None


class IBMPowerAdapter(PlatformAdapter):
    def fetch_single_dc(self, cursor, dc_param: str, start_ts, end_ts) -> dict:
        return {
            "host_count": self._run_value(cursor, iq.HOST_COUNT, (dc_param, start_ts, end_ts)),
            "vios_count": self._run_value(cursor, iq.VIOS_COUNT, (dc_param, start_ts, end_ts)),
            "lpar_count": self._run_value(cursor, iq.LPAR_COUNT, (dc_param, start_ts, end_ts)),
            "memory": self._run_row(cursor, iq.MEMORY, (dc_param, start_ts, end_ts)),
            "cpu": self._run_row(cursor, iq.CPU, (dc_param, start_ts, end_ts)),
        }

    def fetch_batch_queries(self, dc_list, pattern_list, start_ts, end_ts) -> list:
        ts_params = (start_ts, end_ts)
        return [
            ("ibm_host_raw", iq.BATCH_RAW_HOST,   ts_params),
            ("ibm_vios_raw", iq.BATCH_RAW_VIOS,   ts_params),
            ("ibm_lpar_raw", iq.BATCH_RAW_LPAR,   ts_params),
            ("ibm_mem_raw",  iq.BATCH_RAW_MEMORY,  ts_params),
            ("ibm_cpu_raw",  iq.BATCH_RAW_CPU,     ts_params),
        ]

    def process_raw_batch(self, raw_data: dict, dc_set_upper: set[str]) -> dict:
        ibm_h: dict[str, int] = {}
        for row in raw_data.get("ibm_host_raw", []):
            dc = _extract_dc(row[0], dc_set_upper) if row else None
            if dc:
                ibm_h.setdefault(dc, set()).add(row[0])
        ibm_h = {dc: len(names) for dc, names in ibm_h.items()}

        ibm_vios: dict[str, int] = {}
        for row in raw_data.get("ibm_vios_raw", []):
            dc = _extract_dc(row[0], dc_set_upper) if row and len(row) > 1 else None
            if dc:
                ibm_vios.setdefault(dc, set()).add(row[1])
        ibm_vios = {dc: len(names) for dc, names in ibm_vios.items()}

        ibm_lpar: dict[str, int] = {}
        for row in raw_data.get("ibm_lpar_raw", []):
            dc = _extract_dc(row[0], dc_set_upper) if row and len(row) > 1 else None
            if dc:
                ibm_lpar.setdefault(dc, set()).add(row[1])
        ibm_lpar = {dc: len(names) for dc, names in ibm_lpar.items()}

        # Latest sample per (dc, server) in MB, then sum for DC.
        mem_hosts: dict[str, dict[str, list]] = {}
        for row in raw_data.get("ibm_mem_raw", []):
            if not row or len(row) < 5:
                continue
            server_name = row[0]
            dc = _extract_dc(server_name, dc_set_upper)
            if not dc:
                continue
            try:
                t_mem = float(row[1] or 0)
                a_mem = float(row[2] or 0)
                as_mem = float(row[3] or 0)
            except (TypeError, ValueError):
                continue
            ts = row[4]
            mem_hosts.setdefault(dc, {}).setdefault(server_name, []).append(
                (t_mem, a_mem, as_mem, ts)
            )
        ibm_mem: dict[str, tuple] = {}
        for dc, hosts in mem_hosts.items():
            t_mb = a_mb = as_mb = 0.0
            for _svr, samples in hosts.items():
                if not samples:
                    continue
                lt, la, las, _ts = max(samples, key=lambda v: v[3])
                t_mb += lt
                a_mb += la
                as_mb += las
            ibm_mem[dc] = (t_mb, a_mb, as_mb)

        cpu_hosts: dict[str, dict[str, list]] = {}
        for row in raw_data.get("ibm_cpu_raw", []):
            if not row or len(row) < 6:
                continue
            server_name = row[0]
            dc = _extract_dc(server_name, dc_set_upper)
            if not dc:
                continue
            try:
                tpu = float(row[1] or 0)
                apu = float(row[2] or 0)
                used = float(row[3] or 0)
                asg = float(row[4] or 0)
            except (TypeError, ValueError):
                continue
            ts = row[5]
            cpu_hosts.setdefault(dc, {}).setdefault(server_name, []).append(
                (tpu, apu, used, asg, ts)
            )
        ibm_cpu: dict[str, tuple] = {}
        for dc, hosts in cpu_hosts.items():
            st = sa = 0.0
            used_vals: list[float] = []
            asg_vals: list[float] = []
            for _svr, samples in hosts.items():
                if not samples:
                    continue
                tpu, apu, u, a, _ts = max(samples, key=lambda v: v[4])
                st += tpu
                sa += apu
                used_vals.append(u)
                asg_vals.append(a)
            nu = len(used_vals) or 1
            na = len(asg_vals) or 1
            ibm_cpu[dc] = (
                st,
                sa,
                sum(used_vals) / nu,
                sum(asg_vals) / na,
            )

        return {"hosts": ibm_h, "vios": ibm_vios, "lpar": ibm_lpar, "mem": ibm_mem, "cpu": ibm_cpu}
