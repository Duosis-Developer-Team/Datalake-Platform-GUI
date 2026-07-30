# NetBackup fatura tabanı mutabakatı

Generated: 2026-07-30T23:11:28.902054+00:00

## Decision context (K-01 dual basis)

- Customer / CRM sold semantics → **PreDedup**
- DC / real cost → **PostDedup**
- Inventory shows both

## (A) CRM sold

| SKU | Name | UOM | Sold | TL | Customers |
|-----|------|-----|------|----|-----------|
| 000BLT-142 | Uygulama Yedekleme Hizmeti (Veritas NetBackup) | GB | 24599.0 | 10417 | 10 |
| 000BLT-203 | Klasik Mimari İmaj Yedekleme (Veritas Netbackup) | GB | 56274.6 | 27793 | 15 |

## (B/C) Jobs 30d pre vs post (GiB as GB proxy)

| Category | Jobs | PreDedup GB | PostDedup GB | Avg dedup |
|----------|------|-------------|--------------|-----------|
| application | 18417608 | 29837762.0 | 421912.2 | 92.57 |
| image | 106206 | 44324027.9 | 459335.0 | 96.26 |

**Totals:** pre=74161789.9 GB, post=881247.2 GB

## (D) Physical pools (latest)

- usable_gb=45127581.3
- used_gb=2108389.2
- free_gb=43019192.2

**Post vs pool used delta:** post=881247.2, pool_used=2108389.2, delta=-1227142.0

## (F) dedupratio DQ

- null=1465896, zero=4735, total=19216948, min=0.10, max=100.00, avg=92.59

## Recommendation

Use **dual basis** (not single pick): PreDedup for sold/customer; PostDedup for cost. Expect post ≈ pool used when job window and pool freshness align; large gaps indicate DQ or window mismatch.
