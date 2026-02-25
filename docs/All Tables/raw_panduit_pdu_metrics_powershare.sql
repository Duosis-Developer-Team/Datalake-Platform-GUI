CREATE TABLE public.raw_panduit_pdu_metrics_powershare (
	id int4 DEFAULT nextval('panduit_pdu_metrics_powershare_id_seq'::regclass) NOT NULL,
	collection_timestamp timestamptz NOT NULL,
	pdu_id int4 NOT NULL,
	function_status int4 NULL,
	function_upstream_status int4 NULL,
	"input" int4 NULL,
	operation_status int4 NULL,
	CONSTRAINT panduit_pdu_metrics_powershare_pkey PRIMARY KEY (id),
	CONSTRAINT uq_panduit_powershare_metrics_pdu_timestamp UNIQUE (pdu_id, collection_timestamp)
);
CREATE INDEX idx_panduit_powershare_metrics_pdu_id_timestamp ON public.raw_panduit_pdu_metrics_powershare USING btree (pdu_id, collection_timestamp DESC);