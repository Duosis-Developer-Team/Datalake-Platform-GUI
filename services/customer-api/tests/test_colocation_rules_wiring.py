"""Kural setinin colocation cache anahtarına ve hesabına bağlanması."""

from shared.colocation.role_rules import RoleRules
from app.services.colocation_matching_service import ColocationMatchingService
from app.services.sellable_service import SellableService


def test_colocation_cache_key_carries_the_rule_etag(monkeypatch):
    """İki farklı kural seti aynı cache anahtarını paylaşmamalı.

    Yakaladığı bozulma: etag anahtarda değilse operatör ayarı değiştirir,
    Redis'teki eski payload aynı anahtar altında durmaya devam eder ve
    6 saat boyunca eski sayı servis edilir.
    """
    a = RoleRules({"1": False, "2": True})
    b = RoleRules({"1": True, "2": True})
    assert ColocationMatchingService._cache_key("DC13", a) != \
           ColocationMatchingService._cache_key("DC13", b)
    assert ColocationMatchingService._cache_key("DC13", a).startswith("colocation:DC13:")


def test_sellable_result_cache_key_carries_the_rule_etag():
    """sellable:panels anahtarı da kural setine bağlı olmalı.

    Yakaladığı bozulma: colocation kartı yeni sayıyı gösterirken CRM
    sellable paneli eskisini gösterir -- iki ekran birbiriyle çelişir.
    """
    a = RoleRules({"1": False, "2": True})
    b = RoleRules({"1": True, "2": True})
    key_a = SellableService._result_cache_key("DC13", None, None, rules_etag=a.etag)
    key_b = SellableService._result_cache_key("DC13", None, None, rules_etag=b.etag)
    assert key_a != key_b
    assert key_a.startswith("sellable:panels:DC13:")
