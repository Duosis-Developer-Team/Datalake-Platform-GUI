"""Colocation renders as a Physical Inventory sub-tab, not a top-level tab."""
from src.pages import dc_view


def _tab_values(component):
    """Collect every dmc.TabsTab `value` in a Dash component tree."""
    out = []
    stack = [component]
    while stack:
        node = stack.pop()
        if node is None or isinstance(node, str):
            continue
        if type(node).__name__ == "TabsTab":
            value = getattr(node, "value", None)
            if value:
                out.append(value)
        children = getattr(node, "children", None)
        if isinstance(children, (list, tuple)):
            stack.extend(children)
        elif children is not None:
            stack.append(children)
    return out


def test_phys_inv_subtab_values():
    panel = dc_view._build_phys_inv_tab_content(
        phys_inv={}, coloc={}, show_overview=True, show_colo=True,
    )

    values = _tab_values(panel)
    assert "phys-overview" in values
    assert "phys-colo" in values


def test_colocation_subtab_hidden_without_permission():
    panel = dc_view._build_phys_inv_tab_content(
        phys_inv={}, coloc={}, show_overview=True, show_colo=False,
    )

    assert "phys-colo" not in _tab_values(panel)


def test_overview_subtab_hidden_without_permission():
    panel = dc_view._build_phys_inv_tab_content(
        phys_inv={}, coloc={}, show_overview=False, show_colo=True,
    )

    values = _tab_values(panel)
    assert "phys-overview" not in values
    assert "phys-colo" in values
