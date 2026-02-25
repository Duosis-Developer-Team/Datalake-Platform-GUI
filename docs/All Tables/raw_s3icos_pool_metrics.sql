CREATE TABLE public.raw_s3icos_pool_metrics (
	id int4 DEFAULT nextval('s3icos_pool_metrics_id_seq'::regclass) NOT NULL,
	collection_timestamp timestamptz NOT NULL,
	vault_id int4 NOT NULL,
	pool_id int4 NOT NULL,
	pool_name varchar(255) NULL,
	usable_size_bytes int8 NULL,
	used_physical_size_bytes int8 NULL,
	used_logical_size_bytes int8 NULL,
	estimate_usable_used_logical_size_bytes int8 NULL,
	estimate_usable_total_logical_size_bytes int8 NULL,
	CONSTRAINT s3icos_pool_metrics_pkey PRIMARY KEY (id)
);
CREATE INDEX idx_pool_metrics_vault_id_pool_id_timestamp ON public.raw_s3icos_pool_metrics USING btree (vault_id, pool_id, collection_timestamp DESC);