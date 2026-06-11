# 00 — Bulutistan Datalake WebUI Overview

## Ürün amacı

Bulutistan Datalake Platform GUI / WebUI, Bulutistan'ın veri merkezi, müşteri, altyapı, availability, backup, S3, storage, network, physical inventory, CRM sellable-potential ve IAM operasyonlarını tek bir web arayüzünde görünür hale getiren dashboard ürünüdür.

Uygulama Dash/Flask frontend shell'i ve ayrı FastAPI microservice'lerinden oluşur. WebUI sayfaları `src/pages/*`, UI componentleri `src/components/*`, backend API client katmanı `src/services/api_client.py` içindedir.

## Ana mimari

```text
Browser
  ↓
Dash/Flask WebUI frontend server
  ↓
Internal FastAPI microservices
  ├─ datacenter-api
  ├─ customer-api
  ├─ query-api
  ├─ crm-engine
  └─ admin-api
  ↓
PostgreSQL + Redis/cache + external telemetry/source systems
```

Chatbot eklentisi bunun yanında ayrı internal service'tir:

```text
WebUI chatbot widget
  ↓ server-side callback
chatbot-api
  ↓ hybrid planner + seed tools + optional LLM ReAct loop
allowlisted API tools + allowlisted read-only DB tools
  ↓
Bulutistan LLMaaS analysis-first answer (ReAct draft or synthesis)
```

## Chatbot'un rolü

Chatbot genel amaçlı internet botu değildir. Şu rolü üstlenmelidir:

- Bulutistan Datalake WebUI domain expert
- Datacenter/customer/VM/host/cluster data analyst
- Mevcut API + DB veri kaynaklarını bilen assistant
- Veriyi sadece listeleyen değil, risk ve aksiyon çıkaran operasyonel yardımcı

## Ana prensipler

1. **Page-independent reasoning:** Kullanıcı herhangi bir sayfadayken DC13/Boyner/S3/SLA/CRM sorusu sorabilir.
2. **Domain-aware planning:** "Klasik mimari", "KM", "allocated", "usage", "capacity", "değişkenlik" gibi kavramları doğru ayırmalıdır.
3. **Tool-first factuality:** Sayısal cevaplar yalnızca API/DB tool sonuçlarına dayanmalıdır.
4. **Repo/data model knowledge:** WebUI'da görünen kart/grafiklerin hangi endpointlerden ve tablolardan beslendiğini bilmelidir (ör. cluster listesi için `get_dc_classic_clusters` / `get_dc_hyperconverged_clusters`, zabbix storage trend için `get_dc_zabbix_storage_trend` gibi mevcut tool'lar dahil).
5. **Safe DB access:** DB'ye serbest SQL yok; sadece allowlist SELECT template. API yetersizse DB fallback — bkz. [[11_api_vs_db_routing]].
6. **Analytical answer:** Cevaplarda önce analiz, sonra sonuç; tablo, risk, aksiyon ve kaynak — bkz. [[13_executive_investigation]].
7. **Conversation session:** X ile kapatınca history silinir; açık oturumda context korunur — bkz. [[12_conversation_session]].
8. **Investigation budget:** Soru başına en fazla 150 tool + 150 LLM ReAct turu; veri yok iddiası yalnızca investigation_trace sonrası — bkz. [[13_executive_investigation]].
