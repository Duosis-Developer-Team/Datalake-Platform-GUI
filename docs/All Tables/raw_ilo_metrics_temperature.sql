CREATE TABLE public.raw_ilo_metrics_temperature (
	collection_timestamp timestamptz NOT NULL,
	chassis_serial_number varchar(255) NOT NULL,
	sensor_name varchar(255) NOT NULL,
	reading_celsius float4 NULL,
	status_health varchar(50) NULL,
	CONSTRAINT ilo_metrics_temperature_pkey PRIMARY KEY (collection_timestamp, chassis_serial_number, sensor_name)
);
CREATE INDEX idx_metrics_temp_sensor_time ON public.raw_ilo_metrics_temperature USING btree (sensor_name, collection_timestamp DESC);
CREATE INDEX idx_metrics_temp_serial_time ON public.raw_ilo_metrics_temperature USING btree (chassis_serial_number, collection_timestamp DESC);