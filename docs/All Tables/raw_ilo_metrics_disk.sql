CREATE TABLE public.raw_ilo_metrics_disk (
	collection_timestamp timestamptz NOT NULL,
	chassis_serial_number varchar(255) NOT NULL,
	disk_id varchar(50) NOT NULL,
	power_on_hours int4 NULL,
	temperature_celsius float4 NULL,
	endurance_utilization_percent float4 NULL,
	uncorrected_read_errors int4 NULL,
	uncorrected_write_errors int4 NULL,
	CONSTRAINT ilo_metrics_disk_pkey PRIMARY KEY (collection_timestamp, chassis_serial_number, disk_id)
);
CREATE INDEX idx_metrics_disk_id_time ON public.raw_ilo_metrics_disk USING btree (disk_id, collection_timestamp DESC);
CREATE INDEX idx_metrics_disk_serial_time ON public.raw_ilo_metrics_disk USING btree (chassis_serial_number, collection_timestamp DESC);