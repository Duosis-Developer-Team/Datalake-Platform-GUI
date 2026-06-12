import json
import re
from pathlib import Path

import pytest

from app.catalog import data_source_catalog, domain_catalog
from app.models.schemas import FrontendContext
from app.services import query_planner
from app.services.tool_registry import get_tool

_REPO = Path(__file__).resolve().parents[4]
_DOCS = _REPO / "docs" / "chatbot-knowledge"
_CATALOG_DIR = Path(__file__).resolve().parents[1] / "catalog"

# Acceptance case from the knowledge pack.
ACCEPT_Q = "DC13'te son 7 günde CPU allocated değişkenliği en yüksek 3 Klasik mimari host hangisi?"

_SECRET = re.compile(
    r"(BulutLakePas|sk-proj-[A-Za-z0-9]|DB_PASS=[A-Za-z0-9]|postgres(ql)?://[^\s]*:[^\s]*@|Bearer\s+[A-Za-z0-9_\-]{12})"
)
_KNOWLEDGE_FILES = [
    "00_overview.md", "01_webui_pages_and_context.md", "02_api_endpoint_catalog.md",
    "03_data_source_catalog.md", "04_metric_semantics.md", "05_architecture_mapping.md",
    "06_db_schema_notes.md", "07_query_planning_rules.md", "08_response_analysis_guidelines.md",
    "09_known_limitations.md", "10_examples.md",
]


def _tools(plan):
    return [t["tool"] for t in plan.initial_tools]


# --- knowledge files exist + secret-free --------------------------------- #


@pytest.mark.parametrize("name", _KNOWLEDGE_FILES)
def test_knowledge_file_exists(name):
    assert (_DOCS / name).is_file(), f"missing knowledge doc {name}"


def test_knowledge_and_catalog_have_no_secrets():
    targets = list(_DOCS.glob("*.md")) + list(_CATALOG_DIR.glob("*"))
    for p in targets:
        if p.is_file():
            assert not _SECRET.search(p.read_text(encoding="utf-8", errors="ignore")), f"secret in {p}"


def test_generated_catalog_loads_and_is_clean():
    data = json.loads((_CATALOG_DIR / "generated_catalog.json").read_text(encoding="utf-8"))
    assert data["version"] >= 2
    keys = {m["key"] for m in data["metrics"]}
    assert "classic_host_cpu_allocation_variability" in keys
    assert "dc_vm_cpu_top" in keys


# --- catalog content ------------------------------------------------------ #


def test_catalog_contains_required_metrics():
    assert domain_catalog.get("classic_host_cpu_allocation_variability") is not None
    assert domain_catalog.get("dc_vm_cpu_top") is not None


def test_added_tools_registered():
    for t in ("get_dc_classic_clusters", "get_dc_hyperconverged_clusters", "get_dc_zabbix_storage_trend"):
        assert get_tool(t) is not None


def test_every_catalog_tool_is_allowlisted():
    # Forbidden + primary/fallback tools must all exist in the registry.
    for m in domain_catalog.all_metric_definitions():
        for t in (*m.primary_tools, *m.fallback_tools, *m.forbidden_tools):
            assert get_tool(t) is not None, f"{m.key} references unknown tool {t}"


def test_data_source_catalog_tools_exist():
    for t in (*data_source_catalog.api_tool_keys(), *data_source_catalog.db_tool_keys()):
        assert get_tool(t) is not None, f"data_source_catalog references unknown tool {t}"


# --- acceptance case ------------------------------------------------------ #


def test_acceptance_classic_allocation_plan():
    p = query_planner.plan(ACCEPT_Q, None, None)
    assert p.entity_type == "host"
    assert p.architecture == "classic"
    assert p.metric == "cpu_allocated"
    assert p.calculation == "variability"
    assert p.dc_code == "DC13"
    assert p.days == 7 and p.limit == 3
    tools = _tools(p)
    assert "get_dc_classic_clusters" in tools
    assert "get_dc_classic_host_cpu_allocation_variability" in tools
    assert "get_customer_resources" not in tools


def test_stale_customer_context_not_selected_for_dc_host_metric():
    ctx = FrontendContext(selected_customer="Boyner", pathname="/customer/Boyner")
    p = query_planner.plan(ACCEPT_Q, ctx, None)
    assert not any("customer" in t for t in _tools(p))
    assert p.customer_name is None


def test_forbidden_tools_excluded_from_plan():
    p = query_planner.plan("DC13 VM seviyesinde en çok cpu kullanan 10 makine", None, None)
    assert "get_customer_resources" not in _tools(p)


def test_catalog_guidance_is_narrative_first():
    for m in domain_catalog.all_metric_definitions():
        for g in m.answer_guidance:
            assert "tablo halinde listele" not in g.lower()
