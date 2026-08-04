"""Colocation rack-role rule service — webui CRUD ve DEFAULT'a düşme."""

from shared.colocation.role_rules import DEFAULT_RULES
from app.services.colocation_role_rule_service import ColocationRoleRuleService


class _FakeWebui:
    def __init__(self, rows=None, available=True):
        self.is_available = available
        self._rows = rows or []
        self.executed = []

    def run_rows(self, sql, params=None):
        return list(self._rows)

    def execute(self, sql, params=None):
        self.executed.append(params)
        return 1

    def execute_all(self, statements):
        statements = list(statements)
        for _sql, params in statements:
            self.executed.append(params)
        return len(statements)


def test_unavailable_webui_falls_back_to_default_rules():
    """webui kapalıyken bugünkü kural seti uygulanmalı.

    Yakaladığı bozulma: config okunamayınca boş kural seti dönerse her rol
    'kayıtsız' olur, kayıtsız rol sellable sayılır ve sellable U bir DB
    kesintisi yüzünden platform toplamına fırlar.
    """
    svc = ColocationRoleRuleService(_FakeWebui(available=False))
    assert svc.load_rules() == DEFAULT_RULES


def test_saved_rules_are_written_for_every_role_and_reload():
    """Kaydetme dört rolü de yazmalı ve sonraki okuma yeni kuralı vermeli.

    Yakaladığı bozulma: kısmi yazım (yalnız değişen rol) ekranda görülen hâl
    ile DB'deki hâli ayrıştırır; memo temizlenmezse kaydetme 30 saniye
    boyunca hiçbir şeyi değiştirmez.
    """
    webui = _FakeWebui(rows=[{"role_id": "1", "sellable": False},
                             {"role_id": "2", "sellable": True}])
    svc = ColocationRoleRuleService(webui)
    assert svc.load_rules().is_sellable("1") is False

    webui._rows = [{"role_id": "1", "sellable": True},
                   {"role_id": "2", "sellable": True}]
    rules = svc.save_rules([{"role_id": "1", "sellable": True},
                            {"role_id": "2", "sellable": True}],
                           updated_by="tester")

    assert len(webui.executed) == 2
    assert rules.is_sellable("1") is True
    assert svc.load_rules().is_sellable("1") is True
