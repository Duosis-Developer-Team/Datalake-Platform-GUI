"""Canonical colocation occupancy module — the single source of truth for
used/free rack-U. Verified against prod (over_capacity=0) on 2026-07-23."""
from shared.colocation import occupancy as occ
from shared.colocation.allocation import is_colocation_rack, resolve_rack_customer_label


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.executed = None

    def execute(self, sql, params=None):
        self.executed = (sql, params)

    def fetchall(self):
        return self._rows


def test_sql_uses_current_tables_only():
    sql = occ.OCCUPANCY_SQL.lower()
    assert "discovery_netbox_inventory_device" in sql
    assert "loki_device_types" in sql
    assert "discovery_loki_rack" in sql
    assert "discovery_loki_location" in sql
    # The stale / nonexistent tables must never appear.
    assert "loki_devices" not in sql
    assert "discovery_loki_racks" not in sql
    assert "discovery_netbox_inventory_device_type" not in sql


def test_sql_scopes_by_name_and_site_and_front_face():
    sql = occ.OCCUPANCY_SQL.lower()
    assert "s.rack_name = r.rack_name" in sql
    assert "coalesce(s.site_name, '') = coalesce(r.site_name, '')" in sql
    assert "in ('front', '')" in sql
    assert "coalesce(l.parent_name, l.name)" in sql  # DC label


def test_sql_selects_role_id_tags_description_tenant_name():
    sql = occ.OCCUPANCY_SQL.lower()
    assert "r.role_id" in sql
    assert "r.tags" in sql
    assert "r.description" in sql
    assert "r.tenant_name" in sql


def test_sql_tenants_filter_is_u_range_bounded():
    """The tenants ARRAY_AGG must only count devices within the rack's own U
    range, so a device positioned outside the rack height (which already
    contributes 0 to used_u) cannot list a phantom tenant."""
    sql = occ.OCCUPANCY_SQL.lower()
    assert "array_agg(distinct s.tenant_name)" in sql
    # The bare U-range guard appears 3x total: used_u's COUNT FILTER, free_u's
    # COUNT FILTER, and (new) the tenants ARRAY_AGG FILTER.
    assert sql.count("s.u between 1 and r.capacity_u") >= 3
    # And specifically: within the tenants FILTER clause (after the
    # ARRAY_AGG), the U-range guard is AND-ed onto the existing tenant-name
    # conditions rather than replacing them.
    tenants_clause = sql.split("array_agg(distinct s.tenant_name)", 1)[1]
    assert "tenant_name is not null" in tenants_clause
    assert "and s.u between 1 and r.capacity_u" in tenants_clause


def test_row_to_dict_maps_and_coerces():
    row = ("R1", "116", "DC13", "DH1", 47, 35, 12, ["Boyner", "Bulutistan - Linux TEAM"], "ISTANBUL")
    d = occ.row_to_dict(row)
    assert d == {
        "rack_id": "R1", "rack_name": "116", "dc": "DC13", "hall": "DH1",
        "capacity_u": 47, "used_u": 35, "free_u": 12,
        "tenants": ["Boyner", "Bulutistan - Linux TEAM"], "site_name": "ISTANBUL",
        # Phase 2 Task B fields: absent from this (pre-Task-B-shaped) row
        # tuple, so row_to_dict's length guard defaults them to None rather
        # than raising -- old callers passing 9-element rows keep working.
        "role_id": None, "tags": None, "description": None, "tenant_name": None,
    }


def test_row_to_dict_handles_nulls():
    d = occ.row_to_dict(("R2", "117", "DC13", None, 47, None, None, None, None))
    assert d["used_u"] == 0 and d["free_u"] == 0 and d["tenants"] == []
    assert d["site_name"] is None


def test_row_to_dict_carries_role_id_tags_description_tenant_name():
    """Phase 2 Task B: each rack row also carries role_id/tags/description/
    tenant_name straight from discovery_loki_rack, appended after the
    phase-1 columns so existing positional assumptions hold."""
    row = (
        "R3", "119", "DC13", "DH4", 47, 0, 47, [], "ISTANBUL",
        "4", [{"name": "SABANCI DX CO LOCATION"}], "some description", "Boyner",
    )
    d = occ.row_to_dict(row)
    assert d["role_id"] == "4"
    assert d["tags"] == [{"name": "SABANCI DX CO LOCATION"}]
    assert d["description"] == "some description"
    assert d["tenant_name"] == "Boyner"


