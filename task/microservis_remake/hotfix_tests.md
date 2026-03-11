# Hotfix Test Planı — db_service.py Coverage %77 → %85+

> **Amaç:** `backend/app/services/db_service.py` dosyasının test kapsamını %77'den %85 üzerine çıkarmak
> için eksik senaryoların tespiti ve Executer'a birebir uygulanacak test yazma direktifleri.

---

> [!CAUTION]
> ## EXECUTER İÇİN MUTLAK KURAL
> **Yazacağın yeni test dosyalarında TEK BİR YORUM SATIRI (`#`) DAHİ OLMAYACAK.**
> Fonksiyon isimleri yeterince açıklayıcı olacak. Docstring YASAK.

---

## 1. Coverage Gap Analizi

`db_service.py` toplam 1135 satır. Mevcut testler aşağıdaki bölgeleri KAPSAMIYOR:

| # | Kapsanmayan Bölge | Satır Aralığı | Tahmini Satır Sayısı | Neden Kapsanmıyor |
|---|-------------------|---------------|----------------------|-------------------|
| **GAP-1** | `get_customer_resources` happy path | 816–1092 | ~276 satır | Mevcut testler sadece `pool=None` fallback'ini test ediyor (satır 969-1023). DB bağlantılı happy path (Intel VM, Power LPAR, Veeam, NetBackup, Zerto, Storage sorguları ve sonuç yapısı) hiç çalıştırılmıyor |
| **GAP-2** | `_load_dc_list` tüm dalları | 195–213 | ~19 satır | Happy path (status filtreli sorgu başarılı), ikinci deneme (status filtresiz), ve boş DC listesi fallback'i test edilmiyor |
| **GAP-3** | `execute_registered_query` dalları | 160–193 | ~34 satır | `result_type == "row"` ve `result_type == "rows"` dalları, `OperationalError` exception handler'ı ve genel exception handler'ı test edilmiyor |
| **GAP-4** | `_run_value/_run_row/_run_rows` ROLLBACK iç dalları | 114–117, 128–130, 141–143 | ~9 satır | Sorgu hatası sonrası ROLLBACK'in kendisi de exception fırlatırsa (çift hata senaryosu) — iç `try/except` dalları kapsanmıyor |
| **GAP-5** | `_rebuild_summary` sıfır-kaynak DC skip dalı | 673–675 | ~3 satır | `host_count == 0 and vm_count == 0` olan DC'lerin summary'den atlanıp yalnızca cache'e yazılma dalı test edilmiyor |

**Toplam kapsanmayan tahmini satır:** ~341 satır → %30 civarı. Bunların ~260'ı GAP-1'den geliyor.

---

## 2. Öncelik Sıralaması

%85'e ulaşmak için yaklaşık 90 satırlık ek kapsam gerekiyor. En verimli strateji:

| Öncelik | Gap | Kazanım | Efor |
|---------|-----|---------|------|
| 🔴 P0 | GAP-1: `get_customer_resources` happy path | ~276 satır (tek başına %77→%90+ potansiyeli) | Yüksek |
| 🟡 P1 | GAP-3: `execute_registered_query` dalları | ~34 satır | Düşük |
| 🟡 P1 | GAP-2: `_load_dc_list` dalları | ~19 satır | Düşük |
| 🟢 P2 | GAP-4: ROLLBACK çift-hata senaryosu | ~9 satır | Düşük |
| 🟢 P2 | GAP-5: Sıfır-kaynak DC skip dalı | ~3 satır | Düşük |

---

## 3. Test Yazma Direktifleri

### 3.1 — Yeni Dosya: `backend/tests/test_customer_resources_service.py`

**Hedef:** GAP-1'i kapatmak

**Mock Stratejisi:**
```python
from unittest.mock import MagicMock, patch
from contextlib import contextmanager
```

Mevcut `_make_svc_with_conn` helper'ını (`test_db_service_conn_mock.py` satır 30-42) referans alarak, cursor mock'unu konfigüre et. `_run_row` ve `_run_rows` çağrılarının sırasını takip ederek `cursor.fetchone` ve `cursor.fetchall` return value'larını `side_effect` listesi ile sırala.

**`get_customer_resources` iç sorgu sırası (satır 819-967):**

