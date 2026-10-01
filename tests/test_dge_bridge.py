import json
from pathlib import Path

from api import app


def test_bridge_exposes_safe_v1_surface():
    paths = {route.path for route in app.routes}
    expected = {
        "/health",
        "/v1/summary",
        "/v1/missions",
        "/v1/missions/{mission_id}",
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
    assert '"mock":true' in draft_node["parameters"]["body"].replace(" ", "")
    assert all("/send" not in str(node.get("parameters", {})).lower() for node in data["nodes"])
