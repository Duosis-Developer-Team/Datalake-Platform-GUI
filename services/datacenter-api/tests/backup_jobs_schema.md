# Backup Job Tables — Live Schema Inspection

Bu rapor `tests/test_backup_jobs_schema.py` koşturulduğunda otomatik üretilir.
Üretildiği yer: `app/tests/backup_jobs_schema.md`


## Mevcut backup tabloları (bulutlake.public)

- `raw_netbackup_disk_pools_metrics`
- `raw_netbackup_jobs_metrics`
- `raw_veeam_jobs_states`
- `raw_veeam_managed_server_components`
- `raw_veeam_managed_servers`
- `raw_veeam_proxies`
- `raw_veeam_proxy_datastores`
- `raw_veeam_repositories_states`
- `raw_veeam_sessions`
- `raw_zerto_alert_metrics`
- `raw_zerto_license_metrics`
- `raw_zerto_site_metrics`
- `raw_zerto_vm_metrics`
- `raw_zerto_vpg_metrics`
- `raw_zerto_vra_metrics`

## `raw_veeam_jobs_states` kolonları

- `('id', 'text', 'NO')`
- `('name', 'text', 'YES')`
- `('description', 'text', 'YES')`
- `('type', 'text', 'YES')`
- `('status', 'text', 'YES')`
- `('last_result', 'text', 'YES')`
- `('last_run', 'timestamp with time zone', 'NO')`
- `('next_run', 'timestamp with time zone', 'YES')`
- `('workload', 'text', 'YES')`
- `('objects_count', 'integer', 'YES')`
- `('repository_id', 'text', 'YES')`
- `('repository_name', 'text', 'YES')`
- `('session_id', 'text', 'NO')`
- `('source_ip', 'text', 'NO')`
- `('collection_time', 'timestamp with time zone', 'NO')`

## `raw_veeam_sessions` kolonları

- `('id', 'text', 'NO')`
- `('name', 'text', 'YES')`
- `('job_id', 'text', 'NO')`
- `('session_type', 'text', 'YES')`
- `('state', 'text', 'YES')`
- `('creation_time', 'timestamp with time zone', 'NO')`
- `('end_time', 'timestamp with time zone', 'YES')`
- `('result_result', 'text', 'YES')`
- `('result_message', 'text', 'YES')`
- `('result_is_canceled', 'boolean', 'YES')`
- `('progress_percent', 'integer', 'YES')`
- `('usn', 'bigint', 'YES')`
- `('platform_id', 'text', 'YES')`
- `('platform_name', 'text', 'YES')`
- `('resource_id', 'text', 'YES')`
- `('resource_reference', 'text', 'YES')`
- `('parent_session_id', 'text', 'YES')`
- `('source_ip', 'text', 'NO')`
- `('collection_time', 'timestamp with time zone', 'NO')`

## `raw_zerto_vpg_metrics` kolonları

- `('data_type', 'character varying', 'NO')`
- `('collection_timestamp', 'timestamp with time zone', 'NO')`
- `('zerto_host', 'character varying', 'NO')`
- `('id', 'character varying', 'NO')`
- `('name', 'character varying', 'YES')`
- `('status', 'integer', 'YES')`
- `('actualrpo', 'integer', 'YES')`
- `('vmscount', 'integer', 'YES')`
- `('alertstatus', 'integer', 'YES')`
- `('priority', 'integer', 'YES')`
- `('source_site', 'character varying', 'YES')`
- `('target_site', 'character varying', 'YES')`
- `('vm_identifiers', 'jsonb', 'YES')`
- `('iops', 'integer', 'YES')`
- `('throughput_mb', 'numeric', 'YES')`
- `('provisioned_storage_mb', 'bigint', 'YES')`
- `('used_storage_mb', 'bigint', 'YES')`

## `raw_zerto_vm_metrics` kolonları

- `('data_type', 'character varying', 'NO')`
- `('collection_timestamp', 'timestamp with time zone', 'NO')`
- `('zerto_host', 'character varying', 'NO')`
- `('id', 'character varying', 'NO')`
- `('vm_identifier', 'character varying', 'YES')`
- `('vm_name', 'character varying', 'YES')`
- `('name', 'character varying', 'YES')`
- `('status', 'integer', 'YES')`
- `('vpg_identifier', 'character varying', 'YES')`
- `('cpu_count', 'integer', 'YES')`
- `('memory_mb', 'bigint', 'YES')`
- `('disk_count', 'integer', 'YES')`
- `('vm_network_count', 'integer', 'YES')`
- `('os', 'character varying', 'YES')`
- `('ip_addresses', 'jsonb', 'YES')`
- `('disk_info', 'jsonb', 'YES')`
- `('is_protected', 'boolean', 'YES')`
- `('is_archived', 'boolean', 'YES')`
- `('is_offline', 'boolean', 'YES')`

