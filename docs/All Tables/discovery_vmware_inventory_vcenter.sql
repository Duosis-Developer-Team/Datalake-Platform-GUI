CREATE TABLE public.discovery_vmware_inventory_vcenter (
	id varchar DEFAULT nextval('vmware_inventory_vcenter_id_seq'::regclass) NOT NULL,
	first_observed timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
	last_observed timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
	vcenter_uuid uuid NULL,
	vcenter_ip varchar(255) NOT NULL,
	vcenter_hostname text NULL,
	data_type varchar(50) NOT NULL,
	component_moid varchar(255) NOT NULL,
	"name" text NOT NULL,
	status varchar(20) NOT NULL,
	status_description text NULL,
	"version" varchar(50) NULL,
	CONSTRAINT uq_vcenter_comp_moid UNIQUE (component_moid),
	CONSTRAINT vmware_inventory_vcenter_pkey PRIMARY KEY (id)
);
CREATE INDEX idx_vcenter_last_observed ON public.discovery_vmware_inventory_vcenter USING btree (last_observed DESC);

-- Table Triggers

create trigger update_vcenter_last_observed before
update
    on
    public.discovery_vmware_inventory_vcenter for each row execute function update_last_observed_column();