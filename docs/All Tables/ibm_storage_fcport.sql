CREATE TABLE public.ibm_storage_fcport (
	id int4 NULL,
	fc_io_port_id int4 NULL,
	port_id int4 NULL,
	"type" varchar(10) NULL,
	port_speed varchar(10) NULL,
	node_id int4 NULL,
	node_name varchar(50) NULL,
	wwpn varchar(50) NULL,
	nportid varchar(10) NULL,
	status varchar(50) NULL,
	attachment varchar(20) NULL,
	cluster_use varchar(20) NULL,
	adapter_location int4 NULL,
	adapter_port_id int4 NULL,
	"timestamp" timestamp NULL,
	storage_ip varchar(255) NULL
);