-- 006_seed_panel_definitions.sql
-- Seeds the gui_panel_definition registry with the granular panel taxonomy
-- derived from the 222 CRM products (Bulutistan Managed Cloud catalog).
--
-- Panel taxonomy:
--   * Virtualization: Hyperconverged / Klasik (Classic) / Power / Intel HANA / Power HANA
--     - Each split into _cpu / _ram / _storage panels.
--   * Backup: Veeam (replication cpu/ram/storage + image), Zerto (replication cpu/ram/storage),
--     NetBackup (storage), Hyperconverged image backup, Offsite (S3 / Veeam), Remote (Nutanix).
--   * Storage: S3 Ankara, S3 Istanbul.
--   * Firewall / Load Balancer: FortiGate, Palo Alto, Sophos, Citrix dedicated, Citrix shared LB.
--   * Licensing: Microsoft CSP, Microsoft SPLA, Red Hat, Ubuntu, SUSE, Veeam, Zerto, Plesk, cPanel.
--   * Network: Public IPv4, Public IPv6, DC access, DC port, VPN, DNS.
--   * Datacenter: Hosting (kabinet), Hosting (U), Energy.
--   * Management services (per VM / Adet): DB (Oracle, MSSQL, PostgreSQL, DB2, Azure SQL),
--     OS (Linux, Windows, Unix, SAP), Monitoring (standard / premium), Backup mgmt,
--     Security (SOC, SIEM, Firewall mgmt), Replication (Veeam / Zerto), AD, Support 7x24.
--   * Public Cloud (Azure Accelerated VMs).
--   * Other (catch-all).

BEGIN;

