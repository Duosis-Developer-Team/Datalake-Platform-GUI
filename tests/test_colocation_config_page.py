"""Colocation Configuration sayfası — birleştirme, önizleme, layout, RBAC."""

from unittest.mock import patch

from src.pages.settings import shell
from src.pages.settings.integrations import colocation_config as page
from src.utils.colocation_config_ui import (
    merge_rules_with_catalog,
    preview_sellable_free_u,
)

CATALOG = [
    {"role_id": "1", "role_name": "NETWORK RACK"},
    {"role_id": "2", "role_name": "HOST RACK"},
    {"role_id": "5", "role_name": "YENI ROL"},
]
RULES = [
    {"role_id": "1", "sellable": False},
    {"role_id": "2", "sellable": True},
]
BREAKDOWN = [
    {"role_id": "1", "rack_count": 42, "capacity_u": 1930, "free_u": 900},
    {"role_id": "2", "rack_count": 139, "capacity_u": 6408, "free_u": 3503},
]


def _walk(node):
    yield node
    children = getattr(node, "children", None)
    if children is None:
        return
    if not isinstance(children, (list, tuple)):
        children = [children]
    for c in children:
        yield from _walk(c)


def _ids(layout):
    return [getattr(n, "id", None) for n in _walk(layout) if getattr(n, "id", None)]


def test_role_without_a_rule_is_shown_as_new_and_sellable():
    """Katalogda olup kuralı olmayan rol, sellable ve 'yeni' işaretli gelmeli.

    Yakaladığı bozulma: Loki'ye 5. rol eklendiğinde ekran onu ya hiç
    göstermez (operatör sellable U'nun neden büyüdüğünü bulamaz) ya da
    hesaptan farklı olarak 'kapalı' gösterir -- ekran ile motor ayrışır.
    """
    merged = merge_rules_with_catalog(RULES, CATALOG, BREAKDOWN)
    new_role = next(r for r in merged if r["role_id"] == "5")
    assert new_role["sellable"] is True
    assert new_role["is_new"] is True
    assert new_role["free_u"] == 0


def test_preview_reflects_pending_switch_state_not_saved_state():
    """Önizleme, kaydedilmemiş switch durumuna göre hesaplamalı.

    Yakaladığı bozulma: önizleme kaydedilmiş kuralı gösterirse operatör
    'kaydedince ne olacak' sorusunun cevabını göremez; NETWORK'ü açıp
    3.503 görmeye devam eder, sonra kaydedip 4.403 ile karşılaşır.
    """
    merged = merge_rules_with_catalog(RULES, CATALOG, BREAKDOWN)
    assert preview_sellable_free_u(merged, {}) == 3503
    assert preview_sellable_free_u(merged, {"1": True}) == 4403
    assert preview_sellable_free_u(merged, {"2": False}) == 0


def test_layout_builds_with_switch_per_catalog_role():
    """Sayfa, katalogdaki her rol için bir switch üretmeli.

    Yakaladığı bozulma: layout kayıtlı kural listesi üzerinden kurulursa
    kuralı olmayan rol ekrana hiç gelmez ve ayarlanamaz.
    """
    payload = {"rules": RULES, "catalog": CATALOG, "etag": "abcd1234", "degraded": False}
    with patch.object(page.api, "get_colocation_role_rules", return_value=payload), \
         patch.object(page.api, "get_colocation", return_value={"aggregate": {"role_breakdown": BREAKDOWN}}):
        layout = page.build_layout()

    ids = _ids(layout)
    for role_id in ("1", "2", "5"):
        assert {"type": "coloc-cfg-switch", "role": role_id} in ids
    assert "coloc-cfg-save" in ids


def test_page_is_denied_by_its_own_permission_code():
    """Administration'a erişebilen ama BU kodu olmayan kullanıcı reddedilmeli.

    Yakaladığı bozulma: sayfa _PAGE_BUILDERS'a eklenip kendi permission
    koduna bağlanmazsa, sellable U'yu platform genelinde değiştirebilen bir
    ekran Administration'a erişebilen herkese açılır.

    can_view SADECE yeni kod için False döner; tümden False yapmak testi
    tautolojik yapardı, çünkü has_any_settings_access zaten daha kapıda
    reddeder ve kod hiç bağlanmasa da test geçerdi.
    """
    def _can_view(_user_id, code):
        return code != "page:settings_colocation_config"

    with patch("src.auth.permission_service.can_view", side_effect=_can_view):
        out = shell.build_settings_page(
            "/administration/integrations/netbox/colocation", user_id=999
        )
    assert "denied" in str(out).lower()


def test_netbox_sub_nav_lists_both_tabs():
    """NetBox/Loki altında iki sekme de görünmeli.

    Yakaladığı bozulma: sub-nav bloğu eklenmezse yeni sayfaya hiçbir yerden
    link olmaz, yalnızca URL'i bilen ulaşır.
    """
    with patch("src.auth.permission_service.can_view", return_value=True):
        nav = shell._sub_nav(1, "/administration/integrations/netbox/colocation")
    text = str(nav)
    assert "Filters" in text
    assert "Colocation Configuration" in text
