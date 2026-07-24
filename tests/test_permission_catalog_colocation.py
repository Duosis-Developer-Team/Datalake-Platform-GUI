"""Test that sec:dc_view:colocation is registered in the permission catalog."""

from src.auth.permission_catalog import build_default_permission_roots


def test_colocation_section_registered():
    """Verify that sec:dc_view:colocation is registered under dc_view page."""
    roots = build_default_permission_roots()

    # Find the Dashboard group
    dashboard = None
    for root in roots:
        if root.code == "grp:dashboard":
            dashboard = root
            break
    assert dashboard is not None, "Dashboard group not found"

    # Find the DC View page
    dc_view_page = None
    for page in dashboard.children:
        if page.code == "page:dc_view":
            dc_view_page = page
            break
    assert dc_view_page is not None, "DC View page not found"

    # Verify sec:dc_view:colocation is among dc_view sections
    section_codes = [child.code for child in dc_view_page.children]
    assert "sec:dc_view:colocation" in section_codes, (
        f"sec:dc_view:colocation not found in dc_view sections. "
        f"Found: {section_codes}"
    )

    # Verify it has the correct name and sort_order
    colocation_section = None
    for child in dc_view_page.children:
        if child.code == "sec:dc_view:colocation":
            colocation_section = child
            break

    assert colocation_section is not None
    assert colocation_section.name == "Kolokasyon"
    assert colocation_section.resource_type == "section"
    assert colocation_section.sort_order == 75
