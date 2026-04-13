"""IAM Users page: LDAP import in slide-in panel, edit via panel (no legacy modal)."""

from __future__ import annotations

from typing import Any, Iterable


def _walk(obj: Any) -> Iterable[Any]:
    if obj is None:
        return
    if isinstance(obj, (list, tuple)):
        for item in obj:
            yield from _walk(item)
        return
    yield obj
    ch = getattr(obj, "children", None)
    if ch is not None:
        yield from _walk(ch)


def _ids_in_layout(root: Any) -> set[Any]:
    found: set[Any] = set()
    for node in _walk(root):
        i = getattr(node, "id", None)
        if i is not None:
            found.add(i)
    return found


def test_users_layout_has_inline_ldap_checklist_and_slide_panel(monkeypatch):
    from src.pages.settings.iam import users as users_page

    monkeypatch.setattr(users_page.settings_crud, "list_users_with_roles", lambda: [])
    monkeypatch.setattr(users_page.settings_crud, "list_roles", lambda: [])
    monkeypatch.setattr(users_page.settings_crud, "list_teams", lambda: [])

    layout = users_page.build_layout()
    ids = _ids_in_layout(layout)

    assert "ad-import-checklist" in ids
    assert "ad-search-modal" not in ids
    assert "iam-user-panel-store" in ids
    assert "user-slide-panel" in ids
    assert "iam-user-open-create" in ids
