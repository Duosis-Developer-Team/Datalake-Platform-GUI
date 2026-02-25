CREATE TABLE public.raw_ilo_inventory_memory (
	collection_timestamp timestamptz NOT NULL,
	chassis_serial_number varchar(255) NOT NULL,
	dimm_id varchar(50) NOT NULL,
	memory_type varchar(50) NULL,
	capacity_mib int4 NULL,
	operating_speed_mhz int4 NULL,
	manufacturer varchar(255) NULL,
	part_number varchar(255) NULL,
	status_health varchar(50) NULL,
	status_state varchar(50) NULL,
	CONSTRAINT ilo_inventory_memory_pkey PRIMARY KEY (collection_timestamp, chassis_serial_number, dimm_id)
);
CREATE INDEX idx_inventory_memory_serial_time ON public.raw_ilo_inventory_memory USING btree (chassis_serial_number, collection_timestamp DESC);