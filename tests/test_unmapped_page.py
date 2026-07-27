"""The unmapped (Eşleşmeyen Veriler) page had no test at all — only its classifier
did. These pin the things a reader of the page depends on: it renders without a
backend, and it always offers a visible way back to the customers list.
"""
from unittest.mock import patch

_PAYLOAD = {
    "rows": [
        {"name": "Acme_Kilit-Web01", "guessed_owner": "Örnek Kilit A.Ş.",
         "platform": "Nutanix", "reason": "alias_gap", "kind": "vm",
         "guessed_owner_id": "acc-1", "suggested_alias": "Acme_Kilit",
         "suggested_method": "prefix"},
        {"name": "123host", "guessed_owner": None, "platform": "VMware",
         "reason": "orphan", "kind": "vm",
         "guessed_owner_id": None, "suggested_alias": None,
         "suggested_method": None},
    ],
    "total": 2,
    "alias_gap_count": 1,
    "orphan_count": 1,
}


def _render(payload=_PAYLOAD):
    from src.pages import unmapped_resources as page

    with patch("src.services.api_client.get_unmapped_resources", return_value=payload):
        return str(page.build_layout({"preset": "7d", "start": "2026-07-10", "end": "2026-07-16"}))


def test_page_offers_a_visible_way_back_to_customers():
    # The page is reachable only from the customers list, so the link back is the
    # only exit. It must render a *filled* button — "subtle" paints no background
    # until hover, which read as no button at all on a fresh load.
    out = _render()
    assert "Müşterilere dön" in out
    assert "/customers" in out
    assert "variant='subtle'" not in out


def test_page_renders_counts_and_rows():
    out = _render()
    assert "Toplam eşleşmeyen" in out
    assert "Acme_Kilit-Web01" in out
    assert "Örnek Kilit A.Ş." in out


def test_page_renders_when_the_backend_is_down():
    # An orphan report must never take the page down: build_layout swallows the
    # failure and still renders (empty), rather than raising into the router.
    from src.pages import unmapped_resources as page

    with patch("src.services.api_client.get_unmapped_resources",
               side_effect=RuntimeError("customer-api down")):
        out = str(page.build_layout({"preset": "7d"}))
    assert "Müşterilere dön" in out
    assert "Toplam eşleşmeyen" in out


def test_alias_gap_rows_offer_an_action_and_orphans_do_not():
    """Sahipsiz satırda bağlanacak müşteri yok; işlem hücresi boş kalır."""
    from src.pages.unmapped_resources import ACTION_LABEL, _table_rows

    rows = _table_rows(_PAYLOAD["rows"])
    by_name = {r["name"]: r for r in rows}

    assert by_name["Acme_Kilit-Web01"]["action"] == ACTION_LABEL
    assert by_name["123host"]["action"] == ""


def test_table_rows_carry_a_stable_key_for_the_click_handler():
    """active_cell yalnızca satır indeksi verir; sıralama/filtre sonrası indeks kayar."""
    from src.pages.unmapped_resources import _table_rows

    rows = _table_rows(_PAYLOAD["rows"])
    assert rows[0]["row_key"] == "vm::Acme_Kilit-Web01"
    assert rows[1]["row_key"] == "vm::123host"


def test_hint_links_to_customer_aliases_not_internal_aliases():
    """İç Alias yalnızca INTERNAL rezerve hesabı içindir; müşteri alias'ı oraya yazılmaz."""
    out = _render()
    assert "/settings/integrations/crm/internal-aliases" not in out
    assert "crm-aliases" in out or "crm/aliases" in out
