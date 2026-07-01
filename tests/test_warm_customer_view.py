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
    assert m_res.call_count == 2
    assert m_av.call_count == 2
    assert m_it.call_count == 2


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
