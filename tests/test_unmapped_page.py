"""The unmapped (Eşleşmeyen Veriler) page had no test at all — only its classifier
did. These pin the things a reader of the page depends on: it renders without a
backend, and it always offers a visible way back to the customers list.
"""
from unittest.mock import patch


def _walk(node):
    if node is None:
        return
    if isinstance(node, (list, tuple)):
        for item in node:
            yield from _walk(item)
        return
    yield node
    children = getattr(node, "children", None)
    if children is not None:
        yield from _walk(children)


def _find_by_id(component, target_id):
    for node in _walk(component):
        if getattr(node, "id", None) == target_id:
            return node
    return None


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


def _build_body(payload):
    """The live component tree build_body() produces — not its string repr —
    so a test can inspect a specific DataTable's own `data`, not text that
    happens to appear somewhere in the whole rendered page.
    """
    from src.pages import unmapped_resources as page

    with patch("src.services.api_client.get_unmapped_resources", return_value=payload):
        return page.build_body({"preset": "7d", "start": "2026-07-10", "end": "2026-07-16"})


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


_MIXED_PAYLOAD = {
    "rows": [
        {"name": "Acme_Kilit-Web01", "guessed_owner": "Örnek Kilit A.Ş.",
         "platform": "Nutanix", "reason": "alias_gap", "kind": "vm",
         "guessed_owner_id": "acc-1", "suggested_alias": "Acme_Kilit",
         "suggested_method": "prefix"},
        {"name": "abc-dete-s4hana-prd-log", "guessed_owner": "ABC Deterjan",
         "platform": "netbackup", "reason": "alias_gap", "kind": "backup",
         "guessed_owner_id": "acc-abc", "suggested_alias": "abc-dete",
         "suggested_method": "prefix", "candidate_count": 1},
        {"name": "avro-CLAVRDB01-H", "guessed_owner": None,
         "platform": "netbackup", "reason": "ambiguous", "kind": "backup",
         "guessed_owner_id": None, "suggested_alias": None,
         "suggested_method": None, "candidate_count": 2},
    ],
    "total": 3,
    "alias_gap_count": 2,
    "orphan_count": 0,
    "ambiguous_count": 1,
}


def test_backup_tab_renders_next_to_virtualization():
    out = _render(_MIXED_PAYLOAD)
    assert "Sanallaştırma" in out
    assert "Backup" in out
    assert "abc-dete-s4hana-prd-log" in out


def test_backup_rows_do_not_leak_into_the_virtualization_table():
    """Her sekme yalnızca kendi kaynağını gösterir.

    Exercises build_body()'s own kind-based split (src/pages/unmapped_resources.py
    vm_rows/backup_rows comprehensions), not a filter re-derived here: it locates
    the two rendered DataTables by their table_id() and reads each one's own
    `data`, so a leak in build_body's split — e.g. both tables getting every
    row — is directly observable via the row content, not just via which text
    strings appear somewhere in the page.
    """
    from src.pages.unmapped_resources import table_id

    body = _build_body(_MIXED_PAYLOAD)
    vm_table = _find_by_id(body, table_id("vm"))
    backup_table = _find_by_id(body, table_id("backup"))

    assert {r["name"] for r in vm_table.data} == {"Acme_Kilit-Web01"}
    assert {r["name"] for r in backup_table.data} == {
        "abc-dete-s4hana-prd-log", "avro-CLAVRDB01-H",
    }


def test_ambiguous_rows_are_labelled_and_offer_no_action():
    """Yanlış müşteriye backup bağlamak boş bırakmaktan kötüdür."""
    from src.pages.unmapped_resources import _table_rows

    rows = _table_rows([r for r in _MIXED_PAYLOAD["rows"] if r["kind"] == "backup"])
    by_name = {r["name"]: r for r in rows}

    assert by_name["avro-CLAVRDB01-H"]["reason"] == "Belirsiz (2 aday)"
    assert by_name["avro-CLAVRDB01-H"]["action"] == ""
    assert by_name["abc-dete-s4hana-prd-log"]["action"] == "Alias ekle"


def test_ambiguous_kpi_appears_only_when_there_are_ambiguous_rows():
    # Checked against the KPI card's own label, not the bare word "Belirsiz":
    # the DataTable's static style_data_conditional carries a
    # "{reason} contains 'Belirsiz'" filter_query on every rendered table
    # (VM included) regardless of whether any row actually has that reason,
    # so a bare substring check can never tell the two payloads apart.
    assert "Belirsiz (elle seçim)" in _render(_MIXED_PAYLOAD)
    assert "Belirsiz (elle seçim)" not in _render(_PAYLOAD)
