"""RoleRules — kural çözümü ve etag davranışı."""

from shared.colocation.role_rules import DEFAULT_RULES, RoleRules


def test_unknown_and_missing_roles_are_sellable():
    """Rol taşımayan satırlar (Floor Map occupancy özeti) sellable kalmalı.

    Yakaladığı bozulma: bilinmeyen rolü 'satılamaz' saymak, rol bilgisi
    olmayan aggregate'lerin boş U'sunu sessizce sıfırlar.
    """
    rules = RoleRules({"1": False, "2": True})
    assert rules.is_sellable(None) is True
    assert rules.is_sellable("") is True
    assert rules.is_sellable("99") is True
    assert rules.is_sellable(" 2 ") is True   # varchar, trimlenir
    assert rules.is_sellable(1) is False      # int gelse de string gibi çözülür


def test_empty_rows_fall_back_to_default_rules():
    """Tablo boşsa/okunamıyorsa bugünkü kural seti geçerli olmalı.

    Yakaladığı bozulma: boş sonucu 'hiç kural yok, her şey sellable' diye
    yorumlamak sellable U'yu 3.503'ten platform toplamına şişirir.
    """
    assert RoleRules.from_rows([]) == DEFAULT_RULES
    assert RoleRules.from_rows(None) == DEFAULT_RULES


def test_etag_is_order_independent():
    """Aynı kural seti, satırlar farklı sırada okunduğunda aynı etag vermeli.

    Yakaladığı bozulma: sıraya duyarlı etag her istekte yeni cache anahtarı
    üretir, 6 saatlik colocation cache'i tamamen etkisiz kalır.
    """
    a = RoleRules.from_rows([{"role_id": "1", "sellable": False},
                             {"role_id": "2", "sellable": True}])
    b = RoleRules.from_rows([{"role_id": "2", "sellable": True},
                             {"role_id": "1", "sellable": False}])
    assert a.etag == b.etag


def test_etag_changes_when_a_rule_changes():
    """Bir rol sellable yapılınca etag değişmeli.

    Yakaladığı bozulma: etag sabit kalırsa operatör ayarı kaydeder, cache
    eski anahtarla eski sayıyı servis etmeye devam eder -- 'kaydettim ama
    ekran değişmedi' şikâyetinin ta kendisi.
    """
    before = RoleRules({"1": False, "2": True})
    after = RoleRules({"1": True, "2": True})
    assert before.etag != after.etag
    assert len(before.etag) == 8
