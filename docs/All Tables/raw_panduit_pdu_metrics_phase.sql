CREATE TABLE public.raw_panduit_pdu_metrics_phase (
	id int4 DEFAULT nextval('panduit_pdu_metrics_phase_id_seq'::regclass) NOT NULL,
	collection_timestamp timestamptz NOT NULL,
	pdu_id int4 NOT NULL,
	phase_index varchar(10) NOT NULL,
	"current" int4 NULL,
	current_percent_load int4 NULL,
	current_rating int4 NULL,
	power_factor int4 NULL,
	power_va int8 NULL,
	power_watts int8 NULL,
	voltage int4 NULL,
	CONSTRAINT panduit_pdu_metrics_phase_pkey PRIMARY KEY (id),
	CONSTRAINT uq_panduit_phase_metrics_pdu_timestamp_phase UNIQUE (pdu_id, collection_timestamp, phase_index)
);
CREATE INDEX idx_panduit_phase_metrics_pdu_id_phase_timestamp ON public.raw_panduit_pdu_metrics_phase USING btree (pdu_id, phase_index, collection_timestamp DESC);