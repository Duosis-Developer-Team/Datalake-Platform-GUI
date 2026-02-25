CREATE TABLE public.ibm_storage_enclosure_stats (
	enclosure_id int4 NOT NULL,
	power_w int4 NULL,
	temp_c int4 NULL,
	temp_f int4 NULL,
	"timestamp" timestamp NULL,
	storage_ip varchar(255) NULL
);