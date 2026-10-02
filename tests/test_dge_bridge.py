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

    assert "Build Evidence Batch" in node_names
    assert "Persist and Score Markets" in node_names
    assert "Expand Top 5" in node_names

    persist = next(node for node in data["nodes"] if node["name"] == "Persist and Score Markets")
    assert "/v1/market-intelligence/evidence/batch" in persist["parameters"]["url"]

    generator = next(node for node in data["nodes"] if node["name"] == "Generate Demand Queries")
    code = generator["parameters"]["jsCode"]
    assert "DGE_SIGNAL=" in code
    assert "demand_spend" in code
    assert "hiring" in code
    assert "competition" in code
