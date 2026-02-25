CREATE TABLE public.raw_ilo_metrics_fan (
	collection_timestamp timestamptz NOT NULL,
	chassis_serial_number varchar(255) NOT NULL,
	fan_name varchar(255) NOT NULL,
	reading_percent float4 NULL,
	reading_units varchar(50) NULL,
	status_health varchar(50) NULL,
	CONSTRAINT ilo_metrics_fan_pkey PRIMARY KEY (collection_timestamp, chassis_serial_number, fan_name)
);
CREATE INDEX idx_metrics_fan_name_time ON public.raw_ilo_metrics_fan USING btree (fan_name, collection_timestamp DESC);
CREATE INDEX idx_metrics_fan_serial_time ON public.raw_ilo_metrics_fan USING btree (chassis_serial_number, collection_timestamp DESC);