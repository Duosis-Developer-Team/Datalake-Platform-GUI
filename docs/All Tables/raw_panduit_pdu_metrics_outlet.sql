CREATE TABLE public.raw_panduit_pdu_metrics_outlet (
	id int4 DEFAULT nextval('panduit_pdu_metrics_outlet_id_seq'::regclass) NOT NULL,
	collection_timestamp timestamptz NOT NULL,
	pdu_id int4 NOT NULL,
	outlet_index varchar(20) NOT NULL,
	control_status int4 NULL,
	control_switchable int4 NULL,
	"current" int4 NULL,
	power_factor int4 NULL,
	watts int8 NULL,
	wh int8 NULL,
	CONSTRAINT panduit_pdu_metrics_outlet_pkey PRIMARY KEY (id),
	CONSTRAINT uq_panduit_outlet_metrics_pdu_timestamp_outlet UNIQUE (pdu_id, collection_timestamp, outlet_index)
);
CREATE INDEX idx_panduit_outlet_metrics_pdu_id_outlet_timestamp ON public.raw_panduit_pdu_metrics_outlet USING btree (pdu_id, outlet_index, collection_timestamp DESC);