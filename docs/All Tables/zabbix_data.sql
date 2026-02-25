CREATE TABLE public.zabbix_data (
	groupname varchar(255) NULL,
	hostname varchar(255) NULL,
	"name" text NULL,
	lastvalue text NULL,
	timestamp_unix_utc int4 NULL,
	itemid int4 NULL,
	"type" int4 NULL,
	hostid int4 NULL,
	units varchar(50) NULL,
	groupid int4 NULL,
	collection_time timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	vendorname varchar(255) NULL
);
CREATE INDEX idx_zabbix_data_hostname ON public.zabbix_data USING btree (hostname);
CREATE INDEX idx_zabbix_data_name ON public.zabbix_data USING btree (name);
CREATE INDEX idx_zabbix_data_timestamp_unix_utc ON public.zabbix_data USING btree (timestamp_unix_utc);