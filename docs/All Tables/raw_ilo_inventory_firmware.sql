CREATE TABLE public.raw_ilo_inventory_firmware (
	collection_timestamp timestamptz NOT NULL,
	chassis_serial_number varchar(255) NOT NULL,
	component_name varchar(255) NOT NULL,
	"version" varchar(255) NOT NULL,
	updateable bool NULL,
	device_context varchar(255) NULL,
	CONSTRAINT ilo_inventory_firmware_pkey PRIMARY KEY (collection_timestamp, chassis_serial_number, component_name, version)
);