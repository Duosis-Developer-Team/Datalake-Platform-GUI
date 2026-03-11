import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.config import settings
from app.services import query_overrides as qo
from app.db.queries.registry import QUERY_REGISTRY


def test_settings_has_db_host_attribute():
    assert hasattr(settings, "db_host")


def test_settings_db_host_default():
    assert settings.db_host == "10.134.16.6"


def test_settings_db_port_default():
    assert settings.db_port == "5000"


def test_settings_db_name_default():
    assert settings.db_name == "bulutlake"


def test_settings_db_user_default():
    assert settings.db_user == "datalakeui"


def test_query_registry_is_non_empty_dict():
    assert isinstance(QUERY_REGISTRY, dict)
    assert len(QUERY_REGISTRY) > 0


def test_query_registry_each_entry_has_sql_field():
    for key, entry in QUERY_REGISTRY.items():
        assert "sql" in entry, f"Entry {key} missing 'sql'"


def test_query_registry_each_entry_has_result_type():
    for key, entry in QUERY_REGISTRY.items():
        assert "result_type" in entry, f"Entry {key} missing 'result_type'"


def test_load_overrides_returns_empty_dict_when_file_missing():
    from pathlib import Path
    nonexistent = Path("/tmp/does_not_exist_xyz_overrides_test.json")
    with patch.object(qo, "_OVERRIDES_PATH", nonexistent):
        result = qo.load_overrides()
    assert result == {}


def test_get_merged_entry_returns_none_for_unknown_key():
    result = qo.get_merged_entry("totally_unknown_key_xyz")
    assert result is None


def test_get_merged_entry_returns_base_entry_for_known_registry_key():
    from pathlib import Path
    first_key = next(iter(QUERY_REGISTRY))
    nonexistent = Path("/tmp/does_not_exist_xyz_overrides_test.json")
    with patch.object(qo, "_OVERRIDES_PATH", nonexistent):
        result = qo.get_merged_entry(first_key)
    assert result is not None
    assert "sql" in result


def test_list_all_query_keys_returns_sorted_list():
    from pathlib import Path
    nonexistent = Path("/tmp/does_not_exist_xyz_overrides_test.json")
    with patch.object(qo, "_OVERRIDES_PATH", nonexistent):
        keys = qo.list_all_query_keys()
    assert isinstance(keys, list)
    assert keys == sorted(keys)
    assert len(keys) >= len(QUERY_REGISTRY)


def test_load_overrides_handles_corrupt_json_gracefully():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("not valid json {{{")
        tmp_path = Path(f.name)
    with patch.object(qo, "_OVERRIDES_PATH", tmp_path):
        result = qo.load_overrides()
    assert result == {}
    tmp_path.unlink(missing_ok=True)


def test_load_overrides_handles_non_dict_json_gracefully():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump([1, 2, 3], f)
        tmp_path = Path(f.name)
    with patch.object(qo, "_OVERRIDES_PATH", tmp_path):
        result = qo.load_overrides()
    assert result == {}
    tmp_path.unlink(missing_ok=True)


def test_get_merged_entry_merges_override_sql_over_base():
    first_key = next(iter(QUERY_REGISTRY))
    fake_override = {first_key: {"sql": "SELECT 999"}}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(fake_override, f)
        tmp_path = Path(f.name)
    with patch.object(qo, "_OVERRIDES_PATH", tmp_path):
        result = qo.get_merged_entry(first_key)
    assert result["sql"] == "SELECT 999"
    tmp_path.unlink(missing_ok=True)


def test_set_override_writes_entry_to_file_and_is_retrievable():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / "overrides.json"
        with patch.object(qo, "_OVERRIDES_PATH", tmp_path):
            qo.set_override("custom_test_key", "SELECT 1", result_type="value", params_style="exact")
            result = qo.get_merged_entry("custom_test_key")
    assert result is not None
    assert result["sql"] == "SELECT 1"


def test_remove_override_deletes_existing_entry():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / "overrides.json"
        with patch.object(qo, "_OVERRIDES_PATH", tmp_path):
            qo.set_override("remove_test_key", "SELECT 2", result_type="value", params_style="exact", source="custom")
            removed = qo.remove_override("remove_test_key")
            still_there = qo.get_merged_entry("remove_test_key")
    assert removed is True
    assert still_there is None


def test_remove_override_returns_false_for_nonexistent_key():
    nonexistent = Path("/tmp/does_not_exist_xyz_overrides_test.json")
    with patch.object(qo, "_OVERRIDES_PATH", nonexistent):
        result = qo.remove_override("key_that_was_never_set")
    assert result is False


def test_set_override_for_existing_registry_key_merges_from_base():
    first_key = next(iter(QUERY_REGISTRY))
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / "overrides.json"
        with patch.object(qo, "_OVERRIDES_PATH", tmp_path):
            qo.set_override(first_key, "SELECT overridden")
            result = qo.get_merged_entry(first_key)
    assert result["sql"] == "SELECT overridden"
