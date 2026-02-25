CREATE TABLE public.ibm_lpar_storage_vfc (
	servername varchar(255) NULL,
	lparname varchar(255) NULL,
	"location" varchar(255) NULL,
	viosid int4 NULL,
	id varchar(255) NULL,
	wwpn varchar(255) NULL,
	wwpn2 varchar(255) NULL,
	physicallocation varchar(255) NULL,
	physicalportwwpn float8 NULL,
	numofreads float8 NULL,
	numofwrites float8 NULL,
	readbytes float8 NULL,
	writebytes float8 NULL,
	runningspeed float8 NULL,
	"time" timestamptz NULL,
	CONSTRAINT unique_ibm_lpar_storag_vfc_metric_entry UNIQUE (lparname, wwpn, wwpn2, "time")
);
CREATE INDEX idx_ibm_vfc_lpar_time ON public.ibm_lpar_storage_vfc USING btree (lparname, "time" DESC);
CREATE INDEX idx_ibm_vfc_wwpn1 ON public.ibm_lpar_storage_vfc USING btree (wwpn);
CREATE INDEX idx_ibm_vfc_wwpn2 ON public.ibm_lpar_storage_vfc USING btree (wwpn2);