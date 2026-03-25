import os
import sys

sys.path.append(os.path.abspath(' services/datacenter-api'))
sys.path.append(os.path.abspath('.'))

import psycopg2
from app.db.connection import get_db

conn = get_db()
cur = conn.cursor()
cur.execute("""
WITH latest AS (
    SELECT storage_ip, MAX("timestamp") AS max_ts
    FROM public.raw_ibm_storage_system
    GROUP BY storage_ip
)
SELECT s.name, s.location, s.capacity, s.allocated_space 
FROM public.raw_ibm_storage_system s
JOIN latest l ON s.storage_ip = l.storage_ip AND s."timestamp" = l.max_ts;
""")
rows = cur.fetchall()
print("IBM Storage Rows:")
for r in rows:
    print(r)
