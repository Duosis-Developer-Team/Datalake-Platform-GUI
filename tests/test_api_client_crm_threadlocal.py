"""P2b: CRM httpx client must be thread-local (one client per thread)."""
import threading
from src.services import api_client as api


def test_get_client_crm_is_thread_local():
    assert hasattr(api, "_get_client_crm"), "expected a _get_client_crm() accessor"
    main_client = api._get_client_crm()
    assert main_client is api._get_client_crm()  # stable within a thread

    other = {}
    def worker():
        other["client"] = api._get_client_crm()
    t = threading.Thread(target=worker)
    t.start(); t.join()
    assert other["client"] is not main_client  # different thread -> different client
