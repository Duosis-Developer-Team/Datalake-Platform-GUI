CREATE TABLE public.ibm_storage_host (
	id varchar(255) NULL,
	"name" varchar(255) NULL,
	"timestamp" timestamp NULL,
	port_count int4 NULL,
	iogrp_count int4 NULL,
	status varchar(255) NULL,
	site_id int4 NULL,
	site_name varchar(255) NULL,
	host_cluster_id int4 NULL,
	host_cluster_name varchar(255) NULL,
	protocol varchar(255) NULL,
	owner_id int4 NULL,
	owner_name varchar(255) NULL,
	portset_id int4 NULL,
	portset_name varchar(255) NULL,
	storage_ip varchar(255) NULL
);