| Çağrı # | Metot | Sorgu Sabiti | fetch tipi |
|---------|-------|-------------|------------|
| 1 | `_run_row` | `CUSTOMER_INTEL_VM_COUNTS` | `fetchone` |
| 2 | `_run_row` | `CUSTOMER_INTEL_CPU_TOTALS` | `fetchone` |
| 3 | `_run_row` | `CUSTOMER_INTEL_MEMORY_TOTALS` | `fetchone` |
| 4 | `_run_row` | `CUSTOMER_INTEL_DISK_TOTALS` | `fetchone` |
| 5 | `_run_rows` | `CUSTOMER_INTEL_VM_DETAIL_LIST` | `fetchall` |
| 6 | `_run_value` | `CUSTOMER_POWER_CPU_TOTAL` | `fetchone` |
| 7 | `_run_value` | `IBM_LPAR_TOTALS` | `fetchone` |
| 8 | `_run_value` | `CUSTOMER_POWER_MEMORY_TOTAL` | `fetchone` |
| 9 | `_run_rows` | `CUSTOMER_POWER_LPAR_DETAIL_LIST` | `fetchall` |
| 10 | `_run_value` | `CUSTOMER_VEEAM_DEFINED_SESSIONS` | `fetchone` |
| 11 | `_run_rows` | `CUSTOMER_VEEAM_SESSION_TYPES` | `fetchall` |
| 12 | `_run_rows` | `CUSTOMER_VEEAM_SESSION_PLATFORMS` | `fetchall` |
| 13 | `_run_row` | `CUSTOMER_NETBACKUP_BACKUP_SUMMARY` | `fetchone` |
| 14 | `_run_value` | `CUSTOMER_ZERTO_PROTECTED_VMS` | `fetchone` |
| 15 | `_run_rows` | `CUSTOMER_ZERTO_PROVISIONED_STORAGE` | `fetchall` |
| 16 | `_run_value` | `CUSTOMER_STORAGE_VOLUME_CAPACITY` | `fetchone` |

**Yazılacak test fonksiyonları:**

- [ ] `test_get_customer_resources_happy_path_builds_correct_totals`
  - Tüm 16 sorguyu mock'layarak gerçekçi verilerle çalıştır
  - `result["totals"]["vms_total"]` = intel_vms_total + power_lpars olduğunu doğrula
  - `result["totals"]["cpu_total"]` = intel_cpu_total + power_cpu olduğunu doğrula
  - `result["assets"]["intel"]["vm_list"]` uzunluğunun dönen satır sayısına eşit olduğunu doğrula

- [ ] `test_get_customer_resources_caches_result_on_success`
  - İlk çağrıda DB sorguları çalışır
  - İkinci çağrıda cache'ten döner (cursor.execute çağrı sayısı artmaz)

- [ ] `test_get_customer_resources_empty_customer_name_uses_wildcard_patterns`
  - `customer_name=""` ile çağır
  - Pattern'lerin `"%"` olduğunu doğrula (satır 807-812'deki `else "%"` dalları)

- [ ] `test_get_customer_resources_storage_volume_exception_uses_zero`
  - 16. sorguyu (`CUSTOMER_STORAGE_VOLUME_CAPACITY`) exception fırlatan bir mock ile konfigüre et
  - `storage_volume_gb` değerinin `0.0` olduğunu doğrula (satır 966-967 dalı)

- [ ] `test_get_customer_resources_backup_detail_structures`
  - Veeam session types, Veeam platforms, Zerto VPG'ler ve NetBackup dedup gibi detay alanlarının doğru yapılandırıldığını doğrula

### 3.2 — Yeni Dosya: `backend/tests/test_load_dc_list.py`

**Hedef:** GAP-2'yi kapatmak

**Yazılacak test fonksiyonları:**

- [ ] `test_load_dc_list_returns_names_from_db_when_status_query_succeeds`
  - `_run_rows` ilk çağrısında `[("DC11",), ("DC12",)]` dönmesini sağla
  - Sonucun `["DC11", "DC12"]` olduğunu doğrula

- [ ] `test_load_dc_list_retries_without_status_when_first_query_empty`
  - İlk `_run_rows` çağrısı `[]` döner, ikincisi `[("AZ11",)]` döner
  - Sonucun `["AZ11"]` olduğunu doğrula (satır 201-203 dalı)

- [ ] `test_load_dc_list_returns_fallback_when_both_queries_empty`
  - Her iki sorgu da `[]` döner
  - Sonucun `_FALLBACK_DC_LIST` kopyası olduğunu doğrula (satır 212-213 dalı)

- [ ] `test_load_dc_list_returns_fallback_on_operational_error`
  - `_get_connection` OperationalError fırlatsın
  - Sonucun `_FALLBACK_DC_LIST` kopyası olduğunu doğrula (satır 204-206 dalı)

### 3.3 — Mevcut Dosyaya Ekleme: `backend/tests/test_db_service_conn_mock.py`

**Hedef:** GAP-3'ü kapatmak

