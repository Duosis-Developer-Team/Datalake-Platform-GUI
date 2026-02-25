CREATE TABLE public.raw_ilo_metrics_system (
	collection_timestamp timestamptz NOT NULL,
	chassis_serial_number varchar(255) NOT NULL,
	cpu_utilization_percent float4 NULL,
	memory_bus_utilization_percent float4 NULL,
	CONSTRAINT ilo_metrics_system_pkey PRIMARY KEY (collection_timestamp, chassis_serial_number)
);
CREATE INDEX idx_metrics_system_serial_time ON public.raw_ilo_metrics_system USING btree (chassis_serial_number, collection_timestamp DESC);