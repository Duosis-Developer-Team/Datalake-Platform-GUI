CREATE TABLE public.zabbix_network_device_metrics (
	id bigserial NOT NULL,
	collection_timestamp timestamptz NOT NULL,
	data_type varchar(50) NOT NULL,
	host varchar(255) NOT NULL,
	"location" varchar(255) NULL,
	loki_id varchar(100) NULL,
	applied_templates text NULL,
	icmp_status int4 NULL,
	icmp_loss_pct numeric(5, 2) NULL,
	icmp_response_time_ms numeric(10, 4) NULL,
	cpu_utilization_pct numeric(5, 2) NULL,
	memory_utilization_pct numeric(5, 2) NULL,
	uptime_seconds int8 NULL,
	system_name varchar(255) NULL,
	system_description text NULL,
	total_ports_count int4 NULL,
	active_ports_count int4 NULL,
	CONSTRAINT zabbix_network_device_metrics_pkey PRIMARY KEY (id, collection_timestamp)
);
CREATE INDEX idx_zabbix_net_device_host ON public.zabbix_network_device_metrics USING btree (host, collection_timestamp DESC);
CREATE INDEX zabbix_network_device_metrics_collection_timestamp_idx ON public.zabbix_network_device_metrics USING btree (collection_timestamp DESC);

-- Table Triggers

create trigger ts_insert_blocker before
insert
    on
    public.zabbix_network_device_metrics for each row execute function _timescaledb_functions.insert_blocker();


CREATE TABLE public.zabbix_network_interface_metrics (
	id bigserial NOT NULL,
	collection_timestamp timestamptz NOT NULL,
	data_type varchar(50) NOT NULL,
	host varchar(255) NOT NULL,
	interface_name varchar(255) NOT NULL,
	interface_alias varchar(255) NULL,
	operational_status int4 NULL,
	duplex_status int4 NULL,
	speed int8 NULL,
	bits_received int8 NULL,
	bits_sent int8 NULL,
	inbound_packets_discarded int8 NULL,
	inbound_packets_with_errors int8 NULL,
	outbound_packets_discarded int8 NULL,
	outbound_packets_with_errors int8 NULL,
	interface_type int4 NULL,
	CONSTRAINT zabbix_network_interface_metrics_pkey PRIMARY KEY (id, collection_timestamp)
);
CREATE INDEX idx_zabbix_net_iface_host_name ON public.zabbix_network_interface_metrics USING btree (host, interface_name, collection_timestamp DESC);
CREATE INDEX zabbix_network_interface_metrics_collection_timestamp_idx ON public.zabbix_network_interface_metrics USING btree (collection_timestamp DESC);

-- Table Triggers

create trigger ts_insert_blocker before
insert
    on
    public.zabbix_network_interface_metrics for each row execute function _timescaledb_functions.insert_blocker();


CREATE TABLE public.zabbix_storage_device_metrics (
	id bigserial NOT NULL,
	collection_timestamp timestamptz NOT NULL,
	data_type text NOT NULL,
	host text NOT NULL,
	"location" text NULL,
	loki_id text NULL,
	total_capacity_bytes int8 NULL,
	used_capacity_bytes int8 NULL,
	free_capacity_bytes int8 NULL,
	health_status text NULL,
	applied_templates text NULL,
	CONSTRAINT zabbix_storage_device_metrics_pkey PRIMARY KEY (id, collection_timestamp)
);
CREATE INDEX zabbix_storage_device_metrics_collection_timestamp_idx ON public.zabbix_storage_device_metrics USING btree (collection_timestamp DESC);

-- Table Triggers

create trigger ts_insert_blocker before
insert
    on
    public.zabbix_storage_device_metrics for each row execute function _timescaledb_functions.insert_blocker();



CREATE TABLE public.zabbix_storage_disk_metrics (
	id bigserial NOT NULL,
	collection_timestamp timestamptz NOT NULL,
	data_type text NOT NULL,
	host text NOT NULL,
	disk_name text NOT NULL,
	health_status text NULL,
	running_status text NULL,
	temperature_c numeric(5, 2) NULL,
	total_capacity_bytes int8 NULL,
	free_capacity_bytes int8 NULL,
	read_iops numeric(15, 2) NULL,
	write_iops numeric(15, 2) NULL,
	total_iops numeric(15, 2) NULL,
	latency_ms numeric(10, 4) NULL,
	total_throughput_bps int8 NULL,
	CONSTRAINT zabbix_storage_disk_metrics_pkey PRIMARY KEY (id, collection_timestamp)
);
CREATE INDEX zabbix_storage_disk_metrics_collection_timestamp_idx ON public.zabbix_storage_disk_metrics USING btree (collection_timestamp DESC);

-- Table Triggers

create trigger ts_insert_blocker before
insert
    on
    public.zabbix_storage_disk_metrics for each row execute function _timescaledb_functions.insert_blocker();



CREATE TABLE public.zabbix_storage_pool_metrics (
	id bigserial NOT NULL,
	collection_timestamp timestamptz NOT NULL,
	data_type text NOT NULL,
	host text NOT NULL,
	pool_name text NOT NULL,
	total_capacity_bytes int8 NULL,
	used_capacity_bytes int8 NULL,
	free_capacity_bytes int8 NULL,
	health_status text NULL,
	CONSTRAINT zabbix_storage_pool_metrics_pkey PRIMARY KEY (id,collection_timestamp)
);
CREATE INDEX zabbix_storage_pool_metrics_collection_timestamp_idx ON public.zabbix_storage_pool_metrics (collection_timestamp DESC);


CREATE TABLE public.zabbix_storage_volume_metrics (
	id bigserial NOT NULL,
	collection_timestamp timestamptz NOT NULL,
	data_type text NOT NULL,
	host text NOT NULL,
	volume_name text NOT NULL,
	total_capacity_bytes int8 NULL,
	used_capacity_bytes int8 NULL,
	health_status text NULL,
	total_iops numeric(15, 2) NULL,
	read_iops numeric(15, 2) NULL,
	write_iops numeric(15, 2) NULL,
	latency_ms numeric(10, 4) NULL,
	total_throughput_bps int8 NULL,
	CONSTRAINT zabbix_storage_volume_metrics_pkey PRIMARY KEY (id,collection_timestamp)
);
CREATE INDEX zabbix_storage_volume_metrics_collection_timestamp_idx ON public.zabbix_storage_volume_metrics (collection_timestamp DESC);