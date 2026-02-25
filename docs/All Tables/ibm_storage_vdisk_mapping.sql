CREATE TABLE public.ibm_storage_vdisk_mapping (
	id int4 NULL,
	"name" varchar(250) NULL,
	scsi_id int4 NULL,
	vdisk_id int4 NULL,
	vdisk_name varchar(250) NULL,
	vdisk_uid varchar(250) NULL,
	io_group_id int4 NULL,
	io_group_name varchar(250) NULL,
	mapping_type varchar(250) NULL,
	host_cluster_id varchar(250) NULL,
	host_cluster_name varchar(250) NULL,
	protocol varchar(250) NULL,
	"timestamp" timestamp NULL,
	storage_ip varchar(255) NULL
);