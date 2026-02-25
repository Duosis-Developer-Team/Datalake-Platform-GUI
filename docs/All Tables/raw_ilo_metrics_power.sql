CREATE TABLE public.raw_ilo_metrics_power (
	collection_timestamp timestamptz NOT NULL,
	chassis_serial_number varchar(255) NOT NULL,
	psu_id int4 NOT NULL,
	power_output_watts float4 NULL,
	CONSTRAINT ilo_metrics_power_pkey PRIMARY KEY (collection_timestamp, chassis_serial_number, psu_id)
);
CREATE INDEX idx_metrics_power_psu_time ON public.raw_ilo_metrics_power USING btree (psu_id, collection_timestamp DESC);
CREATE INDEX idx_metrics_power_serial_time ON public.raw_ilo_metrics_power USING btree (chassis_serial_number, collection_timestamp DESC);