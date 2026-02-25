CREATE TABLE public.raw_veeam_proxy_datastores (
	id int4 DEFAULT nextval('veeam_proxy_datastores_id_seq'::regclass) NOT NULL,
	proxy_id text NOT NULL,
	datastore_id text NOT NULL,
	source_ip text NOT NULL,
	collection_time timestamptz NULL,
	CONSTRAINT veeam_proxy_datastores_pkey PRIMARY KEY (id),
	CONSTRAINT veeam_proxy_datastores_source_ip_proxy_id_fkey FOREIGN KEY (source_ip,proxy_id) REFERENCES public.raw_veeam_proxies(source_ip,id) ON DELETE CASCADE
);