"""Pure helpers for CRM source mapping UI (no Dash imports)."""
from __future__ import annotations

UI_COLUMNS: list[tuple[str, str, tuple[str, ...]]] = [
    ("virtualization", "Virtualization", ("virtualization", "netbox_vm_customer")),
    ("backup", "Backup & Replication", ("backup_veeam", "backup_zerto", "backup_netbackup")),
    ("physical_device", "Physical Device", ("physical_device",)),
    ("storage", "Storage", ("storage_ibm",)),
    ("s3", "S3", ("s3_icos",)),
    ("itsm", "ITSM", ("itsm_servicecore",)),
]

MATCH_METHOD_OPTIONS = [
    {"label": "Contains", "value": "contains"},
    {"label": "Prefix", "value": "prefix"},
    {"label": "Suffix", "value": "suffix"},
    {"label": "Exact", "value": "exact"},
    {"label": "ID exact", "value": "id_exact"},
]


def mappings_for_column(source_mappings: list[dict], data_sources: tuple[str, ...]) -> list[dict]:
    allowed = set(data_sources)
    return [
        m
        for m in (source_mappings or [])
        if str(m.get("data_source") or "") in allowed
    ]


def collect_mappings_for_account(
    account_id: str,
    method_states: list,
    value_states: list,
    enabled_states: list,
    source_states: list,
) -> list[dict]:
    column_default_source = {key: sources[0] for key, _, sources in UI_COLUMNS}

    def _state_index(state: dict) -> tuple[str, str, int] | None:
        state_id = state.get("id") or {}
        if str(state_id.get("account")) != account_id:
            return None
        return (
            str(state_id.get("account")),
            str(state_id.get("column")),
            int(state_id.get("index", 0)),
        )

    method_by_key = {_state_index(s): s.get("value") for s in method_states if _state_index(s)}
    value_by_key = {_state_index(s): s.get("value") for s in value_states if _state_index(s)}
    enabled_by_key = {_state_index(s): s.get("value") for s in enabled_states if _state_index(s)}
    source_by_key = {_state_index(s): s.get("value") for s in source_states if _state_index(s)}

    mappings: list[dict] = []
    for key, value in value_by_key.items():
        raw_value = str(value or "").strip()
        if not raw_value:
            continue
        _, column_key, _idx = key
        mappings.append(
            {
                "data_source": str(source_by_key.get(key) or column_default_source.get(column_key, "virtualization")),
                "match_method": str(method_by_key.get(key) or "contains"),
                "match_value": raw_value,
                "enabled": bool(enabled_by_key.get(key, True)),
            }
        )
    return mappings
