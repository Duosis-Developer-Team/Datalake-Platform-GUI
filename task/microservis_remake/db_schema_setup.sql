CREATE SCHEMA IF NOT EXISTS infra;

CREATE SCHEMA IF NOT EXISTS customer;

CREATE OR REPLACE VIEW customer.v_customer_nutanix_vms AS
SELECT
    vm_name,
    cpu_count,
    memory_capacity,
    disk_capacity,
    host_name,
    cluster_uuid,
    collection_time
FROM public.nutanix_vm_metrics;

CREATE OR REPLACE VIEW customer.v_customer_vmware_vms AS
SELECT
    vmname,
    number_of_cpus,
    total_memory_capacity_gb,
    timestamp,
    datacenter,
    cluster
FROM public.vm_metrics;

CREATE OR REPLACE VIEW customer.v_customer_ibm_lpars AS
SELECT
    lparname,
    lpar_details_servername,
    lpar_processor_currentvirtualprocessors,
    lpar_memory_logicalmem,
    lpar_details_state,
    time
FROM public.ibm_lpar_general;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'infra_svc') THEN
        CREATE USER infra_svc WITH PASSWORD 'InfraSvc@Bulut2026';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'customer_svc') THEN
        CREATE USER customer_svc WITH PASSWORD 'CustomerSvc@Bulut2026';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'query_svc') THEN
        CREATE USER query_svc WITH PASSWORD 'QuerySvc@Bulut2026';
    END IF;
END;
$$;

GRANT USAGE ON SCHEMA public TO infra_svc;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO infra_svc;

GRANT USAGE ON SCHEMA customer TO customer_svc;
GRANT SELECT ON ALL TABLES IN SCHEMA customer TO customer_svc;

GRANT USAGE ON SCHEMA public TO query_svc;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO query_svc;
