CREATE TABLE public.ibm_vios_network_generic (
	servername varchar(255) NULL,
	viosname varchar(255) NULL,
	id varchar(255) NULL,
	"location" varchar(255) NULL,
	"type" varchar(255) NULL,
	physicallocation varchar(255) NULL,
	receivedpackets float8 NULL,
	sentpackets float8 NULL,
	droppedpackets float8 NULL,
	sentbytes float8 NULL,
	receivedbytes float8 NULL,
	transferredbytes float8 NULL,
	"time" timestamptz NULL,
	CONSTRAINT unique_ibm_vios_network_generic_metric_entry UNIQUE (viosname, id, "time")
);