# SQL queries for ServiceCore ITSM data endpoints.
#
# Customer resolution chain (no DDL changes to datalake tables):
#   customer_name → email_needle → discovery_servicecore_users.user_id
#   → discovery_servicecore_incidents.org_user_id  (BIGINT, indexed)
#   → discovery_servicecore_servicerequests.requester_id (BIGINT, indexed)
#
# Resolution-time KPI is computed for INCIDENTS only (closed_and_done_date exists).
# Service Requests have no close-timestamp; they use state_text for open/closed counts
# and target_resolution_date < NOW() for SLA breach detection.

# ---------------------------------------------------------------------------
# Shared base CTE — reused across all three endpoints via string interpolation.
# Params for this fragment: (email_needle, start_ts, end_ts, start_ts, end_ts)
# ---------------------------------------------------------------------------

_CUSTOMER_TICKETS_CTE = """
WITH customer_users AS (
    SELECT user_id, full_name, email
    FROM   discovery_servicecore_users
    WHERE  email ILIKE %(needle)s
      AND  COALESCE(is_enabled,    TRUE) = TRUE
      AND  COALESCE(soft_deleted, FALSE) = FALSE
),
customer_tickets AS (
    -- Incidents ---------------------------------------------------------
    SELECT
        'incident'::TEXT                                                   AS source,
        i.ticket_id                                                        AS id,
        i.subject,
        COALESCE(i.state_text, i.status_name)                             AS stage,
        i.state_text,
        i.status_name,
        i.priority_name,
        i.category_name,
        i.org_users_name                                                   AS customer_user,
        i.agent_group_name,
        i.created_date                                                     AS opened_at,
        i.target_resolution_date,
        i.closed_and_done_date,
        CASE
            WHEN i.closed_and_done_date IS NOT NULL
            THEN EXTRACT(EPOCH FROM (i.closed_and_done_date - i.created_date)) / 3600.0
            ELSE NULL
        END                                                                AS resolution_hours,
        CASE
            WHEN i.closed_and_done_date IS NULL
            THEN EXTRACT(EPOCH FROM (NOW() - i.created_date)) / 86400.0
            ELSE NULL
        END                                                                AS open_age_days
    FROM   discovery_servicecore_incidents i
    JOIN   customer_users u ON u.user_id = i.org_user_id
    WHERE  i.created_date BETWEEN %(start_ts)s AND %(end_ts)s
      AND  COALESCE(i.is_deleted, FALSE) = FALSE

    UNION ALL

    -- Service Requests --------------------------------------------------
    SELECT
        'servicerequest'::TEXT,
        sr.service_request_id,
        COALESCE(sr.subject, sr.service_request_name),
        COALESCE(sr.state_text, sr.status_name),
        sr.state_text,
        sr.status_name,
        sr.priority_name,
        COALESCE(sr.category_name, sr.service_category_name),
        COALESCE(sr.requester_full_name, sr.org_users_name),
        sr.agent_group_name,
        sr.request_date,
        sr.target_resolution_date,
        NULL::TIMESTAMPTZ,     -- SR has no closed_and_done_date
        NULL::FLOAT,           -- resolution_hours only for incidents
        CASE
            WHEN COALESCE(sr.state_text, sr.status_name) NOT IN ('Closed', 'Done', 'Resolved')
            THEN EXTRACT(EPOCH FROM (NOW() - sr.request_date)) / 86400.0
            ELSE NULL
        END
    FROM   discovery_servicecore_servicerequests sr
    JOIN   customer_users u ON u.user_id = sr.requester_id
    WHERE  sr.request_date BETWEEN %(start_ts)s AND %(end_ts)s
      AND  COALESCE(sr.is_deleted, FALSE) = FALSE
)
"""

# ---------------------------------------------------------------------------
# /customers/{name}/itsm/summary
# Params dict: {needle, start_ts, end_ts}
# ---------------------------------------------------------------------------

