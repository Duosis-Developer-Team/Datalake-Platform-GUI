"""
database_service.py — Async Data Access Layer (DAL)

Legacy (psycopg2 / ThreadedConnectionPool) → asyncpg migration:
  - ThreadedConnectionPool      → asyncpg.Pool (managed by lifespan in main.py)
  - @contextmanager + getconn   → async with pool.acquire() as conn
  - cursor.execute / fetchone   → await conn.fetchval / fetchrow / fetch
  - %s placeholders             → $1, $2, ... placeholders (in query files)
  - explicit ROLLBACK           → not needed; asyncpg auto-handles on exception

Cache sorumluluğu: Bu servis tamamen stateless'tır.
  Caching → query-service (Phase 2 / Redis) sorumluluğu.

Return types: dict yerine shared.schemas Pydantic modelleri kullanılır.
"""

import logging
from typing import Any

import asyncpg

from shared.schemas.infrastructure import DCMeta, PowerInfo
from shared.schemas.metrics import DCStats, EnergyMetrics, IntelMetrics
from shared.schemas.responses import DCDetail, DCSummary, GlobalOverview
from src.queries import energy as eq
from src.queries import ibm as iq
from src.queries import loki as lq
from src.queries import nutanix as nq
from src.queries import vmware as vq

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_FALLBACK_DC_LIST: list[str] = [
    "AZ11", "DC11", "DC12", "DC13", "DC14", "DC15", "DC16", "DC17", "ICT11",
]

DC_LOCATIONS: dict[str, str] = {
    "AZ11":  "Azerbaycan",
    "DC11":  "Istanbul",
    "DC13":  "Istanbul",
    "ICT11": "Almanya",
}


def _empty_dc(dc_code: str) -> DCDetail:
    """Veritabanına ulaşılamadığında sıfırlı DCDetail modeli döndürür."""
    return DCDetail(
        meta=DCMeta(
            name=dc_code,
            location=DC_LOCATIONS.get(dc_code, "Unknown Data Center"),
        ),
        intel=IntelMetrics(),
        power=PowerInfo(),
        energy=EnergyMetrics(),
    )


# ── Async low-level query helpers ─────────────────────────────────────────────

async def _fetchval(conn: asyncpg.Connection, sql: str, *params: Any) -> float | int:
    """Scalar sorgu: ilk satırın ilk sütununu döndürür; hata veya NULL → 0."""
    try:
        result = await conn.fetchval(sql, *params)
        return result if result is not None else 0
    except Exception as exc:
        logger.warning("fetchval error [%s]: %r", type(exc).__name__, exc)
        return 0


async def _fetchrow(conn: asyncpg.Connection, sql: str, *params: Any) -> asyncpg.Record | None:
    """Tek satır sorgu: asyncpg.Record veya None döndürür."""
    try:
        return await conn.fetchrow(sql, *params)
    except Exception as exc:
        logger.warning("fetchrow error [%s]: %r", type(exc).__name__, exc)
        return None


async def _fetch(conn: asyncpg.Connection, sql: str, *params: Any) -> list[asyncpg.Record]:
    """Çok satırlı sorgu: asyncpg.Record listesi döndürür; hata → []."""
    try:
        return await conn.fetch(sql, *params) or []
    except Exception as exc:
        logger.warning("fetch error [%s]: %r", type(exc).__name__, exc)
        return []


# ── DatabaseService ───────────────────────────────────────────────────────────

