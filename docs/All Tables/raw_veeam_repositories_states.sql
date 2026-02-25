CREATE TABLE public.raw_veeam_repositories_states (
	id text NOT NULL,
	"name" text NULL,
	description text NULL,
	"type" text NULL,
	host_id text NULL,
	host_name text NULL,
	"path" text NULL,
	capacity_gb numeric NULL,
	free_gb numeric NULL,
	used_space_gb numeric NULL,
	is_online bool NULL,
	source_ip text NOT NULL,
	collection_time timestamptz NULL
);