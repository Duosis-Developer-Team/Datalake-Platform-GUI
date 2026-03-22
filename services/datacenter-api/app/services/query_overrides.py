# Query overrides: load/save JSON and merge with QUERY_REGISTRY for Query Explorer.
# Overrides allow editing SQL (and optional metadata) from the UI without changing .py files.

import json
import logging
from pathlib import Path

from app.db.queries.registry import QUERY_REGISTRY

logger = logging.getLogger(__name__)

_THIS_DIR = Path(__file__).resolve().parent
# services/datacenter-api/app/services -> repo root (5 levels up)
_PROJECT_ROOT = _THIS_DIR.parent.parent.parent.parent.parent
_OVERRIDES_PATH = _PROJECT_ROOT / "data" / "query_overrides.json"


def _ensure_data_dir() -> None:
    """Ensure data directory exists."""
    _OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_overrides() -> dict[str, dict]:
    """Load override entries from JSON file. Returns dict key -> { sql?, result_type?, params_style?, source? }."""
    if not _OVERRIDES_PATH.exists():
        return {}
    try:
        with open(_OVERRIDES_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("Failed to load query overrides from %s: %s", _OVERRIDES_PATH, exc)
        return {}


def save_overrides(overrides: dict[str, dict]) -> None:
    """Write override entries to JSON file."""
    _ensure_data_dir()
    with open(_OVERRIDES_PATH, "w", encoding="utf-8") as f:
        json.dump(overrides, f, indent=2, ensure_ascii=False)
    logger.info("Saved query overrides to %s", _OVERRIDES_PATH)


def get_merged_entry(query_key: str) -> dict | None:
    """
    Return merged query entry for a key: registry base + override overlay.
    Keys only in overrides (custom queries) are returned as-is with required fields.
    """
    overrides = load_overrides()
    base = QUERY_REGISTRY.get(query_key)
    override = overrides.get(query_key)

    if base is None and override is None:
        return None
    if base is None:
        # Custom query: must have sql, result_type, params_style at minimum
        if not override or "sql" not in override or "result_type" not in override or "params_style" not in override:
            return None
        return {
            "sql": override["sql"],
            "source": override.get("source", "custom"),
            "result_type": override["result_type"],
            "params_style": override["params_style"],
            "provider": override.get("provider", "custom"),
        }
    # Registry entry with optional override
    merged = dict(base)
    if override:
        if "sql" in override:
            merged["sql"] = override["sql"]
        if "result_type" in override:
            merged["result_type"] = override["result_type"]
        if "params_style" in override:
            merged["params_style"] = override["params_style"]
    return merged


def list_all_query_keys() -> list[str]:
    """Return all query keys: registry keys plus override-only (custom) keys, sorted."""
    overrides = load_overrides()
    keys = set(QUERY_REGISTRY.keys()) | set(overrides.keys())
    return sorted(keys)


def set_override(query_key: str, sql: str, result_type: str | None = None, params_style: str | None = None, source: str = "custom") -> None:
    """Write or update a single override entry. None for result_type/params_style keeps registry default for that key."""
    overrides = load_overrides()
    base = QUERY_REGISTRY.get(query_key)
    entry = {"sql": sql}
    if result_type is not None:
        entry["result_type"] = result_type
    elif base is not None:
        entry["result_type"] = base["result_type"]
    else:
        entry["result_type"] = "value"
    if params_style is not None:
        entry["params_style"] = params_style
    elif base is not None:
        entry["params_style"] = base["params_style"]
    else:
        entry["params_style"] = "wildcard"
    if base is None:
        entry["source"] = source
    overrides[query_key] = entry
    save_overrides(overrides)


def remove_override(query_key: str) -> bool:
    """Remove override for a key. Returns True if an override was removed."""
    overrides = load_overrides()
    if query_key not in overrides:
        return False
    del overrides[query_key]
    save_overrides(overrides)
    return True
