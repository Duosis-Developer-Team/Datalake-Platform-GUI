CREATE TABLE public.ibm_server_power (
	server_name varchar(255) NULL,
	atom_id varchar(255) NULL,
	"timestamp" timestamp NULL,
	power_watts int4 NULL,
	mb0 int4 NULL,
	mb1 int4 NULL,
	mb2 int4 NULL,
	mb3 int4 NULL,
	cpu0 int4 NULL,
	cpu1 int4 NULL,
	cpu2 int4 NULL,
	cpu3 int4 NULL,
	cpu4 int4 NULL,
	cpu5 int4 NULL,
	cpu6 int4 NULL,
	cpu7 int4 NULL,
	inlet_temp int4 NULL,
	CONSTRAINT unique_ibm_server_power_metric_entry UNIQUE (server_name, "timestamp")
);
CREATE INDEX idx_ibm_server_power_server_name ON public.ibm_server_power USING btree (server_name);
CREATE INDEX idx_ibm_server_power_timestamp ON public.ibm_server_power USING btree ("timestamp");