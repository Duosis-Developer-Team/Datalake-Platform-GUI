CREATE TABLE public.raw_ilo_inventory_processor (
	collection_timestamp timestamptz NOT NULL,
	chassis_serial_number varchar(255) NOT NULL,
	processor_id varchar(50) NOT NULL,
	model varchar(255) NULL,
	max_speed_mhz int4 NULL,
	total_cores int4 NULL,
	total_threads int4 NULL,
	status_health varchar(50) NULL,
	status_state varchar(50) NULL,
	CONSTRAINT ilo_inventory_processor_pkey PRIMARY KEY (collection_timestamp, chassis_serial_number, processor_id)
);
CREATE INDEX idx_inventory_processor_serial_time ON public.raw_ilo_inventory_processor USING btree (chassis_serial_number, collection_timestamp DESC);