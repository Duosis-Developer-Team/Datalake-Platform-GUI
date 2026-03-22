"""S3 (IBM iCOS) SQL query definitions.

Tables:
    - raw_s3icos_pool_metrics  : pool-level metrics per vault
    - raw_s3icos_vault_metrics : vault-level metrics per customer

The reporting rules are:
    - Datacenter perspective: filter pools by pool_name ILIKE '%DC13%' etc.
    - Customer perspective  : filter vaults by vault_name ILIKE '%Boyner%'.
"""

# ---------------------------------------------------------------------------
# Datacenter / pool queries (raw_s3icos_pool_metrics)
# ---------------------------------------------------------------------------

# Pool list for a given DC.
# Params:
#   1) pool_name_pattern (e.g. '%DC13%')
#   2) start_ts
#   3) end_ts
POOL_LIST = """
SELECT DISTINCT pool_name
FROM public.raw_s3icos_pool_metrics
WHERE pool_name ILIKE %s
  AND collection_timestamp BETWEEN %s AND %s
ORDER BY pool_name
"""


# Latest snapshot per pool (usable + used physical capacity).
# Params:
#   1) pool_names[] (text[])
#   2) start_ts
#   3) end_ts
POOL_LATEST = """
WITH per_timestamp AS (
    SELECT
        pool_name,
        collection_timestamp,
        SUM(total_capacity_bytes) AS total_usable,
        SUM(used_capacity_bytes)  AS total_used
    FROM public.raw_s3icos_pool_metrics
    WHERE pool_name = ANY(%s)
      AND collection_timestamp BETWEEN %s AND %s
    GROUP BY pool_name, collection_timestamp
),
ranked AS (
    SELECT
        per_timestamp.*,
        ROW_NUMBER() OVER (PARTITION BY pool_name ORDER BY collection_timestamp DESC) AS rn
    FROM per_timestamp
)
SELECT pool_name, total_usable, total_used, collection_timestamp
FROM ranked
WHERE rn = 1
"""


# First and last snapshot per pool for growth calculation.
# Params:
#   1) pool_names[] (text[])
#   2) start_ts
#   3) end_ts
POOL_FIRST_LAST = """
WITH per_timestamp AS (
    SELECT
        pool_name,
        collection_timestamp,
        SUM(total_capacity_bytes) AS total_usable,
        SUM(used_capacity_bytes)  AS total_used
    FROM public.raw_s3icos_pool_metrics
    WHERE pool_name = ANY(%s)
      AND collection_timestamp BETWEEN %s AND %s
    GROUP BY pool_name, collection_timestamp
),
ranked AS (
    SELECT
        per_timestamp.*,
        ROW_NUMBER() OVER (PARTITION BY pool_name ORDER BY collection_timestamp ASC)  AS rn_first,
        ROW_NUMBER() OVER (PARTITION BY pool_name ORDER BY collection_timestamp DESC) AS rn_last
    FROM per_timestamp
)
SELECT
    pool_name,
    MAX(CASE WHEN rn_first = 1 THEN total_used  END) AS first_used,
    MAX(CASE WHEN rn_last  = 1 THEN total_used  END) AS last_used,
    MAX(CASE WHEN rn_first = 1 THEN collection_timestamp END) AS first_ts,
    MAX(CASE WHEN rn_last  = 1 THEN collection_timestamp END) AS last_ts
FROM ranked
GROUP BY pool_name
"""


# ---------------------------------------------------------------------------
# Customer / vault queries (raw_s3icos_vault_metrics)
# ---------------------------------------------------------------------------

# Vault list for a given customer.
# Params:
#   1) vault_name_pattern (e.g. '%Boyner%')
#   2) start_ts
#   3) end_ts
VAULT_LIST = """
SELECT DISTINCT vault_name
FROM public.raw_s3icos_vault_metrics
WHERE vault_name ILIKE %s
  AND collection_timestamp BETWEEN %s AND %s
ORDER BY vault_name
"""


VAULT_LATEST = """
WITH latest_metrics AS (
    SELECT
        vault_id,
        vault_name,
        collection_timestamp,
        estimate_usable_used_logical_size_bytes AS used_logical_bytes
    FROM public.raw_s3icos_vault_metrics
    WHERE vault_name = ANY(%s)
      AND collection_timestamp BETWEEN %s AND %s
),
ranked AS (
    SELECT
        latest_metrics.*,
        ROW_NUMBER() OVER (PARTITION BY vault_id ORDER BY collection_timestamp DESC) AS rn
    FROM latest_metrics
),
latest_snapshot AS (
    SELECT *
    FROM ranked
    WHERE rn = 1
)
SELECT
    ls.vault_id,
    ls.vault_name,
    vi.hard_quota_bytes,
    ls.used_logical_bytes,
    ls.collection_timestamp
FROM latest_snapshot ls
LEFT JOIN LATERAL (
    SELECT hard_quota_bytes
    FROM public.raw_s3icos_vault_inventory
    WHERE vault_id = ls.vault_id
      AND collection_timestamp <= ls.collection_timestamp
    ORDER BY collection_timestamp DESC
    LIMIT 1
) AS vi ON TRUE
"""


VAULT_FIRST_LAST = """
WITH per_timestamp AS (
    SELECT
        vault_id,
        vault_name,
        collection_timestamp,
        SUM(estimate_usable_used_logical_size_bytes) AS used_logical_bytes
    FROM public.raw_s3icos_vault_metrics
    WHERE vault_name = ANY(%s)
      AND collection_timestamp BETWEEN %s AND %s
    GROUP BY vault_id, vault_name, collection_timestamp
),
ranked AS (
    SELECT
        per_timestamp.*,
        ROW_NUMBER() OVER (PARTITION BY vault_id ORDER BY collection_timestamp ASC)  AS rn_first,
        ROW_NUMBER() OVER (PARTITION BY vault_id ORDER BY collection_timestamp DESC) AS rn_last
    FROM per_timestamp
),
first_last AS (
    SELECT
        vault_id,
        vault_name,
        MAX(CASE WHEN rn_first = 1 THEN used_logical_bytes END) AS first_used,
        MAX(CASE WHEN rn_last  = 1 THEN used_logical_bytes END) AS last_used,
        MAX(CASE WHEN rn_first = 1 THEN collection_timestamp END) AS first_ts,
        MAX(CASE WHEN rn_last  = 1 THEN collection_timestamp END) AS last_ts
    FROM ranked
    GROUP BY vault_id, vault_name
)
SELECT
    fl.vault_id,
    fl.vault_name,
    fl.first_used,
    fl.last_used,
    fl.first_ts,
    fl.last_ts,
    vi.hard_quota_bytes
FROM first_last fl
LEFT JOIN LATERAL (
    SELECT hard_quota_bytes
    FROM public.raw_s3icos_vault_inventory
    WHERE vault_id = fl.vault_id
    ORDER BY collection_timestamp DESC
    LIMIT 1
) AS vi ON TRUE
"""

