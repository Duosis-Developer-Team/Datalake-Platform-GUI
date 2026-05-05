"""Deterministic CRM product -> panel_key mapping.

Per ADR-0011 / the C-level dashboard plan, every CRM product (productid) is
assigned to exactly one panel_key. Mapping rules are based on **exact display
name patterns** (substring + prefix tests) and the product UoM, NOT regex
guessing. The full table below was reviewed against the 222-row product CSV
on 2026-05-04 and covers every active SKU in the Bulutistan Managed Cloud
catalog.

If a product's name does not match any rule the mapper returns the literal
string ``"other"`` (the catch-all panel). Operators can still attach an
explicit override in the Settings UI.

Public API:
    classify(name: str, uom: str | None = None) -> str
    classify_batch(rows: Iterable[dict]) -> list[tuple[productid, page_key]]
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class _Rule:
    """A single deterministic match rule.

    Order matters: more specific rules MUST appear before broader ones. The
    classifier walks the list and returns the FIRST matching panel_key.
    """

    panel_key: str
    contains_all: tuple[str, ...] = ()       # all substrings must be present
    starts_with: tuple[str, ...] = ()        # name must start with one of these
    equals: tuple[str, ...] = ()             # exact name match
    uom_in: tuple[str, ...] = ()             # extra UoM constraint (case-insensitive)


# Rules are evaluated top-to-bottom; first match wins.
_RULES: tuple[_Rule, ...] = (
    # ----- Hyperconverged Mimari (Nutanix) -----
    _Rule("virt_hyperconverged_cpu",     contains_all=("Hyperconverged Mimari", "Intel CPU")),
    _Rule("virt_hyperconverged_ram",     contains_all=("Hyperconverged Mimari", "Intel RAM")),
    _Rule("virt_hyperconverged_storage", contains_all=("Hyperconverged Mimari", "Intel Disk")),

    # ----- Klasik Mimari (VMware) -----
    _Rule("virt_classic_cpu",            contains_all=("Klasik Mimari", "Intel CPU")),
    _Rule("virt_classic_ram",            contains_all=("Klasik Mimari", "Intel RAM")),
    _Rule("virt_classic_storage",        contains_all=("Klasik Mimari", "Intel Disk")),

    # ----- IBM Power Mimari (standard; SAP Power HANA rules below are more specific)
    _Rule("virt_power_cpu",     contains_all=("IBM Power", "CPU")),
    _Rule("virt_power_ram",     contains_all=("IBM Power", "RAM")),
    _Rule("virt_power_storage", contains_all=("NVMi",)),

    # ----- SAP HANA (Intel + Power) -----
    _Rule("virt_intel_hana_cpu",         contains_all=("SAP Intel HANA", "CPU")),
    _Rule("virt_intel_hana_ram",         contains_all=("SAP Intel HANA", "RAM")),
    _Rule("virt_intel_hana_storage",     contains_all=("SAP Intel HANA", "Storage")),
    _Rule("virt_power_hana_cpu",         contains_all=("SAP Power HANA", "CPU")),
    _Rule("virt_power_hana_ram",         contains_all=("SAP Power HANA", "RAM")),
    _Rule("virt_power_hana_storage",     contains_all=("SAP Power HANA", "Storage")),

    # ----- Backup: Veeam Replication compute -----
    _Rule("backup_veeam_replication_cpu",     contains_all=("Veeam Replication", "vCpu")),
    _Rule("backup_veeam_replication_ram",     contains_all=("Veeam Replication", "RAM")),
    _Rule("backup_veeam_replication_storage", contains_all=("Veeam Replication", "Disk")),
    _Rule("backup_veeam_image",               contains_all=("Veeam Cloud Connect Backup",)),

    # ----- Backup: Zerto Replication compute -----
    _Rule("backup_zerto_replication_cpu",     contains_all=("Zerto Replication", "vCpu")),
    _Rule("backup_zerto_replication_ram",     contains_all=("Zerto Replication", "RAM")),
    _Rule("backup_zerto_replication_storage", contains_all=("Zerto Replication", "Disk")),

    # ----- Backup: NetBackup, image, offsite, remote -----
    _Rule("backup_netbackup_storage",         contains_all=("Veritas",)),  # NetBackup or Netbackup name
    _Rule("backup_netbackup_storage",         contains_all=("NetBackup",)),
    _Rule("backup_image_hyperconverged",      contains_all=("Hyperconverged", "İmaj Yedekleme")),
    _Rule("backup_offsite_s3",                contains_all=("Offsite Backup", "S3")),
    _Rule("backup_offsite_veeam",             contains_all=("Offsite Backup", "Veeam")),
    _Rule("backup_remote_nutanix",            contains_all=("Remote Backup", "Nutanix")),

    # ----- Object storage -----
    _Rule("storage_s3_ankara",                contains_all=("IBM ICOS S3 Ankara",)),
    _Rule("storage_s3_istanbul",              contains_all=("IBM ICOS S3", "stanbul")),  # İ/i variant safe

    # ----- Firewalls / Load Balancer -----
    _Rule("firewall_fortigate",               contains_all=("FortiGate",)),
    _Rule("firewall_paloalto",                contains_all=("Palo Alto",)),
    _Rule("firewall_sophos",                  contains_all=("Sophos XG",)),
    _Rule("firewall_citrix_dedicated",        contains_all=("Citrix", "Dedike WAF & LB")),
    _Rule("loadbalancer_citrix_shared",       contains_all=("Citrix", "Paylaşımlı")),

    # ----- Microsoft licenses -----
    _Rule("license_microsoft_csp",            starts_with=("CSP - Microsoft", "CSP-Microsoft", "CSP - Office", "CSP - Exchange")),
    _Rule("license_microsoft_csp",            contains_all=("CSP -", "Microsoft")),
    _Rule("license_microsoft_csp",            contains_all=("CSP -", "Office")),
    _Rule("license_microsoft_csp",            contains_all=("CSP -", "Exchange")),
    _Rule("license_microsoft_spla",           starts_with=("SPLA -", "SPLA-")),
    _Rule("license_microsoft_spla",           equals=("MS Windows Lisans",)),

    # ----- Other licenses -----
    _Rule("license_redhat",                   starts_with=("CCSP-RH", "CCSP-MCT")),
    _Rule("license_suse",                     equals=("SUSE Lisans Bedeli",)),
    _Rule("license_ubuntu",                   starts_with=("Ubuntu Pro",)),
    _Rule("license_veeam",                    contains_all=("Veeam Cloud Connect Replication",)),
    _Rule("license_zerto",                    contains_all=("Zerto Enterprise Cloud Edition",)),
    _Rule("license_plesk",                    starts_with=("Plesk ",)),
    _Rule("license_cpanel",                   contains_all=("cPanel",)),

    # ----- Network -----
    _Rule("network_public_ipv4",              starts_with=("Public IPv4",)),
    _Rule("network_public_ipv6",              starts_with=("Public IPv6",)),
    _Rule("network_dc_access",                contains_all=("Veri Merkezi Erişim",)),
    _Rule("network_dc_port",                  contains_all=("Cross Connection Port",)),
    _Rule("network_dc_port",                  contains_all=("Switch Port",)),
    _Rule("network_vpn",                      contains_all=("Sophos SSL VPN",)),
    _Rule("network_dns",                      contains_all=("Cloud DNS",)),

    # ----- Datacenter hosting -----
    _Rule("dc_hosting_kabinet",               contains_all=("Veri Merkezi Barındırma", "Kabinet")),
    _Rule("dc_hosting_u",                     contains_all=("Veri Merkezi Barındırma", "(U)")),
    _Rule("dc_energy",                        contains_all=("Veri Merkezi Enerji",)),

    # ----- Managed services: database -----
    _Rule("mgmt_database_oracle",             starts_with=("Oracle Veritabanı",)),
    _Rule("mgmt_database_mssql",              starts_with=("MSSQL Veritabanı",)),
    _Rule("mgmt_database_postgres",           starts_with=("PostgreSQL Veritabanı",)),
    _Rule("mgmt_database_db2",                starts_with=("DB2 Veritabanı",)),
    _Rule("mgmt_database_azure_sql",          starts_with=("Azure SQL Veritabanı",)),

    # ----- Managed services: OS -----
    _Rule("mgmt_os_sap",                      contains_all=("SUSE for SAP HANA",)),
    _Rule("mgmt_os_linux",                    starts_with=("Linux İşletim Sistemi",)),
    _Rule("mgmt_os_linux",                    contains_all=("Standart Intel Linux",)),
    _Rule("mgmt_os_windows",                  starts_with=("Windows İşletim Sistemi",)),
    _Rule("mgmt_os_windows",                  contains_all=("Standart Windows İşletim",)),
    _Rule("mgmt_os_unix",                     starts_with=("Unix İşletim Sistemi",)),

    # ----- Managed services: monitoring / backup mgmt / security -----
    _Rule("mgmt_monitoring_premium",          equals=("Premium Monitoring Hizmeti",)),
    _Rule("mgmt_monitoring_standard",         equals=("Standart Monitoring Hizmeti",)),
    _Rule("mgmt_backup",                      starts_with=("Yedekleme Yönetimi",)),
    _Rule("mgmt_security_soc",                starts_with=("SOC Yönetim",)),
    _Rule("mgmt_security_siem",               starts_with=("SIEM Yönetim",)),
    _Rule("mgmt_security_firewall",           starts_with=("Güvenlik Duvarı Hizmet",)),

    # ----- Managed replication / AD / support -----
    _Rule("mgmt_replication_veeam",           equals=("Veeam Replikasyon Yönetim Hizmeti",)),
    _Rule("mgmt_replication_zerto",           equals=("Zerto Replikasyon Yönetim Hizmeti",)),
    _Rule("mgmt_active_directory",            equals=("Active Directory Yönetim Hizmeti",)),
    _Rule("mgmt_support_7x24",                contains_all=("Bulutistan Destek",)),

    # ----- Public Cloud (Azure Accelerated) -----
    _Rule("public_cloud_azure",               starts_with=("Public Cloud - Accelerated",)),
)


_KNOWN_PANELS: frozenset[str] = frozenset(r.panel_key for r in _RULES) | frozenset({"other"})


def known_panel_keys() -> frozenset[str]:
    """All panel_keys reachable via classify(), plus 'other'."""
    return _KNOWN_PANELS


def _normalise(s: str) -> str:
    """Collapse internal whitespace so CRM data quirks (e.g. ``Linux  İşletim``
    with double space) still match the rule table."""
    return " ".join((s or "").split())


def classify(name: str | None, uom: str | None = None) -> str:
    """Return the panel_key for a CRM product display name.

    Falls back to ``"other"`` when no rule matches. Matching is case-sensitive
    on the substrings declared in the rule table — display names from the
    Dynamics CRM catalog use stable Turkish/English casing so this is safe.
    Internal whitespace is normalised before comparison so source data with
    accidental double-spaces still matches deterministically.
    """
    n = _normalise(name or "")
    u = (uom or "").strip().lower()
    if not n:
        return "other"
    for rule in _RULES:
        if rule.uom_in and u not in {x.lower() for x in rule.uom_in}:
            continue
        if rule.equals and n in rule.equals:
            return rule.panel_key
        if rule.starts_with and any(n.startswith(p) for p in rule.starts_with):
            return rule.panel_key
        if rule.contains_all and all(p in n for p in rule.contains_all):
            return rule.panel_key
    return "other"


def classify_batch(rows: Iterable[dict]) -> list[tuple[str, str]]:
    """Classify CSV-style dict rows. Each row needs ``productid`` and ``name``.

    Returns list of (productid, panel_key) preserving input order. Rows
    without a productid are skipped.
    """
    out: list[tuple[str, str]] = []
    for row in rows:
        pid = (row.get("productid") or "").strip().strip('"')
        if not pid:
            continue
        name = row.get("name") or ""
        uom = row.get("defaultuomid_name") or row.get("uom") or ""
        out.append((pid, classify(name, uom)))
    return out
