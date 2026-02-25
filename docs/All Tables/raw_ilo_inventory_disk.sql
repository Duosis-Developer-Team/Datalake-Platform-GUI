CREATE TABLE public.raw_ilo_inventory_disk (
	collection_timestamp timestamptz NOT NULL,
	chassis_serial_number varchar(255) NOT NULL,
	disk_id varchar(50) NOT NULL,
	model varchar(255) NULL,
	capacity_bytes int8 NULL,
	protocol varchar(50) NULL,
	media_type varchar(50) NULL,
	serial_number varchar(255) NULL,
	status_health varchar(50) NULL,
	status_state varchar(50) NULL,
	firmware_version varchar(50) NULL,
	block_size_bytes int4 NULL,
	CONSTRAINT ilo_inventory_disk_pkey PRIMARY KEY (collection_timestamp, chassis_serial_number, disk_id)
);
CREATE INDEX idx_inventory_disk_serial_time ON public.raw_ilo_inventory_disk USING btree (chassis_serial_number, collection_timestamp DESC);