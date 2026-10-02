import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api import app


def test_bridge_exposes_safe_v1_surface():
    paths = {route.path for route in app.routes if getattr(route, "path", None)}
    expected = {
        "/health",
        "/v1/summary",
        "/v1/missions",
        "/v1/missions/{mission_id}",
        "/v1/research",
        "/v1/market-intelligence/scout",
        "/v1/market-intelligence/scout/queries",
        "/v1/market-intelligence/evidence/batch",
        "/v1/market-intelligence/shortlist",
        "/v1/market-intelligence/evidence",
        "/v1/leads",
        "/v1/leads/hunt",
        "/v1/outreach/drafts",
        "/v1/audits",
        "/v1/approvals",
        "/v1/approvals/{approval_id}/decision",
    }
    assert expected.issubset(paths)
    assert not any("send" in path.lower() for path in paths)


def test_dge01_workflow_is_importable_json_and_draft_only():
    path = Path("n8n/workflows/dge-01-lead-research-to-drafts.json")
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["name"] == "DGE-01 Lead Research to Draft Queue"
    node_names = {node["name"] for node in data["nodes"]}
    assert "Hunt Leads" in node_names
    assert "Create Safe Drafts" in node_names
    assert "Read Approval Queue" in node_names

    draft_node = next(node for node in data["nodes"] if node["name"] == "Create Safe Drafts")
    assert "mock:true" in draft_node["parameters"]["body"].replace(" ", "")
    assert all("/send" not in str(node.get("parameters", {})).lower() for node in data["nodes"])
    assert not any(node["type"] == "n8n-nodes-base.code" for node in data["nodes"])
    result_node = next(node for node in data["nodes"] if node["name"] == "Result")
    assert result_node["parameters"]["keepOnlySet"] is True


def test_all_dge_workflows_are_valid_json():
    workflow_dir = Path("n8n/workflows")
    files = sorted(workflow_dir.glob("dge-*.json"))
    assert len(files) >= 3

    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["name"].startswith("DGE-")
        assert data["active"] is False
        assert data["nodes"]
        assert data["connections"]



def test_dge03_persists_and_scores_market_evidence():
    path = Path("n8n/workflows/dge-03-demand-scout-v0.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    node_names = {node["name"] for node in data["nodes"]}

    assert data["name"] == "DGE-03 Demand Scout V1"
    assert "Webhook Intake" in node_names
    assert "Collect Evidence" in node_names
    assert "Persist and Score Markets" in node_names
    assert "Respond" in node_names
    assert not any(node["type"] == "n8n-nodes-base.code" for node in data["nodes"])

    scout = next(node for node in data["nodes"] if node["name"] == "Collect Evidence")
    assert "/v1/research" in scout["parameters"]["url"]
    assert "context: $json.context" in scout["parameters"]["body"]


def test_gmail_handoff_is_explicit_draft_create_only():
    data = json.loads(Path("n8n/workflows/dge-02-safe-gmail-draft-handoff.json").read_text())
    gmail = [node for node in data["nodes"] if node["type"] == "n8n-nodes-base.gmail"]
    operations = {node["parameters"]["operation"] for node in gmail}
    assert operations == {"create", "get"}
    assert all(node["parameters"]["resource"] == "draft" for node in gmail)
    assert all(node["credentials"]["gmailOAuth2"] == {
        "id": "P7st5BStiXMH12dv", "name": "Gmail account",
    } for node in gmail)
    config = next(node for node in data["nodes"] if node["name"] == "DGE Config")
    limit = next(value for value in config["parameters"]["values"]["number"] if value["name"] == "limit")
    assert limit["value"] == 1
    review = next(node for node in data["nodes"] if node["name"] == "Human Review Required")
    assert review["parameters"]["keepOnlySet"] is True
    assert all("send" not in node["parameters"].get("operation", "").lower() for node in gmail)
    assert data["active"] is False


def test_research_api_preserves_context_and_failure_flag(monkeypatch):
    from fastapi.testclient import TestClient

    import api
    from agents.base_agent import AgentResult

    monkeypatch.setenv("DGE_API_KEY", "unit-test-only")
    monkeypatch.setattr(api.research, "execute", lambda **_: AgentResult(
        success=False, output="Search unavailable", data=[],
    ))
    client = TestClient(api.app)
    payload = {"query": "roofing hiring", "context": {"niche": "roofing", "signal_type": "hiring"}}
    assert client.post("/v1/research", json=payload).status_code == 401
    response = client.post("/v1/research", json=payload, headers={"X-DGE-API-Key": "unit-test-only"})
    assert response.status_code == 200
    assert response.json()["context"] == payload["context"]
    assert response.json()["success"] is False
    assert response.json()["results"] == []


def test_scout_query_input_is_bounded_and_defaults_are_contextual():
    import pytest
    from pydantic import ValidationError

    from market_api import MarketScoutRequest, market_scout_queries

    items = market_scout_queries(MarketScoutRequest(niches=[" roofing ", "roofing"]))["items"]
    assert len(items) == 3
    assert {item["context"]["signal_type"] for item in items} == {"demand_spend", "hiring", "competition"}
    assert all(item["context"]["niche"] == "roofing" for item in items)
    assert len(market_scout_queries(MarketScoutRequest())["items"]) == 30
    for niches in ([" "], ["a" * 121], ["roofing"] * 21):
        with pytest.raises(ValidationError):
            MarketScoutRequest(niches=niches)


def test_dge_workflows_have_stable_ids_and_live_webhook_entrypoints():
    specs = {
        "dge-01-lead-research-to-drafts.json": (
            "dgeLeadResearchToDrafts01",
            "dge/lead-research",
        ),
        "dge-03-demand-scout-v0.json": (
            "dgeDemandScout03",
            "dge/demand-scout",
        ),
    }

    for filename, (workflow_id, webhook_path) in specs.items():
        data = json.loads(Path("n8n/workflows", filename).read_text(encoding="utf-8"))
        assert data["id"] == workflow_id
        webhook = next(node for node in data["nodes"] if node["type"] == "n8n-nodes-base.webhook")
        assert webhook["parameters"]["path"] == webhook_path
