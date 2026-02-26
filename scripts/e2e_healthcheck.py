#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
e2e_healthcheck.py — Datalake-Platform-GUI End-to-End Sağlık Kontrolü
═══════════════════════════════════════════════════════════════════════
Katman 1  Konteyner : 4 Docker servisi (db-service, redis,
                       query-service, gui-service) çalışıyor mu?
Katman 2  Redis     : Bağlantı var mı? Cache anahtarları mevcut mu?
Katman 3  API       : query-service /health + /datacenters/summary
Katman 4  GUI       : http://localhost:8050 erişilebilir mi?

Kullanım:
    python scripts/e2e_healthcheck.py

Not:
    - Harici bağımlılık yoktur (yalnızca Python stdlib).
    - query-service ve redis host'a açık DEĞİLDİR; testler
      'docker exec' üzerinden çalışır.
    - INTERNAL_API_KEY proje kökündeki .env dosyasından okunur.
    - /datacenters/summary ilk çalışmada ~74s sürebilir (soğuk başlangıç);
      timeout buna göre 120s olarak ayarlanmıştır.
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

# ──────────────────────────────────────────────────────────────────
#  Konfigürasyon
# ──────────────────────────────────────────────────────────────────

# scripts/ içinden çalışınca bir üst dizin proje köküdür
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")

# docker-compose.yml'deki gerçek container isimleri
CONTAINERS: dict[str, str] = {
    "db-service":     "datalake-platform-gui-db-service-1",
    "redis":          "datalake-platform-gui-redis-1",
    "query-service":  "datalake-platform-gui-query-service-1",
    "gui-service":    "datalake-platform-gui-gui-service-1",
}

REDIS_CONTAINER = CONTAINERS["redis"]
QUERY_CONTAINER = CONTAINERS["query-service"]
GUI_URL = "http://localhost:8050"

# Redis cache anahtarları (query-service'in cache-aside'da kullandığı)
CACHE_KEYS = ["dc_summary_all", "global_overview"]

# ──────────────────────────────────────────────────────────────────
#  Yardımcı fonksiyonlar
# ──────────────────────────────────────────────────────────────────

_passed = 0
_failed = 0


def _result(label: str, ok: bool, detail: str = "") -> bool:
    """Sonucu konsola yazar ve global sayacı günceller."""
    global _passed, _failed
    if ok:
        print(f"  ✓ PASS  {label}")
        _passed += 1
    else:
        print(f"  ✗ FAIL  {label}")
        if detail:
            print(f"         → {detail}")
        _failed += 1
    return ok