**Eklenecek test fonksiyonları:**

- [ ] `test_execute_registered_query_returns_row_result_type`
  - `result_type == "row"` olan bir registry entry'si kullan (veya `qo.get_merged_entry`'yi mock'la)
  - `cursor.fetchone` → `(1, 2, 3)`, `cursor.description` → `[("a",), ("b",), ("c",)]`
  - Sonucun `{"result_type": "row", "columns": ["a","b","c"], "data": [1,2,3]}` olduğunu doğrula

- [ ] `test_execute_registered_query_returns_rows_result_type`
  - `result_type == "rows"` olan bir entry
  - `fetchall` → `[(1,2), (3,4)]`
  - Sonucun `{"result_type": "rows", "columns": [...], "data": [[1,2],[3,4]]}` olduğunu doğrula

- [ ] `test_execute_registered_query_returns_error_on_operational_error`
  - `cursor.execute` → `OperationalError("connection lost")` fırlatsın
  - Sonucun `{"error": "Database error: ..."}` formatında olduğunu doğrula (satır 188-190 dalı)

- [ ] `test_execute_registered_query_returns_error_on_generic_exception`
  - `cursor.execute` → `ValueError("unexpected")` fırlatsın
  - Sonucun `{"error": "unexpected"}` olduğunu doğrula (satır 191-193 dalı)

- [ ] `test_execute_registered_query_returns_error_when_no_sql_in_entry`
  - `qo.get_merged_entry`'yi `{"result_type": "value"}` (SQL yok) döndürecek şekilde mock'la
  - Sonucun `{"error": "No SQL for query: ..."}` olduğunu doğrula (satır 167-168 dalı)

### 3.4 — Mevcut Dosyaya Ekleme: `backend/tests/test_db_service_conn_mock.py`

**Hedef:** GAP-4'ü kapatmak

**Eklenecek test fonksiyonları:**

- [ ] `test_run_value_rollback_itself_fails_silently`
  - İlk `cursor.execute(sql)` → `Exception("query fail")`
  - İkinci `cursor.execute("ROLLBACK")` → `Exception("rollback fail")`
  - Sonucun yine `0` olduğunu doğrula (satır 116-117, iç `except` dalı)

- [ ] `test_run_row_rollback_itself_fails_silently`
  - Aynı pattern: sorgu hatası + ROLLBACK hatası → `None` döner (satır 129-130)

- [ ] `test_run_rows_rollback_itself_fails_silently`
  - Aynı pattern: sorgu hatası + ROLLBACK hatası → `[]` döner (satır 142-143)

**Mock Stratejisi:**
```python
call_count = [0]
def execute_side_effect(sql, params=None):
    call_count[0] += 1
    if call_count[0] == 1:
        raise Exception("query fail")
    raise Exception("rollback fail")
cursor.execute = MagicMock(side_effect=execute_side_effect)
```

### 3.5 — Mevcut Dosyaya Ekleme: `backend/tests/test_db_service_conn_mock.py`

**Hedef:** GAP-5'i kapatmak

- [ ] `test_rebuild_summary_skips_dcs_with_zero_hosts_and_zero_vms`
  - `_fetch_all_batch` dönüşünü mock'la: bir DC tüm değerleri sıfır
  - `_rebuild_summary` sonucunun bu DC'yi summary listesine ekleMEdiğini doğrula
  - Bu DC'nin yine de `dc_details:{dc}:...` cache key'i ile cache'e yazıldığını doğrula (satır 674)

---

## 4. Çalıştırma ve Doğrulama Komutu

```bash
cd backend && pytest tests/ -v --cov=app/services/db_service --cov-report=term-missing --tb=short
```

**Kabul kriteri:**
- `db_service.py` coverage ≥ %85
- SIFIR test FAILED
- Test dosyalarında SIFIR yorum satırı: `grep -rn "^#" backend/tests/test_customer_resources_service.py backend/tests/test_load_dc_list.py` → boş çıktı

---

## 5. Tahmini Etki Analizi

| Gap | Kapsanacak Yeni Satır | Coverage Artışı (tahmini) |
|-----|----------------------|--------------------------|
| GAP-1 | ~200-250 satır | %77 → %95 (bu tek başına yeterli) |
| GAP-2 | ~15 satır | +%1.3 |
| GAP-3 | ~25 satır | +%2.2 |
| GAP-4 | ~6 satır | +%0.5 |
| GAP-5 | ~3 satır | +%0.3 |

**GAP-1 (customer resources happy path) tek başına %85 hedefini aşmaya yeter.** Ancak sağlam bir test altyapısı için P1 ve P2 gap'leri de kapatılmalıdır.
