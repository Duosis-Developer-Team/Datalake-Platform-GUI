"""NetBackup policy naming standard, derived from backup-musteri-isim.xlsx and
validated against 1,294 live policy names.

Standard: <first4(word1)>[-<first4(word2)>]-<workload>-<env>-<type>, Turkish-folded.
"""
from shared.customer.backup_policy import (
    build_policy_index,
    guess_policy_owner,
    policy_tokens_for_account,
)


def test_tokens_follow_the_first_four_letters_of_each_word():
    assert "abc-dete" in policy_tokens_for_account("ABC Deterjan")
    assert "ayak-duny" in policy_tokens_for_account("Ayakkabı Dünyası")
    assert "cele-hold" in policy_tokens_for_account("Çelebi Holding")


def test_turkish_characters_fold_the_same_way_the_classifier_folds_them():
    assert "capa-medi" in policy_tokens_for_account("Çapa Medikal")
    assert "alki-kagi" in policy_tokens_for_account("Alkim Kağıt")
    assert "bizi-topt" in policy_tokens_for_account("Bizim Toptan")


def test_single_word_accounts_yield_the_short_and_the_full_form():
    tokens = policy_tokens_for_account("Aksular")
    assert "aksu" in tokens
    assert "aksular" in tokens


def test_legal_suffixes_are_not_treated_as_name_words():
    """'ABRAK ENERJİ ... ANONİM ŞİRKETİ' must not produce 'abra-anon'."""
    tokens = policy_tokens_for_account("ABRAK ENERJİ ELEKTRİK ÜRETİM ANONİM ŞİRKETİ")
    assert "abra-ener" in tokens
    assert not any(t.endswith("-anon") or t.endswith("-sirk") for t in tokens)


def test_two_segment_token_wins_over_one_segment():
    """abc-dete is more specific than abc; the longer match is the safer owner."""
    index = build_policy_index([
        {"name": "ABC Deterjan", "accountid": "acc-abc-dete"},
        {"name": "ABC Holding", "accountid": "acc-abc-hold"},
    ])
    token, candidates = guess_policy_owner("abc-dete-s4hana-prd-log", index)

    assert token == "abc-dete"
    assert candidates == [("ABC Deterjan", "acc-abc-dete")]


def test_an_ambiguous_token_returns_every_candidate():
    """avro matches AVROMED and AVRORA LLC. Measured on live data: 27% of
    policies land here. Callers must not pick one."""
    index = build_policy_index([
        {"name": "AVROMED", "accountid": "acc-avromed"},
        {"name": "AVRORA LLC", "accountid": "acc-avrora"},
    ])
    token, candidates = guess_policy_owner("avro-CLAVRDB01-H", index)

    assert token == "avro"
    assert len(candidates) == 2
    assert {c[0] for c in candidates} == {"AVROMED", "AVRORA LLC"}


def test_an_unknown_policy_has_no_owner():
    index = build_policy_index([{"name": "ABC Deterjan", "accountid": "acc-1"}])
    assert guess_policy_owner("visa01-vm-image", index) is None
    assert guess_policy_owner("", index) is None


def test_a_token_must_not_match_a_longer_segment_it_merely_starts():
    """'abcd' must not claim 'abcdef-prd': the segment boundary is a dash.

    An account named 'Abcd Company' produces the token 'abcd'. A policy named
    'abcdef-prd-log' must not be assigned to that account, because 'abcd' is
    a whole segment and 'abcdef' is a different segment."""
    index = build_policy_index([{"name": "Abcd Company", "accountid": "acc-1"}])
    assert guess_policy_owner("abcdef-prd-log", index) is None


def test_candidates_are_ordered_deterministically():
    """Two runs must not disagree about which candidate is listed first."""
    index = build_policy_index([
        {"name": "AVRORA LLC", "accountid": "acc-avrora"},
        {"name": "AVROMED", "accountid": "acc-avromed"},
    ])
    _, candidates = guess_policy_owner("avro-db", index)
    assert candidates == [("AVROMED", "acc-avromed"), ("AVRORA LLC", "acc-avrora")]


def test_the_standard_reproduces_the_spreadsheets_own_tokens():
    """The sheet is ground truth. If a change to the standard stops
    reproducing its documented tokens, that is a regression, not an
    improvement. These pairs are copied verbatim from AD-KARŞILIĞI.
    """
    documented = {
        "ABC Deterjan": "abc-dete",
        "Akasya Maden": "akas-made",
        "Alkim Kağıt": "alki-kagi",
        "Ayakkabı Dünyası": "ayak-duny",
        "Bizim Toptan": "bizi-topt",
        "Bony Çorap": "bony-cora",
        "Çapa Medikal": "capa-medi",
        "Çelebi Holding": "cele-hold",
        "Gama Holding": "gama-hold",
        "Kale Holding": "kale-hold",
        "Kibar Holding": "kiba-hold",
        "Rönesans Holding": "rone-hold",
        "Zorlu Holding": "zorl-hold",
        "Engin LTD": "engi-ltd",
        "Azer": "azer",
        "Boyner": "boyner",
    }
    for account, token in documented.items():
        assert token in policy_tokens_for_account(account), f"{account} -> {token}"
