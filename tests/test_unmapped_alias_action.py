"""The one-click alias action. The save endpoint replaces an account's whole
mapping set, so these pin that the union is sent — not the bare new rule.

The account's existing rules are read with ``get_crm_account_source_mappings``
(one account, uncached), never ``get_crm_aliases`` (project customers only):
``guessed_owner_id`` comes from the full discovery_crm_accounts roster, so for
any account without a PRJ-* sales order the project-scoped list reads back as
"no mappings" and the replace-all PUT then deletes whatever was already there.
"""
from unittest.mock import patch

_PAYLOAD_ROW = {
    "name": "Acme_Kilit-Web01",
    "guessed_owner": "Örnek Kilit A.Ş.",
    "guessed_owner_id": "acc-1",
    "suggested_alias": "Acme_Kilit",
    "suggested_method": "prefix",
    "reason": "alias_gap",
    "kind": "vm",
    "platform": "nutanix",
}

_BACKUP_PAYLOAD_ROW = {
    "name": "abc-dete-s4hana-prd-log",
    "guessed_owner": "ABC Deterjan",
    "guessed_owner_id": "acc-abc",
    "suggested_alias": "abc-dete",
    "suggested_method": "prefix",
    "reason": "alias_gap",
    "kind": "backup",
    "platform": "netbackup",
}

_EXISTING_MAPPINGS = [
    {"data_source": "backup_netbackup", "match_method": "prefix",
     "match_value": "acme-kili", "crm_account_name": "Örnek Kilit A.Ş."},
]

# What /crm/aliases returns for a project customer — used only for the
# "is this visible on the Customer Aliases page" probe.
_PROJECT_ALIAS = {"crm_accountid": "acc-1", "crm_account_name": "Örnek Kilit A.Ş.",
                  "source_mappings": []}


def _apply(row=_PAYLOAD_ROW, *, existing=None, aliases=None, put_return=([], None)):
    """Run apply_alias_suggestion with both reads stubbed. Returns (status, message, put)."""
    from src.pages.unmapped_resources_callbacks import apply_alias_suggestion

    with patch("src.services.api_client.get_crm_account_source_mappings",
               return_value=list(existing or [])), \
         patch("src.services.api_client.get_crm_aliases",
               return_value=list(aliases if aliases is not None else [_PROJECT_ALIAS])), \
         patch("src.services.api_client.put_crm_source_mappings",
               return_value=put_return) as put:
        status, message = apply_alias_suggestion(row)
    return status, message, put


def test_action_sends_the_union_not_just_the_new_rule():
    status, _msg, put = _apply(existing=_EXISTING_MAPPINGS)

    assert status == "saved"
    (account_id,), kwargs = put.call_args
    assert account_id == "acc-1"
    sent = kwargs["mappings"]
    assert len(sent) == 2
    assert {"backup_netbackup", "virtualization"} == {m["data_source"] for m in sent}
    new = [m for m in sent if m["data_source"] == "virtualization"][0]
    assert new["match_method"] == "prefix"
    assert new["match_value"] == "Acme_Kilit"


def test_a_non_project_account_keeps_the_rules_a_previous_click_wrote():
    """The destruction case.

    ``guessed_owner_id`` is derived from the FULL CRM roster (2,668 accounts);
    ``get_crm_aliases()`` returns only the ~354 project customers. Resolving
    `existing` against that list yields [] for the other 4,945 clickable rows,
    and because the PUT REPLACES the account's whole mapping set, the second
    click on such an account used to delete the first click's rule.

    Here /crm/aliases deliberately does NOT contain acc-1, while the account's
    own mappings do carry a rule. That rule must survive the write.
    """
    status, _msg, put = _apply(existing=_EXISTING_MAPPINGS, aliases=[])

    assert status == "saved"
    sent = put.call_args.kwargs["mappings"]
    assert {"acme-kili", "Acme_Kilit"} == {m["match_value"] for m in sent}