## `raw_zerto_alert_metrics` kolonları

- `('data_type', 'character varying', 'NO')`
- `('collection_timestamp', 'timestamp with time zone', 'NO')`
- `('zerto_host', 'character varying', 'NO')`
- `('id', 'character varying', 'NO')`
- `('alert_identifier', 'character varying', 'YES')`
- `('title', 'character varying', 'YES')`
- `('description', 'text', 'YES')`
- `('severity', 'character varying', 'YES')`
- `('category', 'character varying', 'YES')`
- `('creation_date', 'timestamp with time zone', 'YES')`
- `('site_identifier', 'character varying', 'YES')`
- `('vpg_identifier', 'character varying', 'YES')`
- `('is_acknowledged', 'boolean', 'YES')`
- `('is_resolved', 'boolean', 'YES')`
- `('related_entities', 'jsonb', 'YES')`
- `('tags', 'jsonb', 'YES')`

## `raw_netbackup_jobs_metrics` kolonları

- `('data_type', 'character varying', 'NO')`
- `('collection_timestamp', 'timestamp with time zone', 'NO')`
- `('netbackup_host', 'character varying', 'NO')`
- `('id', 'character varying', 'NO')`
- `('type', 'character varying', 'YES')`
- `('jobid', 'character varying', 'YES')`
- `('parentjobid', 'character varying', 'YES')`
- `('activeprocessid', 'character varying', 'YES')`
- `('jobtype', 'character varying', 'YES')`
- `('jobsubtype', 'character varying', 'YES')`
- `('policytype', 'character varying', 'YES')`
- `('policyname', 'character varying', 'YES')`
- `('scheduletype', 'character varying', 'YES')`
- `('schedulename', 'character varying', 'YES')`
- `('clientname', 'character varying', 'YES')`
- `('jobowner', 'character varying', 'YES')`
- `('jobgroup', 'character varying', 'YES')`
- `('backupid', 'character varying', 'YES')`
- `('destinationstorageunitname', 'character varying', 'YES')`
- `('destinationmediaservername', 'character varying', 'YES')`
- `('datamovement', 'character varying', 'YES')`
- `('streamnumber', 'integer', 'YES')`
- `('copynumber', 'integer', 'YES')`
- `('priority', 'integer', 'YES')`
- `('compression', 'integer', 'YES')`
- `('state', 'character varying', 'YES')`
- `('numberoffiles', 'bigint', 'YES')`
- `('estimatedfiles', 'bigint', 'YES')`
- `('kilobytestransferred', 'bigint', 'YES')`
- `('kilobytestotransfer', 'bigint', 'YES')`
- `('transferrate', 'numeric', 'YES')`
- `('percentcomplete', 'numeric', 'YES')`
- `('restartable', 'boolean', 'YES')`
- `('suspendable', 'boolean', 'YES')`
- `('resumable', 'boolean', 'YES')`
- `('frozenimage', 'boolean', 'YES')`
- `('transporttype', 'character varying', 'YES')`
- `('currentoperation', 'integer', 'YES')`
- `('sessionid', 'character varying', 'YES')`
- `('numberoftapetoeject', 'integer', 'YES')`
- `('submissiontype', 'integer', 'YES')`
- `('auditdomaintype', 'integer', 'YES')`
- `('starttime', 'timestamp with time zone', 'YES')`
- `('endtime', 'timestamp with time zone', 'YES')`
- `('activetrystarttime', 'timestamp with time zone', 'YES')`
- `('lastupdatetime', 'timestamp with time zone', 'YES')`
- `('childcount', 'integer', 'YES')`
- `('jobpath', 'character varying', 'YES')`
- `('retentionlevel', 'integer', 'YES')`
- `('try', 'integer', 'YES')`
- `('cancellable', 'boolean', 'YES')`
- `('jobqueuereason', 'integer', 'YES')`
- `('kilobytesdatatransferred', 'bigint', 'YES')`
- `('elapsedtime', 'character varying', 'YES')`
- `('activeelapsedtime', 'character varying', 'YES')`
- `('dtemode', 'character varying', 'YES')`
- `('workloaddisplayname', 'character varying', 'YES')`
- `('offhosttype', 'character varying', 'YES')`
- `('dedupratio', 'numeric', 'YES')`
- `('status', 'integer', 'YES')`
- `('profilename', 'character varying', 'YES')`
- `('dedupspaceratio', 'numeric', 'YES')`
- `('compressionspaceratio', 'numeric', 'YES')`

