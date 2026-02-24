import asyncio
import asyncpg

# ── Bağlantı parametreleri — buraya kendi değerlerini gir ──────────────────
DB_HOST = "10.134.16.6"
DB_PORT = 5000
DB_NAME = "bulutlake"
DB_USER = "bulutlake"
DB_PASS = "BulutLakePas24"
# ───────────────────────────────────────────────────────────────────────────

async def main():
    print(f"Bağlanılıyor: {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    try:
        conn = await asyncpg.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            timeout=10,
            # ssl="require",   # <-- SSL hatası alırsan bu satırı aç
        )
        version = await conn.fetchval("SELECT version()")
        print(f"BASARILI — PostgreSQL: {version[:70]}\n")

        # 1. DC listesi (loki_locations)
        dc_list = await conn.fetch("""
            SELECT DISTINCT
                CASE WHEN parent_id IS NULL THEN name ELSE parent_name END AS dc_name
            FROM public.loki_locations
            WHERE CASE WHEN parent_id IS NULL THEN name ELSE parent_name END IS NOT NULL
              AND status_value = 'active'
            ORDER BY 1
        """)
        print(f"=== DC LİSTESİ ({len(dc_list)} adet) ===")
        for row in dc_list:
            print(f"  {row['dc_name']}")

        # 2. datacenter_metrics (VMware) — son satır
        vmw = await conn.fetchrow("""
            SELECT datacenter, total_cluster_count, total_host_count, total_vm_count
            FROM public.datacenter_metrics
            ORDER BY timestamp DESC LIMIT 1
        """)
        print(f"\n=== VMware datacenter_metrics (son kayıt) ===")
        print(f"  {dict(vmw)}")

        # 3. nutanix_cluster_metrics — son satır
        ntx = await conn.fetchrow("""
            SELECT cluster_name, datacenter_name, num_nodes
            FROM public.nutanix_cluster_metrics
            ORDER BY collection_time DESC LIMIT 1
        """)
        print(f"\n=== Nutanix nutanix_cluster_metrics (son kayıt) ===")
        print(f"  {dict(ntx)}")

        # 4. ibm_server_general — örnek satır
        ibm = await conn.fetchrow("""
            SELECT server_details_servername
            FROM public.ibm_server_general
            LIMIT 1
        """)
        print(f"\n=== IBM ibm_server_general (örnek) ===")
        print(f"  {dict(ibm)}")

        await conn.close()
    except asyncpg.InvalidPasswordError:
        print("HATA: Parola yanlis.")
    except OSError as e:
        print(f"HATA: Sunucuya ulasilamiyor — {e}")
        print("Kontrol: VPN aktif mi? Port dogru mu?")
    except Exception as e:
        print(f"HATA ({type(e).__name__}): {e}")

asyncio.run(main())
