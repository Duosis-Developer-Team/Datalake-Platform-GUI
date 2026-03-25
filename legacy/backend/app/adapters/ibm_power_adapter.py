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
            ("ibm_storage_raw", """
WITH latest AS (
    SELECT storage_ip, MAX("timestamp") AS max_ts
    FROM public.raw_ibm_storage_system
    GROUP BY storage_ip
)
SELECT s.name, s.location, s.capacity, s.allocated_space
FROM public.raw_ibm_storage_system s
JOIN latest l ON s.storage_ip = l.storage_ip AND s."timestamp" = l.max_ts
            """, ()),
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

        ibm_mem_acc: dict[str, list] = {}
        for row in raw_data.get("ibm_mem_raw", []):
            if not row or len(row) < 3:
                continue
            dc = _extract_dc(row[0], dc_set_upper)
            if dc:
                ibm_mem_acc.setdefault(dc, []).append((float(row[1] or 0), float(row[2] or 0)))
        ibm_mem: dict[str, tuple] = {}
        for dc, vals in ibm_mem_acc.items():
            n_vals = len(vals)
            ibm_mem[dc] = (
                sum(v[0] for v in vals) / n_vals,
                sum(v[1] for v in vals) / n_vals,
            )

        ibm_cpu_acc: dict[str, list] = {}
        for row in raw_data.get("ibm_cpu_raw", []):
            if not row or len(row) < 4:
                continue
            dc = _extract_dc(row[0], dc_set_upper)
            if dc:
                ibm_cpu_acc.setdefault(dc, []).append(
                    (float(row[1] or 0), float(row[2] or 0), float(row[3] or 0))
                )
        ibm_cpu: dict[str, tuple] = {}
        for dc, vals in ibm_cpu_acc.items():
            n_vals = len(vals)
            ibm_cpu[dc] = (
                sum(v[0] for v in vals) / n_vals,
                sum(v[1] for v in vals) / n_vals,
                sum(v[2] for v in vals) / n_vals,
            )

        def _canonical_dc(raw_key) -> str | None:
            if raw_key is None or not str(raw_key).strip():
                return None
            s = str(raw_key).strip()
            # Simple match against known DC codes since we don't have DC_LOCATIONS here immediately,
            # but we can check if it matches exactly. Otherwise we rely on the main loc map if needed.
            # However, since we don't have DC_LOCATIONS imported, we will just pass it out as-is if it's in the set.
            if s.upper() in dc_set_upper:
                return s.upper()
            return None
            
        ibm_storage_tb: dict[str, tuple[float, float]] = {}
        for row in raw_data.get("ibm_storage_raw", []):
            if not row or len(row) < 4:
                continue
            name_val, loc_val, cap_str, used_str = row
            dc = _extract_dc(f"{name_val or ''} {loc_val or ''}", dc_set_upper)
            if not dc:
                dc = _canonical_dc(name_val)
            if not dc:
                dc = _canonical_dc(loc_val)

            if dc:
                def parse_capacity(val: str) -> float:
                    if not val: return 0.0
                    val = str(val).upper().strip()
                    try:
                        num = float(''.join(c for c in val if c.isdigit() or c == '.'))
                        if 'GB' in val: return num / 1024.0
                        if 'MB' in val: return num / (1024.0**2)
                        if 'PB' in val: return num * 1024.0
                        return num
                    except Exception: return 0.0
                cap_tb = parse_capacity(cap_str)
                used_tb = parse_capacity(used_str)
                curr_cap, curr_used = ibm_storage_tb.get(dc, (0.0, 0.0))
                ibm_storage_tb[dc] = (curr_cap + cap_tb, curr_used + used_tb)

        return {"hosts": ibm_h, "vios": ibm_vios, "lpar": ibm_lpar, "mem": ibm_mem, "cpu": ibm_cpu, "storage": ibm_storage_tb}
