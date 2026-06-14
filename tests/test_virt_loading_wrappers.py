"""P4a: Virt compute panels must be wrapped in dcc.Loading so cold fetches show a spinner."""
from dash import dcc
from src.pages import dc_view


def _has_loading_around(component, target_id: str) -> bool:
    """DFS: is there a dcc.Loading whose subtree contains a child with id==target_id?"""
    found = {"loading_ancestor": False}

    def walk(node, under_loading):
        if getattr(node, "id", None) == target_id and under_loading:
            found["loading_ancestor"] = True
        children = getattr(node, "children", None)
        now = under_loading or isinstance(node, dcc.Loading)
        if isinstance(children, (list, tuple)):
            for ch in children:
                if ch is not None:
                    walk(ch, now)
        elif children is not None and hasattr(children, "children"):
            walk(children, now)
    for top in component:
        if top is not None:
            walk(top, False)
    return found["loading_ancestor"]


def test_classic_panel_wrapped_in_loading():
    stack = dc_view._build_virt_subtab_stack(
        "classic", dc_id="DC13", classic={}, hyperconv={}, power={}, energy={},
        classic_clusters=["DC13-KM-01"], hyperconv_clusters=[], storage_capacity={},
        storage_performance={}, san_bottleneck={}, show_virt_hosts=False,
    )
    assert _has_loading_around(stack, "classic-virt-panel")


def test_hyperconv_panel_wrapped_in_loading():
    stack = dc_view._build_virt_subtab_stack(
        "hyperconv", dc_id="DC13", classic={}, hyperconv={}, power={}, energy={},
        classic_clusters=[], hyperconv_clusters=["AZ11-Nutanix-1"], storage_capacity={},
        storage_performance={}, san_bottleneck={}, show_virt_hosts=False,
    )
    assert _has_loading_around(stack, "hyperconv-virt-panel")
