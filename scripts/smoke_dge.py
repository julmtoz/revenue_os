"""Run bounded local DGE smoke checks; never execute the Gmail workflow."""
from __future__ import annotations

import argparse
import json
import os
from urllib.request import Request, urlopen


def request(base: str, path: str, payload: dict | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if base.endswith(":8787") and os.getenv("DGE_API_KEY"):
        headers["X-DGE-API-Key"] = os.environ["DGE_API_KEY"]
    data = json.dumps(payload).encode() if payload is not None else None
    with urlopen(Request(base + path, data=data, headers=headers), timeout=240) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat-scout", action="store_true", help="Repeat the same roofing scout to verify deduplication")
    args = parser.parse_args()
    api = "http://localhost:8787"
    bus = "http://localhost:5678"
    health = request(api, "/health")
    assert health["status"] == "ok"
    assert health["dry_run"] and health["approval_mode"]
    assert not health["allow_external_send"] and not health["allow_website_edit"]
    assert request(bus, "/healthz")["status"] == "ok"
    lead = request(bus, "/webhook/dge/lead-research", {
        "city": "Newark", "niche": "roofing", "limit": 1, "mock": True,
    })
    assert lead["status"] == "DGE-01 completed", lead
    assert lead["leads_found"] == 1, lead
    assert lead["decision_status"] == "HUMAN_REVIEW", lead
    assert lead["external_send_performed"] is False, lead
    print("DGE-01", json.dumps({key: lead[key] for key in (
        "status", "leads_found", "drafts_created", "approvals_waiting",
        "decision_status", "external_send_performed",
    )}))
    before = request(api, "/v1/market-intelligence/evidence?niche=roofing&limit=500")
    scout = request(bus, "/webhook/dge/demand-scout", {"niches": ["roofing"]})
    assert scout["researched_queries"] == 3, scout
    assert scout["failed_queries"] == 0, scout
    assert scout["decision_status"] == "HUMAN_REVIEW", scout
    assert 0 < len(scout["shortlist"]) <= 5, scout
    after = request(api, "/v1/market-intelligence/evidence?niche=roofing&limit=500")
    signals = {row["signal_type"] for row in after["evidence"] if row["source_url"]}
    assert {"demand_spend", "hiring", "competition"} <= signals, signals
    assert after["count"] >= before["count"]
    print("DGE-03", json.dumps({
        "inserted": scout["inserted"], "evidence_before": before["count"],
        "evidence_after": after["count"], "signals": sorted(signals),
        "shortlist_count": len(scout["shortlist"]), "decision_status": scout["decision_status"],
    }))
    if args.repeat_scout:
        repeated = request(bus, "/webhook/dge/demand-scout", {"niches": ["roofing"]})
        assert repeated["failed_queries"] == 0
        assert repeated["inserted"] == 0, repeated
        assert repeated["shortlist"] == scout["shortlist"]
        print("DGE-03 repeat: inserted=0; shortlist unchanged")
    assert request(api, "/health") == health
    print("Safety defaults unchanged; Gmail workflow was not executed.")


if __name__ == "__main__":
    main()
