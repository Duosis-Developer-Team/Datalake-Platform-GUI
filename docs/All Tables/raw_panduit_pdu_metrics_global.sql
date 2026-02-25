CREATE TABLE public.raw_panduit_pdu_metrics_global (
	id int4 DEFAULT nextval('panduit_pdu_metrics_global_id_seq'::regclass) NOT NULL,
	collection_timestamp timestamptz NOT NULL,
	pdu_id int4 NOT NULL,
	pdu_status int4 NULL,
	temperature_scale int4 NULL,
	door_sensor_11_state int4 NULL,
	door_sensor_11_status int4 NULL,
	door_sensor_12_state int4 NULL,
	door_sensor_12_status int4 NULL,
	dry_sensor_11_status int4 NULL,
	dry_sensor_12_status int4 NULL,
	rope_sensor_11_state int4 NULL,
	rope_sensor_11_status int4 NULL,
	rope_sensor_12_state int4 NULL,
	rope_sensor_12_status int4 NULL,
	spot_sensor_11_state int4 NULL,
	spot_sensor_11_status int4 NULL,
	spot_sensor_12_state int4 NULL,
	spot_sensor_12_status int4 NULL,
	CONSTRAINT panduit_pdu_metrics_global_pkey PRIMARY KEY (id),
	CONSTRAINT uq_panduit_global_metrics_pdu_timestamp UNIQUE (pdu_id, collection_timestamp)
);
CREATE INDEX idx_panduit_global_metrics_pdu_id_timestamp ON public.raw_panduit_pdu_metrics_global USING btree (pdu_id, collection_timestamp DESC);