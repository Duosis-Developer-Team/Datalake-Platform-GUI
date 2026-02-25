CREATE TABLE public.raw_zerto_alert_metrics (
	data_type varchar(50) NOT NULL,
	collection_timestamp timestamptz NOT NULL,
	zerto_host varchar(50) DEFAULT ''::character varying NOT NULL,
	id varchar(255) NOT NULL,
	alert_identifier varchar(255) NULL,
	title varchar(500) NULL,
	description text NULL,
	severity varchar(50) NULL,
	category varchar(100) NULL,
	creation_date timestamptz NULL,
	site_identifier varchar(255) NULL,
	vpg_identifier varchar(255) NULL,
	is_acknowledged bool NULL,
	is_resolved bool NULL,
	related_entities jsonb NULL,
	tags jsonb NULL,
	CONSTRAINT zerto_alert_metrics_pkey PRIMARY KEY (id, collection_timestamp)
);