"""The one-click alias action. The save endpoint replaces an account's whole
mapping set, so these pin that the union is sent — not the bare new rule.
"""
from unittest.mock import patch

_ROW = {
    "row_key": "vm::Acme_Kilit-Web01",
    "guessed_owner": "Örnek Kilit A.Ş.",
    "name": "Acme_Kilit-Web01",
    "reason": "Alias eksik",
    "action": "Alias ekle",
}

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

_EXISTING_ALIAS = {
    "crm_accountid": "acc-1",
    "crm_account_name": "Örnek Kilit A.Ş.",
    "source_mappings": [
        {"data_source": "backup_netbackup", "match_method": "prefix", "match_value": "acme-kili"},
    ],
}


def test_action_sends_the_union_not_just_the_new_rule():
    from src.pages.unmapped_resources_callbacks import apply_alias_suggestion

    with patch("src.services.api_client.get_crm_aliases", return_value=[_EXISTING_ALIAS]), \
         patch("src.services.api_client.put_crm_source_mappings",
               return_value=([], None)) as put:
        status, _ = apply_alias_suggestion(_PAYLOAD_ROW)

    assert status == "saved"
    (account_id,), kwargs = put.call_args
    assert account_id == "acc-1"
    sent = kwargs["mappings"]
    assert len(sent) == 2
    assert {"backup_netbackup", "virtualization"} == {m["data_source"] for m in sent}
    new = [m for m in sent if m["data_source"] == "virtualization"][0]
    assert new["match_method"] == "prefix"
    assert new["match_value"] == "Acme_Kilit"


def test_repeat_click_writes_nothing():
    from src.pages.unmapped_resources_callbacks import apply_alias_suggestion

    already = {
        **_EXISTING_ALIAS,
        "source_mappings": [
            {"data_source": "virtualization", "match_method": "prefix", "match_value": "Acme_Kilit"},
        ],
    }
    with patch("src.services.api_client.get_crm_aliases", return_value=[already]), \
         patch("src.services.api_client.put_crm_source_mappings") as put:
        status, _ = apply_alias_suggestion(_PAYLOAD_ROW)

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
    from src.pages.unmapped_resources_callbacks import apply_alias_suggestion

    with patch("src.services.api_client.get_crm_aliases", return_value=[_EXISTING_ALIAS]), \
         patch("src.services.api_client.put_crm_source_mappings",
               return_value=([], "cache not cleared")):
        status, message = apply_alias_suggestion(_PAYLOAD_ROW)

    assert status == "warning"
    assert "cache not cleared" in message


def test_a_backend_failure_is_reported_not_raised():
    from src.pages.unmapped_resources_callbacks import apply_alias_suggestion

    with patch("src.services.api_client.get_crm_aliases", side_effect=RuntimeError("api down")):
        status, message = apply_alias_suggestion(_PAYLOAD_ROW)

    assert status == "error"
    assert message