INSERT INTO gui_panel_definition (panel_key, label, family, resource_kind, display_unit, sort_order, notes) VALUES
    -- Hyperconverged Mimari (Nutanix backed)
    ('virt_hyperconverged_cpu',         'Hyperconverged Mimari — CPU',         'virt_hyperconverged', 'cpu',     'vCPU', 110, 'Nutanix cluster CPU capacity'),
    ('virt_hyperconverged_ram',         'Hyperconverged Mimari — RAM',         'virt_hyperconverged', 'ram',     'GB',   111, 'Nutanix cluster memory capacity'),
    ('virt_hyperconverged_storage',     'Hyperconverged Mimari — Storage',     'virt_hyperconverged', 'storage', 'GB',   112, 'Nutanix cluster storage capacity'),

    -- Klasik Mimari (VMware backed)
    ('virt_classic_cpu',                'Klasik Mimari — CPU',                  'virt_classic',        'cpu',     'vCPU', 120, 'VMware datacenter CPU capacity'),
    ('virt_classic_ram',                'Klasik Mimari — RAM',                  'virt_classic',        'ram',     'GB',   121, 'VMware datacenter memory capacity'),
    ('virt_classic_storage',            'Klasik Mimari — Storage',              'virt_classic',        'storage', 'GB',   122, 'VMware datacenter datastore capacity'),

    -- Power LPAR
    ('virt_power_cpu',                  'IBM Power Mimari — CPU',               'virt_power',          'cpu',     'Core', 130, 'IBM Power processor units'),
    ('virt_power_ram',                  'IBM Power Mimari — RAM',               'virt_power',          'ram',     'GB',   131, 'IBM Power memory'),
    ('virt_power_storage',              'IBM Power Mimari — Storage',           'virt_power',          'storage', 'GB',   132, 'IBM Power attached storage'),

    -- SAP Intel HANA (own family — CPU sized differently)
    ('virt_intel_hana_cpu',             'SAP Intel HANA — CPU',                 'virt_intel_hana',     'cpu',     'vCPU', 140, 'Intel HANA dedicated capacity'),
    ('virt_intel_hana_ram',             'SAP Intel HANA — RAM',                 'virt_intel_hana',     'ram',     'GB',   141, ''),
    ('virt_intel_hana_storage',         'SAP Intel HANA — Storage',             'virt_intel_hana',     'storage', 'GB',   142, ''),

    -- SAP Power HANA
    ('virt_power_hana_cpu',             'SAP Power HANA — CPU',                 'virt_power_hana',     'cpu',     'Core', 150, ''),
    ('virt_power_hana_ram',             'SAP Power HANA — RAM',                 'virt_power_hana',     'ram',     'GB',   151, ''),
    ('virt_power_hana_storage',         'SAP Power HANA — Storage',             'virt_power_hana',     'storage', 'GB',   152, ''),

    -- Veeam replication compute
    ('backup_veeam_replication_cpu',     'Veeam Replication — CPU',             'backup_veeam_replication', 'cpu',     'vCPU', 210, ''),
    ('backup_veeam_replication_ram',     'Veeam Replication — RAM',             'backup_veeam_replication', 'ram',     'GB',   211, ''),
    ('backup_veeam_replication_storage', 'Veeam Replication — Storage',         'backup_veeam_replication', 'storage', 'GB',   212, 'SSD/NVMe replikasyon disk alanı'),
    ('backup_veeam_image',               'Veeam Cloud Connect Backup',          'backup_veeam',             'other',   'per VM', 213, 'Veeam image backup license'),

    -- Zerto replication
    ('backup_zerto_replication_cpu',     'Zerto Replication — CPU',             'backup_zerto_replication', 'cpu',     'vCPU', 220, ''),
    ('backup_zerto_replication_ram',     'Zerto Replication — RAM',             'backup_zerto_replication', 'ram',     'GB',   221, ''),
    ('backup_zerto_replication_storage', 'Zerto Replication — Storage',         'backup_zerto_replication', 'storage', 'GB',   222, ''),

    -- NetBackup
    ('backup_netbackup_storage',         'NetBackup — Storage',                 'backup_netbackup',         'storage', 'GB',   230, 'Veritas NetBackup pool'),

    -- Image / offsite / remote backup
    ('backup_image_hyperconverged',      'Hyperconverged İmaj Yedekleme',       'backup_image',             'storage', 'GB',   240, ''),
    ('backup_offsite_s3',                'Offsite Backup — S3',                 'backup_offsite',           'storage', 'GB',   241, ''),
    ('backup_offsite_veeam',             'Offsite Backup — Veeam',              'backup_offsite',           'storage', 'GB',   242, ''),
    ('backup_remote_nutanix',            'Remote Backup — Nutanix',             'backup_remote',            'storage', 'GB',   243, ''),

    -- Object storage (S3 ICOS)
    ('storage_s3_ankara',                'IBM ICOS S3 — Ankara',                'storage_s3',               'storage', 'TB',   310, ''),
    ('storage_s3_istanbul',              'IBM ICOS S3 — İstanbul',              'storage_s3',               'storage', 'TB',   311, ''),

    -- Firewall appliances
    ('firewall_fortigate',               'FortiGate Sanal Dedike Appliance',    'firewall',                 'other',   'Adet', 410, ''),
    ('firewall_paloalto',                'Palo Alto Sanal Dedike Appliance',    'firewall',                 'other',   'Adet', 411, ''),
    ('firewall_sophos',                  'Sophos XG Sanal Dedike Appliance',    'firewall',                 'other',   'Adet', 412, ''),
    ('firewall_citrix_dedicated',        'Citrix Dedike WAF & LB',              'firewall',                 'other',   'Adet', 413, ''),
    ('loadbalancer_citrix_shared',       'Citrix Paylaşımlı LB / WAF',          'loadbalancer',             'other',   'Adet', 414, ''),

    -- Licensing
    ('license_microsoft_csp',            'Microsoft CSP / M365',                'license_microsoft',        'other',   'per User', 510, ''),
    ('license_microsoft_spla',           'Microsoft SPLA',                      'license_microsoft',        'other',   'Adet',     511, ''),
    ('license_redhat',                   'Red Hat (CCSP)',                      'license_redhat',           'other',   'Adet',     520, ''),
    ('license_suse',                     'SUSE Linux',                          'license_other',            'other',   'Adet',     521, ''),
    ('license_ubuntu',                   'Ubuntu Pro',                          'license_other',            'other',   'per VM',   522, ''),
    ('license_veeam',                    'Veeam Cloud Connect Replication',     'license_other',            'other',   'per VM',   523, ''),
    ('license_zerto',                    'Zerto Enterprise Cloud Edition',      'license_other',            'other',   'Adet',     524, ''),
    ('license_plesk',                    'Plesk',                               'license_other',            'other',   'Adet',     525, ''),
    ('license_cpanel',                   'cPanel',                              'license_other',            'other',   'Adet',     526, ''),

    -- Network
    ('network_public_ipv4',              'Public IPv4 Blokları',                'network',                  'other',   'Adet', 610, ''),
    ('network_public_ipv6',              'Public IPv6 Blokları',                'network',                  'other',   'Adet', 611, ''),
    ('network_dc_access',                'Veri Merkezi Erişim ve L3 DDoS',      'network',                  'other',   'Mbit', 612, ''),
    ('network_dc_port',                  'DC Switch / Cross Connect Portları',  'network',                  'other',   'Adet', 613, ''),
    ('network_vpn',                      'Sophos SSL VPN',                      'network',                  'other',   'per User', 614, ''),
    ('network_dns',                      'Cloud DNS Hizmeti',                   'network',                  'other',   'per Domain', 615, ''),

    -- Datacenter hosting
    ('dc_hosting_kabinet',               'DC Barındırma — Kabinet',             'dc_hosting',               'other',   'Adet', 710, ''),
    ('dc_hosting_u',                     'DC Barındırma — U',                   'dc_hosting',               'other',   'U',    711, ''),
    ('dc_energy',                        'DC Enerji Birim Bedeli',              'dc_energy',                'other',   'kW',   712, ''),

    -- Managed services (database)
    ('mgmt_database_oracle',             'Oracle Veritabanı Yönetimi',          'mgmt_database',            'other',   'Adet', 810, ''),
    ('mgmt_database_mssql',              'MSSQL Veritabanı Yönetimi',           'mgmt_database',            'other',   'Adet', 811, ''),
    ('mgmt_database_postgres',           'PostgreSQL Veritabanı Yönetimi',      'mgmt_database',            'other',   'Adet', 812, ''),
    ('mgmt_database_db2',                'DB2 Veritabanı Yönetimi',             'mgmt_database',            'other',   'Adet', 813, ''),
    ('mgmt_database_azure_sql',          'Azure SQL Veritabanı Yönetimi',       'mgmt_database',            'other',   'Adet', 814, ''),

    -- Managed OS
    ('mgmt_os_linux',                    'Linux İşletim Sistemi Yönetimi',      'mgmt_os',                  'other',   'per VM', 820, ''),
    ('mgmt_os_windows',                  'Windows İşletim Sistemi Yönetimi',    'mgmt_os',                  'other',   'per VM', 821, ''),
    ('mgmt_os_unix',                     'Unix İşletim Sistemi Yönetimi',       'mgmt_os',                  'other',   'per VM', 822, ''),
    ('mgmt_os_sap',                      'SUSE for SAP HANA Yönetimi',          'mgmt_os',                  'other',   'per VM', 823, ''),

    -- Managed monitoring / backup / security
    ('mgmt_monitoring_standard',         'Standart Monitoring Hizmeti',         'mgmt_monitoring',          'other',   'per VM', 830, ''),
    ('mgmt_monitoring_premium',          'Premium Monitoring Hizmeti',          'mgmt_monitoring',          'other',   'per VM', 831, ''),
    ('mgmt_backup',                      'Yedekleme Yönetimi (Tier-3)',         'mgmt_backup',              'other',   'per VM', 840, ''),
    ('mgmt_security_soc',                'SOC Yönetim Hizmeti',                 'mgmt_security',            'other',   'Adet', 850, ''),
    ('mgmt_security_siem',               'SIEM Yönetim Hizmeti',                'mgmt_security',            'other',   'Adet', 851, ''),
    ('mgmt_security_firewall',           'Güvenlik Duvarı Hizmet Yönetimi',     'mgmt_security',            'other',   'Adet', 852, ''),

    -- Managed replication / AD / support
    ('mgmt_replication_veeam',           'Veeam Replikasyon Yönetim Hizmeti',   'mgmt_replication',         'other',   'Adet', 860, ''),
    ('mgmt_replication_zerto',           'Zerto Replikasyon Yönetim Hizmeti',   'mgmt_replication',         'other',   'Adet', 861, ''),
    ('mgmt_active_directory',            'Active Directory Yönetim Hizmeti',    'mgmt_misc',                'other',   'per VM', 870, ''),
    ('mgmt_support_7x24',                'Bulutistan 7x24 Destek',              'mgmt_misc',                'other',   'per VM', 871, ''),

    -- Public cloud (Azure Accelerated)
    ('public_cloud_azure',               'Public Cloud — Azure Accelerated',    'public_cloud',             'other',   'Adet', 910, ''),

    -- Catch-all
    ('other',                            'Diğer / Sınıflandırılmamış',          'other',                    'other',   'Adet', 999, '')
ON CONFLICT (panel_key) DO UPDATE SET
    label         = EXCLUDED.label,
    family        = EXCLUDED.family,
    resource_kind = EXCLUDED.resource_kind,
    display_unit  = EXCLUDED.display_unit,
    sort_order    = EXCLUDED.sort_order,
    notes         = COALESCE(NULLIF(EXCLUDED.notes,''), gui_panel_definition.notes),
    updated_by    = 'seed',
    updated_at    = NOW();

COMMIT;