def test_occupancy_rows_executes_with_dc_pattern():
    cur = _FakeCursor([("R1", "116", "DC13", "DH1", 47, 35, 12, ["Boyner"])])
    rows = occ.occupancy_rows(cur, dc_pattern="%DC13%")
    assert cur.executed[1] == {"dc_pattern": "%DC13%"}
    assert rows[0]["rack_name"] == "116" and rows[0]["free_u"] == 12


def test_occupancy_rows_dedupes_duplicate_physical_racks():
    """discovery_loki_rack has multiple rows for one physical rack (234 rows /
    188 unique name+site). The device->rack join is by (rack_name, site_name)
    only, so each duplicate re-counts the SAME devices (used_u=36 three times).
    occupancy_rows must collapse them to ONE physical rack so used/free U are
    not inflated; a same-name rack at a *different* site stays separate."""
    cur = _FakeCursor([
        # same physical rack "102"/ISTANBUL, 3 duplicate rows (differing dc + cap)
        ("id-a", "102", "DH3", "hallA", 52, 36, 16, ["Boyner"], "ISTANBUL"),
        ("id-b", "102", "DC13", "hallB", 47, 36, 11, ["Boyner"], "ISTANBUL"),
        ("id-c", "102", "DC13", "hallC", 47, 36, 11, ["Boyner"], "ISTANBUL"),
        # genuinely different rack: same name, different site -> kept separate
        ("id-d", "102", "AZ11", "hallD", 48, 16, 32, ["A101"], "ANKARA"),
    ])
    rows = occ.occupancy_rows(cur, dc_pattern=None)
    assert len(rows) == 2  # ISTANBUL/102 collapsed, ANKARA/102 kept
    ist = next(r for r in rows if (r.get("site_name") or "") == "ISTANBUL")
    assert ist["used_u"] == 36            # NOT 108 (3x)
    assert ist["capacity_u"] == 52        # max capacity among duplicates
    assert ist["free_u"] == 16            # 52 - 36
    assert ist["dc"] == "DC13"            # most-common dc among duplicates
    # the aggregate must reflect real physical capacity, not the fan-out
    agg = occ.aggregate_by_dc(rows)
    assert sum(a["used_u"] for a in agg.values()) == 36 + 16
    assert sum(a["total_u"] for a in agg.values()) == 52 + 48


def test_occupancy_rows_dedupe_unions_tenants_across_duplicates():
    cur = _FakeCursor([
        ("id-a", "9", "DC13", "h", 47, 20, 27, ["Boyner"], "IST"),
        ("id-b", "9", "DC13", "h", 47, 20, 27, ["AytemizBank"], "IST"),
    ])
    rows = occ.occupancy_rows(cur, dc_pattern=None)
    assert len(rows) == 1
    assert sorted(rows[0]["tenants"]) == ["AytemizBank", "Boyner"]


# --- Phase 2 Task B: colocation identity among duplicate-rack conflicts ----
# Verified against prod bulutlake 2026-07-27: a physical rack can have
# multiple discovery_loki_rack rows (same rack_name+site_name) that disagree
# on role_id/tags/description/tenant_name.
#
# capacity_u/used_u/free_u/tenants/dc are NEVER affected by any of this --
# they keep the exact phase-1 max/union/vote merge regardless of colocation
# role (fix round 2: an earlier version let a colocation-role duplicate's OWN
# capacity/used_u override the max-merge, which was both unnecessary --
# sellable_free_u/potential_tl come out identical either way, since a
# colocation-role rack's free_u never enters the sellable pool regardless of
# its capacity value -- and NON-commutative: swapping which duplicate row was
# fed to the merge first changed the result, because the swap only fired
# when the incoming row was colocation-role AND won its own earlier-observed
# tie-break, so a losing-but-still-colocation duplicate fell through to the
# max-merge branch by accident. Reverted; see _resolve_colocation_identity).
#
# Only role_id/tags/description/tenant_name are resolved from the subset of
# duplicates that are colocation-role (3/4):
#   * exactly one such duplicate -> unambiguous, use it;
#   * two or more agreeing on the resolved customer -> use it;
#   * two or more DISAGREEING on the resolved customer -> UNATTRIBUTED
#     (never guessed at from an arbitrary/paginated ordering signal), logged.

def _row(rack_id, rack_name, dc, hall, capacity_u, used_u, free_u, tenants, site_name,
         role_id, tags, description, tenant_name):
    return (rack_id, rack_name, dc, hall, capacity_u, used_u, free_u, tenants, site_name,
            role_id, tags, description, tenant_name)


