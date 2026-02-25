CREATE TABLE public.raw_panduit_pdu_metrics_input (
	id int4 DEFAULT nextval('panduit_pdu_metrics_input_id_seq'::regclass) NOT NULL,
	collection_timestamp timestamptz NOT NULL,
	pdu_id int4 NOT NULL,
	frequency int4 NULL,
	frequency_status int4 NULL,
	phase_total_current int4 NULL,
	power_factor int4 NULL,
	power_va int8 NULL,
	power_var int8 NULL,
	power_watts int8 NULL,
	resettable_energy int8 NULL,
	total_energy int8 NULL,
	CONSTRAINT panduit_pdu_metrics_input_pkey PRIMARY KEY (id),
	CONSTRAINT uq_panduit_input_metrics_pdu_timestamp UNIQUE (pdu_id, collection_timestamp)
);
CREATE INDEX idx_panduit_input_metrics_pdu_id_timestamp ON public.raw_panduit_pdu_metrics_input USING btree (pdu_id, collection_timestamp DESC);