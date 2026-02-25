CREATE TABLE public.discovery_vmware_inventory_vm (
	id varchar DEFAULT nextval('vmware_inventory_vm_id_seq'::regclass) NOT NULL,
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
	guest_os text NULL,
	tools_status varchar(50) NULL,
	CONSTRAINT uq_vm_unique UNIQUE (vcenter_uuid, component_moid),
	CONSTRAINT vmware_inventory_vm_pkey PRIMARY KEY (id)
);
CREATE INDEX idx_vm_component_uuid ON public.discovery_vmware_inventory_vm USING btree (component_uuid);
CREATE INDEX idx_vm_last_observed ON public.discovery_vmware_inventory_vm USING btree (last_observed DESC);
CREATE INDEX idx_vm_parent_moid ON public.discovery_vmware_inventory_vm USING btree (parent_component_moid);

-- Table Triggers

create trigger update_vm_last_observed before
update
    on
    public.discovery_vmware_inventory_vm for each row execute function update_last_observed_column();