CREATE TABLE public.raw_veeam_jobs_states (
	id text NOT NULL,
	"name" text NULL,
	description text NULL,
	"type" text NULL,
	status text NULL,
	last_result text NULL,
	last_run timestamptz NOT NULL,
	next_run timestamptz NULL,
	workload text NULL,
	objects_count int4 NULL,
	repository_id text NULL,
	repository_name text NULL,
	session_id text NOT NULL,
	source_ip text NOT NULL,
	collection_time timestamptz NULL,
	CONSTRAINT veeam_jobs_states_pkey PRIMARY KEY (source_ip, id, last_run, session_id)
);