## `raw_veeam_jobs_states` örnek 3 satır

- `('d83f5189-eaf2-460b-a2c9-532e314a7e14', 'Bayraktar_6Hours_DR2', 'Created by BLTVC\\adminerdemo at 3/25/2024 3:12 PM.', 'VSphereReplica', 'inactive', 'Success', datetime.datetime(2025, 8, 18, 12, 12, 29, 507000, tzinfo=datetime.timezone.utc), None, 'vm', 5, 'dda7dad9-4e16-452c-ad8e-61ae3a323fe7', 'BackupRepo', 'e4b43a9d-5094-44bb-b4de-d630c2f2e3ee', '10.34.2.104', datetime.datetime(2025, 8, 18, 14, 3, 42, 778000, tzinfo=datetime.timezone.utc))`
- `('278cc39c-ef7b-4af8-b7ae-79d40476ddd0', 'Bayraktar_6Hours_DR3', 'Created by BLTVC\\adminerdemo at 3/25/2024 3:12 PM.', 'VSphereReplica', 'inactive', 'Success', datetime.datetime(2025, 8, 18, 12, 52, 9, 563000, tzinfo=datetime.timezone.utc), None, 'vm', 4, 'dda7dad9-4e16-452c-ad8e-61ae3a323fe7', 'BackupRepo', 'aaef025f-8344-49bb-88f4-b03459ffe700', '10.34.2.104', datetime.datetime(2025, 8, 18, 14, 3, 42, 778000, tzinfo=datetime.timezone.utc))`
- `('81d47bae-0086-4bcc-8e27-69a9c49fbc5c', 'ETB-Ekds2_Prod-DR', 'Created by BLTVC\\adminibrahima at 21/06/2025 12:44 PM.', 'VSphereReplica', 'inactive', 'Success', datetime.datetime(2025, 8, 18, 2, 6, 51, 44000, tzinfo=datetime.timezone.utc), None, 'vm', 1, 'dda7dad9-4e16-452c-ad8e-61ae3a323fe7', 'BackupRepo', '64a187ee-f07e-4372-8fb1-1532d91faac7', '10.34.2.104', datetime.datetime(2025, 8, 18, 14, 3, 42, 778000, tzinfo=datetime.timezone.utc))`

## `raw_veeam_sessions` örnek 3 satır

- `('87fa4bb7-0d61-42c7-b9d3-c5cec6254516', 'KaleKilit_FortiAnalyzer', '4fb95242-fb4a-44f8-92ca-e977d161d88d', 'ReplicaJob', 'Working', datetime.datetime(2025, 8, 18, 17, 0, 22, 583000, tzinfo=datetime.timezone.utc), None, 'None', '', False, 0, 958030140, '00000000-0000-0000-0000-000000000000', 'VMware', '2f8c2a27-377a-4a61-b61e-7388d86164de', '/api/v1/replicas/2f8c2a27-377a-4a61-b61e-7388d86164de', None, '10.34.2.104', datetime.datetime(2025, 8, 18, 14, 3, 42, 778000, tzinfo=datetime.timezone.utc))`
- `('52988129-29ef-4bdf-852d-e7c9f59c46c8', 'KaleKilit2', '9010f29e-6eb3-4d76-8f74-a22151b6af36', 'ReplicaJob', 'Working', datetime.datetime(2025, 8, 18, 17, 0, 22, 533000, tzinfo=datetime.timezone.utc), None, 'None', '', False, 0, 958029900, '00000000-0000-0000-0000-000000000000', 'VMware', None, '/api/v1/replicas?jobIdFilter=9010f29e-6eb3-4d76-8f74-a22151b6af36', None, '10.34.2.104', datetime.datetime(2025, 8, 18, 14, 3, 42, 778000, tzinfo=datetime.timezone.utc))`
- `('656ea9e5-5a78-41c3-9fbe-6e5dc2bf5a81', 'Marubeni-TIMSAPPRD01new', 'a0d9364d-6815-4ffe-b6aa-a16966f15445', 'ReplicaJob', 'Working', datetime.datetime(2025, 8, 18, 17, 0, 22, 52000, tzinfo=datetime.timezone.utc), None, 'None', '', False, 0, 958030107, '00000000-0000-0000-0000-000000000000', 'VMware', '2a05dd40-b680-48a2-8172-2c5697d795a5', '/api/v1/replicas/2a05dd40-b680-48a2-8172-2c5697d795a5', None, '10.34.2.104', datetime.datetime(2025, 8, 18, 14, 3, 42, 778000, tzinfo=datetime.timezone.utc))`

