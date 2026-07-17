"""Regression tests for the two save callbacks that consume
``api.put_crm_source_mappings``.

That function used to return a plain list of mappings; it now returns
``(mappings, cache_warning)`` so the backend can say "saved, but the cache is
still showing the old mapping". Both callbacks were updated to unpack the
tuple, but neither was covered — a silent unpack break here reaches users
directly, as a red "Save failed" alert on a save that actually succeeded.

Follows the callback-testing pattern from test_hmdl_env_card_click.py: import
the callbacks module, patch its module-level ``ctx``, and call the undecorated
function.
"""

import unittest
from unittest.mock import patch

from src.pages.settings.integrations import (
    crm_aliases_callbacks,
    crm_internal_aliases_callbacks,
)
from src.pages.settings.integrations.crm_internal_aliases import (
    INTERNAL_ACCOUNT_ID,
    INTERNAL_ACCOUNT_NAME,
)
from src.utils.crm_source_mapping_ui import build_editor_state

_SAVED_MAPPINGS = [
    {
        "data_source": "virtualization",
        "match_method": "contains",
        "match_value": "acme",
        "enabled": True,
    }
]


class _FakeCtx:
    def __init__(self, states_list=None):
        self.states_list = states_list or []


def _editor_state(account_id, account_name):
    return build_editor_state(
        {
            "crm_accountid": account_id,
            "crm_account_name": account_name,
            "notes": "",
            "source_mappings": _SAVED_MAPPINGS,
        }
    )


def _alert_text(alert) -> str:
    return f"{getattr(alert, 'title', '')} {getattr(alert, 'children', '')}"


class TestInternalSaveCallback(unittest.TestCase):
    """The Internal (Bulutistan) editor — the consumer flagged as unprotected."""

    def _save(self, put_return):
        editor_state = _editor_state(INTERNAL_ACCOUNT_ID, INTERNAL_ACCOUNT_NAME)
        with patch.object(crm_internal_aliases_callbacks, "ctx", _FakeCtx()), patch.object(
            crm_internal_aliases_callbacks.api,
            "put_crm_source_mappings",
            return_value=put_return,
        ) as put:
            result = crm_internal_aliases_callbacks.save_editor_mappings_cb(
                1, [], [], [], [], "", editor_state, None
            )
        return result, put

    def test_unpacks_the_tuple_and_reports_success(self):
        (alert, refreshed_editor, _shell), put = self._save((_SAVED_MAPPINGS, None))

        put.assert_called_once()
        self.assertEqual(put.call_args.args[0], INTERNAL_ACCOUNT_ID)
        # Green, not the red "Save failed" a broken unpack would produce.
        self.assertEqual(alert.color, "green")
        self.assertIn("Saved", _alert_text(alert))
        self.assertEqual(refreshed_editor["crm_accountid"], INTERNAL_ACCOUNT_ID)

    def test_surfaces_the_cache_warning_in_yellow(self):
        warning = "Mapping kaydedildi, ancak cache temizlenemedi — lütfen tekrar kaydedin."
        (alert, _editor, _shell), _put = self._save((_SAVED_MAPPINGS, warning))

        # Saved is still true — the warning must not read as a failure.
        self.assertEqual(alert.color, "yellow")
        self.assertIn(warning, _alert_text(alert))

    def test_a_list_return_would_be_caught(self):
        """Guards the guard: if put_crm_source_mappings ever regressed to
        returning a bare list, this callback must not silently paper over it."""
        (alert, _editor, _shell), _put = self._save(_SAVED_MAPPINGS)

        self.assertEqual(alert.color, "red")


class TestCustomerSaveCallback(unittest.TestCase):
    """The Customer aliases editor. The review called the Internal editor the
    only unprotected consumer of the tuple change; in fact neither callback had
    coverage, so the same test applies here."""

    def _save(self, put_return):
        editor_state = _editor_state("acct-1", "Acme A.Ş.")
        with patch.object(crm_aliases_callbacks, "ctx", _FakeCtx()), patch.object(
            crm_aliases_callbacks.api, "put_crm_source_mappings", return_value=put_return
        ) as put:
            result = crm_aliases_callbacks.save_editor_mappings_cb(
                1, [], [], [], [], "", editor_state, [], "", 0, None
            )
        return result, put

    def test_unpacks_the_tuple_and_reports_success(self):
        result, put = self._save((_SAVED_MAPPINGS, None))

        put.assert_called_once()
        self.assertEqual(put.call_args.args[0], "acct-1")
        self.assertEqual(result[0].color, "green")

    def test_surfaces_the_cache_warning_in_yellow(self):
        warning = "Mapping kaydedildi, ancak cache temizlenemedi — lütfen tekrar kaydedin."
        result, _put = self._save((_SAVED_MAPPINGS, warning))

        self.assertEqual(result[0].color, "yellow")
        self.assertIn(warning, _alert_text(result[0]))


if __name__ == "__main__":
    unittest.main()
