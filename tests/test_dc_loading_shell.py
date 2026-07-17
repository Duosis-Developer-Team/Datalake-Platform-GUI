"""DC View loading shell structure tests."""


def test_build_dc_loading_shell_has_status_and_skeleton():
    from src.components.dc_loading import build_dc_loading_shell

    shell = build_dc_loading_shell("IST1")
    assert shell is not None
    ids = _collect_ids(shell)
    assert "dc-loading-layer" in ids
    assert "dc-loading-status" in ids
    assert "dc-loading-stage-interval" in ids


def test_build_dc_view_layout_shell_has_async_roots():
    from src.pages.dc_view import build_dc_view_layout_shell

    layout = build_dc_view_layout_shell("IST1", time_range={"preset": "7d"})
    blob = layout.to_plotly_json() if hasattr(layout, "to_plotly_json") else str(layout)
    text = str(blob)
    assert "dc-view-page-root" in text
    assert "dc-view-visible-sections" in text
    assert "dc-view-loaded-tabs" in text
    assert "dc-view-active-tab" in text
    assert "backup-panels-ready" in text
    assert "backup-category-tab-store" in text
    assert "backup-image-tab-store" in text
    assert "backup-replication-tab-store" in text
    assert "backup-uj-defer" in text


def _collect_ids(component, found=None):
    found = found or set()
    cid = getattr(component, "id", None)
    if cid:
        found.add(cid)
    children = getattr(component, "children", None)
    if children is None:
        return found
    if isinstance(children, (list, tuple)):
        for ch in children:
            if ch is not None:
                _collect_ids(ch, found)
    else:
        _collect_ids(children, found)
    return found