def test_dedupe_single_colocation_duplicate_identity_is_unambiguous():
    """Rack '303'/ISTANBUL: a 52U HOST-role (role 2) duplicate and a 42U
    SABANCI DX NON-STANDART-role (role 3) duplicate -- only ONE is
    colocation-role, so its identity applies unambiguously. Capacity/used_u
    are still the plain MAX across BOTH duplicates (52, not 42) -- identity
    resolution and capacity/used merge are independent."""
    cur = _FakeCursor([
        _row("host-303", "303", "DH3", "DH3-Hall", 52, 10, 42, [], "ISTANBUL",
             "2", [], "", None),
        _row("sabanci-303", "303", "DC13", "DH7", 42, 15, 27, [], "ISTANBUL",
             "3", [{"name": "SABANCI DX CO LOCATION"}], "Sabancı DX  Non Standart Rack Area",
             None),
    ])
    rows = occ.occupancy_rows(cur, dc_pattern=None)
    assert len(rows) == 1
    row = rows[0]
    assert row["role_id"] == "3"
    assert row["description"] == "Sabancı DX  Non Standart Rack Area"
    assert row["capacity_u"] == 52          # MAX(52, 42), unchanged phase-1 rule
    assert row["used_u"] == 15               # MAX(10, 15)
    assert row["free_u"] == 37               # 52 - 15, recomputed from the merged pair


def test_dedupe_single_colocation_duplicate_identity_is_order_stable():
    non_colo = _row("host-303", "303", "DH3", "DH3-Hall", 52, 10, 42, [], "ISTANBUL",
                     "2", [], "", None)
    colo = _row("sabanci-303", "303", "DC13", "DH7", 42, 15, 27, [], "ISTANBUL",
                "3", [{"name": "SABANCI DX CO LOCATION"}], "Sabancı DX  Non Standart Rack Area",
                None)

    forward = occ.occupancy_rows(_FakeCursor([non_colo, colo]), dc_pattern=None)[0]
    backward = occ.occupancy_rows(_FakeCursor([colo, non_colo]), dc_pattern=None)[0]

    # rack_id/hall are the pre-existing, documented "first row encountered"
    # fields (order-dependent, never part of any total-U guarantee -- see
    # the DC13 dedup regression tests below). Everything that feeds identity
    # or a total-U figure must still be order-independent.
    for row in (forward, backward):
        assert row["role_id"] == "3"
        assert row["description"] == "Sabancı DX  Non Standart Rack Area"
        assert row["capacity_u"] == 52
        assert row["used_u"] == 15


def test_dedupe_two_colocation_duplicates_disagreeing_on_customer_is_unattributed():
    """Rack '306'/ISTANBUL: a 52U CUSTOMER-role (role 4) TURKONAY duplicate
    and a 42U NON-STANDART-role (role 3) SABANCI DX duplicate -- BOTH
    colocation-role, but they name DIFFERENT customers. There is no data
    signal that makes one authoritative over the other (verified against
    prod: this is a real, not hypothetical, conflict) -- resolve to
    Unattributed rather than picking either name. Capacity/used_u are still
    plain MAX regardless (52), unaffected by the identity conflict.

    Mutation guard: role_id 4 > 3 and capacity 52 > 42 both point at
    TURKONAY here, so a "higher role_id wins" or "larger capacity wins"
    mutant would ALSO produce TURKONAY -- indistinguishable from this test
    alone. See test_dedupe_conflict_not_decided_by_role_id_or_capacity_magnitude
    below, which swaps those signals against each other.
    """
    turkonay = _row("turkonay-306", "306", "DH3", "DH3 - FINANCE CAGE", 52, 0, 52, [], "ISTANBUL",
                     "4", [], "TURKONAY", None)
    sabanci = _row("sabanci-306", "306", "DC13", "DH7", 42, 0, 42, [], "ISTANBUL",
                   "3", [{"name": "SABANCI DX CO LOCATION"}], "Sabancı DX  Non Standart Rack Area",
                   None)

    forward = occ.occupancy_rows(_FakeCursor([turkonay, sabanci]), dc_pattern=None)[0]
    backward = occ.occupancy_rows(_FakeCursor([sabanci, turkonay]), dc_pattern=None)[0]

    for row in (forward, backward):
        assert row["tenant_name"] is None
        assert row["tags"] == []
        assert row["description"] == ""
        # role_id still names A colocation role (still counted as
        # colocation-estate capacity) -- just not attributed to a customer.
        assert is_colocation_rack(row["role_id"])
        assert resolve_rack_customer_label(
            row["tenant_name"], row["tags"], row["description"]
        ) == "Unattributed"
        assert row["capacity_u"] == 52   # MAX(52, 42), same rule regardless of the conflict


