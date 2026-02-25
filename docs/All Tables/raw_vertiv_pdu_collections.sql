CREATE TABLE public.raw_vertiv_pdu_collections (
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
	CONSTRAINT vertiv_pdu_collections_pkey PRIMARY KEY (pdu_name, collection_timestamp)
);
CREATE INDEX idx_collections_building ON public.raw_vertiv_pdu_collections USING btree (building);
CREATE INDEX idx_collections_room ON public.raw_vertiv_pdu_collections USING btree (room);
CREATE INDEX idx_collections_unit ON public.raw_vertiv_pdu_collections USING btree (unit);
CREATE INDEX vertiv_pdu_collections_collection_timestamp_idx ON public.raw_vertiv_pdu_collections USING btree (collection_timestamp DESC);

-- Table Triggers

create trigger ts_insert_blocker before
insert
    on
    public.raw_vertiv_pdu_collections for each row execute function _timescaledb_functions.insert_blocker();