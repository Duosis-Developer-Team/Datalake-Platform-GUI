"""Regression tests for virt-total CRM client (thread-local accessor)."""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.services import api_client as api
from src.services import cache_service


def test_get_virt_sellable_panels_uses_get_client_crm():
    cache_service.clear()
    mock_client = MagicMock()
    rows = [{"panel_key": "virt_classic", "potential_tl": 100.0, "has_infra_source": True}]

    with patch.object(api, "_get_client_crm", return_value=mock_client) as get_crm:
        with patch.object(api, "_get_json", return_value=rows) as get_json:
            out = api.get_virt_sellable_panels("DC13", ["KM1"], ["HC1"])

    get_crm.assert_called_once()
    get_json.assert_called_once()
    client_arg, url_arg = get_json.call_args[0]
    assert client_arg is mock_client
    assert "/api/v1/crm/sellable-potential/virt-total?" in url_arg
    assert "dc_code=DC13" in url_arg
    assert "classic_clusters=KM1" in url_arg
    assert "hyperconv_clusters=HC1" in url_arg
    assert out == rows


def test_api_client_has_no_bare_client_crm_symbol():
    source = Path(api.__file__).read_text(encoding="utf-8")
    bare = re.findall(r"(?<![\w])_client_crm(?![\w])", source)
    assert bare == [], f"bare _client_crm references found: {bare}"
