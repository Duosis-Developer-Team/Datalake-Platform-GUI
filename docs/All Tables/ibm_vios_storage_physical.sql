CREATE TABLE public.ibm_vios_storage_physical (
	servername varchar(255) NULL,
	viosname varchar(255) NULL,
	id varchar(255) NULL,
	"location" varchar(255) NULL,
	"type" varchar(50) NULL,
	physicallocation varchar(255) NULL,
	numofreads float8 NULL,
	numofwrites float8 NULL,
	readbytes float8 NULL,
	writebytes float8 NULL,
	"time" timestamptz NULL,
	CONSTRAINT unique_ibm_vios_storage_physical_metric_entry UNIQUE (viosname, id, "time")
);