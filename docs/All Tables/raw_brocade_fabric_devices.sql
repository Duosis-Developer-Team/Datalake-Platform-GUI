CREATE TABLE public.raw_brocade_fabric_devices (
	switch_host varchar(255) NOT NULL,
	collection_timestamp timestamptz NOT NULL,
	device_wwpn varchar(23) NOT NULL,
	device_wwnn varchar(23) NULL,
	port_index int4 NULL,
	port_id varchar(10) NULL,
	port_symbolic_name text NULL,
	node_symbolic_name text NULL,
	device_port_type varchar(50) NULL,
	class_of_service varchar(50) NULL,
	CONSTRAINT brocade_fabric_devices_pkey PRIMARY KEY (switch_host, collection_timestamp, device_wwpn)
);