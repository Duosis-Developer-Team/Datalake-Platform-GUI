"""
query-service/tests/test_endpoints.py — API endpoint birim testleri

Test kapsamı:
  [1] GET /health → 200 OK, service=query-service
  [2] GET /overview/trends → boş Redis → boş labels/values
  [3] GET /overview/trends → dolu Redis → doğru değerler
  [4] GET /datacenters/summary → 200 OK, liste dönüyor

Mimari notlar:
  - TestClient doğrudan FastAPI app'e istek atar (gerçek HTTP yok).
  - dependency_overrides (conftest.py'de) tüm dış bağımlılıkları mock'lar.
  - Sampler background task'ı testi etkilememesi için suppress edilir;
    lifespan etkisi TestClient raise_server_exceptions ile kontrol altında.
"""

import pytest


# ── Sağlık Kontrolü ──────────────────────────────────────────────────────────

class TestHealth:
    def test_health_returns_200(self, api_client):
        """GET /health → 200 OK."""
        resp = api_client.get("/health")
        assert resp.status_code == 200

    def test_health_body_has_status_ok(self, api_client):
        """Yanıt JSON: status == 'ok'."""
        resp = api_client.get("/health")
        body = resp.json()
        assert body.get("status") == "ok"

    def test_health_body_has_service_name(self, api_client):
        """Yanıt JSON: service alanı mevcut."""
        resp = api_client.get("/health")
        body = resp.json()
        assert "service" in body


# ── GET /overview/trends ─────────────────────────────────────────────────────

class TestOverviewTrends:
    def test_trends_returns_200(self, api_client):
        """GET /overview/trends → 200 OK."""
        resp = api_client.get("/overview/trends")
        assert resp.status_code == 200

    def test_trends_response_has_all_keys(self, api_client):
        """Yanıt JSON: cpu_pct, ram_pct, energy_kw anahtarları var."""
        resp = api_client.get("/overview/trends")
        body = resp.json()
        assert "cpu_pct" in body
        assert "ram_pct" in body
        assert "energy_kw" in body

    def test_trends_series_has_labels_and_values(self, api_client):
        """Her trend serisi labels + values listesi içermeli."""
        resp = api_client.get("/overview/trends")
        body = resp.json()
        for key in ("cpu_pct", "ram_pct", "energy_kw"):
            assert "labels" in body[key], f"{key}.labels eksik"
            assert "values" in body[key], f"{key}.values eksik"

    def test_trends_with_data_returns_correct_value(self, api_client):
        """
        mock_redis: lrange → [{"ts":..., "v": 42.5}]
        Tüm 3 trend anahtarı için values[0] == 42.5 beklenir.
        """
        resp = api_client.get("/overview/trends")
        body = resp.json()
        for key in ("cpu_pct", "ram_pct", "energy_kw"):
            values = body[key]["values"]
            assert len(values) == 1, f"{key}: 1 nokta beklendi, {len(values)} geldi"
            assert values[0] == pytest.approx(42.5), \
                f"{key}: 42.5 beklendi, {values[0]} geldi"

    def test_trends_with_data_returns_label(self, api_client):
        """Timestamp label ISO format olarak dönmeli."""
        resp = api_client.get("/overview/trends")
        body = resp.json()
        label = body["cpu_pct"]["labels"][0]
        assert "2026-02-25" in label

    def test_trends_empty_redis_returns_empty_lists(self, api_client_empty_redis):
        """
        Boş Redis (lrange → []) → graceful degradation:
        Tüm trend serileri boş liste döndürmeli, 503/500 atmamalı.
        """
        resp = api_client_empty_redis.get("/overview/trends")
        assert resp.status_code == 200
        body = resp.json()
        for key in ("cpu_pct", "ram_pct", "energy_kw"):
            assert body[key]["values"] == [], \
                f"Boş Redis'te {key}.values boş olmalı"
            assert body[key]["labels"] == [], \
                f"Boş Redis'te {key}.labels boş olmalı"


# ── GET /datacenters/summary ─────────────────────────────────────────────────

class TestDatacentersSummary:
    def test_summary_returns_200(self, api_client):
        """GET /datacenters/summary → 200 OK."""
        resp = api_client.get("/datacenters/summary")
        assert resp.status_code == 200

    def test_summary_returns_list(self, api_client):
        """Yanıt JSON: liste tipinde olmalı."""
        resp = api_client.get("/datacenters/summary")
        body = resp.json()
        assert isinstance(body, list)

    def test_summary_list_not_empty(self, api_client):
        """Mock veriyle en az 1 DC dönmeli."""
        resp = api_client.get("/datacenters/summary")
        body = resp.json()
        assert len(body) >= 1

    def test_summary_item_has_id(self, api_client):
        """Her DC özeti 'id' alanı içermeli (DCSummary.id)."""
        resp = api_client.get("/datacenters/summary")
        body = resp.json()
        first = body[0]
        assert "id" in first, f"'id' alanı bulunamadı: {list(first.keys())}"

    def test_summary_item_has_stats(self, api_client):
        """Her DC özeti stats alt objesi içermeli."""
        resp = api_client.get("/datacenters/summary")
        body = resp.json()
        first = body[0]
        assert "stats" in first
        assert "used_cpu_pct" in first["stats"]