def test_a_repeat_click_on_a_non_project_account_writes_nothing():
    """Idempotence for the same 4,945 rows: the 'zaten ekli' path could never
    fire for an account missing from /crm/aliases, so every repeat click
    re-PUT the same rule forever."""
    already = [{"data_source": "virtualization", "match_method": "prefix",
                "match_value": "Acme_Kilit"}]
    status, _msg, put = _apply(existing=already, aliases=[])

    assert status == "exists"
    put.assert_not_called()


def test_the_toast_says_the_rule_is_visible_on_the_aliases_page():
    """The user asked to be able to find the rule again. When the account is a
    project customer the Customer Aliases page can address it, and the toast
    says so by name."""
    status, message, _put = _apply(existing=[], aliases=[_PROJECT_ALIAS])

    assert status == "saved"
    assert "Müşteri Alias" in message
    assert "görünür" in message
    assert "Örnek Kilit A.Ş." in message


def test_the_toast_admits_when_the_rule_will_not_appear_on_the_aliases_page():
    """Writing a mapping never creates a gui_crm_customer_alias row, and
    _build_all_aliases() never iterates orphan source-mappings — so for an
    account with no PRJ-* sales order the rule is saved, active, and
    permanently invisible on that admin page. The write still happens (the row
    has to leave the worklist); the toast must not pretend otherwise."""
    status, message, put = _apply(existing=[], aliases=[])

    assert status == "saved"
    put.assert_called_once()
    assert "görünmez" in message
    assert "CRM proje kaydı" in message


def test_a_failed_addressability_probe_does_not_fail_the_save():
    """The probe is cosmetic. /crm/aliases being down must not turn a committed
    write into a red 'Kaydedilemedi'."""
    from src.pages.unmapped_resources_callbacks import apply_alias_suggestion

    with patch("src.services.api_client.get_crm_account_source_mappings", return_value=[]), \
         patch("src.services.api_client.get_crm_aliases", side_effect=RuntimeError("api down")), \
         patch("src.services.api_client.put_crm_source_mappings", return_value=([], None)) as put:
        status, message = apply_alias_suggestion(_PAYLOAD_ROW)

    assert status == "saved"
    put.assert_called_once()
    assert "Acme_Kilit" in message


def test_a_backup_row_writes_a_backup_netbackup_rule():
    status, _msg, put = _apply(_BACKUP_PAYLOAD_ROW, existing=[], aliases=[])

    assert status == "saved"
    sent = put.call_args.kwargs["mappings"]
    assert [m["data_source"] for m in sent] == ["backup_netbackup"]


def test_repeat_click_writes_nothing():
    already = [{"data_source": "virtualization", "match_method": "prefix",
                "match_value": "Acme_Kilit"}]
    status, _msg, put = _apply(existing=already)

    assert status == "exists"
    put.assert_not_called()


def test_a_row_without_an_account_id_is_refused():
    from src.pages.unmapped_resources_callbacks import apply_alias_suggestion

    with patch("src.services.api_client.put_crm_source_mappings") as put:
        status, _ = apply_alias_suggestion({**_PAYLOAD_ROW, "guessed_owner_id": None})

    assert status == "error"
    put.assert_not_called()


def test_a_cache_warning_still_counts_as_saved():
    """The write has already committed by the time the cache drop is attempted;
    reporting failure would say 'not saved' about a saved mapping."""
    status, message, _put = _apply(existing=_EXISTING_MAPPINGS,
                                   put_return=([], "cache not cleared"))

    assert status == "warning"
    assert "cache not cleared" in message


def test_a_backend_failure_is_reported_not_raised():
    from src.pages.unmapped_resources_callbacks import apply_alias_suggestion

    with patch("src.services.api_client.get_crm_account_source_mappings",
               side_effect=RuntimeError("api down")):
        status, message = apply_alias_suggestion(_PAYLOAD_ROW)

    assert status == "error"
    assert message

