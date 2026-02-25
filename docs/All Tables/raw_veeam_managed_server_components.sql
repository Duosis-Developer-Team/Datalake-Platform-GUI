CREATE TABLE public.raw_veeam_managed_server_components (
	id int4 DEFAULT nextval('veeam_managed_server_components_id_seq'::regclass) NOT NULL,
	managed_server_id text NOT NULL,
	component_name text NULL,
	port int4 NULL,
	source_ip text NOT NULL,
	collection_time timestamptz NULL,
	CONSTRAINT veeam_managed_server_components_pkey PRIMARY KEY (id),
	CONSTRAINT veeam_managed_server_component_source_ip_managed_server_id_fkey FOREIGN KEY (source_ip,managed_server_id) REFERENCES public.raw_veeam_managed_servers(source_ip,id) ON DELETE CASCADE
);