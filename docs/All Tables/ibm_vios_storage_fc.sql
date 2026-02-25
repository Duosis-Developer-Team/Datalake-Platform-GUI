CREATE TABLE public.ibm_vios_storage_fc (
	servername varchar(255) NULL,
	viosname varchar(255) NULL,
	id varchar(255) NULL,
	"location" varchar(255) NULL,
	wwpn float8 NULL,
	physicallocation varchar(255) NULL,
	numofports int4 NULL,
	numofreads float8 NULL,
	numofwrites float8 NULL,
	readbytes float8 NULL,
	writebytes float8 NULL,
	runningspeed float8 NULL,
	"time" timestamptz NULL,
	CONSTRAINT unique_ibm_vioss_storage_fc_metric_entry UNIQUE (viosname, id, wwpn, "time")
);