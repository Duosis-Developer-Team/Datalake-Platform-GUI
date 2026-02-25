CREATE TABLE public.discovery_nutanix_inventory_host (
	id varchar DEFAULT nextval('discovery_nutanix_inventory_host_id_seq'::regclass) NOT NULL,
	first_observed timestamptz DEFAULT CURRENT_TIMESTAMP NULL,
	last_observed timestamptz DEFAULT CURRENT_TIMESTAMP NULL,
	data_type varchar(50) NOT NULL,
	component_moid varchar(255) NOT NULL,
	nutanix_uuid varchar(255) NULL,
	parent_component_moid varchar(255) NULL,
	component_uuid varchar(255) NULL,
	"name" text NULL,
	status varchar(20) NULL,
	status_description text NULL,
	serial varchar(255) NULL,
	model text NULL,
	CONSTRAINT discovery_nutanix_inventory_host_pkey PRIMARY KEY (id),
	CONSTRAINT uniq_host_parent_moid UNIQUE (parent_component_moid, component_moid)
);