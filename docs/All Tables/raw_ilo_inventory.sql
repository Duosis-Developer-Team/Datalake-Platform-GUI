CREATE TABLE public.raw_ilo_inventory (
	id int4 DEFAULT nextval('ilo_inventory_id_seq'::regclass) NOT NULL,
	collection_timestamp timestamptz NOT NULL,
	chassis_serial_number varchar(255) NOT NULL,
	chassis_model varchar(255) NULL,
	chassis_manufacturer varchar(255) NULL,
	system_hostname varchar(255) NULL,
	system_power_state varchar(50) NULL,
	processor_count int4 NULL,
	processor_model varchar(255) NULL,
	processor_status_health varchar(50) NULL,
	total_system_memory_gib int4 NULL,
	total_system_persistent_memory_gib int4 NULL,
	memory_status_health varchar(50) NULL,
	CONSTRAINT ilo_inventory_collection_timestamp_chassis_serial_number_key UNIQUE (collection_timestamp, chassis_serial_number),
	CONSTRAINT ilo_inventory_pkey PRIMARY KEY (id)
);
CREATE INDEX idx_inventory_serial_time ON public.raw_ilo_inventory USING btree (chassis_serial_number, collection_timestamp DESC);