def test_dedupe_conflict_not_decided_by_role_id_or_capacity_magnitude():
    """Same shape of conflict as rack 306, but with role_id and capacity
    magnitude pointing at the OPPOSITE candidate from the resolved name, so a
    "higher role_id wins" or "larger capacity wins" mutant would pick the
    WRONG name where this test's -- and the real rule's -- answer is
    Unattributed regardless. (Mirrors rack '112'/ISTANBUL in prod: two
    role-4 duplicates disagreeing on customer, so role_id can't discriminate
    at all there either.)"""
    small_role_big_cap = _row(
        "a", "X1", "DC13", "H1", 90, 0, 90, [], "ISTANBUL",
        "3", [], "BIGCAP SMALLROLE", None,
    )
    big_role_small_cap = _row(
        "b", "X1", "DC13", "H2", 10, 0, 10, [], "ISTANBUL",
        "4", [], "SMALLCAP BIGROLE", None,
    )
    forward = occ.occupancy_rows(_FakeCursor([small_role_big_cap, big_role_small_cap]),
                                  dc_pattern=None)[0]
    backward = occ.occupancy_rows(_FakeCursor([big_role_small_cap, small_role_big_cap]),
                                   dc_pattern=None)[0]
    for row in (forward, backward):
        assert row["tenant_name"] is None
        assert row["description"] == ""
        assert row["capacity_u"] == 90   # still plain MAX, independent of which "wins" identity


def test_dedupe_non_colocation_role_conflict_resolves_to_network_deterministically():
    """A rack whose duplicates disagree between NETWORK (1) and HOST (2) has
    no colocation-role row, so _resolve_colocation_identity never runs and
    role_id used to fall out of ``base = dict(group[0])`` -- i.e. whichever
    duplicate the DB happened to paginate first. Measured 2026-08-04: 24
    racks carry conflicting role_id and 5 of them (101/102/103/108/201,
    107 U) flipped between consecutive runs.

    That was harmless while role_id only gated colocation identity. Once
    NETWORK is non-sellable the same coin-flip moves money, so the tie is
    resolved by rule: the most restrictive role any duplicate claims wins.
    Rationale -- there is no authority signal in the data (first_observed is
    the same sub-second sweep), and the failure we are correcting is
    OVERstating sellable capacity, so ties break toward not selling."""
    network = _row("net-101", "101", "DC13", "H1", 47, 30, 17, [], "ISTANBUL",
                   "1", [], "", None)
    host = _row("host-101", "101", "DC13", "H2", 47, 30, 17, [], "ISTANBUL",
                "2", [], "", None)

    forward = occ.occupancy_rows(_FakeCursor([network, host]), dc_pattern=None)[0]
    backward = occ.occupancy_rows(_FakeCursor([host, network]), dc_pattern=None)[0]

    assert forward["role_id"] == "1"
    assert backward["role_id"] == "1"
    assert forward["capacity_u"] == backward["capacity_u"] == 47


def test_dedupe_unanimous_non_colocation_role_is_preserved():
    """No conflict, no rule: two HOST duplicates stay HOST."""
    a = _row("a", "H9", "DC13", "H1", 47, 20, 27, [], "ISTANBUL", "2", [], "", None)
    b = _row("b", "H9", "DC13", "H2", 42, 10, 32, [], "ISTANBUL", "2", [], "", None)
    row = occ.occupancy_rows(_FakeCursor([a, b]), dc_pattern=None)[0]
    assert row["role_id"] == "2"
    assert row["capacity_u"] == 47


def test_dedupe_colocation_role_still_beats_network_in_a_three_way_conflict():
    """Precedence order is 4 > 3 > 1 > 2. A group holding NETWORK and
    CUSTOMER duplicates must stay CUSTOMER, because the colocation branch
    also carries the customer's identity -- demoting it to NETWORK would
    keep the U out of the sellable pool (same money) but lose the customer
    attribution (different screen)."""
    network = _row("net-306", "306", "DC13", "H1", 47, 0, 47, [], "ISTANBUL",
                   "1", [], "", None)
    customer = _row("cust-306", "306", "DC13", "H2", 47, 0, 47, [], "ISTANBUL",
                    "4", [], "BOYNER", None)
    forward = occ.occupancy_rows(_FakeCursor([network, customer]), dc_pattern=None)[0]
    backward = occ.occupancy_rows(_FakeCursor([customer, network]), dc_pattern=None)[0]
    for row in (forward, backward):
        assert row["role_id"] == "4"
        assert resolve_rack_customer_label(
            row["tenant_name"], row["tags"], row["description"]
        ) == "BOYNER"


