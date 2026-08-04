"""Colocation rack-role rule service — webui CRUD ve DEFAULT'a düşme."""

import pytest

from shared.colocation.role_rules import DEFAULT_RULES
from app.services.colocation_role_rule_service import ColocationRoleRuleService


class _FakeWebui:
    """Fake WebuiPool that tracks COMMITTED state separately from calls made.

    ``execute()`` mirrors the real WebuiPool.execute(): each call commits
    immediately (a role becomes visible in ``committed`` the instant that
    call returns). ``execute_all()`` mirrors the real WebuiPool.execute_all():
    it only updates ``committed`` after every statement in the batch has run
    -- if one of them raises, nothing in the batch is committed. This
    distinction is what lets a test tell "one atomic transaction" apart from
    "N separate commits" instead of just counting calls.

    ``fail_after`` (if set) raises once the shared call counter -- incremented
    by both ``execute()`` and each statement inside ``execute_all()`` -- exceeds
    it, so the same fixture can simulate a mid-write failure whether the
    production code is using the old per-role loop or the new batched call.
    """

    def __init__(self, rows=None, available=True, fail_after=None):
        self.is_available = available
        self._rows = rows or []
        self.executed = []
        self.committed: dict[str, bool] = {}
        self._fail_after = fail_after
        self._call_count = 0

    def run_rows(self, sql, params=None):
        return list(self._rows)

    def execute(self, sql, params=None):
        self._call_count += 1
        if self._fail_after is not None and self._call_count > self._fail_after:
            raise RuntimeError("simulated connection drop")
        self.executed.append(params)
        self.committed[params[0]] = params[1]
        return 1

    def execute_all(self, statements):
        statements = list(statements)
        pending: dict[str, bool] = {}
        for sql, params in statements:
            self._call_count += 1
            if self._fail_after is not None and self._call_count > self._fail_after:
                raise RuntimeError("simulated connection drop")
            self.executed.append(params)
            pending[params[0]] = params[1]
        self.committed.update(pending)
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


def test_save_rules_write_is_atomic_when_it_fails_partway():
    """İkinci rol yazılırken bağlantı koparsa hiçbir rol kalıcı olmamalı.

    Yakaladığı bozulma: save_rules, rolleri tek transaction yerine rol
    başına ayrı commit'lerle yazmaya geri dönerse, ilk rol ikinci rol
    patlamadan önce zaten kalıcı olmuş olur -- yarım yazım DB'de kalır.
    """
    webui = _FakeWebui(fail_after=1)
    svc = ColocationRoleRuleService(webui)

    with pytest.raises(RuntimeError):
        svc.save_rules(
            [{"role_id": "1", "sellable": True},
             {"role_id": "2", "sellable": True}],
            updated_by="tester",
        )

    assert webui.committed == {}
