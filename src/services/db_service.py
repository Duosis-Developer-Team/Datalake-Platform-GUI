import os
import psycopg2
from psycopg2 import OperationalError
from functools import lru_cache

class DatabaseService:
    def __init__(self):
        self.db_host = os.getenv("DB_HOST", "10.134.16.6")  # <-- Resimdeki Host IP
        self.db_port = os.getenv("DB_PORT", "5000")         # <-- DİKKAT! 5432 DEĞİL, 5000!
        self.db_name = os.getenv("DB_NAME", "bulutlake")    # <-- Resimdeki Database Name
        self.db_user = os.getenv("DB_USER", "bulutlake")    # <-- Resimdeki Username
        self.db_pass = os.getenv("DB_PASS")

    # Establish connection
    def _get_connection(self):
        """
        Establishes a connection to the PostgreSQL database.
        Returns the connection object or None if connection fails.
        """
        try:
            conn = psycopg2.connect(
                host=self.db_host,
                port=self.db_port,
                dbname=self.db_name,
                user=self.db_user,
                password=self.db_pass
            )
            return conn
        except OperationalError as e:
            print(f"Error connecting to database: {e}")
            return None

    # Helper: Execute Single Row from Cursor
    def _execute_query_single(self, cursor, sql, params=None):
        try:
            cursor.execute(sql, params)
            return cursor.fetchone()
        except Exception as e:
            print(f"Error executing query (single): {e}")
            return None

    # Helper: Execute Single Value from Cursor
    def _execute_query_value(self, cursor, sql, params=None):
        result = self._execute_query_single(cursor, sql, params)
        if result and result[0] is not None:
            return result[0]
        return 0

    # --- NUTANIX QUERIES (SECTION 4.A) ---
    def get_nutanix_host_count(self, cursor, dc_param):
        """Returns num_nodes (Host Count) from nutanix_cluster_metrics."""
        sql = """
        SELECT num_nodes 
        FROM public.nutanix_cluster_metrics 
        WHERE cluster_name LIKE %s 
        ORDER BY collection_time DESC LIMIT 1
        """
        return self._execute_query_value(cursor, sql, (dc_param,))

    def get_nutanix_memory(self, cursor, dc_param):
        """Returns (total_memory_capacity, used_memory) from nutanix_cluster_metrics."""
        sql = """
        SELECT 
          total_memory_capacity, 
          ((memory_usage_avg / 1000 ) * total_memory_capacity) / 1000 
        FROM nutanix_cluster_metrics 
        WHERE cluster_name LIKE %s 
        ORDER BY collection_time DESC LIMIT 1
        """
        return self._execute_query_single(cursor, sql, (dc_param,))

    def get_nutanix_storage(self, cursor, dc_param):
        """Returns (storage_capacity, storage_usage) from nutanix_cluster_metrics."""
        sql = """
        SELECT 
          storage_capacity / 2, 
          storage_usage / 2 
        FROM nutanix_cluster_metrics 
        WHERE cluster_name LIKE %s 
        ORDER BY collection_time DESC LIMIT 1
        """
        return self._execute_query_single(cursor, sql, (dc_param,))

    def get_nutanix_cpu(self, cursor, dc_param):
        """Returns (total_cpu_capacity, used_cpu) from nutanix_cluster_metrics."""
        sql = """
        SELECT 
          total_cpu_capacity, 
          (cpu_usage_avg * total_cpu_capacity) / 1000000 
        FROM nutanix_cluster_metrics 
        WHERE cluster_name LIKE %s 
        ORDER BY collection_time DESC LIMIT 1
        """
        return self._execute_query_single(cursor, sql, (dc_param,))

    # --- VMWARE QUERIES (SECTION 4.B) ---
    def get_vmware_counts(self, cursor, dc_param):
        """Returns (total_cluster_count, total_host_count, total_vm_count) from datacenter_metrics."""
        sql = """
        SELECT total_cluster_count, total_host_count, total_vm_count 
        FROM public.datacenter_metrics 
        WHERE datacenter ILIKE %s 
        ORDER BY timestamp DESC LIMIT 1
        """
        return self._execute_query_single(cursor, sql, (dc_param,))

    def get_vmware_memory(self, cursor, dc_param):
        """Returns (total_memory_capacity_bytes, total_memory_used_bytes) from datacenter_metrics."""
        sql = """
        SELECT 
          total_memory_capacity_gb * 1024*1024*1024, 
          total_memory_used_gb * 1024*1024*1024 
        FROM datacenter_metrics 
        WHERE datacenter ILIKE %s 
        ORDER BY timestamp DESC LIMIT 1
        """
        return self._execute_query_single(cursor, sql, (dc_param,))

    def get_vmware_storage(self, cursor, dc_param):
        """Returns (total_storage_capacity_bytes, total_used_storage_bytes) from datacenter_metrics."""
        sql = """
        SELECT 
          total_storage_capacity_gb*(1024*1024), 
          total_used_storage_gb*(1024*1024) 
        FROM datacenter_metrics 
        WHERE datacenter ILIKE %s 
        ORDER BY timestamp DESC LIMIT 1
        """
        return self._execute_query_single(cursor, sql, (dc_param,))

    def get_vmware_cpu(self, cursor, dc_param):
        """Returns (total_cpu_hz_capacity, total_cpu_hz_used) from datacenter_metrics."""
        sql = """
        SELECT 
          total_cpu_ghz_capacity * 1000000000, 
          total_cpu_ghz_used * 1000000000 
        FROM datacenter_metrics 
        WHERE datacenter ILIKE %s 
        ORDER BY timestamp DESC LIMIT 1
        """
        return self._execute_query_single(cursor, sql, (dc_param,))

    # --- IBM POWER (HMC) QUERIES (SECTION 4.C) ---
    def get_ibm_host_count(self, cursor, dc_param):
        """Returns host count from ibm_server_general."""
        sql = """
        SELECT COUNT(DISTINCT server_details_servername) 
        FROM public.ibm_server_general 
        WHERE server_details_servername LIKE %s
        """
        return self._execute_query_value(cursor, sql, (dc_param,))

    # --- ENERGY QUERIES (SECTION 4.D) ---
    def get_racks_energy(self, cursor, dc_param):
        """Returns total energy from loki_racks."""
        # DÜZELTİLMİŞ SQL: 
        # 1. replace(..., ',', '.') -> Virgülü noktaya çevirir.
        # 2. regexp_replace(..., '[^0-9.]', '', 'g') -> Sayı ve nokta dışındaki her şeyi siler (W, kw, boşluk vs).
        # 3. NULLIF(..., '') -> Eğer temizlik sonrası boş kalırsa hata verme, NULL yap.
        
        sql = r"""
        SELECT SUM(
            CASE 
                WHEN kabin_enerji ~ '^[0-9]+(\.[0-9]+)?$' THEN kabin_enerji::float 
                ELSE NULLIF(regexp_replace(replace(kabin_enerji, ',', '.'), '[^0-9.]', '', 'g'), '')::float 
            END * 1000
        ) 
        FROM loki_racks 
        WHERE location_name = %s 
          AND id IN (SELECT DISTINCT id FROM loki_racks)
        """
        
        # GÜVENLİK KORUMASI:
        # Bu sorgu çok hassas olduğu için try-except içine alıyoruz.
        # Böylece tek bir satır bozuk diye tüm Dashboard çökmez.
        try:
            val = self._execute_query_value(cursor, sql, (dc_param,))
            return val if val is not None else 0
        except Exception as e:
            print(f"⚠️ Energy Query Warning for {dc_param}: {e}")
            return 0

    def get_ibm_energy(self, cursor, dc_param):
        """Returns total energy from ibm_server_power_sum."""
        sql = """
        SELECT sum(power_watts) FROM ibm_server_power_sum WHERE server_name ILIKE %s
        """
        return self._execute_query_value(cursor, sql, (dc_param,))

    def get_vcenter_energy(self, cursor, dc_param):
        """Returns total energy from vmhost_metrics."""
        # Using Common Table Expression (CTE) inside the query
        sql = """
        WITH latest_per_host AS (
          SELECT DISTINCT ON (vm.vmhost) vm.power_usage
          FROM public.vmhost_metrics vm 
          WHERE vmhost ILIKE %s 
          ORDER BY vm.vmhost, vm."timestamp" DESC
        )
        SELECT SUM(power_usage) FROM latest_per_host
        """
        return self._execute_query_value(cursor, sql, (dc_param,))

    # --- AGGREGATION LOGIC (PHASE 4 - SPEC SECTION 5) ---
    def get_dc_details(self, dc_code):
        """
        Aggregates data for a specific DC.
        Performs unit normalization and handling of partial data.
        """
        conn = self._get_connection()
        if not conn:
            # Return empty structure if DB fails completely
            # Minimal Safe Dict to prevent crashes
            return {
                "meta": {"name": dc_code, "location": "DB Error"},
                "intel": {"clusters": 0, "hosts": 0, "vms": 0, "cpu_cap": 0, "cpu_used": 0, "ram_cap": 0, "ram_used": 0, "storage_cap": 0, "storage_used": 0},
                "power": {"hosts": 0, "vms": 0, "cpu": 0, "ram": 0},
                "energy": {"total_kw": 0}
            }

        try:
            with conn: # Transaction block
                with conn.cursor() as cursor:
                    dc_param_wildcard = f"%{dc_code}%"
                    
                    # 1. Fetch RAW Data using SHARED CURSOR
                    # Nutanix
                    nutanix_host_count = self.get_nutanix_host_count(cursor, dc_param_wildcard)
                    nutanix_mem = self.get_nutanix_memory(cursor, dc_param_wildcard) or (0, 0)
                    nutanix_storage = self.get_nutanix_storage(cursor, dc_param_wildcard) or (0, 0)
                    nutanix_cpu = self.get_nutanix_cpu(cursor, dc_param_wildcard) or (0, 0)
                    
                    # VMware
                    vmware_counts = self.get_vmware_counts(cursor, dc_param_wildcard) or (0, 0, 0) # cluster, host, vm
                    vmware_mem = self.get_vmware_memory(cursor, dc_param_wildcard) or (0, 0) # bytes
                    vmware_storage = self.get_vmware_storage(cursor, dc_param_wildcard) or (0, 0) # bytes
                    vmware_cpu = self.get_vmware_cpu(cursor, dc_param_wildcard) or (0, 0) # hz
                    
                    # IBM Power
                    power_hosts = self.get_ibm_host_count(cursor, dc_param_wildcard)
                    
                    # Energy (Passed exactly for Racks if needed, or wildcard)
                    # Racks SQL uses '=' so we pass dc_code exactly
                    racks_w = self.get_racks_energy(cursor, dc_code)
                    ibm_w = self.get_ibm_energy(cursor, dc_param_wildcard)
                    vcenter_w = self.get_vcenter_energy(cursor, dc_param_wildcard)
                    
                    # 2. Aggregations & Normalization
                    
                    # Memory -> Target GB
                    # Nutanix Raw is TB (Spec 4.A.2) -> * 1024
                    # VMware Raw is Bytes -> / 1024^3
                    n_mem_cap_gb = (nutanix_mem[0] or 0) * 1024
                    n_mem_used_gb = (nutanix_mem[1] or 0) * 1024
                    v_mem_cap_gb = (vmware_mem[0] or 0) / (1024**3)
                    v_mem_used_gb = (vmware_mem[1] or 0) / (1024**3)
                    
                    total_mem_cap_gb = n_mem_cap_gb + v_mem_cap_gb
                    total_mem_used_gb = n_mem_used_gb + v_mem_used_gb
                    
                    # Storage -> Target TB
                    # Nutanix Raw is TB (Spec 4.A.3) -> No change
                    # VMware Raw is Bytes -> / 1024^4
                    n_stor_cap_tb = (nutanix_storage[0] or 0)
                    n_stor_used_tb = (nutanix_storage[1] or 0)
                    v_stor_cap_tb = (vmware_storage[0] or 0) / (1024**4)
                    v_stor_used_tb = (vmware_storage[1] or 0) / (1024**4)
                    
                    total_stor_cap_tb = n_stor_cap_tb + v_stor_cap_tb
                    total_stor_used_tb = n_stor_used_tb + v_stor_used_tb
                    
                    # CPU -> Target GHz
                    # Nutanix Raw is GHz (Spec 4.A.4) -> No change
                    # VMware Raw is Hz -> / 1e9
                    n_cpu_cap_ghz = (nutanix_cpu[0] or 0)
                    n_cpu_used_ghz = (nutanix_cpu[1] or 0)
                    v_cpu_cap_ghz = (vmware_cpu[0] or 0) / 1000000000
                    v_cpu_used_ghz = (vmware_cpu[1] or 0) / 1000000000
                    
                    total_cpu_cap_ghz = n_cpu_cap_ghz + v_cpu_cap_ghz
                    total_cpu_used_ghz = n_cpu_used_ghz + v_cpu_used_ghz
                    
                    # Counts
                    # Nutanix Cluster count not available in query, using VMware only for clusters + Nutanix Host implies >=1?
                    # Leaving clusters as VMware count for safety
                    total_clusters = (vmware_counts[0] or 0) 
                    intel_hosts = (nutanix_host_count or 0) + (vmware_counts[1] or 0)
                    intel_vms = (vmware_counts[2] or 0)
                    
                    # Energy -> Target kW
                    # FIX: PostgreSQL'den gelen 'Decimal' verisini 'float'a çeviriyoruz.
                    # Böylece "Decimal / float" hatası almayacağız.
                    racks_w_float = float(racks_w or 0)
                    ibm_w_float = float(ibm_w or 0)
                    vcenter_w_float = float(vcenter_w or 0)
                    
                    total_energy_w = racks_w_float + ibm_w_float + vcenter_w_float
                    total_energy_kw = total_energy_w / 1000.0
                    
                    # Locations Map
                    loc_map = {
                        "AZ11": "Azerbaycan", "DC11": "Istanbul", "DC13": "Istanbul", "ICT11": "Almanya"
                    }
                    
                    return {
                        "meta": {
                            "name": dc_code, 
                            "location": loc_map.get(dc_code, "Unknown Data Center")
                        },
                        "intel": {
                            "clusters": int(total_clusters),
                            "hosts": int(intel_hosts),
                            "vms": int(intel_vms),
                            "cpu_cap": round(total_cpu_cap_ghz, 2),
                            "cpu_used": round(total_cpu_used_ghz, 2),
                            "ram_cap": round(total_mem_cap_gb, 2),
                            "ram_used": round(total_mem_used_gb, 2),
                            "storage_cap": round(total_stor_cap_tb, 2),
                            "storage_used": round(total_stor_used_tb, 2)
                        },
                        "power": {
                            "hosts": int(power_hosts or 0),
                            "vms": 0, "cpu": 0, "ram": 0
                        },
                        "energy": {
                            "total_kw": round(total_energy_kw, 2)
                        }
                    }
        finally:
            conn.close()

    @lru_cache(maxsize=10)
    def get_all_datacenters_summary(self):
        """
        Iterates over all defined DCs and returns summary list for Datacenters Page.
        """
        dc_list = ['AZ11', 'DC11', 'DC12', 'DC13', 'DC14', 'DC15', 'DC16', 'DC17', 'ICT11']
        summary_list = []
        
        for dc in dc_list:
            d = self.get_dc_details(dc)
            
            # Extract totals
            tot_hosts = d["intel"]["hosts"] + d["power"]["hosts"]
            tot_vms = d["intel"]["vms"] + d["power"]["vms"] # Power VMs 0 for now
            tot_clusters = d["intel"]["clusters"]
            
            # Format Stats Strings
            cpu_txt = f"{d['intel']['cpu_used']:,} / {d['intel']['cpu_cap']:,} GHz"
            ram_txt = f"{d['intel']['ram_used']:,} / {d['intel']['ram_cap']:,} GB"
            stor_txt = f"{d['intel']['storage_used']:,} / {d['intel']['storage_cap']:,} TB"
            
            # Calculate percentages
            cpu_pct = (d['intel']['cpu_used'] / d['intel']['cpu_cap'] * 100) if d['intel']['cpu_cap'] > 0 else 0
            ram_pct = (d['intel']['ram_used'] / d['intel']['ram_cap'] * 100) if d['intel']['ram_cap'] > 0 else 0
            stor_pct = (d['intel']['storage_used'] / d['intel']['storage_cap'] * 100) if d['intel']['storage_cap'] > 0 else 0
            
            summary_list.append({
                "id": dc,
                "name": dc,
                "location": d["meta"]["location"],
                "status": "Healthy", # Mock status for now
                "cluster_count": tot_clusters,
                "host_count": tot_hosts,
                "vm_count": tot_vms,
                "stats": {
                    "total_cpu": cpu_txt,
                    "used_cpu_pct": round(cpu_pct, 1),
                    "total_ram": ram_txt,
                    "used_ram_pct": round(ram_pct, 1),
                    "total_storage": stor_txt,
                    "used_storage_pct": round(stor_pct, 1),
                    "last_updated": "Live",
                    "total_energy_kw": d["energy"]["total_kw"] # Embedding for global sum
                }
            })

        print(f"🔥 DEBUG LIST DATA (First Item): {summary_list[0] if summary_list else 'EMPTY LIST'}")
            
        return summary_list

    @lru_cache(maxsize=1)
    def get_global_overview(self):
        """Returns global totals for Home Page."""
        summaries = self.get_all_datacenters_summary()
        
        total_hosts = sum(s["host_count"] for s in summaries)
        total_vms = sum(s["vm_count"] for s in summaries)
        total_energy = sum(s["stats"]["total_energy_kw"] for s in summaries)
        
        result = {
            "total_hosts": total_hosts,
            "total_vms": total_vms,
            "total_energy_kw": round(total_energy, 2),
            "dc_count": len(summaries)
        }
        print(f"🔥 DEBUG GLOBAL DATA: {result}") 
        # ----------------------
        
        return result
