"""allocation.py'nin kural setini parametre olarak alması."""

from shared.colocation.allocation import (
    aggregate_rack_allocations,
    sellable_rack_totals,
)
from shared.colocation.role_rules import RoleRules

# Dört rolden birer kabin. free_u değerleri bilerek farklı, ki hangi rolün
# havuza girdiği toplamdan okunabilsin.
ROWS = [
    {"rack_name": "N1", "role_id": "1", "capacity_u": 40, "used_u": 10, "free_u": 30},
    {"rack_name": "H1", "role_id": "2", "capacity_u": 40, "used_u": 15, "free_u": 25},
    {"rack_name": "S1", "role_id": "3", "capacity_u": 40, "used_u": 20, "free_u": 20},
    {"rack_name": "C1", "role_id": "4", "capacity_u": 40, "used_u": 25, "free_u": 15},
]


def test_default_rules_reproduce_todays_numbers():
    """rules verilmezse bugünkü davranış birebir çıkmalı: yalnız HOST sellable.

    Yakaladığı bozulma: varsayılan kayarsa canlı sellable U deploy anında
    kimse dokunmadan değişir -- 8. şikâyette düzeltilen sayı geri bozulur.
    """
    assert sellable_rack_totals(ROWS) == (40.0, 15.0)
    assert aggregate_rack_allocations(ROWS)["sellable_free_u"] == 25


def test_making_customer_racks_sellable_moves_their_free_u_into_the_pool():
    """CUSTOMER (4) sellable yapılınca free U'su havuza girmeli ve breakdown
    bayrağı da dönmeli.

    Yakaladığı bozulma: kural okunuyor ama toplamaya uygulanmıyorsa ekran
    ayarı kaydeder, sayı değişmez; ya da toplam değişir ama kartın legend'ı
    hâlâ 'satılamaz' der -- ikisi birbiriyle çelişir.
    """
    rules = RoleRules({"1": False, "2": True, "3": False, "4": True})

    assert sellable_rack_totals(ROWS, rules) == (80.0, 40.0)

    agg = aggregate_rack_allocations(ROWS, rules)
    assert agg["sellable_free_u"] == 40           # 25 (HOST) + 15 (CUSTOMER)
    assert agg["colocation_allocated_u"] == 80    # müşteri atfı DEĞİŞMEDİ
    bucket = next(b for b in agg["role_breakdown"] if b["role_id"] == "4")
    assert bucket["sellable"] is True
