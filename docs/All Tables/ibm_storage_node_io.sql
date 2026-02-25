CREATE TABLE public.ibm_storage_node_io (
	node_id text NULL,
	"timestamp" timestamp NULL,
	"cluster" text NULL,
	node_id_hex text NULL,
	cluster_id text NULL,
	ro int8 NULL,
	wo int8 NULL,
	rb int8 NULL,
	lrb int8 NULL,
	wb int8 NULL,
	lwb int8 NULL,
	re int8 NULL,
	we int8 NULL,
	rq int8 NULL,
	wq int8 NULL,
	storage_ip varchar(255) NULL
);