"""Domain scope guard — deterministic out-of-scope / instruction-override handling."""

from __future__ import annotations

import re
from dataclasses import dataclass

_DC_RE = re.compile(r"\b(?:DC|AZ|ICT|UZ|DH)\d+\b", re.IGNORECASE)

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

_OFFTOPIC = (
    "aşk hayat", "ask hayat", "aşk yaşam", "magazin", "ünlü", "unlu", "şarkıcı", "sarkici",
    "oyuncu", "sanatçı", "sanatci", "biyografi", "kimin sevgili", "kiminle evli", "siyaset",
    "seçim", "secim", "cumhurbaşkan", "milletvekili", "futbol", "basketbol", " maç", " mac ",
    "spor müsabaka", "yemek tarif", "tarifi ver", "şiir yaz", "siir yaz", "film öner", "dizi öner",
    "burç", "astroloji", "hava durumu", "ajda pekkan", "şarkı söz", "hikaye yaz", "masal anlat",
    "fıkra anlat", "espri yap", "şaka yap",
    "sigara", "tütün", "tutun", "içki", "alkol", "sağlık", "saglik", "zararlı", "zararli",
    "kanser", "nikotin", "beslenme", "diyet",
)

_GREETING = (
    "merhaba", "selam", "hey", "hi", "hello", "günaydın", "gunaydin", "iyi günler",
    "nasılsın", "nasilsin", "test",
)

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
    run_tools: bool = True
    reason: str = ""


def _has(text: str, kws: tuple[str, ...]) -> bool:
    return any(k in text for k in kws)


def has_domain_signal(message: str) -> bool:
    text = (message or "").lower()
    return _has(text, _DOMAIN) or bool(_DC_RE.search(message or ""))


def is_greeting_only(message: str) -> bool:
    text = (message or "").lower().strip()
    if has_domain_signal(message):
        return False
    if len(text) > 40:
        return False
    return _has(text, _GREETING) or text in ("test", "deneme", "ok")


def evaluate(message: str) -> ScopeDecision:
    text = (message or "").lower()
    has_domain = has_domain_signal(message)
    has_offtopic = _has(text, _OFFTOPIC)
    has_injection = _has(text, _INJECTION)

    if has_offtopic and not has_domain:
        reason = "injection_offtopic" if has_injection else "off_topic"
        return ScopeDecision(in_scope=False, run_tools=False, reason=reason)

    run_tools = not is_greeting_only(message)

    return ScopeDecision(
        in_scope=True,
        reset_conversation=has_injection,
        run_tools=run_tools,
        reason="greeting_no_tools" if not run_tools else "",
    )
