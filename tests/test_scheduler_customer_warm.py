"""The legacy NO-OP customer warm hook must not exist as a live scheduler target.
Customer-view warm is owned by warm_common on the 240s server-side timer
(see app_background_warm.warm_common); the old 15-min scheduler jobs did nothing.
"""
from src.services import scheduler_service


def test_no_noop_customer_warm_hook():
    assert not hasattr(scheduler_service, "warm_warmed_customer_caches"), (
        "delete the NO-OP customer warm hook; customer-view warm is owned by warm_common"
    )
