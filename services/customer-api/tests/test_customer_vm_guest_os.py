"""Customer VM lists must carry the guest OS, with a NetBox fallback.

Measured live 2026-07-27 for the hyperconverged bucket:

    Nutanix VMs (last 2 days) ......... 11,792
      also present in vm_metrics ....... 5,993   -> vm_metrics.guest_os (100% filled)
      Nutanix-only .................... 5,799   -> no guest_os in nutanix_vm_metrics
        rescued by NetBox ............. 4,901   (85%)
        still without any OS signal ....   898

So vm_metrics alone would leave ~5.8k customer VMs blank; the NetBox
custom_fields_guest_os fallback is what makes the column usable.
"""

import re

from app.db.queries import customer as cq


def _count_psycopg2_placeholders(sql: str) -> int:
    """Count %s placeholders (ignore %% escapes)."""
    return len(re.findall(r"(?<!%)%s", sql))


def test_classic_vm_list_selects_guest_os_from_vm_metrics():
    sql = cq.CUSTOMER_CLASSIC_VM_LIST
    assert '"Guest OS"' in sql
    assert "guest_os" in sql
    # Classic is 100% covered by vm_metrics — no NetBox join needed, so the
    # placeholder count must stay at 6.
    assert _count_psycopg2_placeholders(sql) == 6


def test_hyperconv_vm_list_falls_back_to_netbox_for_nutanix_only_vms():
    sql = cq.CUSTOMER_HYPERCONV_VM_LIST
    assert '"Guest OS"' in sql
    assert "discovery_netbox_virtualization_vm" in sql
    assert "custom_fields_guest_os" in sql
    # vm_metrics wins over NetBox: NetBox is a daily snapshot, vm_metrics is live.
    assert re.search(r"COALESCE\(\s*v\.guest_os\s*,\s*nb\.guest_os\s*\)", sql)


def test_pure_nutanix_vm_list_falls_back_to_netbox():
    sql = cq.CUSTOMER_PURE_NUTANIX_VM_LIST
    assert '"Guest OS"' in sql
    assert "discovery_netbox_virtualization_vm" in sql


def test_netbox_fallback_is_deduped_and_customer_scoped():
    """The raw NetBox table holds ~2 rows per VM. An undeduped join would fan the
    VM list out; an unscoped one would scan all 42k rows on every request."""
    for sql in (cq.CUSTOMER_HYPERCONV_VM_LIST, cq.CUSTOMER_PURE_NUTANIX_VM_LIST):
        block = sql[sql.index("discovery_netbox_virtualization_vm") - 400:]
        assert "DISTINCT ON" in block
        assert "name ILIKE %s" in block


def test_no_stray_percent_signs_in_touched_queries():
    for sql in (
        cq.CUSTOMER_CLASSIC_VM_LIST,
        cq.CUSTOMER_HYPERCONV_VM_LIST,
        cq.CUSTOMER_PURE_NUTANIX_VM_LIST,
    ):
        assert re.search(r"(?<!%)%(?!s)", sql.replace("%%", "")) is None
