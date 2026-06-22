# Datalake'te Veri Toplanamayan (Erişilemeyen) Sanallaştırma Datasource'ları

**Hazırlanma tarihi:** 2026-06-22
**Veri kaynağı:** HMDL Collector Monitoring — `hmdl.collector_target` + `hmdl.collector_check_log` (bulutlake DB `10.134.16.6:5000`)
**Durum tarihi (son collector sync run):** 2026-06-10
**Erişim sinyali:** `last_check_status = 'telnet_fail'` → NiFi proxy ilgili port'a (vCenter 443 / Nutanix Prism 9440 / IBM-HMC 12443) ulaşamıyor.

> Not: Liste, son sync run'ın (2026-06-10) durumunu yansıtır. Güncel durum için yeni bir collector sync run gerekir.

---

## Kapsam

"Sanallaştırma datasource'u" olarak şu collector tipleri alınmıştır:

| Collector | Platform | Port |
|---|---|---|
| `VmWare` | vCenter | 443 |
| `Nutanix` | Prism | 9440 |
| `IBM-HMC` | IBM Power (HMC) | 12443 |

Storage (IBM-SAN, IBM-Virtualize, S3), yedekleme (Veeam, Netbackup, Zerto) ve donanım (ILO/Inspur Redfish) datasource'ları kapsam dışıdır.

## Doğrulama

