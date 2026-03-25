import sys, os
sys.path.append(os.path.abspath('services/datacenter-api'))
sys.path.append(os.path.abspath('.'))

try:
    from app.core.config import settings
    import psycopg2
    conn = psycopg2.connect(str(settings.DATABASE_URL).replace("+psycopg2", ""))
    cur = conn.cursor()
    cur.execute("SELECT name, location, capacity, allocated_space FROM public.raw_ibm_storage_system LIMIT 10")
    rows = cur.fetchall()
    print("ROWS:")
    for r in rows:
        print(r)
except Exception as e:
    print("ERROR:", e)
