CREATE TABLE public.raw_veeam_managed_servers (
	id text NOT NULL,
	"name" text NULL,
	description text NULL,
	"type" text NULL,
	status text NULL,
	port int4 NULL,
	credentials_id text NULL,
	vi_host_type text NULL,
	network_port_range_start int4 NULL,
	network_port_range_end int4 NULL,
	network_server_side bool NULL,
	source_ip text NOT NULL,
	collection_time timestamptz NULL,
	CONSTRAINT veeam_managed_servers_pkey PRIMARY KEY (source_ip, id)
);