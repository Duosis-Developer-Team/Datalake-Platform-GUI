"""
query-service/tests/conftest.py — Paylaşılan pytest fixture'ları

Önemli httpx Notu:
  httpx.Response, request atanmadan oluşturulduğunda raise_for_status()
  "A request instance has not been set" RuntimeError fırlatır.
  _httpx_response helper'ı bu yüzden dummy request ekler.

DI İzolasyonu:
  dependency_overrides[get_db_client] → mock_db_client (httpx mock)
  dependency_overrides[get_redis]     → mock_redis (AsyncMock)
  dependency_overrides[verify_internal_key] → lambda: None (bypass)
  Lifespan gerçek bağlantı kurar ama endpoint'lere gelen bağımlılıklar
  override'dan gelir → testler tamamen izole.
"""

import json
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from src.dependencies import get_db_client, get_redis, verify_internal_key
from src.main import app

# ── Sabit örnek veriler ───────────────────────────────────────────────────────

SAMPLE_TREND_ENTRY = json.dumps({"ts": "2026-02-25T12:00:00+00:00", "v": 42.5})

# DCSummary Pydantic modeline tam uygun veri
# Şema: id, name, location, status, cluster_count, host_count, vm_count, stats(DCStats)
SAMPLE_SUMMARY_RAW = [
    {
        "id": "DC11",
        "name": "DC11",
        "location": "Istanbul",
        "cluster_count": 4,
        "host_count": 64,
        "vm_count": 1370,
        "status": "Healthy",
        "stats": {
            "total_cpu": "100 / 500 GHz",
            "used_cpu_pct": 20.0,
            "total_ram": "200 / 1000 GB",
            "used_ram_pct": 25.0,
            "total_storage": "50 / 200 TB",
            "used_storage_pct": 30.0,
            "last_updated": "Live",
            "total_energy_kw": 18.0,
        },
    }
]


# ── Helpers: gerçek httpx.Response nesneleri ──────────────────────────────────

def _httpx_response(status_code: int, json_body, url: str = "http://db-service:8001/") -> httpx.Response:
    """
    httpx.Response nesnesi döndürür.

    UYARI: httpx.Response'da raise_for_status() ve hata metodları 'request'
    attribute'unu gerektirir. request kwarg'ı olmadan RuntimeError fırlatır.
    Bu yüzden dummy httpx.Request oluşturup response'a bağlıyoruz.
    """
    content = json.dumps(json_body).encode("utf-8")
    # Dummy request — raise_for_status() ve diğer metodlar için gerekli
    dummy_request = httpx.Request("GET", url)
    return httpx.Response(
        status_code=status_code,
        headers={"content-type": "application/json"},
        content=content,
        request=dummy_request,
    )


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_redis():
    """
    Redis mock — Cache MISS senaryosu:
      .get()    → None  (json.loads(None) çağrılmaz → MISS, httpx'e düş)
      .set()    → True
      .lrange() → tek noktalı trend JSON listesi
    """
    redis = AsyncMock()
    redis.get.return_value = None
    redis.set.return_value = True
    redis.lrange.return_value = [SAMPLE_TREND_ENTRY]
    return redis


@pytest.fixture
def mock_redis_empty():
    """Boş Redis — trends graceful degradation testi."""
    redis = AsyncMock()
    redis.get.return_value = None
    redis.set.return_value = True
    redis.lrange.return_value = []
    return redis


@pytest.fixture
def mock_db_client():
    """
    httpx.AsyncClient mock'u — gerçek httpx.Response nesneleri döndürür.
    URL path'a göre:
      /datacenters/summary → SAMPLE_SUMMARY_RAW listesi
      diğerleri            → boş liste
    """
    async def _mock_get(url, **kwargs):
        url_str = str(url)
        if "summary" in url_str:
            return _httpx_response(200, SAMPLE_SUMMARY_RAW, url_str)
        return _httpx_response(200, [], url_str)

    client = AsyncMock(spec=httpx.AsyncClient)
    client.get = _mock_get
    return client


@pytest.fixture
def api_client(mock_db_client, mock_redis):
    """
    DI override'lı TestClient.
    dependency_overrides ile tüm dış bağımlılıklar izole edilir.
    """
    app.dependency_overrides[get_db_client] = lambda: mock_db_client
    app.dependency_overrides[get_redis] = lambda: mock_redis
    app.dependency_overrides[verify_internal_key] = lambda: None

    with TestClient(app, raise_server_exceptions=True) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def api_client_empty_redis(mock_db_client, mock_redis_empty):
    """Boş Redis ile TestClient — trends graceful degradation testi."""
    app.dependency_overrides[get_db_client] = lambda: mock_db_client
    app.dependency_overrides[get_redis] = lambda: mock_redis_empty
    app.dependency_overrides[verify_internal_key] = lambda: None

    with TestClient(app, raise_server_exceptions=True) as client:
        yield client

    app.dependency_overrides.clear()
