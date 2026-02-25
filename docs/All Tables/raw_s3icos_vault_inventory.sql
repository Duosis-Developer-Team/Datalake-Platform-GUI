CREATE TABLE public.raw_s3icos_vault_inventory (
	id int4 DEFAULT nextval('s3icos_vault_inventory_id_seq'::regclass) NOT NULL,
	collection_timestamp timestamptz NOT NULL,
	vault_id int4 NOT NULL,
	vault_name varchar(255) NULL,
	"uuid" varchar(255) NULL,
	description text NULL,
	"type" varchar(50) NULL,
	width int4 NULL,
	threshold int4 NULL,
	write_threshold int4 NULL,
	privacy_enabled bool NULL,
	vault_purpose varchar(50) NULL,
	soft_quota_bytes int8 NULL,
	hard_quota_bytes int8 NULL,
	CONSTRAINT s3icos_vault_inventory_pkey PRIMARY KEY (id)
);
CREATE INDEX idx_vault_inventory_vault_id_timestamp ON public.raw_s3icos_vault_inventory USING btree (vault_id, collection_timestamp DESC);