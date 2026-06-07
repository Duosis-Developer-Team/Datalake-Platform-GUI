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

_SECTION_KEYS = [key for key, _, _ in UI_COLUMNS]
_COLUMN_SOURCE_DEFAULTS = {key: sources[0] for key, _, sources in UI_COLUMNS}


def mappings_for_column(source_mappings: list[dict], data_sources: tuple[str, ...]) -> list[dict]:
    allowed = set(data_sources)
    return [
        m
        for m in (source_mappings or [])
        if str(m.get("data_source") or "") in allowed
    ]


def _short_account_id(account_id: str) -> str:
    cleaned = (account_id or "").strip()
    if len(cleaned) <= 12:
        return cleaned
    return f"{cleaned[:8]}…"


def _mapping_status(source_mappings: list[dict], *, alias_source: str = "") -> str:
    mappings = source_mappings or []
    if not mappings:
        return "empty"
    if str(alias_source or "").lower() == "seed":
        return "seed"
    if any(str(m.get("source") or "").lower() == "seed" for m in mappings):
        return "seed"
    if any(str(m.get("match_value") or "").strip() for m in mappings):
        return "configured"
    return "empty"


def compute_coverage(source_mappings: list[dict]) -> tuple[int, int]:
    covered = 0
    for column_key, _, data_sources in UI_COLUMNS:
        entries = mappings_for_column(source_mappings, data_sources)
        if any(
            str(m.get("match_value") or "").strip()
            for m in entries
            if m.get("enabled", True) is not False
        ):
            covered += 1
    return covered, len(UI_COLUMNS)


def alias_to_table_row(alias: dict) -> dict:
    account_id = str(alias.get("crm_accountid") or "")
    mappings = alias.get("source_mappings") or []
    covered, total = compute_coverage(mappings)
    mapping_count = len([m for m in mappings if str(m.get("match_value") or "").strip()])
    status = _mapping_status(mappings, alias_source=str(alias.get("source") or ""))
    return {
        "crm_accountid": account_id,
        "crm_account_name": str(alias.get("crm_account_name") or account_id or "-"),
        "account_id_short": _short_account_id(account_id),
        "mapping_count": mapping_count,
        "coverage": f"{covered}/{total}",
        "status": status,
    }


def aliases_to_table_rows(aliases: list[dict]) -> list[dict]:
    rows = [alias_to_table_row(a) for a in (aliases or []) if a.get("crm_accountid")]
    rows.sort(key=lambda r: str(r.get("crm_account_name") or "").casefold())
    return rows


DEFAULT_ALIAS_TABLE_PAGE_SIZE = 25


def filter_alias_table_rows(rows: list[dict], query: str) -> list[dict]:
    q = (query or "").strip().casefold()
    if not q:
        return list(rows or [])
    return [
        row
        for row in (rows or [])
        if q in str(row.get("crm_account_name") or "").casefold()
        or q in str(row.get("crm_accountid") or "").casefold()
    ]


def paginate_alias_table_rows(
    rows: list[dict],
    page: int,
    page_size: int = DEFAULT_ALIAS_TABLE_PAGE_SIZE,
) -> list[dict]:
    size = max(int(page_size or DEFAULT_ALIAS_TABLE_PAGE_SIZE), 1)
    start = max(int(page or 0), 0) * size
    return list(rows or [])[start : start + size]


