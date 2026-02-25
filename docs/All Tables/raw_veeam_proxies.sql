CREATE TABLE public.raw_veeam_proxies (
	id text NOT NULL,
	"name" text NULL,
	description text NULL,
	"type" text NULL,
	server_host_id text NULL,
	server_transport_mode text NULL,
	server_failover_to_network bool NULL,
	server_host_to_proxy_encryption bool NULL,
	server_max_task_count int4 NULL,
	server_connected_datastores_auto_select_enabled bool NULL,
	source_ip text NOT NULL,
	collection_time timestamptz NULL,
	CONSTRAINT veeam_proxies_pkey PRIMARY KEY (source_ip, id)
);