def test_dedupe_non_colocation_role_conflict_is_logged(caplog):
    network = _row("net-101", "101", "DC13", "H1", 47, 30, 17, [], "ISTANBUL",
                   "1", [], "", None)
    host = _row("host-101", "101", "DC13", "H2", 47, 30, 17, [], "ISTANBUL",
                "2", [], "", None)
    with caplog.at_level("WARNING"):
        occ.occupancy_rows(_FakeCursor([network, host]), dc_pattern=None)
    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == 1
    assert "101" in messages[0] and "ISTANBUL" in messages[0]


def test_dedupe_two_colocation_duplicates_agreeing_on_customer_uses_it():
    """Two colocation-role duplicates that happen to resolve to the SAME
    customer (e.g. differing only in capacity/hall) are not a conflict --
    use that customer, and capacity is still the plain MAX."""
    a = _row("a", "Y1", "DC13", "H1", 42, 0, 42, [], "ISTANBUL",
             "4", [], "BOYNER", None)
    b = _row("b", "Y1", "DC13", "H2", 47, 0, 47, [], "ISTANBUL",
             "3", [{"name": "BOYNER CO LOCATION"}], "", None)
    rows = occ.occupancy_rows(_FakeCursor([a, b]), dc_pattern=None)
    assert len(rows) == 1
    row = rows[0]
    assert resolve_rack_customer_label(
        row["tenant_name"], row["tags"], row["description"]
    ) == "BOYNER"
    assert row["capacity_u"] == 47   # MAX(42, 47)


def test_dedupe_conflict_is_logged_with_rack_name_and_competing_values(caplog):
    turkonay = _row("turkonay-306", "306", "DH3", "DH3 - FINANCE CAGE", 52, 0, 52, [], "ISTANBUL",
                     "4", [], "TURKONAY", None)
    sabanci = _row("sabanci-306", "306", "DC13", "DH7", 42, 0, 42, [], "ISTANBUL",
                   "3", [{"name": "SABANCI DX CO LOCATION"}], "Sabancı DX  Non Standart Rack Area",
                   None)
    with caplog.at_level("WARNING"):
        occ.occupancy_rows(_FakeCursor([turkonay, sabanci]), dc_pattern=None)
    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == 1
    msg = messages[0]
    assert "306" in msg and "ISTANBUL" in msg
    assert "TURKONAY" in msg
    assert "SABANCI DX" in msg or "Sabancı DX" in msg


def test_dedupe_non_colocation_duplicates_unaffected_by_identity_logic():
    """Neither duplicate is colocation-role: capacity/used still MAX-merge
    exactly as before Task B (no behaviour change for the ~96% of racks with
    no colocation role at all)."""
    cur = _FakeCursor([
        ("a", "101", "DC13", "DH1", 47, 30, 17, ["Boyner"], "ISTANBUL",
         "1", [], "", None),
        ("b", "101", "DH3", "DH3-Hall", 42, 20, 22, ["AytemizBank"], "ISTANBUL",
         "2", [], "", None),
    ])
    rows = occ.occupancy_rows(cur, dc_pattern=None)
    assert len(rows) == 1
    assert rows[0]["capacity_u"] == 47   # MAX(47, 42), unchanged rule
    assert rows[0]["used_u"] == 30


# --- Regression guard: DC13 "2,629 vs 2,719 total U" ambiguity -------------
# Root cause (verified against prod 2026-07-27, NOT a stale build / u_height
# patch): 25 physical racks at site ISTANBUL are registered in NetBox under
# TWO conflicting dc labels at once (DC13+DH3 or DC13+DH4) with DIFFERENT
# capacity_u per label -- racks 101-105 and 201-205 carry both 47 and 52;
# racks 303-306 carry both 42 and 52. _dedupe_physical_racks collapses these
# to one row per (rack_name, site_name), so which capacity "wins" depends on
# which of the conflicting rows made it into the query's row set. These
# tests pin the CURRENT merge rule so a change to the tie-break silently
# changing reported totals gets caught.

