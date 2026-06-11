"""Regression test: HMDL env-card click must not hijack DC selection on rebuild.

Bug: selecting any DC in the Datalake Sync Health dropdown reverted to AZ11.
Cause: changing the dropdown rebuilds the page, which re-adds the per-DC
``hmdl-env-select`` cards (n_clicks=0). That spuriously fired
``hmdl_env_card_clicked``, which acted on ctx.triggered_id alone (ignoring
n_clicks) and reset url.search to the first card's DC (AZ11).

Fix: only navigate when a real click happened (triggering n_clicks is truthy).
"""

import unittest
from unittest.mock import patch

from dash import no_update

from src.pages.settings.admin_routes import ADMIN_PREFIX
from src.pages.settings.integrations import hmdl_callbacks

_PATH = f"{ADMIN_PREFIX}/integrations/hmdl/sync-health"


class _FakeCtx:
    def __init__(self, triggered_id, triggered):
        self.triggered_id = triggered_id
        self.triggered = triggered


class TestHmdlEnvCardClick(unittest.TestCase):
    def test_real_click_navigates_to_clicked_dc(self):
        fake = _FakeCtx(
            triggered_id={"type": "hmdl-env-select", "dc": "DC15"},
            triggered=[{"prop_id": '{"dc":"DC15","type":"hmdl-env-select"}.n_clicks', "value": 2}],
        )
        with patch.object(hmdl_callbacks, "ctx", fake):
            result = hmdl_callbacks.hmdl_env_card_clicked([0, 2, 0], [], _PATH)
        self.assertEqual(result, ("DC15", _PATH, "?dc=DC15"))

    def test_spurious_rebuild_fire_is_ignored(self):
        # Page rebuild re-adds cards with n_clicks=0 -> must NOT navigate.
        fake = _FakeCtx(
            triggered_id={"type": "hmdl-env-select", "dc": "AZ11"},
            triggered=[{"prop_id": '{"dc":"AZ11","type":"hmdl-env-select"}.n_clicks', "value": 0}],
        )
        with patch.object(hmdl_callbacks, "ctx", fake):
            result = hmdl_callbacks.hmdl_env_card_clicked([0, 0, 0], [], _PATH)
        self.assertEqual(result, (no_update, no_update, no_update))

    def test_none_nclicks_fire_is_ignored(self):
        fake = _FakeCtx(
            triggered_id={"type": "hmdl-env-select", "dc": "AZ11"},
            triggered=[{"prop_id": "...", "value": None}],
        )
        with patch.object(hmdl_callbacks, "ctx", fake):
            result = hmdl_callbacks.hmdl_env_card_clicked([None, None], [], _PATH)
        self.assertEqual(result, (no_update, no_update, no_update))


if __name__ == "__main__":
    unittest.main()