- Her datasource birden çok proxy'den kontrol edilir (DC'nin NIFI1/NIFI2 + merkezi MAIN/hub). Aşağıdaki liste **IP bazında tekilleştirilmiştir**.
- **Doğrulandı:** Erişilemeyen datasource'ların hiçbiri başka bir proxy'den de erişilemiyor (alternatif proxy'den `ok` alan yok). Yani hepsi gerçekten tüm noktalarından erişilemez durumda.

## Özet

- **Toplam tekil erişilemeyen sanallaştırma datasource: 26**
  - **`monitored` (20)** → toplanması gereken ama erişilemeyen → **gerçek aksiyon listesi** (ağ/firewall/port açılması gereken noktalar)
  - **`not_monitored` (4)** → kasıtlı olarak toplanmıyor
  - **`customer_environment` (2)** → müşterinin kendi ortamı, bizim sorumluluğumuzda değil

---

## DC Bazında Liste

### DC11 — NiFi: `10.6.116.250` (NIFI1), `10.6.116.251` (NIFI2)
| Tip | İsim | IP | Durum |
|---|---|---|---|
| IBM-HMC | HMC_DC11 | `10.6.2.153` | monitored |
| Nutanix | PremierDC-Nutanix-DC11-G3 | `10.6.2.80` | monitored |
| Nutanix | PremierDC-Nutanix-DC11-G4 | `10.6.2.97` | monitored |
| Nutanix | PremierDC-Nutanix-DC11-G5 | `10.6.2.28` | monitored |
| Nutanix | PremierDC-Nutanix-DC11-G6 | `10.6.2.200` | monitored |
| VmWare | PremierDC-Vmware-IST-Premier | `10.6.2.146` | monitored |

### DC12 — NiFi: `10.35.16.250` (NIFI1), `10.35.16.251` (NIFI2)
| Tip | İsim | IP | Durum |
|---|---|---|---|
| Nutanix | Vodafone İzmir-Nutanix-DC12-G4 | `10.35.2.178` | monitored |

### DC13 (hub) — NiFi: `10.134.16.10` (NIFI1)
| Tip | İsim | IP | Durum |
|---|---|---|---|
| Nutanix | Equinix IL2-Agesa-DC13 | `172.31.21.10` | monitored |
| Nutanix | Gateway-PRD-CLS | `10.87.63.200` | monitored |
| Nutanix | Equinix IL2-Nutanix-AYT-PROD-DC13 | `10.128.2.200` | not_monitored |
| VmWare | Equinix IL2-Vmware-IST-Equinix_vc1 | `10.34.2.10` | not_monitored |
| VmWare | MoneyGram-CLS | `10.100.0.200` | customer_environment |

### DC14 — NiFi: `10.50.16.250` (NIFI1), `10.50.16.251` (NIFI2)
| Tip | İsim | IP | Durum |
|---|---|---|---|
| VmWare | Paycore Vcenter | `10.82.197.10` | monitored |

### DC15 — NiFi: `10.40.16.250` (NIFI1), `10.40.16.251` (NIFI2)
| Tip | İsim | IP | Durum |
|---|---|---|---|
| IBM-HMC | HMC_DC15 | `10.40.10.110` | monitored |
| Nutanix | Turk Telekom-Nutanix-DC15-G1 | `10.40.2.66` | monitored |
| Nutanix | Turk Telekom-Nutanix-DC15-G2 | `10.40.2.146` | monitored |
| Nutanix | Turk Telekom-Nutanix-DC15-G3 | `10.40.2.207` | monitored |
| VmWare | Turk Telekom-Vmware-IST-TT Esenyurt | `10.40.2.150` | monitored |

### DC16 — NiFi: `10.60.16.250` (NIFI1), `10.60.16.251` (NIFI2)
| Tip | İsim | IP | Durum |
|---|---|---|---|
| Nutanix | Gateway-DR-CLS | `10.87.77.30` | monitored |
| Nutanix | HRWEB-DR-CLS | `10.242.2.20` | monitored |
| Nutanix | Turksat-Nutanix-AYT-DR-DC16 | `10.129.2.200` | not_monitored |
| VmWare | MoneyGramDr-CLS | `10.200.0.200` | customer_environment |

### DC17 — NiFi: `10.90.16.250` (NIFI1), `10.90.16.251` (NIFI2)
| Tip | İsim | IP | Durum |
|---|---|---|---|
| VmWare | Isttelkom-Vmware-IST-İsttelkom | `10.90.2.64` | not_monitored |

> DC17'nin tek kaydı `not_monitored` — DC17'nin sanallaştırılamaması durumuyla tutarlı.

### DC18 (hub) — NiFi: `10.134.16.207` (NIFI1), `10.134.16.208` (NIFI2)
| Tip | İsim | IP | Durum |
|---|---|---|---|
| Nutanix | HRWEB-CLS | `10.241.2.20` | monitored |

### UZ11 — NiFi: `10.85.16.13` (NIFI1), `10.85.16.14` (NIFI2)
| Tip | İsim | IP | Durum |
|---|---|---|---|
| Nutanix | Uzbekistan-Nutanix-UZ11-CLS | `10.85.3.50` | monitored |
| VmWare | Uzbekistan-Vmware-UZ11 | `10.85.2.50` | monitored |

---

## Aksiyon Listesi (yalnızca `monitored` — 20 adet)

Bunlar veri toplamamız gereken ama NiFi proxy'lerin erişemediği noktalar — ağ/firewall ekibiyle ilgili port'ların açılması gerekir:

| DC | Tip | İsim | IP | Port |
|---|---|---|---|---|
| DC11 | IBM-HMC | HMC_DC11 | `10.6.2.153` | 12443 |
| DC11 | Nutanix | PremierDC-Nutanix-DC11-G3 | `10.6.2.80` | 9440 |
| DC11 | Nutanix | PremierDC-Nutanix-DC11-G4 | `10.6.2.97` | 9440 |
| DC11 | Nutanix | PremierDC-Nutanix-DC11-G5 | `10.6.2.28` | 9440 |
| DC11 | Nutanix | PremierDC-Nutanix-DC11-G6 | `10.6.2.200` | 9440 |
| DC11 | VmWare | PremierDC-Vmware-IST-Premier | `10.6.2.146` | 443 |
| DC12 | Nutanix | Vodafone İzmir-Nutanix-DC12-G4 | `10.35.2.178` | 9440 |
| DC13 | Nutanix | Equinix IL2-Agesa-DC13 | `172.31.21.10` | 9440 |
| DC13 | Nutanix | Gateway-PRD-CLS | `10.87.63.200` | 9440 |
| DC14 | VmWare | Paycore Vcenter | `10.82.197.10` | 443 |
| DC15 | IBM-HMC | HMC_DC15 | `10.40.10.110` | 12443 |
| DC15 | Nutanix | Turk Telekom-Nutanix-DC15-G1 | `10.40.2.66` | 9440 |
| DC15 | Nutanix | Turk Telekom-Nutanix-DC15-G2 | `10.40.2.146` | 9440 |
| DC15 | Nutanix | Turk Telekom-Nutanix-DC15-G3 | `10.40.2.207` | 9440 |
| DC15 | VmWare | Turk Telekom-Vmware-IST-TT Esenyurt | `10.40.2.150` | 443 |
| DC16 | Nutanix | Gateway-DR-CLS | `10.87.77.30` | 9440 |
| DC16 | Nutanix | HRWEB-DR-CLS | `10.242.2.20` | 9440 |
| DC18 | Nutanix | HRWEB-CLS | `10.241.2.20` | 9440 |
| UZ11 | Nutanix | Uzbekistan-Nutanix-UZ11-CLS | `10.85.3.50` | 9440 |
| UZ11 | VmWare | Uzbekistan-Vmware-UZ11 | `10.85.2.50` | 443 |
