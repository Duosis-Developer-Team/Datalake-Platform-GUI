CREATE TABLE public.discovery_vmware_inventory_host (
	id varchar DEFAULT nextval('vmware_inventory_host_id_seq'::regclass) NOT NULL,
	first_observed timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
	last_observed timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
	vcenter_uuid uuid NOT NULL,
	data_type varchar(50) NOT NULL,
	component_moid varchar(255) NOT NULL,
	parent_component_moid varchar(255) NOT NULL,
	component_uuid varchar(255) NULL,
	"name" text NOT NULL,
	status varchar(20) NOT NULL,
	status_description text NULL,
	model text NULL,
	"version" varchar(50) NULL,
	build varchar(50) NULL,
	CONSTRAINT uq_host_hier UNIQUE (parent_component_moid, component_moid),
	CONSTRAINT vmware_inventory_host_pkey PRIMARY KEY (id)
);
CREATE INDEX idx_host_component_uuid ON public.discovery_vmware_inventory_host USING btree (component_uuid);
CREATE INDEX idx_host_last_observed ON public.discovery_vmware_inventory_host USING btree (last_observed DESC);
CREATE INDEX idx_host_parent_moid ON public.discovery_vmware_inventory_host USING btree (parent_component_moid);

-- Table Triggers

create trigger update_host_last_observed before
update
    on
    public.discovery_vmware_inventory_host for each row execute function update_last_observed_column();