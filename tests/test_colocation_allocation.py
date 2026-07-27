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


# --- Fix round 1 -----------------------------------------------------
# Reviewer-confirmed findings on the initial implementation: (1) the tag
# marker regex matched anywhere in the string rather than only as a
# trailing suffix, which could mangle a legitimate name; (2) there was no
# single safe entry point combining resolve + normalise + the UNATTRIBUTED
# fallback, and the obvious hand-written composition
# (normalize_customer_name(resolved or UNATTRIBUTED)) silently upper-cases
# the sentinel, breaking equality with the exported constant.

# 1 (Important): anchor the marker strip to the end of the string.

def test_tag_marker_not_trailing_is_not_split_mid_string():
    """'SABANCI CO LOCATION DX' must NOT become 'SABANCI  DX' (double
    space from splicing the two halves back together) -- the marker here
    is not a suffix, so the tag doesn't qualify and resolution falls
    through to description untouched."""
    resolved = alloc.resolve_rack_customer(
        None, [{"name": "SABANCI CO LOCATION DX"}], "SABANCI DX"
    )
    assert resolved == "SABANCI DX"


def test_tag_marker_as_prefix_does_not_destroy_the_name():
    """'COLOCATION EXPRESS' must NOT become 'EXPRESS' -- the marker is a
    prefix, not a suffix, so the tag doesn't qualify and resolution falls
    through to description untouched."""
    resolved = alloc.resolve_rack_customer(
        None, [{"name": "COLOCATION EXPRESS"}], "EXPRESS HOLDING"
    )
    assert resolved == "EXPRESS HOLDING"


def test_tag_marker_not_trailing_yields_none_when_nothing_else_resolves():
    assert alloc.resolve_rack_customer(None, [{"name": "COLOCATION EXPRESS"}], None) is None
    assert alloc.resolve_rack_customer(None, [{"name": "SABANCI CO LOCATION DX"}], None) is None


def test_tag_marker_still_matches_when_genuinely_trailing():
    # Regression guard: the anchor must not break the real prod shape.
    assert alloc.resolve_rack_customer(
        None, [{"name": "SABANCI DX CO LOCATION"}], None
    ) == "SABANCI DX"


# 2 (Important for Task B): single safe entry point.

def test_resolve_rack_customer_label_normalizes_a_resolved_name():
    assert alloc.resolve_rack_customer_label("Turkonay", None, None) == "TURKONAY"
    assert (
        alloc.resolve_rack_customer_label("Turkonay", None, None)
        == alloc.resolve_rack_customer_label("TURKONAY", None, None)
    )


def test_resolve_rack_customer_label_returns_the_unattributed_constant_untouched():
    result = alloc.resolve_rack_customer_label(None, None, None)
    assert result == alloc.UNATTRIBUTED
    assert result is alloc.UNATTRIBUTED  # not a re-derived/upper-cased copy


def test_resolve_rack_customer_label_via_tag_and_description_sources():
    assert alloc.resolve_rack_customer_label(
        None, [{"name": "SABANCI DX CO LOCATION"}], None
    ) == "SABANCI DX"
    assert alloc.resolve_rack_customer_label(None, None, "AKSIGORTA") == "AKSIGORTA"


# 3 (Minor): tags as a list of non-dict elements.

def test_tags_list_of_non_dict_elements_is_ignored_not_raised():
    resolved = alloc.resolve_rack_customer(None, ["x", 42, None], "GATEWAY HOLDING")
    assert resolved == "GATEWAY HOLDING"


# 4 (Minor): the real-world row shape motivating the bare-CUSTOMER-tag rule.

def test_tenant_name_wins_even_with_a_bare_customer_tag_present():
    """The design doc's cited reason for rejecting a bare 'CUSTOMER' tag:
    a real row can carry tenant_name='AytemizBank' alongside a generic
    'CUSTOMER' tag with no CO LOCATION marker -- tenant_name must still
    win, and the bare tag must never be mistaken for a name."""
    resolved = alloc.resolve_rack_customer("AytemizBank", [{"name": "CUSTOMER"}], None)
    assert resolved == "AytemizBank"


# --- Task B: allocation aggregation ------------------------------------

def _boyner_rows():
    # Boyner: 7 racks, 312 U allocated total, 87 U used total (design doc's
    # worked example -- fixture capacities are illustrative, not a literal
    # per-rack reproduction of prod).
    return [
        {"rack_name": f"B{i}", "role_id": "4", "tags": [], "description": "",
         "tenant_name": "Boyner", "capacity_u": 42, "used_u": 12, "free_u": 30}
        for i in range(6)
    ] + [
        {"rack_name": "B6", "role_id": "4", "tags": [], "description": "",
         "tenant_name": "Boyner", "capacity_u": 60, "used_u": 15, "free_u": 45},
    ]


