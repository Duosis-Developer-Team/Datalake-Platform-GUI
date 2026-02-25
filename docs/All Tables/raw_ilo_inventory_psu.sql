CREATE TABLE public.raw_ilo_inventory_psu (
	collection_timestamp timestamptz NOT NULL,
	chassis_serial_number varchar(255) NOT NULL,
	psu_id varchar(50) NOT NULL,
	model varchar(255) NULL,
	serial_number varchar(255) NULL,
	part_number varchar(255) NULL,
	firmware_version varchar(50) NULL,
	power_capacity_watts int4 NULL,
	status_health varchar(50) NULL,
	CONSTRAINT ilo_inventory_psu_pkey PRIMARY KEY (collection_timestamp, chassis_serial_number, psu_id)
);
CREATE INDEX idx_inventory_psu_serial_time ON public.raw_ilo_inventory_psu USING btree (chassis_serial_number, collection_timestamp DESC);