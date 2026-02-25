CREATE TABLE public.raw_ilo_inventory_bios (
	collection_timestamp timestamptz NOT NULL,
	chassis_serial_number varchar(255) NOT NULL,
	workloadprofile varchar(255) NULL,
	prochyperthreading varchar(50) NULL,
	procvirtualization varchar(50) NULL,
	powerregulator varchar(50) NULL,
	sriov varchar(50) NULL,
	bootmode varchar(50) NULL,
	CONSTRAINT ilo_inventory_bios_pkey PRIMARY KEY (collection_timestamp, chassis_serial_number)
);
CREATE INDEX idx_inventory_bios_serial_time ON public.raw_ilo_inventory_bios USING btree (chassis_serial_number, collection_timestamp DESC);