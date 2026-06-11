"""DC View active tab persistence tests."""


def test_build_dc_view_honors_active_outer_tab():
    from unittest.mock import patch

    from src.pages.dc_view import build_dc_view

    def _track(name):
        def _fn(*_a, **_k):
            if name == "get_dc_details":
                return {
                    "meta": {"name": "DC13", "location": "Istanbul", "description": "Equinox"},
                    "classic": {
                        "hosts": 1, "cpu_cap": 10, "cpu_used": 5,
                        "mem_cap": 100, "mem_used": 50, "stor_cap": 1, "stor_used": 0.5,
                    },
                    "hyperconv": {},
                    "power": {},
                    "energy": {},
                    "intel": {"vms": 0},
                }
            if name == "get_sla_by_dc":
                return {}
            if name == "get_classic_cluster_list":
                return ["c1"]
            if name == "get_hyperconv_cluster_list":
                return []
            if name == "get_sellable_summary_light":
                return {"families": [], "total_potential_tl": 0}
            return {}

        return _fn

    api_patch = {
        "get_dc_details": _track("get_dc_details"),
        "get_sla_by_dc": _track("get_sla_by_dc"),
        "get_classic_cluster_list": _track("get_classic_cluster_list"),
        "get_hyperconv_cluster_list": _track("get_hyperconv_cluster_list"),
        "get_sellable_summary_light": _track("get_sellable_summary_light"),
    }

    with patch.multiple("src.pages.dc_view.api", **api_patch):
        page = build_dc_view(
            "DC13",
            time_range={"preset": "7d"},
            eager_tabs=frozenset({"summary"}),
            active_outer_tab="virt",
        )

    tabs = _find_by_id(page, "dc-main-tabs")
    assert tabs is not None
    assert tabs.value == "virt"


def _find_by_id(component, target_id, found=None):
    if component is None:
        return None
    cid = getattr(component, "id", None)
    if cid == target_id:
        return component
    children = getattr(component, "children", None)
    if children is None:
        return None
    if isinstance(children, (list, tuple)):
        for ch in children:
            hit = _find_by_id(ch, target_id)
            if hit is not None:
                return hit
    else:
        return _find_by_id(children, target_id)
    return None