def page_count_for_rows(total: int, page_size: int = DEFAULT_ALIAS_TABLE_PAGE_SIZE) -> int:
    if page_size <= 0 or total <= 0:
        return 1
    return max(1, (total + page_size - 1) // page_size)


def compute_summary(aliases: list[dict]) -> dict[str, int]:
    rows = aliases or []
    configured = sum(1 for a in rows if (a.get("source_mappings") or []))
    empty = len(rows) - configured
    boyner_seed = 0
    for alias in rows:
        name = str(alias.get("crm_account_name") or "").casefold()
        if "boyner" in name:
            boyner_seed = len(alias.get("source_mappings") or [])
            break
    return {
        "total": len(rows),
        "configured": configured,
        "empty": max(empty, 0),
        "boyner_mappings": boyner_seed,
    }


def _normalize_mapping_entry(entry: dict, *, default_source: str) -> dict:
    return {
        "data_source": str(entry.get("data_source") or default_source),
        "match_method": str(entry.get("match_method") or "contains"),
        "match_value": str(entry.get("match_value") or ""),
        "enabled": bool(entry.get("enabled", True)),
    }


def build_editor_state(alias: dict | None) -> dict | None:
    if not alias or not alias.get("crm_accountid"):
        return None
    sections: dict[str, list[dict]] = {}
    source_mappings = alias.get("source_mappings") or []
    for column_key, _, data_sources in UI_COLUMNS:
        default_source = data_sources[0]
        entries = mappings_for_column(source_mappings, data_sources)
        if entries:
            sections[column_key] = [
                _normalize_mapping_entry(e, default_source=default_source) for e in entries
            ]
        else:
            sections[column_key] = [
                {
                    "data_source": default_source,
                    "match_method": "contains",
                    "match_value": "",
                    "enabled": True,
                }
            ]
    return {
        "crm_accountid": str(alias.get("crm_accountid")),
        "crm_account_name": str(alias.get("crm_account_name") or alias.get("crm_accountid")),
        "notes": str(alias.get("notes") or ""),
        "sections": sections,
    }


def _index_pattern_states(states: list, field: str) -> dict[tuple[str, int], object]:
    indexed: dict[tuple[str, int], object] = {}
    for state in states or []:
        sid = state.get("id") or {}
        section = str(sid.get("section") or "")
        if not section:
            continue
        key = (section, int(sid.get("index", 0)))
        indexed[key] = state.get(field)
    return indexed


def editor_state_from_dash_states(
    editor_state: dict | None,
    *,
    method_states: list,
    value_states: list,
    enabled_states: list,
    source_states: list,
    notes: str | None,
) -> dict | None:
    """Rebuild editor sections from Dash pattern-matched component states."""
    if not editor_state:
        return None
    methods = _index_pattern_states(method_states, "value")
    values = _index_pattern_states(value_states, "value")
    enabled = _index_pattern_states(enabled_states, "value")
    sources = _index_pattern_states(source_states, "value")
    all_keys = set(methods) | set(values) | set(enabled) | set(sources)

    sections: dict[str, list[dict]] = {}
    for section_key in _SECTION_KEYS:
        default_source = _COLUMN_SOURCE_DEFAULTS.get(section_key, "virtualization")
        section_keys = sorted((k for k in all_keys if k[0] == section_key), key=lambda k: k[1])
        if section_keys:
            sections[section_key] = [
                _normalize_mapping_entry(
                    {
                        "data_source": sources.get(key) or default_source,
                        "match_method": methods.get(key) or "contains",
                        "match_value": values.get(key) or "",
                        "enabled": enabled.get(key, True),
                    },
                    default_source=default_source,
                )
                for key in section_keys
            ]
        else:
            original = editor_state.get("sections", {}).get(section_key) or []
            sections[section_key] = [
                _normalize_mapping_entry(dict(entry), default_source=default_source)
                for entry in original
            ] or [
                {
                    "data_source": default_source,
                    "match_method": "contains",
                    "match_value": "",
                    "enabled": True,
                }
            ]

    return {
        "crm_accountid": str(editor_state.get("crm_accountid") or ""),
        "crm_account_name": str(editor_state.get("crm_account_name") or editor_state.get("crm_accountid") or ""),
        "notes": str(notes if notes is not None else editor_state.get("notes") or ""),
        "sections": sections,
    }


def editor_state_to_save_payload(editor_state: dict | None) -> tuple[list[dict], str | None]:
    if not editor_state:
        return [], None
    mappings: list[dict] = []
    for column_key in _SECTION_KEYS:
        for entry in editor_state.get("sections", {}).get(column_key) or []:
            value = str(entry.get("match_value") or "").strip()
            if not value:
                continue
            default_source = _COLUMN_SOURCE_DEFAULTS.get(column_key, "virtualization")
            mappings.append(
                {
                    "data_source": str(entry.get("data_source") or default_source),
                    "match_method": str(entry.get("match_method") or "contains"),
                    "match_value": value,
                    "enabled": bool(entry.get("enabled", True)),
                }
            )
    notes = str(editor_state.get("notes") or "").strip() or None
    return mappings, notes


def merge_alias_after_save(
    page_data: list[dict],
    *,
    account_id: str,
    saved_mappings: list[dict],
    notes: str | None,
) -> list[dict]:
    out: list[dict] = []
    updated = False
    for alias in page_data or []:
        if str(alias.get("crm_accountid")) != account_id:
            out.append(alias)
            continue
        updated = True
        merged = dict(alias)
        merged["source_mappings"] = list(saved_mappings or [])
        if notes is not None:
            merged["notes"] = notes
        merged["source"] = "manual"
        out.append(merged)
    if not updated:
        out.append(
            {
                "crm_accountid": account_id,
                "crm_account_name": account_id,
                "source_mappings": list(saved_mappings or []),
                "notes": notes,
                "source": "manual",
            }
        )
    return out


def find_alias(page_data: list[dict], account_id: str) -> dict | None:
    for alias in page_data or []:
        if str(alias.get("crm_accountid")) == account_id:
            return alias
    return None


def resolve_visible_row_index(
    selected_rows: list[int] | None,
    active_cell: dict | None,
    *,
    trigger_id,
    table_id: str,
) -> int | None:
    """Resolve a page-relative row index; prefer radio selection over active_cell."""
    if selected_rows:
        return int(selected_rows[0])
    if trigger_id == f"{table_id}.active_cell" and active_cell and active_cell.get("row") is not None:
        return int(active_cell["row"])
    if active_cell and active_cell.get("row") is not None:
        return int(active_cell["row"])
    return None


def resolve_visible_rows(
    virtual_data: list[dict] | None,
    viewport_data: list[dict] | None,
    table_data: list[dict] | None,
    page_current: int | None,
    page_size: int | None,
) -> list[dict]:
    """Rows visible in the DataTable after filter/sort/pagination."""
    if virtual_data is not None:
        return list(virtual_data)
    if viewport_data is not None:
        return list(viewport_data)
    rows = list(table_data or [])
    if not rows:
        return []
    size = max(int(page_size or 25), 1)
    page = max(int(page_current or 0), 0)
    start = page * size
    return rows[start : start + size]


def alias_from_table_selection(row: dict | None, page_data: list[dict]) -> dict | None:
    """Build alias payload for editor load, even when page_data lookup misses."""
    if not row:
        return None
    account_id = str(row.get("crm_accountid") or "")
    if not account_id:
        name = str(row.get("crm_account_name") or "")
        for alias in page_data or []:
            if str(alias.get("crm_account_name") or "") == name:
                return dict(alias)
        return None
    found = find_alias(page_data or [], account_id)
    if found:
        return found
    return {
        "crm_accountid": account_id,
        "crm_account_name": str(row.get("crm_account_name") or account_id),
        "source_mappings": [],
        "notes": "",
        "source": "manual",
    }


def collect_mappings_for_account(
    account_id: str,
    method_states: list,
    value_states: list,
    enabled_states: list,
    source_states: list,
) -> list[dict]:
    """Legacy helper for pattern-matched row editors (kept for tests)."""
    column_default_source = _COLUMN_SOURCE_DEFAULTS

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


def editor_state_from_form_inputs(
    editor_state: dict | None,
    *,
    section: str,
    index: int,
    match_method: str | None = None,
    match_value: str | None = None,
    data_source: str | None = None,
    enabled: bool | None = None,
    notes: str | None = None,
) -> dict | None:
    """Apply a single field change onto editor state (immutable-style copy)."""
    if not editor_state:
        return None
    state = {
        "crm_accountid": editor_state.get("crm_accountid"),
        "crm_account_name": editor_state.get("crm_account_name"),
        "notes": notes if notes is not None else editor_state.get("notes", ""),
        "sections": {k: [dict(x) for x in v] for k, v in (editor_state.get("sections") or {}).items()},
    }
    entries = list(state["sections"].get(section) or [])
    if index < 0 or index >= len(entries):
        return None
    entry = dict(entries[index])
    if match_method is not None:
        entry["match_method"] = match_method
    if match_value is not None:
        entry["match_value"] = match_value
    if data_source is not None:
        entry["data_source"] = data_source
    if enabled is not None:
        entry["enabled"] = enabled
    entries[index] = entry
    state["sections"][section] = entries
    return state


def add_mapping_row(editor_state: dict | None, section: str) -> dict | None:
    if not editor_state:
        return None
    state = {
        "crm_accountid": editor_state.get("crm_accountid"),
        "crm_account_name": editor_state.get("crm_account_name"),
        "notes": editor_state.get("notes", ""),
        "sections": {k: [dict(x) for x in v] for k, v in (editor_state.get("sections") or {}).items()},
    }
    default_source = _COLUMN_SOURCE_DEFAULTS.get(section, "virtualization")
    entries = list(state["sections"].get(section) or [])
    entries.append(
        {
            "data_source": default_source,
            "match_method": "contains",
            "match_value": "",
            "enabled": True,
        }
    )
    state["sections"][section] = entries
    return state


def remove_mapping_row(editor_state: dict | None, section: str, index: int) -> dict | None:
    if not editor_state:
        return None
    state = {
        "crm_accountid": editor_state.get("crm_accountid"),
        "crm_account_name": editor_state.get("crm_account_name"),
        "notes": editor_state.get("notes", ""),
        "sections": {k: [dict(x) for x in v] for k, v in (editor_state.get("sections") or {}).items()},
    }
    entries = list(state["sections"].get(section) or [])
    if index < 0 or index >= len(entries):
        return None
    if len(entries) <= 1:
        default_source = _COLUMN_SOURCE_DEFAULTS.get(section, "virtualization")
        state["sections"][section] = [
            {
                "data_source": default_source,
                "match_method": "contains",
                "match_value": "",
                "enabled": True,
            }
        ]
        return state
    entries.pop(index)
    state["sections"][section] = entries
    return state
