"""
services/api_client.py — GUI-Service → Query-Service HTTP İstemcisi

Tüm fonksiyonlar senkron requests kütüphanesi kullanır (Dash callback'leri
senkron Python threadinde çalışır; asyncio event loop'u yoktur).

Hata yönetimi:
  - API erişilemez veya HTTP hata döndürürse logger.error ile loglanır.
  - Hata yukarı fırlatılır (raise): Çağıran callback no_update ile sessiz kalır.
  - Timeout: 120s — query-service cold start ~74s.
"""

import logging
import os

import requests

logger = logging.getLogger(__name__)

_QUERY_URL = os.getenv("QUERY_SERVICE_URL", "http://query-service:8002")
_HEADERS   = {"X-Internal-Key": os.getenv("INTERNAL_API_KEY", "")}
_TIMEOUT   = 120  # query-service cold start ~74s


def get_summary() -> list[dict]:
    """GET /datacenters/summary → list[DCSummary]"""
    try:
        r = requests.get(
            f"{_QUERY_URL}/datacenters/summary",
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except requests.exceptions.Timeout:
        logger.error("GET /datacenters/summary zaman aşımına uğradı (%ds)", _TIMEOUT)
        raise
    except requests.exceptions.HTTPError as exc:
        logger.error("GET /datacenters/summary HTTP hatası: %s", exc)
        raise
    except requests.exceptions.RequestException as exc:
        logger.error("GET /datacenters/summary erişim hatası: %s", exc)
        raise


def get_dc_detail(dc_code: str) -> dict:
    """GET /datacenters/{dc_code} → DCDetail"""
    try:
        r = requests.get(
            f"{_QUERY_URL}/datacenters/{dc_code}",
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except requests.exceptions.Timeout:
        logger.error("GET /datacenters/%s zaman aşımına uğradı (%ds)", dc_code, _TIMEOUT)
        raise
    except requests.exceptions.HTTPError as exc:
        logger.error("GET /datacenters/%s HTTP hatası: %s", dc_code, exc)
        raise
    except requests.exceptions.RequestException as exc:
        logger.error("GET /datacenters/%s erişim hatası: %s", dc_code, exc)
        raise


def get_overview_trends() -> dict:
    """
    GET /overview/trends → OverviewTrends

    Dönen yapı:
      {
        "cpu_pct":   {"labels": [...], "values": [...]},
        "ram_pct":   {"labels": [...], "values": [...]},
        "energy_kw": {"labels": [...], "values": [...]}
      }
    Redis boşsa labels/values listeleri boş döner — hata fırlatmaz.
    """
    try:
        r = requests.get(
            f"{_QUERY_URL}/overview/trends",
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except requests.exceptions.Timeout:
        logger.error("GET /overview/trends zaman aşımına uğradı (%ds)", _TIMEOUT)
        raise
    except requests.exceptions.HTTPError as exc:
        logger.error("GET /overview/trends HTTP hatası: %s", exc)
        raise
    except requests.exceptions.RequestException as exc:
        logger.error("GET /overview/trends erişim hatası: %s", exc)
        raise
