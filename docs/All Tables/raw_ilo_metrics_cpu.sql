CREATE TABLE public.raw_ilo_metrics_cpu (
	collection_timestamp timestamptz NOT NULL,
	chassis_serial_number varchar(255) NOT NULL,
	cpu_id int4 NOT NULL,
	power_watts float4 NULL,
	frequency_mhz float4 NULL,
	CONSTRAINT ilo_metrics_cpu_pkey PRIMARY KEY (collection_timestamp, chassis_serial_number, cpu_id)
);
CREATE INDEX idx_metrics_cpu_id_time ON public.raw_ilo_metrics_cpu USING btree (cpu_id, collection_timestamp DESC);
CREATE INDEX idx_metrics_cpu_serial_time ON public.raw_ilo_metrics_cpu USING btree (chassis_serial_number, collection_timestamp DESC);