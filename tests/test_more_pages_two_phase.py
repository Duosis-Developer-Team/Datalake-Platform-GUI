"""Two-phase skeleton shells for customers-list, customer-view, crm-sellable-potential —
each renders instantly and fills content off the render path (no blank page on a cold backend).
"""
from unittest.mock import patch

import dash
from dash import no_update
from src.pages import customers_list as cl
from src.pages import customer_view as cv
from src.pages import crm_sellable_potential as crm


def test_customers_list_shell_and_fill():
    with patch.object(cl, "build_customers_list") as bd:
        shell = cl.build_customers_list_shell(["p"])
    bd.assert_not_called()
    assert "customers-list-page-root" in repr(shell)
    assert cl._fill_customers_list_content("/global-view", {"preset": "7d"}, None) is no_update
    with patch.object(cl, "build_customers_list", return_value="X") as bd:
        assert cl._fill_customers_list_content("/customers", {"preset": "7d"}, ["p"]) == "X"
    bd.assert_called_once()


def test_customer_view_shell_and_fill_reads_customer_param():
    with patch.object(cv, "build_customer_layout") as bd:
        shell = cv.build_customer_layout_shell(["p"])
    bd.assert_not_called()
    assert "customer-view-page-root" in repr(shell)
    assert cv._fill_customer_view_content("/customers", "?customer=ACME", {}, None) is dash.no_update
    with patch.object(cv, "build_customer_layout", return_value="X") as bd:
        out = cv._fill_customer_view_content("/customer-view", "?customer=ACME", {"preset": "7d"}, ["p"])
    assert out == "X"
    # the chosen customer parsed from ?customer= is passed through
    assert bd.call_args.args[1] == "ACME"


def test_crm_sellable_shell_and_fill():
    with patch.object(crm, "build_layout") as bd:
        shell = crm.build_layout_shell(["p"])
    bd.assert_not_called()
    assert "crm-sellable-page-root" in repr(shell)
    assert crm._fill_crm_sellable_content("/customers", {"preset": "7d"}, None) is dash.no_update
    with patch.object(crm, "build_layout", return_value="X") as bd:
        assert crm._fill_crm_sellable_content("/crm/sellable-potential", {"preset": "7d"}, ["p"]) == "X"
    bd.assert_called_once()
