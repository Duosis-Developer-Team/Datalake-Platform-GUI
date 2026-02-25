CREATE TABLE public.raw_vertiv_pdu_electrical_metrics (
	collection_timestamp timestamptz NOT NULL,
	collection_timestamp_unix int8 NOT NULL,
	collection_date date NOT NULL,
	collection_time time NOT NULL,
	pdu_name varchar(255) NOT NULL,
	building varchar(100) NOT NULL,
	room varchar(100) NOT NULL,
	unit varchar(100) NOT NULL,
	host_id varchar(50) NOT NULL,
	host_name varchar(255) NOT NULL,
	display_name varchar(255) NULL,
	ip_address inet NULL,
	host_status varchar(10) NULL,
	status varchar(10) NOT NULL,
	source_system varchar(50) DEFAULT 'zabbix'::character varying NULL,
	item_id varchar(50) NULL,
	item_name varchar(500) NULL,
	item_key varchar(500) NULL,
	value text NULL,
	units varchar(50) NULL,
	value_type int4 NULL,
	last_check int8 NULL,
	circuit_id varchar(50) NULL,
	phase_id varchar(50) NULL,
	outlet_id varchar(50) NULL,
	CONSTRAINT vertiv_pdu_electrical_metrics_pkey PRIMARY KEY (pdu_name, collection_timestamp)
);
CREATE INDEX idx_electrical_building ON public.raw_vertiv_pdu_electrical_metrics USING btree (building);
CREATE INDEX idx_electrical_room ON public.raw_vertiv_pdu_electrical_metrics USING btree (room);
CREATE INDEX idx_electrical_unit ON public.raw_vertiv_pdu_electrical_metrics USING btree (unit);