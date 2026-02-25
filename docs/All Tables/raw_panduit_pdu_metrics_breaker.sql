CREATE TABLE public.raw_panduit_pdu_metrics_breaker (
	id int4 DEFAULT nextval('panduit_pdu_metrics_breaker_id_seq'::regclass) NOT NULL,
	collection_timestamp timestamptz NOT NULL,
	pdu_id int4 NOT NULL,
	breaker_index varchar(10) NOT NULL,
	breaker_status int4 NULL,
	"current" int4 NULL,
	current_percent_load int4 NULL,
	current_rating int4 NULL,
	power_factor int4 NULL,
	power_va int8 NULL,
	power_watts int8 NULL,
	voltage int4 NULL,
	CONSTRAINT panduit_pdu_metrics_breaker_pkey PRIMARY KEY (id),
	CONSTRAINT uq_panduit_breaker_metrics_pdu_timestamp_breaker UNIQUE (pdu_id, collection_timestamp, breaker_index)
);
CREATE INDEX idx_panduit_breaker_metrics_pdu_id_breaker_timestamp ON public.raw_panduit_pdu_metrics_breaker USING btree (pdu_id, breaker_index, collection_timestamp DESC);