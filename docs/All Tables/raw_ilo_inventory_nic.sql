CREATE TABLE public.raw_ilo_inventory_nic (
	collection_timestamp timestamptz NOT NULL,
	chassis_serial_number varchar(255) NOT NULL,
	interface_id varchar(50) NOT NULL,
	"name" varchar(255) NULL,
	mac_address varchar(50) NULL,
	speed_mbps int4 NULL,
	link_status varchar(50) NULL,
	full_duplex bool NULL,
	ipv4_addresses text NULL,
	status_health varchar(50) NULL,
	CONSTRAINT ilo_inventory_nic_pkey PRIMARY KEY (collection_timestamp, chassis_serial_number, interface_id)
);
CREATE INDEX idx_inventory_nic_serial_time ON public.raw_ilo_inventory_nic USING btree (chassis_serial_number, collection_timestamp DESC);