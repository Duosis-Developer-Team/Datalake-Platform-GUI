"""Load optional CRM service mapping YAML (pages registry for tooling / docs)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore


def default_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "crm_service_mapping.yaml"


def load_mapping_yaml(path: Optional[Path] = None) -> Dict[str, Any]:
    """Return parsed YAML dict; empty dict if file missing or PyYAML unavailable."""
    p = path or default_config_path()
    if yaml is None or not p.is_file():
        return {}
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}