## `raw_zerto_vpg_metrics` örnek 3 satır

- `('zerto_vpg', datetime.datetime(2025, 10, 23, 8, 13, 57, tzinfo=datetime.timezone.utc), '10.50.9.18', '86a9eeff-26dc-44ea-b55f-1489cd774029', ' Cs_Smart_Message-Lsapp_Bltapi_02', 3, 755, 1, 2, 1, 'DC14-Site02-V10', 'TurksatDC_ZVM', [], 92, Decimal('4.7412'), 264289, 264289)`
- `('zerto_vpg', datetime.datetime(2025, 10, 23, 11, 24, 9, 622000, tzinfo=datetime.timezone.utc), '10.50.9.18', 'db100a19-a594-4040-a31a-94c94460e504', ' Cs_Smart_Message-Lsapp_Bltapi_01', 1, 203, 1, 0, 1, 'DC14-Site02-V10', 'TurksatDC_ZVM', [], 93, Decimal('4.2651'), 264289, 264289)`
- `('zerto_vpg', datetime.datetime(2025, 10, 23, 11, 24, 9, 225000, tzinfo=datetime.timezone.utc), '10.50.9.18', '50b590a7-6ae0-4cab-b57d-742a0f495312', ' Cs_Smart_Message-Lsapp_Bltapi_03', 1, 41, 1, 0, 1, 'DC14-Site02-V10', 'TurksatDC_ZVM', [], 90, Decimal('4.0264'), 264310, 264310)`

## `raw_zerto_vm_metrics` örnek 3 satır

- `('zerto_vm', datetime.datetime(2025, 10, 23, 11, 33, 10, 470000, tzinfo=datetime.timezone.utc), '10.50.9.18', '241f9193-f402-41f2-a0d0-fa833ff00201.vm-514822', '241f9193-f402-41f2-a0d0-fa833ff00201.vm-514822', 'Cs_Smart_Message-Lsapp_Bltapi_02', 'Cs_Smart_Message-Lsapp_Bltapi_02', 3, '86a9eeff-26dc-44ea-b55f-1489cd774029', 2, 131072, 1, 1, 'LinuxCentOs', ['10.51.165.121'], [{'volume_id': 'scsi:0:0', 'public_cloud_id': None}], True, None, None)`
- `('zerto_vm', datetime.datetime(2025, 10, 23, 11, 33, 10, 967000, tzinfo=datetime.timezone.utc), '10.50.9.18', '241f9193-f402-41f2-a0d0-fa833ff00201.vm-514821', '241f9193-f402-41f2-a0d0-fa833ff00201.vm-514821', 'Cs_Smart_Message-Lsapp_Bltapi_01', 'Cs_Smart_Message-Lsapp_Bltapi_01', 3, 'db100a19-a594-4040-a31a-94c94460e504', 2, 131072, 1, 1, 'LinuxCentOs', ['10.51.165.120'], [{'volume_id': 'scsi:0:0', 'public_cloud_id': None}], True, None, None)`
- `('zerto_vm', datetime.datetime(2025, 10, 23, 11, 33, 10, 938000, tzinfo=datetime.timezone.utc), '10.50.9.18', '241f9193-f402-41f2-a0d0-fa833ff00201.vm-514823', '241f9193-f402-41f2-a0d0-fa833ff00201.vm-514823', 'Cs_Smart_Message-Lsapp_Bltapi_03', 'Cs_Smart_Message-Lsapp_Bltapi_03', 1, '50b590a7-6ae0-4cab-b57d-742a0f495312', 2, 131072, 1, 1, 'LinuxCentOs', ['10.51.165.133'], [{'volume_id': 'scsi:0:0', 'public_cloud_id': None}], True, None, None)`

## `raw_zerto_alert_metrics` örnek 3 satır