def test_aggregate_rack_allocations_sums_allocated_and_used_per_customer():
    rows = _boyner_rows()
    out = alloc.aggregate_rack_allocations(rows)
    boyner = next(c for c in out["customers"] if c["customer"] == "BOYNER")
    assert boyner["allocated_u"] == 42 * 6 + 60 == 312
    assert boyner["used_u"] == 12 * 6 + 15 == 87
    assert boyner["rack_count"] == 7
    assert sorted(boyner["racks"]) == [f"B{i}" for i in range(7)]


def test_aggregate_rack_allocations_unattributed_bucket_counted_not_dropped():
    rows = [
        {"rack_name": "R1", "role_id": "3", "tags": [], "description": "",
         "tenant_name": None, "capacity_u": 42, "used_u": 0, "free_u": 42},
        {"rack_name": "R2", "role_id": "4", "tags": None, "description": None,
         "tenant_name": "  ", "capacity_u": 47, "used_u": 0, "free_u": 47},
    ]
    out = alloc.aggregate_rack_allocations(rows)
    names = {c["customer"] for c in out["customers"]}
    assert alloc.UNATTRIBUTED in names
    unattributed = next(c for c in out["customers"] if c["customer"] == alloc.UNATTRIBUTED)
    assert unattributed["allocated_u"] == 89
    assert unattributed["rack_count"] == 2


def test_aggregate_rack_allocations_ignores_non_colocation_roles():
    rows = [
        {"rack_name": "H1", "role_id": "2", "tags": [], "description": "",
         "tenant_name": "Boyner", "capacity_u": 47, "used_u": 10, "free_u": 37},
    ]
    out = alloc.aggregate_rack_allocations(rows)
    assert out["customers"] == []
    assert out["colocation_allocated_u"] == 0


def test_aggregate_rack_allocations_colocation_allocated_u_totals_named_and_unattributed():
    rows = [
        {"rack_name": "R1", "role_id": "4", "tags": [], "description": "",
         "tenant_name": "Boyner", "capacity_u": 42, "used_u": 10, "free_u": 32},
        {"rack_name": "R2", "role_id": "3", "tags": [], "description": "",
         "tenant_name": None, "capacity_u": 42, "used_u": 0, "free_u": 42},
    ]
    out = alloc.aggregate_rack_allocations(rows)
    assert out["colocation_allocated_u"] == 84


def test_aggregate_rack_allocations_sellable_free_u_excludes_colocation_racks():
    """Design section 3: free U inside a colocation-role rack is not sellable
    -- only free_u from NON-colocation racks counts toward sellable_free_u."""
    rows = [
        {"rack_name": "R1", "role_id": "4", "tags": [], "description": "",
         "tenant_name": "Boyner", "capacity_u": 42, "used_u": 10, "free_u": 32},
        {"rack_name": "R2", "role_id": "2", "tags": [], "description": "",
         "tenant_name": None, "capacity_u": 47, "used_u": 20, "free_u": 27},
        {"rack_name": "R3", "role_id": "1", "tags": [], "description": "",
         "tenant_name": None, "capacity_u": 47, "used_u": 0, "free_u": 47},
    ]
    out = alloc.aggregate_rack_allocations(rows)
    assert out["sellable_free_u"] == 27 + 47   # R1's 32 free U excluded
    assert out["colocation_allocated_u"] == 42


def test_aggregate_rack_allocations_empty_rows():
    out = alloc.aggregate_rack_allocations([])
    assert out == {"customers": [], "colocation_allocated_u": 0, "sellable_free_u": 0}


def test_aggregate_rack_allocations_sorted_by_allocated_u_descending():
    rows = [
        {"rack_name": "R1", "role_id": "4", "tags": [], "description": "",
         "tenant_name": "Small Co", "capacity_u": 10, "used_u": 0, "free_u": 10},
        {"rack_name": "R2", "role_id": "4", "tags": [], "description": "",
         "tenant_name": "Big Co", "capacity_u": 90, "used_u": 0, "free_u": 90},
    ]
    out = alloc.aggregate_rack_allocations(rows)
    assert [c["customer"] for c in out["customers"]] == ["BIG CO", "SMALL CO"]
