"""api_client — colocation rack rolü kuralları."""

from unittest.mock import patch

from src.services import api_client as api


def test_put_invalidates_the_colocation_and_sellable_caches():
    """Kaydetme, etkilenen GUI cache prefix'lerini temizlemeli.

    Yakaladığı bozulma: prefix temizlenmezse operatör Kaydet'e basar, DC
    Colocation kartı ve CRM sellable paneli GUI cache'inden eski sayıyı
    servis etmeye devam eder -- customer-api tarafı doğru olsa bile.
    """
    cleared: list[str] = []
    with patch.object(api, "_put_json", return_value={"status": "ok", "etag": "abcd1234"}), \
         patch.object(api._api_response_cache, "delete_prefix", side_effect=cleared.append):
        out = api.put_colocation_role_rules([{"role_id": "1", "sellable": True}])

    assert out["etag"] == "abcd1234"
    assert "api:colocation_role_rules" in cleared
    assert any(p.startswith("api:colocation") for p in cleared)
    assert any(p.startswith("api:sellable_summary") for p in cleared)