- `('zerto_alert', datetime.datetime(2025, 10, 23, 11, 36, 3, tzinfo=datetime.timezone.utc), '10.50.9.18', 'bf3fba04-2b2a-43bd-bff4-1c4a4456a0b7', 'bf3fba04-2b2a-43bd-bff4-1c4a4456a0b7', 'The VPG  Cs_Smart_Message-Lsapp_Bltmng_02 has been protected for 12 hours and 14 minutes but the journal history is only 9 hours and 10 minutes.', None, 'Warning', 'Vpg', None, None, 'eb8dce2b-6efe-4927-a9ea-9d28f2dc695c', False, False, [{'rel': None, 'href': 'https://10.50.9.18/v1/vpgs/eb8dce2b-6efe-4927-a9ea-9d28f2dc695c', 'type': 'VpgApi', 'identifier': 'eb8dce2b-6efe-4927-a9ea-9d28f2dc695c'}], [])`
- `('zerto_alert', datetime.datetime(2025, 10, 23, 11, 36, 30, tzinfo=datetime.timezone.utc), '10.50.9.18', 'ec0a68ef-4a4c-411b-a6ae-95f8ce56b3a8', 'ec0a68ef-4a4c-411b-a6ae-95f8ce56b3a8', 'VRA on host  was deleted from the hypervisor manager. Affected VPGS are .', None, 'Error', 'Vra', None, None, None, False, False, [], [])`
- `('zerto_alert', datetime.datetime(2025, 10, 23, 11, 36, 30, tzinfo=datetime.timezone.utc), '10.50.9.18', '78adcae8-c2e3-47ab-9d66-928c86a30527', '78adcae8-c2e3-47ab-9d66-928c86a30527', 'Diskbox on host  was deleted from the hypervisor manager. Affected VPGS are .', None, 'Error', 'Vra', None, None, None, False, False, [], [])`

## `raw_netbackup_jobs_metrics` örnek 3 satır

- `('netbackup_job', datetime.datetime(2026, 2, 18, 22, 31, 4, tzinfo=datetime.timezone.utc), '10.50.1.126', '34936876', 'job', '34936876', '0', '257781', 'BACKUP', 'USERBACKUP', 'SAP', 'abc-dete-bw-dev-catalog', 'APPLICATION_BACKUP', 'Default-Application-Backup', 'abc-dete-bw-dev', 'abdadm', 'sapsys', 'abc-dete-bw-dev_1771453516', 'stu_nbwormstdc13-NONWORM', 'nbmediadc14.blt.vc', 'STANDARD', 0, 0, 0, 0, 'DONE', 1, 0, 2688, 0, Decimal('1816.00'), Decimal('100.00'), False, False, False, False, 'LAN', -99, '0', 0, 0, 0, datetime.datetime(2026, 2, 18, 22, 25, 16, tzinfo=datetime.timezone.utc), datetime.datetime(2026, 2, 18, 22, 25, 24, tzinfo=datetime.timezone.utc), datetime.datetime(2026, 2, 18, 22, 25, 16, tzinfo=datetime.timezone.utc), datetime.datetime(2026, 2, 18, 22, 25, 32, tzinfo=datetime.timezone.utc), 0, '34936876', 3, 1, False, -99, 0, 'PT8S', 'PT8S', 'OFF', 'abc-dete-bw-dev', 'STANDARD', Decimal('95.40'), 0, 'SAP_LOG', Decimal('76.20'), Decimal('19.20'))`
- `('netbackup_job', datetime.datetime(2026, 2, 18, 22, 30, 20, tzinfo=datetime.timezone.utc), '10.50.1.126', '34936589', 'job', '34936589', '0', '252982', 'BACKUP', 'USERBACKUP', 'SAP', 'abc-dete-bw-dev-catalog', 'APPLICATION_BACKUP', 'Default-Application-Backup', 'abc-dete-bw-dev', 'abdadm', 'sapsys', 'abc-dete-bw-dev_1771453247', 'stu_nbwormstdc13-NONWORM', 'nbmediadc14.blt.vc', 'STANDARD', 0, 0, 0, 0, 'DONE', 1, 0, 3424, 0, Decimal('3264.00'), Decimal('100.00'), False, False, False, False, 'LAN', -99, '0', 0, 0, 0, datetime.datetime(2026, 2, 18, 22, 20, 47, tzinfo=datetime.timezone.utc), datetime.datetime(2026, 2, 18, 22, 20, 56, tzinfo=datetime.timezone.utc), datetime.datetime(2026, 2, 18, 22, 20, 47, tzinfo=datetime.timezone.utc), datetime.datetime(2026, 2, 18, 22, 21, 2, tzinfo=datetime.timezone.utc), 0, '34936589', 3, 1, False, -99, 0, 'PT9S', 'PT9S', 'OFF', 'abc-dete-bw-dev', 'STANDARD', Decimal('98.70'), 0, 'SAP_LOG', Decimal('93.40'), Decimal('5.40'))`
- `('netbackup_job', datetime.datetime(2026, 2, 18, 22, 29, 20, tzinfo=datetime.timezone.utc), '10.50.1.126', '34936379', 'job', '34936379', '0', '249415', 'BACKUP', 'USERBACKUP', 'SAP', 'abc-dete-bw-dev-catalog', 'APPLICATION_BACKUP', 'Default-Application-Backup', 'abc-dete-bw-dev', 'abdadm', 'sapsys', 'abc-dete-bw-dev_1771453046', 'stu_nbwormstdc13-NONWORM', 'nbmediadc14.blt.vc', 'STANDARD', 0, 0, 0, 0, 'DONE', 1, 0, 3424, 0, Decimal('2702.00'), Decimal('100.00'), False, False, False, False, 'LAN', -99, '0', 0, 0, 0, datetime.datetime(2026, 2, 18, 22, 17, 26, tzinfo=datetime.timezone.utc), datetime.datetime(2026, 2, 18, 22, 17, 34, tzinfo=datetime.timezone.utc), datetime.datetime(2026, 2, 18, 22, 17, 26, tzinfo=datetime.timezone.utc), datetime.datetime(2026, 2, 18, 22, 17, 42, tzinfo=datetime.timezone.utc), 0, '34936379', 3, 1, False, -99, 0, 'PT8S', 'PT8S', 'OFF', 'abc-dete-bw-dev', 'STANDARD', Decimal('98.80'), 0, 'SAP_LOG', Decimal('93.40'), Decimal('5.40'))`

