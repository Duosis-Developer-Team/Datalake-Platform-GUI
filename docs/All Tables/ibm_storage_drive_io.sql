CREATE TABLE public.ibm_storage_drive_io (
	node_id text NULL,
	"timestamp" timestamp NULL,
	idx text NULL,
	ro int8 NULL,
	wo int8 NULL,
	rb int8 NULL,
	wb int8 NULL,
	re int8 NULL,
	we int8 NULL,
	rq int8 NULL,
	wq int8 NULL,
	pre int8 NULL,
	pwe int8 NULL,
	storage_ip varchar(255) NULL
);