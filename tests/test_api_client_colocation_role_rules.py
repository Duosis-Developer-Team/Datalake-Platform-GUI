"""api_client — colocation rack rolü kuralları."""

from unittest.mock import patch
from urllib.parse import quote

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


def test_put_invalidates_actual_dc_racks_cache():
    """Rol kuralı kaydedildiğinde, get_dc_racks'in ürettiği real cache anahtarları temizlenmeli.

    Yakaladığı bozulma: temizlenen prefix'ler, gerçek cache anahtarlarının
    formatıyla eşleşmezse (örn. "api:dc_racks_" vs "api:dc_racks:"), bayat
    DC rack verisi ekranda kalır. Ayrıca sellable prefix'lerini kopyalamak
    yerine helper çağrılmalı, yoksa "api:sellable_snapshot_meta:" gibi yeni
    prefix'ler ekleneince sessizce geride kalır.
    """
    cleared: list[str] = []

    # Construct real cache key the same way get_dc_racks() does
    dc_code = "DC13"
    enc = quote(dc_code, safe="")
    real_dc_racks_cache_key = f"api:dc_racks:{enc}"

    with patch.object(api, "_put_json", return_value={"status": "ok"}), \
         patch.object(api._api_response_cache, "delete_prefix", side_effect=cleared.append):
        api.put_colocation_role_rules([{"role_id": "1", "sellable": True}])

    # Verify at least one cleared prefix matches the real cache key via startswith
    # (the semantic used by delete_prefix in cache_service.py:118)
    assert any(real_dc_racks_cache_key.startswith(p) for p in cleared), \
        f"No cleared prefix matches {real_dc_racks_cache_key}. Cleared: {cleared}"

    # Verify the full sellable helper was called (catches missing snapshot_meta)
    assert "api:sellable_snapshot_meta:" in cleared, \
        f"Missing api:sellable_snapshot_meta: in cleared prefixes. Cleared: {cleared}"