## `raw_veeam_jobs_states` status dağılımı (son 30 gün)

- `('None', 5443)`
- `('Success', 3902)`
- `('Warning', 34)`
- `('Failed', 26)`

## `raw_veeam_jobs_states` status dağılımı (son 30 gün)

- `('running', 5427)`
- `('inactive', 3977)`
- `('disabled', 2)`

## `raw_veeam_sessions` status dağılımı (son 30 gün)

- `('Success', 3320731)`
- `('None', 50119)`
- `('Failed', 36329)`
- `('Warning', 18523)`

## `raw_zerto_vpg_metrics` status dağılımı (son 30 gün)

- `(1, 1918717)`
- `(2, 4282)`
- `(3, 2603)`
- `(0, 47)`
- `(4, 42)`
- `(5, 3)`

## `raw_netbackup_jobs_metrics` status dağılımı (son 30 gün)

- `(0, 22313282)`
- `(None, 827847)`
- `(2106, 5109)`
- `(230, 3933)`
- `(6, 2960)`
- `(1, 2865)`
- `(54, 2057)`
- `(13, 1591)`
- `(83, 1321)`
- `(196, 1172)`
- `(2074, 1050)`
- `(58, 1037)`
- `(25, 718)`
- `(50, 691)`
- `(87, 586)`
- `(21, 520)`
- `(252, 392)`
- `(247, 381)`
- `(5402, 306)`
- `(88, 303)`
- `(811, 281)`
- `(47, 221)`
- `(29, 198)`
- `(84, 191)`
- `(150, 133)`
- `(800, 70)`
- `(2505, 66)`
- `(199, 57)`
- `(71, 57)`
- `(9132, 55)`
- `(5457, 52)`
- `(2, 48)`
- `(191, 43)`
- `(23, 43)`
- `(802, 38)`
- `(90, 38)`
- `(200, 36)`
- `(24, 29)`
- `(130, 27)`
- `(5455, 20)`
- `(7654, 19)`
- `(160, 15)`
- `(61, 14)`
- `(12, 13)`
- `(4287, 12)`
- `(48, 11)`
- `(4292, 9)`
- `(156, 9)`
- `(26, 8)`
- `(5411, 7)`
- `(14, 5)`
- `(5449, 4)`
- `(40, 3)`
- `(239, 3)`
- `(7640, 3)`
- `(49, 3)`
- `(133, 3)`
- `(7276, 2)`
- `(7658, 2)`
- `(11, 1)`
- `(2107, 1)`
- `(5412, 1)`
