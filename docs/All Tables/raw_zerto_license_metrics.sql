CREATE TABLE public.raw_zerto_license_metrics (
	data_type varchar(50) NOT NULL,
	collection_timestamp timestamptz NOT NULL,
	zerto_host varchar(50) DEFAULT ''::character varying NOT NULL,
	id varchar(255) NOT NULL,
	"name" varchar(255) NULL,
	expirationdate varchar(255) NULL,
	license_key varchar(255) NULL,
	license_type varchar(100) NULL,
	is_valid bool NULL,
	max_vms int4 NULL,
	total_vms_count int4 NULL,
	sites_usage jsonb NULL,
	days_until_expiry int4 NULL,
	CONSTRAINT zerto_license_metrics_pkey PRIMARY KEY (id, collection_timestamp)
);