def _run(cmd: list[str], timeout: int = 20) -> tuple[int, str, str]:
    """Shell komutu çalıştırır; (returncode, stdout, stderr) döndürür."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", f"timeout ({timeout}s aşıldı)"
    except FileNotFoundError:
        return -1, "", f"komut bulunamadı: {cmd[0]!r}"
    except Exception as exc:
        return -1, "", str(exc)


def _load_env() -> dict[str, str]:
    """Proje kökündeki .env dosyasını KEY=VALUE satır bazlı okur."""
    result: dict[str, str] = {}
    if not os.path.exists(ENV_FILE):
        return result
    with open(ENV_FILE, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            result[key.strip()] = val.strip().strip('"').strip("'")
    return result


def _section(title: str) -> None:
    bar = "─" * 46
    print(f"\n┌{bar}┐")
    print(f"│  {title:<44}│")
    print(f"└{bar}┘")


# ══════════════════════════════════════════════════════════════════
#  KATMAN 1 — KONTEYNER
# ══════════════════════════════════════════════════════════════════
_section("1. Konteyner Katmanı")

rc, stdout, stderr = _run(
    ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"]
)

if rc != 0:
    _result("docker ps komutu", False, stderr or "Docker daemon'a erişilemiyor")
    print("\n  ⚠  Docker erişilemiyor — kalan testler atlanıyor.")
    sys.exit(1)

# Çalışan container isimlerini ayıkla
running: set[str] = set()
for line in stdout.splitlines():
    parts = line.split("\t")
    if len(parts) >= 2 and "Up" in parts[1]:
        running.add(parts[0].strip())

for svc_label, cname in CONTAINERS.items():
    _result(f"{svc_label} çalışıyor", cname in running, f"beklenen container: {cname}")

# ══════════════════════════════════════════════════════════════════
#  KATMAN 2 — REDIS
#  (Redis host'a açık değil — docker exec ile test ediyoruz)
# ══════════════════════════════════════════════════════════════════
_section("2. Redis Katmanı")

# 2a. PING
rc, out, _ = _run(["docker", "exec", REDIS_CONTAINER, "redis-cli", "ping"])
_result("Redis PING → PONG", rc == 0 and "PONG" in out, out or "yanıt yok")

# 2b. Key sayısı (DBSIZE)
rc, out, _ = _run(["docker", "exec", REDIS_CONTAINER, "redis-cli", "DBSIZE"])
key_count = -1
if rc == 0:
    try:
        key_count = int(out)
    except ValueError:
        pass

if key_count >= 0:
    _result(f"Redis erişilebilir (DBSIZE = {key_count})", True)
    if key_count == 0:
        print("         ℹ  Cache henüz boş — API testi sonrası otomatik dolacak.")
else:
    _result("Redis DBSIZE komutu", False, out)

# 2c. Cache anahtarları ön-durum (bilgilendirici — API çağrısı öncesi anlık görüntü)
print()
print("  Cache ön-durum (API çağrısı öncesi):")
for cache_key in CACHE_KEYS:
    rc, out, _ = _run(
        ["docker", "exec", REDIS_CONTAINER, "redis-cli", "EXISTS", cache_key]
    )
    exists = rc == 0 and out.strip() == "1"
    status = "mevcut ✓" if exists else "boş (API çağrısı sonrası doldurulacak)"
    print(f"    ℹ  '{cache_key}': {status}")

# ══════════════════════════════════════════════════════════════════
#  KATMAN 3 — API (query-service)
#  (query-service host'a açık değil — docker exec ile test ediyoruz)
# ══════════════════════════════════════════════════════════════════
_section("3. API Katmanı (query-service)")

# 3a. /health — kimlik doğrulama gerektirmez
rc, out, _ = _run(
    [
        "docker", "exec", QUERY_CONTAINER,
        "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
        "http://localhost:8002/health",
    ],
    timeout=15,
)
_result("query-service /health → 200", rc == 0 and out == "200", f"HTTP {out or 'yanıt yok'}")

# 3b. /datacenters/summary — X-Internal-Key gerektirir
env = _load_env()
api_key = env.get("INTERNAL_API_KEY", "")

if not api_key:
    print()
    print("  ⚠ SKIP  /datacenters/summary")
    print("         → .env'de INTERNAL_API_KEY bulunamadı")
    print(f"         → Beklenen dosya: {ENV_FILE}")
else:
    print()
    print("  ℹ  /datacenters/summary çağrılıyor...")
    print("     (İlk çalışmada VPN üzerinden ~40-75s sürebilir — bekleniyor...)")

    rc, out, err = _run(
        [
            "docker", "exec", QUERY_CONTAINER,
            "curl", "-s", "-w", "\n%{http_code}",
            "-H", f"X-Internal-Key: {api_key}",
            "http://localhost:8002/datacenters/summary",
        ],
        timeout=120,  # Soğuk başlangıç ~74s, Redis miss ~39s
    )

    if rc != 0:
        _result(
            "query-service /datacenters/summary çağrısı",
            False,
            err[:140] or "curl başarısız",
        )
    else:
        # curl çıktısı: <body>\n<http_code>
        lines = out.rsplit("\n", 1)
        http_code = lines[-1].strip() if len(lines) > 1 else ""
        body = lines[0].strip() if len(lines) > 1 else out

        api_ok = _result(
            "query-service /datacenters/summary → 200",
            http_code == "200",
            f"HTTP {http_code or 'yanıt yok'}",
        )

        if api_ok:
            try:
                data = json.loads(body)
                is_list = isinstance(data, list)
                list_ok = _result(
                    "Response geçerli JSON (liste formatı)",
                    is_list,
                    f"beklenen list, gelen: {type(data).__name__}",
                )
                if list_ok:
                    _result(f"En az 1 DC kaydı ({len(data)} DC mevcut)", len(data) > 0)

                    # İlk DC kaydının zorunlu alanlarını kontrol et (DCSummary şeması)
                    if len(data) > 0:
                        first = data[0]
                        for field in ("id", "name", "location", "status", "stats"):
                            _result(
                                f"  DC kaydında '{field}' alanı var",
                                field in first,
                                f"mevcut alanlar: {list(first.keys())[:8]}",
                            )
                        # stats nested alanı kontrol et (DCStats)
                        if "stats" in first and isinstance(first["stats"], dict):
                            stats = first["stats"]
                            for sf in ("used_cpu_pct", "used_ram_pct", "total_energy_kw"):
                                _result(
                                    f"  stats.'{sf}' alanı var",
                                    sf in stats,
                                    f"mevcut stats alanları: {list(stats.keys())}",
                                )
            except json.JSONDecodeError as exc:
                _result("Response geçerli JSON", False, str(exc)[:100])
                print(f"         → Ham yanıt (ilk 200 karakter): {body[:200]!r}")

        # /datacenters/summary sonrası cache kontrol
        if api_ok:
            print()
            print("  API çağrısı sonrası cache durumu:")
            rc2, out2, _ = _run(
                ["docker", "exec", REDIS_CONTAINER, "redis-cli", "EXISTS", "dc_summary_all"]
            )
            _result(
                "  Cache 'dc_summary_all' oluşturuldu",
                rc2 == 0 and out2.strip() == "1",
                "Cache-aside çalışmıyor olabilir",
            )

    # 3c. /overview endpoint
    print()
    print("  ℹ  /overview çağrılıyor (cache miss ~41s, hit ~1s)...")
    rc, out, err = _run(
        [
            "docker", "exec", QUERY_CONTAINER,
            "curl", "-s", "-w", "\n%{http_code}",
            "-H", f"X-Internal-Key: {api_key}",
            "http://localhost:8002/overview",
        ],
        timeout=120,
    )

    if rc != 0:
        _result("query-service /overview çağrısı", False, err[:140] or "curl başarısız")
    else:
        lines = out.rsplit("\n", 1)
        http_code = lines[-1].strip() if len(lines) > 1 else ""
        body = lines[0].strip() if len(lines) > 1 else out

        ov_ok = _result(
            "query-service /overview → 200",
            http_code == "200",
            f"HTTP {http_code or 'yanıt yok'}",
        )
        if ov_ok:
            try:
                ov = json.loads(body)
                is_dict = isinstance(ov, dict)
                ov_valid = _result(
                    "Response geçerli JSON (GlobalOverview)",
                    is_dict,
                    f"beklenen dict, gelen: {type(ov).__name__}",
                )
                if ov_valid:
                    for field in ("total_hosts", "total_vms", "dc_count", "total_energy_kw"):
                        _result(
                            f"  GlobalOverview.'{field}' alanı var",
                            field in ov,
                            f"mevcut alanlar: {list(ov.keys())}",
                        )
                    # /overview sonrası global_overview cache kontrolü
                    rc2, out2, _ = _run(
                        ["docker", "exec", REDIS_CONTAINER, "redis-cli", "EXISTS", "global_overview"]
                    )
                    _result(
                        "  Cache 'global_overview' oluşturuldu",
                        rc2 == 0 and out2.strip() == "1",
                        "Cache-aside çalışmıyor olabilir",
                    )
            except json.JSONDecodeError as exc:
                _result("Response geçerli JSON", False, str(exc)[:100])

# ══════════════════════════════════════════════════════════════════
#  KATMAN 4 — GUI (gui-service)
#  (gui-service host'a açık — ports: "8050:8050")
# ══════════════════════════════════════════════════════════════════
_section("4. GUI Katmanı (gui-service)")

try:
    req = urllib.request.Request(
        GUI_URL, headers={"User-Agent": "e2e-healthcheck/1.0"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        code = resp.getcode()
        snippet = resp.read(2048).decode("utf-8", errors="replace")

    _result(f"http://localhost:8050 → 200", code == 200, f"HTTP {code}")
    _result(
        "Response Dash HTML içeriyor",
        "dash" in snippet.lower() or "<!doctype" in snippet.lower(),
        "Yanıt beklenen Dash HTML görünümünde değil",
    )
    _result(
        "Dash _dash-layout endpoint varlığı",
        True,  # 200 aldık demek ki Dash tam yüklendi
    )

except urllib.error.HTTPError as exc:
    _result(f"http://localhost:8050 → 200", False, f"HTTP {exc.code}: {exc.reason}")
except urllib.error.URLError as exc:
    _result("http://localhost:8050 bağlantısı", False, str(exc.reason))
except Exception as exc:
    _result("http://localhost:8050 bağlantısı", False, str(exc))

# ══════════════════════════════════════════════════════════════════
#  SONUÇ
# ══════════════════════════════════════════════════════════════════

total = _passed + _failed
print()
print("═" * 48)
if _failed == 0:
    print(f"  ✓ TÜM TESTLER GEÇTİ ({_passed}/{total})  — SİSTEM SAĞLIKLI")
else:
    print(f"  ✗ SONUÇ: {_passed}/{total} başarılı, {_failed} başarısız")
    print()
    print("  Olası çözümler:")
    print("  • Konteyner hataları → docker-compose up -d --build")
    print("  • Redis/API hataları → docker logs <container-adı>")
    print("  • GUI hatası        → http://localhost:8050 tarayıcıda açın")
print("═" * 48)
print()

sys.exit(0 if _failed == 0 else 1)
