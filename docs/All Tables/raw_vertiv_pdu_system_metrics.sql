CREATE TABLE public.raw_vertiv_pdu_system_metrics (
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
	CONSTRAINT vertiv_pdu_system_metrics_pkey PRIMARY KEY (pdu_name, collection_timestamp)
);
CREATE INDEX idx_system_building ON public.raw_vertiv_pdu_system_metrics USING btree (building);
CREATE INDEX idx_system_room ON public.raw_vertiv_pdu_system_metrics USING btree (room);