def test_dedupe_conflicting_capacity_and_dc_pins_current_tiebreak():
    """Illustrative fixture for rack 101/ISTANBUL's DC13/DH3 double-labelling
    (NOT a literal reproduction of production data -- the real conflicting
    pair for 101-105/201-205 is 47 vs 52, and 42 only co-occurs with 52 for
    the separate 303-306 pairing; here the first row is 47 and the SECOND
    is deliberately made SMALLER (42), a combination that doesn't occur on
    a single rack in prod, so this test can discriminate the tie-break rule
    by itself).

    With the second row's capacity/used_u both SMALLER than the first,
    "last row wins" would report 42/lower-used, while MAX reports 47/the
    larger used -- so this pins MAX specifically, not just "not first
    wins". Combined with the order-swap test below (which shows the result
    is identical either way, ruling out "first wins" and "last wins" both
    being silently order-dependent), the pair together pin: capacity_u/
    used_u = MAX across the conflicting rows (never summed, never simply
    the first or last row's value); free_u is recomputed from that merged
    pair; dc = the most-frequently-voted label, tie broken to the
    alphabetically smallest (DC13 < DH3).
    """
    cur = _FakeCursor([
        ("netbox-a", "101", "DC13", "DH1", 47, 30, 17, ["Boyner"], "ISTANBUL"),
        ("netbox-b", "101", "DH3", "DH3-Hall", 42, 20, 22, ["AytemizBank"], "ISTANBUL"),
    ])
    rows = occ.occupancy_rows(cur, dc_pattern=None)
    assert len(rows) == 1
    row = rows[0]
    assert row["capacity_u"] == 47         # MAX(47, 42) -- last-wins would give 42
    assert row["used_u"] == 30             # MAX(30, 20) -- last-wins would give 20
    assert row["free_u"] == 17             # 47 - 30, recomputed from the merge
    assert row["dc"] == "DC13"             # 1 vote each -> tie -> alphabetically smallest
    assert sorted(row["tenants"]) == ["AytemizBank", "Boyner"]


def test_dedupe_conflicting_capacity_and_dc_is_order_stable():
    """Same ambiguous pair (rack 101/ISTANBUL, DC13/47 vs DH3/52), fed in the
    opposite order. Every field that feeds a total-U figure -- capacity_u,
    used_u, free_u, dc, and the tenant set -- must come out identical
    regardless of input order, because the merge uses commutative max() /
    vote-counting rather than "first row wins". Verified empirically: it IS
    order-stable for these fields.

    NOTE (not asserted here, reported separately -- see task report):
    rack_id and hall are NOT part of this guarantee. They are copied
    verbatim from whichever row is encountered first and are never
    recomputed, so the *identity* of the "surviving" row is order-dependent
    (confirmed by direct experiment: forward run keeps "netbox-a", the
    reversed run keeps "netbox-b"). This never affects any total-U figure
    (aggregate_by_dc only reads capacity_u/used_u/free_u/dc), so it is out
    of scope for this capacity-ambiguity guard, but it is a real
    order-dependency in the function and is flagged rather than pinned as
    if it were intended behaviour.
    """
    row_dc13 = ("netbox-a", "101", "DC13", "DH1", 47, 30, 17, ["Boyner"], "ISTANBUL")
    row_dh3 = ("netbox-b", "101", "DH3", "DH3-Hall", 52, 30, 22, ["AytemizBank"], "ISTANBUL")

    forward = occ.occupancy_rows(_FakeCursor([row_dc13, row_dh3]), dc_pattern=None)[0]
    backward = occ.occupancy_rows(_FakeCursor([row_dh3, row_dc13]), dc_pattern=None)[0]

    assert forward["capacity_u"] == backward["capacity_u"] == 52
    assert forward["used_u"] == backward["used_u"] == 30
    assert forward["free_u"] == backward["free_u"] == 22
    assert forward["dc"] == backward["dc"] == "DC13"
    assert sorted(forward["tenants"]) == sorted(backward["tenants"])


def test_filtered_vs_unfiltered_queries_legitimately_disagree_on_total_u():
    """Simulates the two real call sites for rack 101/ISTANBUL:
    occupancy_rows(cur, "%DC13%") only ever sees the DC13-labelled row (the
    SQL WHERE clause filters the DH3 row out before dedupe runs), while
    occupancy_rows(cur, None) sees BOTH conflicting rows and dedupe picks
    the max. This is why a per-DC figure (2,629-style) and the all-DC figure
    (2,719-style) legitimately disagree for the same physical racks: it is
    not a bug in either query, it is a consequence of which rows survive the
    SQL filter before _dedupe_physical_racks ever gets a chance to merge
    them.
    """
    dc13_row = ("netbox-a", "101", "DC13", "DH1", 47, 30, 17, ["Boyner"], "ISTANBUL")
    dh3_row = ("netbox-b", "101", "DH3", "DH3-Hall", 52, 30, 22, ["AytemizBank"], "ISTANBUL")

    # simulates occupancy_rows(cur, "%DC13%"): only the matching row reaches dedupe
    filtered = occ.occupancy_rows(_FakeCursor([dc13_row]), dc_pattern="%DC13%")
    # simulates occupancy_rows(cur, None): both conflicting labels reach dedupe
    unfiltered = occ.occupancy_rows(_FakeCursor([dc13_row, dh3_row]), dc_pattern=None)

    assert len(filtered) == 1 and len(unfiltered) == 1
    assert filtered[0]["capacity_u"] == 47      # only the row that matched the filter
    assert unfiltered[0]["capacity_u"] == 52    # both rows present -> max wins
    assert filtered[0]["capacity_u"] != unfiltered[0]["capacity_u"]


