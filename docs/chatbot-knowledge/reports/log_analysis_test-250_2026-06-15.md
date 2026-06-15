# Chatbot Log Analysis — 2026-06-15

Source: `root@10.134.52.250`
Days window: **90**
Focus: `all`

Turns analyzed: **41**

## Status distribution

- clarification: 7
- success: 34

## Averages

- Latency (ms): 9578.8
- Tool calls: 2.79
- LLM rounds: 2.82

## Customer / CRM signals

- Customer-related messages: 1
- CRM-related messages: 0
- Turns with customer tools: 0
- Turns with CRM/sellable tools: 1
- Bad or empty-investigation answers: 5
- Zero-tool success turns: 3

## Top tools

- get_datacenters_summary: 42
- get_dashboard_overview: 33
- get_dc_compute_classic: 6
- get_datacenter_detail: 3
- get_dc_vm_cpu_summary: 2
- get_dc_compute_hyperconverged: 2
- get_dc_vm_cpu_top: 1
- get_global_km_cluster_memory_top: 1
- get_sellable_summary: 1
- get_sellable_by_panel: 1
- get_sellable_by_family: 1

## Tool errors

- get_datacenters_summary: 4
- get_dc_compute_classic: 3
- get_dashboard_overview: 1
- get_datacenter_detail: 1
- get_dc_compute_hyperconverged: 1

## Bad answer samples

- `e01a778eb03d471e9f598be9b58a4eff` — vm_count
- `6a30afa53eec43d48b1203904e1bda27` — test
- `b8a700f090b64160bf69863343e77967` — En yoğun datacenter hangisi?
- `ae4175fe18814d889c4653d5df2cac5a` — test
- `2d110bd486654619a01b18c2e8079b18` — test

## Customer message samples

- `3390c085adce4eca8e0a6b42d24a96ed` — daha verimli satış yapabilmek için hangi datacenter'lara hangi mimarilerde yatır | tools: ['get_datacenters_summary', 'get_sellable_summary', 'get_sellable_by_panel', 'get_sellable_by_family', 'get_datacenters_summary', 'get_dc_compute_classic', 'get_dc_compute_hyperconverged', 'get_dc_compute_classic']
