CREATE TABLE public.discovery_nutanix_inventory_prism (
	id varchar DEFAULT nextval('discovery_nutanix_inventory_prism_id_seq'::regclass) NOT NULL,
	first_observed timestamptz DEFAULT CURRENT_TIMESTAMP NULL,
	last_observed timestamptz DEFAULT CURRENT_TIMESTAMP NULL,
	nutanix_uuid varchar(255) NULL,
	data_type varchar(50) NULL,
	component_moid varchar(255) NULL,
	"name" text NULL,
	status varchar(20) NULL,
	status_description text NULL,
	CONSTRAINT discovery_nutanix_inventory_prism_pkey PRIMARY KEY (id),
	CONSTRAINT uniq_prism_moid UNIQUE (component_moid)
);