def test_aggregate_by_dc_rolls_up():
    rows = [
        {"dc": "DC13", "capacity_u": 47, "used_u": 35, "free_u": 12},
        {"dc": "DC13", "capacity_u": 47, "used_u": 20, "free_u": 27},
        {"dc": "DC14", "capacity_u": 45, "used_u": 10, "free_u": 35},
    ]
    agg = occ.aggregate_by_dc(rows)
    assert agg["DC13"] == {"total_u": 94, "used_u": 55, "free_u": 39, "rack_count": 2}
    assert agg["DC14"] == {"total_u": 45, "used_u": 10, "free_u": 35, "rack_count": 1}


def test_is_internal_tenant():
    assert occ.is_internal_tenant("Bulutistan - Virtualization")
    assert occ.is_internal_tenant("Bulut Broker")
    assert occ.is_internal_tenant("CPE-Tenant")
    assert not occ.is_internal_tenant("AytemizBank")
    assert not occ.is_internal_tenant("Boyner")
    assert not occ.is_internal_tenant("")


# --- Exact per-(rack, tenant) occupancy (used by the customer footprint) ---

def test_tenant_occupancy_sql_counts_distinct_u_per_tenant():
    sql = occ.TENANT_OCCUPANCY_SQL.lower()
    # current tables only
    assert "discovery_netbox_inventory_device" in sql
    assert "loki_device_types" in sql
    assert "discovery_loki_rack" in sql
    assert "in ('front', '')" in sql
    # exact per-tenant measurement: COUNT(DISTINCT u)
    assert "count(distinct u)" in sql
    # device-side aggregation FIRST (grouped by rack+site+tenant) — no rack join
    # at this step, so a non-unique (rack_name, site_name) cannot fan out the U.
    assert "group by rack_name, site_name, tenant_name" in sql
    # untagged devices excluded at source so they never inflate a customer
    assert "tenant_name is not null" in sql
    # FAN-OUT GUARD: the rack side is de-duplicated to one row per (name, site)
    # before it is joined on, so a device's U is never multiplied.
    assert "max(capacity_u)" in sql
    assert "group by rack_name, site_name\n" in sql or "group by rack_name, site_name " in sql
    # stale / nonexistent tables must never appear
    assert "loki_devices" not in sql
    assert "discovery_loki_racks" not in sql


def test_tenant_occupancy_rows_executes_with_dc_pattern():
    cur = _FakeCursor([("DC13", "116", "Boyner", 20)])
    rows = occ.tenant_occupancy_rows(cur, dc_pattern="%DC13%")
    assert cur.executed[1] == {"dc_pattern": "%DC13%"}
    assert rows[0] == {"dc": "DC13", "rack_name": "116", "tenant_name": "Boyner", "used_u": 20}


def test_tenant_occupancy_row_coerces_null_used_u():
    cur = _FakeCursor([("DC13", "116", "Boyner", None)])
    rows = occ.tenant_occupancy_rows(cur, dc_pattern=None)
    assert rows[0]["used_u"] == 0


# --- used-U breakdown: External / Internal / Untagged partition ---

def test_classify_slots_partitions_by_priority():
    # slot (R,IST,10): external Boyner + internal -> external wins
    # slot (R,IST,11): only internal
    # slot (R,IST,12): blank/None tenant -> untagged
    rows = [
        ("R", "IST", 10, "Boyner"),
        ("R", "IST", 10, "Bulutistan - Linux TEAM"),
        ("R", "IST", 11, "Bulutistan - Virtualization"),
        ("R", "IST", 12, ""),
        ("R", "IST", 12, None),
        ("R", "IST", 13, "AytemizBank"),
    ]
    out = occ._classify_slots(rows)
    assert out == {
        "external_u": 2,               # slots 10, 13
        "internal_u": 1,               # slot 11
        "untagged_u": 1,               # slot 12
        "external_customer_count": 2,  # Boyner, AytemizBank
    }
    assert out["external_u"] + out["internal_u"] + out["untagged_u"] == 4


