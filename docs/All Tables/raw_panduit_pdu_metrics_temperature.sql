CREATE TABLE public.raw_panduit_pdu_metrics_temperature (
	id int4 DEFAULT nextval('panduit_pdu_metrics_temperature_id_seq'::regclass) NOT NULL,
	collection_timestamp timestamptz NOT NULL,
	pdu_id int4 NOT NULL,
	sensor_id varchar(50) NOT NULL,
	value numeric NULL,
	status int4 NULL,
	th_status int4 NULL,
	CONSTRAINT panduit_pdu_metrics_temperature_pkey PRIMARY KEY (id),
	CONSTRAINT uq_panduit_temperature_metrics_pdu_timestamp_sensor UNIQUE (pdu_id, collection_timestamp, sensor_id)
);
CREATE INDEX idx_panduit_temperature_metrics_pdu_id_sensor_timestamp ON public.raw_panduit_pdu_metrics_temperature USING btree (pdu_id, sensor_id, collection_timestamp DESC);