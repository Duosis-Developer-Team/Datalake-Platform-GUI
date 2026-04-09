-- public.discovery_loki_rack definition

-- Drop table

-- DROP TABLE public.discovery_loki_rack;

CREATE TABLE public.discovery_loki_rack (
	id varchar(255) NOT NULL,
	component_moid varchar(255) NULL,
	parent_component_moid varchar(255) NULL,
	data_type varchar(50) DEFAULT 'loki_inventory_rack'::character varying NULL,
	"name" varchar(255) NULL,
	display_name varchar(255) NULL,
	status varchar(50) NULL,
	status_description text NULL,
	description text NULL,
	"comments" text NULL,
	facility_id varchar(255) NULL,
	serial varchar(255) NULL,
	asset_tag varchar(255) NULL,
	rack_type varchar(255) NULL,
	u_height int4 NULL,
	weight int4 NULL,
	max_weight int4 NULL,
	weight_unit varchar(50) NULL,
	kabin_enerji varchar(255) NULL,
	pdu_a_ip varchar(255) NULL,
	pdu_b_ip varchar(255) NULL,
	site_id varchar(255) NULL,
	location_id varchar(255) NULL,
	role_id varchar(255) NULL,
	tenant_name varchar(255) NULL,
	tags jsonb NULL,
	first_observed timestamptz DEFAULT CURRENT_TIMESTAMP NULL,
	last_observed timestamptz DEFAULT CURRENT_TIMESTAMP NULL,
	CONSTRAINT discovery_loki_rack_component_moid_key UNIQUE (component_moid),
	CONSTRAINT discovery_loki_rack_pkey PRIMARY KEY (id)
);