ITSM_SUMMARY = (
    _CUSTOMER_TICKETS_CTE
    + """
, stats AS (
    SELECT
        COUNT(*)                                                           AS total_count,
        COUNT(*) FILTER (WHERE source = 'incident')                       AS incident_count,
        COUNT(*) FILTER (WHERE source = 'servicerequest')                 AS sr_count,
        -- Incidents
        COUNT(*) FILTER (WHERE source = 'incident' AND closed_and_done_date IS NULL)     AS incident_open,
        COUNT(*) FILTER (WHERE source = 'incident' AND closed_and_done_date IS NOT NULL) AS incident_closed,
        -- Service Requests (open = not in terminal state)
        COUNT(*) FILTER (
            WHERE source = 'servicerequest'
              AND COALESCE(state_text, status_name) NOT IN ('Closed', 'Done', 'Resolved')
        )                                                                  AS sr_open,
        COUNT(*) FILTER (
            WHERE source = 'servicerequest'
              AND COALESCE(state_text, status_name) IN ('Closed', 'Done', 'Resolved')
        )                                                                  AS sr_closed,
        -- Resolution time (incidents only, closed only)
        AVG(resolution_hours)                                             AS avg_resolution_hours,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY resolution_hours)     AS median_resolution_hours,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY resolution_hours)    AS p95_resolution_hours,
        STDDEV_SAMP(resolution_hours)                                      AS stddev_resolution_hours,
        -- SLA breach: open and past target date (both types)
        COUNT(*) FILTER (
            WHERE closed_and_done_date IS NULL
              AND COALESCE(state_text, status_name) NOT IN ('Closed', 'Done', 'Resolved')
              AND target_resolution_date IS NOT NULL
              AND target_resolution_date < NOW()
        )                                                                  AS sla_breach_count
    FROM customer_tickets
),
priority_dist AS (
    SELECT priority_name, COUNT(*) AS cnt
    FROM   customer_tickets
    WHERE  priority_name IS NOT NULL
    GROUP BY priority_name
    ORDER BY cnt DESC
),
state_dist AS (
    SELECT COALESCE(stage, 'Unknown') AS stage_label, COUNT(*) AS cnt
    FROM   customer_tickets
    GROUP BY stage_label
    ORDER BY cnt DESC
),
top_category AS (
    SELECT category_name, COUNT(*) AS cnt
    FROM   customer_tickets
    WHERE  category_name IS NOT NULL
    GROUP BY category_name
    ORDER BY cnt DESC
    LIMIT 1
)
SELECT
    s.total_count,
    s.incident_count,
    s.sr_count,
    s.incident_open,
    s.incident_closed,
    s.sr_open,
    s.sr_closed,
    s.avg_resolution_hours,
    s.median_resolution_hours,
    s.p95_resolution_hours,
    s.stddev_resolution_hours,
    s.sla_breach_count,
    (SELECT category_name FROM top_category)   AS top_category,
    (
        SELECT json_agg(json_build_object('priority', priority_name, 'count', cnt) ORDER BY cnt DESC)
        FROM priority_dist
    )                                          AS priority_distribution,
    (
        SELECT json_agg(json_build_object('stage', stage_label, 'count', cnt) ORDER BY cnt DESC)
        FROM state_dist
    )                                          AS state_distribution
FROM stats s
"""
)

# ---------------------------------------------------------------------------
# /customers/{name}/itsm/extremes
# Params dict: {needle, start_ts, end_ts}
# Returns two result-sets merged:  source_list IN ('long_tail', 'sla_breach')
# ---------------------------------------------------------------------------

ITSM_EXTREMES = (
    _CUSTOMER_TICKETS_CTE
    + """
, incident_stats AS (
    SELECT
        AVG(resolution_hours)        AS avg_rh,
        STDDEV_SAMP(resolution_hours) AS std_rh
    FROM customer_tickets
    WHERE source = 'incident' AND resolution_hours IS NOT NULL
)
SELECT
    'long_tail'::TEXT                                   AS extreme_type,
    t.source,
    t.id,
    t.subject,
    t.stage,
    t.priority_name,
    t.customer_user,
    t.agent_group_name,
    t.opened_at,
    t.target_resolution_date,
    t.closed_and_done_date,
    t.resolution_hours,
    t.open_age_days,
    s.avg_rh                                            AS threshold_avg,
    s.std_rh                                            AS threshold_stddev,
    (s.avg_rh + COALESCE(s.std_rh, 0))                 AS threshold_value
FROM customer_tickets t
CROSS JOIN incident_stats s
WHERE t.source = 'incident'
  AND t.resolution_hours IS NOT NULL
  AND t.resolution_hours > (s.avg_rh + COALESCE(s.std_rh, 0))

UNION ALL

SELECT
    'sla_breach'::TEXT,
    t.source,
    t.id,
    t.subject,
    t.stage,
    t.priority_name,
    t.customer_user,
    t.agent_group_name,
    t.opened_at,
    t.target_resolution_date,
    t.closed_and_done_date,
    t.resolution_hours,
    t.open_age_days,
    NULL::FLOAT,
    NULL::FLOAT,
    NULL::FLOAT
FROM customer_tickets t
WHERE t.closed_and_done_date IS NULL
  AND COALESCE(t.state_text, t.status_name) NOT IN ('Closed', 'Done', 'Resolved')
  AND t.target_resolution_date IS NOT NULL
  AND t.target_resolution_date < NOW()

ORDER BY extreme_type, resolution_hours DESC NULLS LAST, open_age_days DESC NULLS LAST
"""
)

# ---------------------------------------------------------------------------
# /customers/{name}/itsm/tickets
# Params dict: {needle, start_ts, end_ts}
# ---------------------------------------------------------------------------

ITSM_TICKETS = (
    _CUSTOMER_TICKETS_CTE
    + """
SELECT
    source,
    id,
    subject,
    stage,
    state_text,
    status_name,
    priority_name,
    category_name,
    customer_user,
    agent_group_name,
    opened_at,
    target_resolution_date,
    closed_and_done_date,
    resolution_hours,
    open_age_days
FROM customer_tickets
ORDER BY source, opened_at DESC NULLS LAST
"""
)
