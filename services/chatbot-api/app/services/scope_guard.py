"""Domain scope guard — deterministic out-of-scope / instruction-override handling.

Runs before the planner and the LLM. The chatbot is a Bulutistan Datalake WebUI
domain assistant, not a general chatbot. A message that is clearly off-topic and
carries no domain signal is refused deterministically (no LLM, no tools). A pure
instruction-override ("forget everything") on an in-domain question is allowed,
but the prior conversation is dropped — the system/developer instructions are
never overridden.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_DC_RE = re.compile(r"\b(?:DC|AZ|ICT|UZ|DH)\d+\b", re.IGNORECASE)

# In-domain vocabulary (allowlist). Any hit => the message is on-topic enough.
_DOMAIN = (
    "datacenter", "data center", "veri merkezi", " dc", "customer", "müşteri", "musteri",
    "vm", "host", "cluster", "sunucu", "node", "vmware", "classic", "klasik", " km", "nutanix",
    "hyperconverged", "hci", "ibm", "power", "lpar", "cpu", "ram", "memory", "bellek",
    "storage", "disk", "depolama", "network", "trafik", "capacity", "kapasite", "allocated",
    "atanmış", "atanmis", "tahsis", "utilization", "usage", "kullanım", "kullanim", "performance",
    "performans", "sla", "availability", "erişilebilir", "uptime", "downtime", "backup", "yedek",
    "zerto", "veeam", "netbackup", "s3", "object storage", "vault", "pool", "crm", "sellable",
    "satılabilir", "satilabilir", "itsm", "ticket", "çağrı", "webui", "dashboard", "endpoint",
    "api", "database", "veritaban", "postgre", "sql", "compute", "sanal makine", "mimari",
    "inventory", "envanter", "rack", "kabinet",
)

# Clearly out-of-domain markers.
_OFFTOPIC = (
    "aşk hayat", "ask hayat", "aşk yaşam", "magazin", "ünlü", "unlu", "şarkıcı", "sarkici",
    "oyuncu", "sanatçı", "sanatci", "biyografi", "kimin sevgili", "kiminle evli", "siyaset",
    "seçim", "secim", "cumhurbaşkan", "milletvekili", "futbol", "basketbol", " maç", " mac ",
    "spor müsabaka", "yemek tarif", "tarifi ver", "şiir yaz", "siir yaz", "film öner", "dizi öner",
    "burç", "astroloji", "hava durumu", "ajda pekkan", "şarkı söz", "hikaye yaz", "masal anlat",
    "fıkra anlat", "espri yap", "şaka yap",
)

# Instruction-override / prompt-injection markers.
_INJECTION = (
    "söylediğim her şeyi unut", "soyledigim her seyi unut", "her şeyi unut", "herseyi unut",
    "ignore previous", "forget everything", "forget all previous", "önceki talimatları unut",
    "onceki talimatlari unut", "sistem prompt", "system prompt", "developer prompt",
    "talimatları yok say", "talimatlari yok say", "kuralları unut",
)

REFUSAL = (
    "Bu konuda yardımcı olamam. Ben Bulutistan Datalake WebUI içinde datacenter, müşteri, "
    "kapasite, performans, SLA, backup, S3, CRM ve altyapı verilerini analiz etmek için "
    "tasarlanmış bir asistanım. İstersen DC13, VMware, CPU, storage, backup veya müşteri "
    "kaynak kullanımıyla ilgili bir soru sorabilirsin."
)


@dataclass
class ScopeDecision:
    in_scope: bool
    reset_conversation: bool = False
    reason: str = ""


def _has(text: str, kws: tuple[str, ...]) -> bool:
    return any(k in text for k in kws)


def has_domain_signal(message: str) -> bool:
    text = (message or "").lower()
    return _has(text, _DOMAIN) or bool(_DC_RE.search(message or ""))


def evaluate(message: str) -> ScopeDecision:
    text = (message or "").lower()
    has_domain = has_domain_signal(message)
    has_offtopic = _has(text, _OFFTOPIC)
    has_injection = _has(text, _INJECTION)

    # Off-topic with no domain signal -> refuse (also covers injection+off-topic).
    if has_offtopic and not has_domain:
        reason = "injection_offtopic" if has_injection else "off_topic"
        return ScopeDecision(in_scope=False, reason=reason)

    # In scope. An instruction-override on a domain question drops prior
    # conversation (treated as a fresh query); system prompt is never overridden.
    return ScopeDecision(in_scope=True, reset_conversation=has_injection)
