"""Item 4.2: the background warm routine pre-populates customer-view data (into
the shared cache) for the warmed customers, so first visits to those customers
hit the cache instead of the slow backend.
"""
from unittest.mock import patch

from src.services import app_background_warm as warm


def test_warm_customer_view_calls_getters_per_customer():
    with patch("src.services.api_client.get_customer_resources") as m_res, \
         patch("src.services.api_client.get_customer_availability_bundle") as m_av, \
         patch("src.services.api_client.get_customer_itsm_summary") as m_it, \
         patch("src.services.api_client.get_customer_sales_summary") as m_sa, \
         patch("src.services.api_client.get_customer_efficiency_by_category") as m_ef, \
         patch("src.services.api_client.get_customer_s3_vaults") as m_s3:
        n = warm._warm_customer_view(["Acme", "Globex"], {"preset": "7d"})
    assert n == 2
    # 2 customers x 2 anchor variants (anchor + non-anchor) = 4 tr-scoped calls each.
    assert m_res.call_count == 4
    assert m_av.call_count == 4
    assert m_it.call_count == 4


def test_warm_customer_view_survives_one_failing_customer():
    def boom(*a, **k):
        raise RuntimeError("backend down")

    with patch("src.services.api_client.get_customer_resources", side_effect=boom), \
         patch("src.services.api_client.get_customer_availability_bundle"), \
         patch("src.services.api_client.get_customer_itsm_summary"), \
         patch("src.services.api_client.get_customer_sales_summary"), \
         patch("src.services.api_client.get_customer_efficiency_by_category"), \
         patch("src.services.api_client.get_customer_s3_vaults"):
        n = warm._warm_customer_view(["Acme"], {"preset": "7d"})
    assert n == 0  # failed customer counted as not warmed, no crash


def test_warm_customer_view_runs_under_warm_mode():
    # The genuinely-slow cold customer queries must run with the long warm timeout,
    # or they time out during warm and are never cached (warm == cold).
    from src.services import api_client
    seen = []

    def rec(*a, **k):
        seen.append(api_client._WARM_MODE.get())
        return {}

    with patch("src.services.api_client.get_customer_resources", side_effect=rec), \
         patch("src.services.api_client.get_customer_availability_bundle", side_effect=rec), \
         patch("src.services.api_client.get_customer_itsm_summary", side_effect=rec), \
         patch("src.services.api_client.get_customer_sales_summary", side_effect=rec), \
         patch("src.services.api_client.get_customer_efficiency_by_category", side_effect=rec), \
         patch("src.services.api_client.get_customer_s3_vaults", side_effect=rec):
        warm._warm_customer_view(["Acme"], {"preset": "7d"})
    assert seen and all(seen), "every customer getter must run inside warm_mode (long timeout)"


def test_warm_customer_view_warms_both_anchor_variants():
    # The page fetches with anchor_latest (a browser-local toggle) but the old warm
    # only cached the non-anchor key, so those users always missed the warm.
    anchors = []

    def rec_res(name, tr):
        anchors.append(bool((tr or {}).get("anchor_latest")))
        return {}

    with patch("src.services.api_client.get_customer_resources", side_effect=rec_res), \
         patch("src.services.api_client.get_customer_availability_bundle", return_value={}), \
         patch("src.services.api_client.get_customer_itsm_summary", return_value={}), \
         patch("src.services.api_client.get_customer_sales_summary", return_value={}), \
         patch("src.services.api_client.get_customer_efficiency_by_category", return_value=[]), \
         patch("src.services.api_client.get_customer_s3_vaults", return_value={}):
        warm._warm_customer_view(["Acme"], {"preset": "7d", "start": "a", "end": "b"})
    assert set(anchors) == {True, False}, "resources must be warmed for both anchor and non-anchor keys"
