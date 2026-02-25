CREATE TABLE public.raw_zerto_site_metrics (
	data_type varchar(50) NOT NULL,
	collection_timestamp timestamptz NOT NULL,
	zerto_host varchar(50) DEFAULT ''::character varying NOT NULL,
	id varchar(255) NOT NULL,
	"name" varchar(255) NULL,
	status int4 NULL,
	ip varchar(50) NULL,
	site_type varchar(100) NULL,
	"version" varchar(100) NULL,
	port int4 NULL,
	is_connected varchar(10) NULL,
	"location" varchar(255) NULL,
	incoming_throughput_mb numeric(10, 4) NULL,
	outgoing_bandwidth_mb numeric(10, 4) NULL,
	provisioned_storage_mb int8 NULL,
	used_storage_mb int8 NULL,
	CONSTRAINT zerto_site_metrics_pkey PRIMARY KEY (id, collection_timestamp)
);