CREATE TABLE public.nutanix_snapshot_schedule (
	collection_time timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	nutanix_ip varchar(255) NULL,
	protection_domain_name varchar(255) NULL,
	state varchar(255) NULL,
	missing_entities_entity_name varchar(255) NULL,
	missing_entities_entity_type varchar(255) NULL,
	missing_entities_cg_name varchar(255) NULL,
	size_in_bytes int8 NULL,
	vm_names varchar(255) NULL,
	schedule_type varchar(255) NULL,
	schedule_every_nth int4 NULL,
	schedule_start_times_in_usecs int8 NULL,
	schedule_end_time_in_usecs int8 NULL,
	schedule_local_max_snapshots int4 NULL,
	schedule_remote_max_snapshots jsonb NULL
);