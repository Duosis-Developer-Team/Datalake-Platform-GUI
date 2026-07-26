"""Reusable DC → Cluster → Host → VM drill-down tree (nested dmc.Accordion).

Consumes the shape from datacenter-api /vm-topology (shared.topology.build_tree):
{"dcs": [{name, counts, os?, clusters:[{name, counts, os?, hosts:[{name, counts,
os?, vms:[{name, os_family, power_state}]}]}]}], "totals": {...}}. Data is already
loaded; the Accordion only lazy-renders visually. Used by the Licensed OS page
(with_os=True) and the Datalake Coverage page (with_os=False)."""
from __future__ import annotations

import dash_mantine_components as dmc
from dash import html

_OS_COLORS = {"windows": "#528BFF", "rhel": "#EE0000", "suse": "#30BA78",
              "free": "#98A2B3", "unknown": "#D0D5DD"}
_PS_COLOR = {"poweredOn": "green", "poweredOff": "gray"}


def _count_badge(counts: dict) -> dmc.Badge:
    c = counts or {}
    bits = []
    if c.get("clusters") is not None:
        bits.append(f"{c['clusters']} cluster")
    if c.get("hosts") is not None:
        bits.append(f"{c['hosts']} host")
    bits.append(f"{int(c.get('vms') or 0)} VM")
    bits.append(f"{int(c.get('running') or 0)} çalışan")
    return dmc.Badge(" · ".join(bits), color="indigo", variant="light", size="sm")


def _os_bar(os_tally: dict | None):
    if not os_tally:
        return None
    total = sum(int(v or 0) for v in os_tally.values())
    if total <= 0:
        return None
    segs = []
    for fam in ("windows", "rhel", "suse", "free", "unknown"):
        n = int(os_tally.get(fam) or 0)
        if n:
            segs.append(html.Div(title=f"{fam}: {n}", style={
                "width": f"{n / total * 100:.1f}%", "background": _OS_COLORS[fam], "height": "100%"}))
    return html.Div(style={"display": "flex", "width": "140px", "height": "8px",
                           "borderRadius": "4px", "overflow": "hidden",
                           "background": "#F2F4F7"}, children=segs)


def _node_control(name: str, counts: dict, os_tally: dict | None):
    row = [dmc.Text(name, fw=600, size="sm"), _count_badge(counts)]
    bar = _os_bar(os_tally)
    if bar is not None:
        row.append(bar)
    return dmc.Group(gap="sm", align="center", children=row)


def _vm_list(vms: list[dict]):
    rows = [
        dmc.Group(gap="xs", align="center", children=[
            dmc.Badge(v.get("os_family", ""), color=_OS_COLORS_NAME(v.get("os_family")),
                      variant="dot", size="xs"),
            dmc.Text(v.get("name", ""), size="xs"),
            dmc.Badge(v.get("power_state", ""),
                      color=_PS_COLOR.get(v.get("power_state"), "gray"),
                      variant="light", size="xs"),
        ])
        for v in (vms or [])
    ]
    # Long per-host VM lists scroll in their own box (keeps the page compact).
    return html.Div(style={"maxHeight": "260px", "overflowY": "auto", "paddingLeft": "8px"},
                    children=rows or [dmc.Text("VM yok.", size="xs", c="dimmed")])


def _OS_COLORS_NAME(fam: str | None) -> str:
    return {"windows": "blue", "rhel": "red", "suse": "green",
            "free": "gray", "unknown": "gray"}.get(fam or "", "gray")


def build_topology_tree(tree: dict, *, with_os: bool = False):
    dcs = (tree or {}).get("dcs") or []
    if not dcs:
        return dmc.Text("Topoloji verisi yok.", size="sm", c="dimmed")

    dc_items = []
    for dc in dcs:
        cluster_items = []
        for cl in dc.get("clusters", []) or []:
            host_items = []
            for h in cl.get("hosts", []) or []:
                host_items.append(dmc.AccordionItem(value=f"{dc['name']}|{cl['name']}|{h['name']}", children=[
                    dmc.AccordionControl(_node_control(h["name"], h.get("counts"),
                                                       h.get("os") if with_os else None)),
                    dmc.AccordionPanel(_vm_list(h.get("vms"))),
                ]))
            cluster_items.append(dmc.AccordionItem(value=f"{dc['name']}|{cl['name']}", children=[
                dmc.AccordionControl(_node_control(cl["name"], cl.get("counts"),
                                                   cl.get("os") if with_os else None)),
                dmc.AccordionPanel(dmc.Accordion(chevronPosition="left", variant="separated",
                                                 children=host_items)),
            ]))
        dc_items.append(dmc.AccordionItem(value=dc["name"], children=[
            dmc.AccordionControl(_node_control(dc["name"], dc.get("counts"),
                                               dc.get("os") if with_os else None)),
            dmc.AccordionPanel(dmc.Accordion(chevronPosition="left", variant="separated",
                                             children=cluster_items)),
        ]))
    return dmc.Accordion(chevronPosition="left", variant="separated", children=dc_items)