class DatabaseService:
    """
    Asenkron veritabanı erişim katmanı.

    Tüm public metodlar async'tir ve asyncpg pool'dan connection alır.
    Bu sınıf tamamen stateless olup FastAPI dependency olarak her request
    için yeni bir instance oluşturulabilir (pool paylaşılır).
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # ── DC list ───────────────────────────────────────────────────────────────

    async def _load_dc_list(self, conn: asyncpg.Connection) -> list[str]:
        """
        loki_locations tablosundan aktif DC isimlerini çeker.
        Başarısız olursa hardcoded fallback listesini döndürür.
        """
        rows = await _fetch(conn, lq.DC_LIST)
        dc_names = [row[0] for row in rows if row[0]]

        if not dc_names:
            rows = await _fetch(conn, lq.DC_LIST_NO_STATUS)
            dc_names = [row[0] for row in rows if row[0]]

        if dc_names:
            logger.info("Loaded %d datacenters from loki_locations: %s", len(dc_names), dc_names)
            return dc_names

        logger.warning("loki_locations returned empty list — using fallback.")
        return _FALLBACK_DC_LIST.copy()

    # ── Unit normalisation & aggregation ─────────────────────────────────────

    @staticmethod
    def _aggregate_dc(
        dc_code: str,
        nutanix_host_count: int | float,
        nutanix_mem:     tuple | asyncpg.Record | None,
        nutanix_storage: tuple | asyncpg.Record | None,
        nutanix_cpu:     tuple | asyncpg.Record | None,
        vmware_counts:   tuple | asyncpg.Record | None,
        vmware_mem:      tuple | asyncpg.Record | None,
        vmware_storage:  tuple | asyncpg.Record | None,
        vmware_cpu:      tuple | asyncpg.Record | None,
        power_hosts:     int | float,
        racks_w:         float,
        ibm_w:           float,
        vcenter_w:       float,
    ) -> DCDetail:
        """
        Ham sayısal verileri birim normalize eder ve DCDetail Pydantic modeli döndürür.

        Nutanix raw → hedef birim:
          Memory  : TB  × 1024  → GB
          Storage : TB           → TB  (değişmez)
          CPU     : GHz          → GHz (değişmez)

        VMware raw → hedef birim:
          Memory  : Bytes ÷ 1024³ → GB
          Storage : KB (GB×1MB) ÷ 1024⁴ → TB
          CPU     : Hz  ÷ 1e9   → GHz

        Energy  : Watts ÷ 1000  → kW
        """
        nutanix_mem     = nutanix_mem     or (0, 0)
        nutanix_storage = nutanix_storage or (0, 0)
        nutanix_cpu     = nutanix_cpu     or (0, 0)
        vmware_counts   = vmware_counts   or (0, 0, 0)
        vmware_mem      = vmware_mem      or (0, 0)
        vmware_storage  = vmware_storage  or (0, 0)
        vmware_cpu      = vmware_cpu      or (0, 0)

        # Memory → GB
        n_mem_cap_gb  = (nutanix_mem[0] or 0) * 1024
        n_mem_used_gb = (nutanix_mem[1] or 0) * 1024
        v_mem_cap_gb  = (vmware_mem[0]  or 0) / (1024 ** 3)
        v_mem_used_gb = (vmware_mem[1]  or 0) / (1024 ** 3)

        # Storage → TB
        n_stor_cap_tb  = (nutanix_storage[0] or 0)
        n_stor_used_tb = (nutanix_storage[1] or 0)
        v_stor_cap_tb  = (vmware_storage[0]  or 0) / (1024 ** 4)
        v_stor_used_tb = (vmware_storage[1]  or 0) / (1024 ** 4)

        # CPU → GHz
        n_cpu_cap_ghz  = (nutanix_cpu[0] or 0)
        n_cpu_used_ghz = (nutanix_cpu[1] or 0)
        v_cpu_cap_ghz  = (vmware_cpu[0]  or 0) / 1_000_000_000
        v_cpu_used_ghz = (vmware_cpu[1]  or 0) / 1_000_000_000

        # Energy → kW
        total_energy_kw = (
            float(racks_w or 0) + float(ibm_w or 0) + float(vcenter_w or 0)
        ) / 1000.0

        return DCDetail(
            meta=DCMeta(
                name=dc_code,
                location=DC_LOCATIONS.get(dc_code, "Unknown Data Center"),
            ),
            intel=IntelMetrics(
                clusters=     int(vmware_counts[0] or 0),
                hosts=        int((nutanix_host_count or 0) + (vmware_counts[1] or 0)),
                vms=          int(vmware_counts[2] or 0),
                cpu_cap=      round(n_cpu_cap_ghz  + v_cpu_cap_ghz,  2),
                cpu_used=     round(n_cpu_used_ghz + v_cpu_used_ghz, 2),
                ram_cap=      round(n_mem_cap_gb   + v_mem_cap_gb,   2),
                ram_used=     round(n_mem_used_gb  + v_mem_used_gb,  2),
                storage_cap=  round(n_stor_cap_tb  + v_stor_cap_tb,  2),
                storage_used= round(n_stor_used_tb + v_stor_used_tb, 2),
            ),
            power=PowerInfo(hosts=int(power_hosts or 0)),
            energy=EnergyMetrics(total_kw=round(total_energy_kw, 2)),
        )

    # ── Single DC ─────────────────────────────────────────────────────────────

    async def get_dc_details(self, dc_code: str) -> DCDetail:
        """Tek bir DC için tam DCDetail modeli döndürür."""
        try:
            async with self._pool.acquire() as conn:
                dc_wc = f"%{dc_code}%"   # Wildcard pattern for ILIKE/LIKE
                return self._aggregate_dc(
                    dc_code,
                    nutanix_host_count=await _fetchval(conn, nq.HOST_COUNT, dc_wc),
                    nutanix_mem=       await _fetchrow(conn, nq.MEMORY,     dc_wc),
                    nutanix_storage=   await _fetchrow(conn, nq.STORAGE,    dc_wc),
                    nutanix_cpu=       await _fetchrow(conn, nq.CPU,        dc_wc),
                    vmware_counts=     await _fetchrow(conn, vq.COUNTS,     dc_wc),
                    vmware_mem=        await _fetchrow(conn, vq.MEMORY,     dc_wc),
                    vmware_storage=    await _fetchrow(conn, vq.STORAGE,    dc_wc),
                    vmware_cpu=        await _fetchrow(conn, vq.CPU,        dc_wc),
                    power_hosts=       await _fetchval(conn, iq.HOST_COUNT, dc_wc),
                    racks_w=           float(await _fetchval(conn, eq.RACKS,   dc_code) or 0),
                    ibm_w=             float(await _fetchval(conn, eq.IBM,     dc_wc)   or 0),
                    vcenter_w=         float(await _fetchval(conn, eq.VCENTER, dc_wc)   or 0),
                )
        except Exception as exc:
            logger.error("DB unavailable for get_dc_details(%s): %s", dc_code, exc)
            return _empty_dc(dc_code)

    # ── Batch fetch (internal) ────────────────────────────────────────────────

    async def _fetch_all_batch(
        self, conn: asyncpg.Connection, dc_list: list[str]
    ) -> dict[str, DCDetail]:
        """
        Tüm DC'ler için toplu sorgular çalıştırır (~10 DB round-trip).
        asyncpg, Python list'i PostgreSQL text[] array'ine otomatik çevirir.
        """
        wildcard_patterns = [f"%{dc}%" for dc in dc_list]

        # Nutanix — datacenter_name exact match
        n_host_rows  = await _fetch(conn, nq.BATCH_HOST_COUNT, dc_list)
        n_mem_rows   = await _fetch(conn, nq.BATCH_MEMORY,     dc_list)
        n_stor_rows  = await _fetch(conn, nq.BATCH_STORAGE,    dc_list)
        n_cpu_rows   = await _fetch(conn, nq.BATCH_CPU,        dc_list)

        # VMware — datacenter ILIKE ANY(wildcard_patterns)
        v_cnt_rows   = await _fetch(conn, vq.BATCH_COUNTS,  wildcard_patterns)
        v_mem_rows   = await _fetch(conn, vq.BATCH_MEMORY,  wildcard_patterns)
        v_stor_rows  = await _fetch(conn, vq.BATCH_STORAGE, wildcard_patterns)
        v_cpu_rows   = await _fetch(conn, vq.BATCH_CPU,     wildcard_patterns)

        # IBM — LIKE ANY(wildcard_patterns)
        ibm_rows     = await _fetch(conn, iq.BATCH_HOST_COUNT, wildcard_patterns)

        # Energy
        rack_rows    = await _fetch(conn, eq.BATCH_RACKS,   dc_list)
        ibm_e_rows   = await _fetch(conn, eq.BATCH_IBM,     wildcard_patterns)
        vcenter_rows = await _fetch(conn, eq.BATCH_VCENTER, wildcard_patterns)

        # ── Map batch rows back to DC codes ──────────────────────────────────

        def _match_dc(name: str) -> str | None:
            """DC kodunu bir string içinde arar (case-insensitive)."""
            if not name:
                return None
            upper = name.upper()
            for dc in dc_list:
                if dc.upper() in upper:
                    return dc
            return None

        def _index_by_dc(rows: list, col_idx: int = 0) -> dict[str, asyncpg.Record]:
            """DC başına ilk satırı eşler: {dc_code: row}."""
            out: dict[str, asyncpg.Record] = {}
            for row in rows:
                dc = _match_dc(str(row[col_idx]))
                if dc and dc not in out:
                    out[dc] = row
            return out

        def _index_exact(rows: list, col_idx: int = 0) -> dict[str, asyncpg.Record]:
            """Tam anahtar eşleşmesi: {row[col_idx]: row}. Nutanix batch için."""
            return {row[col_idx]: row for row in rows if row[col_idx]}

        def _sum_by_dc(rows: list, value_col: int, col_idx: int = 0) -> dict[str, float]:
            """Sayısal sütunu DC başına toplar (enerji, IBM host sayısı)."""
            out: dict[str, float] = {}
            for row in rows:
                dc = _match_dc(str(row[col_idx]))
                if dc:
                    out[dc] = out.get(dc, 0.0) + float(row[value_col] or 0)
            return out

        # Nutanix → exact datacenter_name key
        n_host = _index_exact(n_host_rows)
        n_mem  = _index_exact(n_mem_rows)
        n_stor = _index_exact(n_stor_rows)
        n_cpu  = _index_exact(n_cpu_rows)

        # VMware / IBM → wildcard-matched name
        v_cnt  = _index_by_dc(v_cnt_rows)
        v_mem  = _index_by_dc(v_mem_rows)
        v_stor = _index_by_dc(v_stor_rows)
        v_cpu  = _index_by_dc(v_cpu_rows)
        ibm_h  = _sum_by_dc(ibm_rows, value_col=1)

        # Energy — racks: exact location_name; IBM/vCenter: wildcard
        rack_e = {row[0]: float(row[1] or 0) for row in rack_rows if row[0]}
        ibm_e  = _sum_by_dc(ibm_e_rows,   value_col=1)
        vctr_e = _sum_by_dc(vcenter_rows,  value_col=1)

        # ── Assemble DCDetail models ──────────────────────────────────────────
        results: dict[str, DCDetail] = {}
        for dc in dc_list:
            nh   = n_host.get(dc)
            nm   = n_mem.get(dc)
            ns   = n_stor.get(dc)
            nc   = n_cpu.get(dc)
            vc   = v_cnt.get(dc)
            vm   = v_mem.get(dc)
            vs   = v_stor.get(dc)
            vcpu = v_cpu.get(dc)

            results[dc] = self._aggregate_dc(
                dc_code=dc,
                nutanix_host_count=nh[1]  if nh   else 0,
                nutanix_mem=       (nm[1], nm[2])   if nm   else None,
                nutanix_storage=   (ns[1], ns[2])   if ns   else None,
                nutanix_cpu=       (nc[1], nc[2])   if nc   else None,
                vmware_counts=     (vc[1], vc[2], vc[3]) if vc else None,
                vmware_mem=        (vm[1], vm[2])   if vm   else None,
                vmware_storage=    (vs[1], vs[2])   if vs   else None,
                vmware_cpu=        (vcpu[1], vcpu[2]) if vcpu else None,
                power_hosts=ibm_h.get(dc, 0),
                racks_w=rack_e.get(dc, 0.0),
                ibm_w=ibm_e.get(dc, 0.0),
                vcenter_w=vctr_e.get(dc, 0.0),
            )

        return results

    # ── Public API ────────────────────────────────────────────────────────────

    async def get_all_datacenters_summary(self) -> list[DCSummary]:
        """
        Tüm aktif DC'ler için DCSummary listesi döndürür.
        DC listesi her çağrıda loki_locations'dan dinamik olarak alınır.
        (Caching sorumluluğu → query-service / Phase 2)
        """
        try:
            async with self._pool.acquire() as conn:
                dc_list     = await self._load_dc_list(conn)
                all_dc_data = await self._fetch_all_batch(conn, dc_list)
        except Exception as exc:
            logger.error("DB unavailable for get_all_datacenters_summary: %s", exc)
            dc_list     = _FALLBACK_DC_LIST
            all_dc_data = {dc: _empty_dc(dc) for dc in dc_list}

        summary: list[DCSummary] = []
        for dc in dc_list:
            d     = all_dc_data.get(dc, _empty_dc(dc))
            intel = d.intel
            power = d.power

            cpu_cap  = intel.cpu_cap     or 0
            cpu_used = intel.cpu_used    or 0
            ram_cap  = intel.ram_cap     or 0
            ram_used = intel.ram_used    or 0
            s_cap    = intel.storage_cap  or 0
            s_used   = intel.storage_used or 0

            summary.append(DCSummary(
                id=            dc,
                name=          dc,
                location=      d.meta.location,
                status=        "Healthy",
                cluster_count= intel.clusters,
                host_count=    intel.hosts + power.hosts,
                vm_count=      intel.vms   + power.vms,
                stats=DCStats(
                    total_cpu=          f"{cpu_used:,} / {cpu_cap:,} GHz",
                    used_cpu_pct=       round((cpu_used / cpu_cap * 100) if cpu_cap else 0, 1),
                    total_ram=          f"{ram_used:,} / {ram_cap:,} GB",
                    used_ram_pct=       round((ram_used / ram_cap * 100) if ram_cap else 0, 1),
                    total_storage=      f"{s_used:,} / {s_cap:,} TB",
                    used_storage_pct=   round((s_used / s_cap * 100) if s_cap else 0, 1),
                    last_updated=       "Live",
                    total_energy_kw=    d.energy.total_kw,
                ),
            ))

        logger.info("Built summary for %d datacenters.", len(summary))
        return summary

    async def get_global_overview(self) -> GlobalOverview:
        """Global toplam metrikleri GlobalOverview modeli olarak döndürür."""
        summaries = await self.get_all_datacenters_summary()
        return GlobalOverview(
            total_hosts=     sum(s.host_count           for s in summaries),
            total_vms=       sum(s.vm_count             for s in summaries),
            total_energy_kw= round(sum(
                s.stats.total_energy_kw for s in summaries
            ), 2),
            dc_count=len(summaries),
        )
