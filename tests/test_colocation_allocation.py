"""Rack-to-colocation-customer allocation (phase 2, Task A) — pure functions,
no DB access. Verified against prod bulutlake 2026-07-27:
loki_racks.role_name resolves discovery_loki_rack.role_id as
1=NETWORK RACK, 2=HOST RACK, 3=NON-STANDART RACK, 4=CUSTOMER RACK; roles 3/4
are the colocation estate. The customer name lives in one of three fields
(tenant_name / tags[].name / description) with a first-hit-wins precedence.
See docs/superpowers/specs/2026-07-27-colocation-allocation-model-design.md
sections 1-2 and Testing.
"""
from shared.colocation import allocation as alloc


# --- Role gating -------------------------------------------------------

def test_colocation_role_ids_are_3_and_4_as_strings():
    assert alloc.COLOCATION_ROLE_IDS == {"3", "4"}
    assert all(isinstance(v, str) for v in alloc.COLOCATION_ROLE_IDS)


def test_is_colocation_rack_true_for_non_standart_and_customer_rack():
    assert alloc.is_colocation_rack("3") is True   # NON-STANDART RACK
    assert alloc.is_colocation_rack("4") is True    # CUSTOMER RACK


def test_is_colocation_rack_accepts_int_role_id_too():
    # discovery_loki_rack.role_id is a varchar, but some callers may already
    # have coerced it to int upstream -- compare as string either way.
    assert alloc.is_colocation_rack(3) is True
    assert alloc.is_colocation_rack(4) is True


def test_is_colocation_rack_false_for_network_and_host_rack():
    assert alloc.is_colocation_rack("1") is False   # NETWORK RACK
    assert alloc.is_colocation_rack("2") is False    # HOST RACK
    assert alloc.is_colocation_rack(2) is False


def test_is_colocation_rack_false_for_none_and_garbage():
    assert alloc.is_colocation_rack(None) is False
    assert alloc.is_colocation_rack("") is False
    assert alloc.is_colocation_rack("not-a-role") is False


def test_is_colocation_rack_tolerates_whitespace():
    assert alloc.is_colocation_rack(" 4 ") is True


def test_host_rack_with_tenant_name_is_not_colocation():
    """A HOST RACK (role 2) carrying a tenant_name must NOT be treated as
    colocation -- role gating and name resolution are independent checks."""
    role_id = "2"
    tenant_name = "Boyner"
    assert alloc.resolve_rack_customer(tenant_name, None, None) == "Boyner"
    assert alloc.is_colocation_rack(role_id) is False


# --- Name resolution precedence: tenant_name > tags > description ------

def test_tenant_name_examples_resolve_verbatim_trimmed():
    for name in ("Boyner", "AytemizBank", "Turkonay"):
        assert alloc.resolve_rack_customer(f"  {name}  ", None, None) == name


def test_tenant_name_wins_over_tags_and_description():
    resolved = alloc.resolve_rack_customer(
        "Boyner", [{"name": "SOME OTHER CO LOCATION"}], "AKSIGORTA"
    )
    assert resolved == "Boyner"


def test_tag_wins_when_tenant_name_absent():
    resolved = alloc.resolve_rack_customer(
        None, [{"name": "SABANCI DX CO LOCATION"}], "AKSIGORTA"
    )
    assert resolved == "SABANCI DX"


def test_tag_marker_matches_boyner_co_location():
    resolved = alloc.resolve_rack_customer(None, [{"name": "BOYNER CO LOCATION"}], None)
    assert resolved == "BOYNER"


def test_bare_customer_tag_is_not_treated_as_a_customer_name():
    resolved = alloc.resolve_rack_customer(None, [{"name": "CUSTOMER"}], None)
    assert resolved is None


def test_bare_customer_tag_falls_through_to_a_later_colocation_tag():
    resolved = alloc.resolve_rack_customer(
        None, [{"name": "CUSTOMER"}, {"name": "BOYNER CO LOCATION"}], None
    )
    assert resolved == "BOYNER"


def test_description_wins_when_tenant_and_tag_absent():
    resolved = alloc.resolve_rack_customer(None, None, "  AKSIGORTA  ")
    assert resolved == "AKSIGORTA"


def test_description_examples_resolve_verbatim_trimmed():
    for desc in ("AKSIGORTA", "GATEWAY HOLDING", "VERION", "HRWEB"):
        assert alloc.resolve_rack_customer(None, None, desc) == desc


def test_tags_accepted_as_already_parsed_list():
    resolved = alloc.resolve_rack_customer(None, [{"name": "SABANCI DX CO LOCATION"}], None)
    assert resolved == "SABANCI DX"


def test_tags_accepted_as_json_string():
    resolved = alloc.resolve_rack_customer(
        None, '[{"name": "SABANCI DX CO LOCATION"}]', None
    )
    assert resolved == "SABANCI DX"


def test_malformed_tags_json_falls_through_to_description():
    resolved = alloc.resolve_rack_customer(None, "{not valid json", "VERION")
    assert resolved == "VERION"


def test_tags_json_object_instead_of_list_falls_through():
    # Parses fine as JSON but is not a list -> treated as absent, not raised.
    resolved = alloc.resolve_rack_customer(
        None, '{"name": "SABANCI DX CO LOCATION"}', "GATEWAY HOLDING"
    )
    assert resolved == "GATEWAY HOLDING"


def test_tags_wrong_python_type_falls_through_without_raising():
    resolved = alloc.resolve_rack_customer(None, 12345, "HRWEB")
    assert resolved == "HRWEB"


def test_nothing_resolves_returns_none():
    assert alloc.resolve_rack_customer(None, None, None) is None


def test_all_blank_inputs_resolve_to_none():
    assert alloc.resolve_rack_customer("   ", [], "   ") is None


def test_tag_entries_missing_name_key_are_skipped_not_raised():
    resolved = alloc.resolve_rack_customer(
        None, [{"colour": "red"}, {"name": "AKSIGORTA CO LOCATION"}], None
    )
    assert resolved == "AKSIGORTA"


# --- Normalisation: case-variant collapse ------------------------------

def test_normalize_collapses_case_variants_to_one_customer():
    assert alloc.normalize_customer_name("Turkonay") == alloc.normalize_customer_name("TURKONAY")
    assert alloc.normalize_customer_name("turkonay") == alloc.normalize_customer_name("Turkonay")


def test_normalize_display_form_is_uppercase_trimmed_and_collapsed():
    assert alloc.normalize_customer_name("  Sabanci   DX ") == "SABANCI DX"


def test_normalize_is_deterministic_regardless_of_encounter_order():
    variants = ["Turkonay", "TURKONAY", "turkonay", "TuRkOnAy"]
    assert len({alloc.normalize_customer_name(v) for v in variants}) == 1
    assert alloc.normalize_customer_name(variants[0]) == alloc.normalize_customer_name(variants[-1])


# --- Unattributed bucket -------------------------------------------------

def test_unattributed_is_a_nonempty_string_constant():
    assert isinstance(alloc.UNATTRIBUTED, str)
    assert alloc.UNATTRIBUTED


def test_rack_with_no_resolvable_name_lands_in_unattributed_not_dropped():
    resolved = alloc.resolve_rack_customer(None, None, None)
    customer = alloc.normalize_customer_name(resolved) if resolved else alloc.UNATTRIBUTED
    assert customer == alloc.UNATTRIBUTED


def test_unattributed_is_distinct_from_any_normalized_real_name():
    for name in ("Boyner", "AytemizBank", "Turkonay", "AKSIGORTA", "HRWEB"):
        assert alloc.normalize_customer_name(name) != alloc.UNATTRIBUTED
