RACKS_BY_DC = """
SELECT
    r.id,
    r.name,
    r.display_name,
    r.status,
    r.status_description,
    r.u_height,
    r.kabin_enerji,
    r.pdu_a_ip,
    r.pdu_b_ip,
    r.rack_type,
    r.serial,
    r.asset_tag,
    r.tenant_name,
    r.facility_id,
    r.weight,
    r.max_weight,
    r.weight_unit,
    r.description,
    r.comments,
    r.first_observed,
    r.last_observed,
    r.location_id,
    r.site_id,
    l.name AS hall_name
FROM public.discovery_loki_rack r
JOIN public.discovery_loki_location l
    ON r.location_id = l.id::varchar
WHERE (l.name = %s OR l.parent_name = %s)
ORDER BY l.name, r.name
"""

DEVICES_BY_RACK_NAME = """
SELECT DISTINCT ON (d.name)
    d.name,
    d.position,
    d.face_value,
    d.device_role_name,
    d.device_type_name,
    d.status_value,
    d.status_label,
    d.manufacturer_name,
    d.description
FROM loki_devices d
WHERE d.rack_name = %s
  AND d.rack_id IS NOT NULL
ORDER BY d.name, d.collection_time DESC
"""

RACK_SUMMARY_BY_DC = """
SELECT
    COUNT(*) AS total_racks,
    COUNT(*) FILTER (WHERE r.status = 'active') AS active_racks,
    COALESCE(SUM(r.u_height), 0) AS total_u_height,
    COUNT(*) FILTER (WHERE r.kabin_enerji IS NOT NULL AND r.kabin_enerji != '') AS racks_with_energy,
    COUNT(*) FILTER (WHERE r.pdu_a_ip IS NOT NULL AND r.pdu_a_ip != '') AS racks_with_pdu
FROM public.discovery_loki_rack r
JOIN public.discovery_loki_location l
    ON r.location_id = l.id::varchar
WHERE (l.name = %s OR l.parent_name = %s)
"""
