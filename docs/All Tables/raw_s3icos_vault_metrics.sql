CREATE TABLE public.raw_s3icos_vault_metrics (
	id int4 DEFAULT nextval('s3icos_vault_metrics_id_seq'::regclass) NOT NULL,
	collection_timestamp timestamptz NOT NULL,
	vault_id int4 NOT NULL,
	vault_name varchar(255) NULL,
	allotted_size_bytes int8 NULL,
	usable_size_bytes int8 NULL,
	used_physical_size_bytes int8 NULL,
	used_logical_size_bytes int8 NULL,
	object_count_estimate int8 NULL,
	allotment_usage int8 NULL,
	estimate_usable_used_logical_size_bytes int8 NULL,
	estimate_usable_total_logical_size_bytes int8 NULL,
	CONSTRAINT s3icos_vault_metrics_pkey PRIMARY KEY (id)
);
CREATE INDEX idx_vault_metrics_vault_id_timestamp ON public.raw_s3icos_vault_metrics USING btree (vault_id, collection_timestamp DESC);