def test_used_u_breakdown_executes_and_classifies():
    cur = _FakeCursor([
        ("102", "IST", 10, "Boyner"),
        ("102", "IST", 11, "Bulutistan - Linux TEAM"),
        ("102", "IST", 12, None),
    ])
    out = occ.used_u_breakdown(cur, dc_pattern="%DC13%")
    assert cur.executed[1] == {"dc_pattern": "%DC13%"}
    assert out == {"external_u": 1, "internal_u": 1, "untagged_u": 1, "external_customer_count": 1}


def test_used_u_breakdown_sql_is_defanned_and_current_tables():
    sql = occ.USED_U_BREAKDOWN_SQL.lower()
    assert "discovery_netbox_inventory_device" in sql
    assert "loki_device_types" in sql
    assert "discovery_loki_rack" in sql
    assert "in ('front', '')" in sql
    assert "s.u between 1 and rc.capacity_u" in sql
    # de-fan: rack side collapsed to one row per (name, site) before the join
    assert "max(capacity_u)" in sql
    assert "group by rack_name, site_name" in sql
    assert "loki_devices" not in sql
    assert "discovery_loki_racks" not in sql


from shared.colocation.occupancy import INTERNAL_TENANT_PREFIXES, is_internal_tenant


def test_is_internal_tenant_uses_builtin_prefixes_by_default():
    assert is_internal_tenant("Bulutistan - Linux TEAM") is True
    assert is_internal_tenant("Boyner") is False


def test_is_internal_tenant_accepts_injected_prefixes():
    injected = ("acme-internal",)
    assert is_internal_tenant("ACME-Internal Fabric", injected) is True
    # Injected prefixes REPLACE the defaults; the caller decides what to union in.
    assert is_internal_tenant("Bulutistan - Linux TEAM", injected) is False


def test_is_internal_tenant_empty_injection_matches_nothing():
    # An empty Administration table must not classify everything as internal.
    assert is_internal_tenant("Bulutistan - Linux TEAM", ()) is False


def test_builtin_prefixes_unchanged():
    assert INTERNAL_TENANT_PREFIXES == (
        "bulutistan", "bulut broker", "cpe-tenant", "dc11 arista",
    )


# --- Fix round 1: internal_prefixes threaded into _classify_slots / used_u_breakdown ---

def test_classify_slots_honours_injected_prefixes():
    rows = [
        ("R", "IST", 1, "Acme-Internal"),
        ("R", "IST", 2, "Boyner"),
    ]
    out = occ._classify_slots(rows, internal_prefixes=("acme-internal",))
    assert out["internal_u"] == 1
    assert out["external_u"] == 1
    assert out["external_customer_count"] == 1


def test_classify_slots_injected_prefixes_replace_builtins():
    # "Bulutistan - Linux TEAM" matches a BUILT-IN prefix, but an injected set
    # REPLACES (not extends) the built-ins, so it must classify as external here.
    rows = [("R", "IST", 1, "Bulutistan - Linux TEAM")]
    out = occ._classify_slots(rows, internal_prefixes=("acme-internal",))
    assert out["internal_u"] == 0
    assert out["external_u"] == 1


def test_classify_slots_slot_priority_external_wins_with_injected_prefixes():
    # Same slot occupied by both an injected-internal tenant and an external
    # one: external must still win the slot (rank 2 > rank 1).
    rows = [
        ("R", "IST", 1, "Acme-Internal"),
        ("R", "IST", 1, "Boyner"),
    ]
    out = occ._classify_slots(rows, internal_prefixes=("acme-internal",))
    assert out["external_u"] == 1
    assert out["internal_u"] == 0


def test_used_u_breakdown_forwards_internal_prefixes():
    rows = [
        ("102", "IST", 10, "Acme-Internal"),
        ("102", "IST", 11, "Boyner"),
    ]
    out_with = occ.used_u_breakdown(
        _FakeCursor(rows), dc_pattern=None, internal_prefixes=("acme-internal",)
    )
    out_without = occ.used_u_breakdown(
        _FakeCursor(rows), dc_pattern=None, internal_prefixes=()
    )
    assert out_with != out_without
    assert out_with == {"external_u": 1, "internal_u": 1, "untagged_u": 0,
                         "external_customer_count": 1}
    assert out_without == {"external_u": 2, "internal_u": 0, "untagged_u": 0,
                            "external_customer_count": 2}
