CREATE TABLE public.raw_panduit_pdu_metrics_hid (
	id int4 DEFAULT nextval('panduit_pdu_metrics_hid_id_seq'::regclass) NOT NULL,
	collection_timestamp timestamptz NOT NULL,
	pdu_id int4 NOT NULL,
	hid_index varchar(10) NOT NULL,
	aisle int4 NULL,
	auto_lock_time int4 NULL,
	door_open_time int4 NULL,
	handle_operation int4 NULL,
	hid_aisle_control int4 NULL,
	max_door_open_time int4 NULL,
	mechanical_lock int4 NULL,
	user_pin_length int4 NULL,
	user_pin_mode int4 NULL,
	CONSTRAINT panduit_pdu_metrics_hid_pkey PRIMARY KEY (id),
	CONSTRAINT uq_panduit_hid_metrics_pdu_timestamp_hid UNIQUE (pdu_id, collection_timestamp, hid_index)
);
CREATE INDEX idx_panduit_hid_metrics_pdu_id_hid_timestamp ON public.raw_panduit_pdu_metrics_hid USING btree (pdu_id, hid_index, collection_timestamp DESC);