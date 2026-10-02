"""Market-intelligence routes for the Digital Growth Engine bridge."""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from agents.market_intelligence.service import (
    ingest_evidence_batch,
    list_evidence,
    shortlist,
)
from agents.research.research_agent import ResearchAgent

router = APIRouter(prefix="/v1/market-intelligence", tags=["market-intelligence"])


def require_api_key(x_dge_api_key: str | None = Header(default=None)) -> None:
    expected = os.getenv("DGE_API_KEY")
    if expected and x_dge_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")


class MarketEvidenceItem(BaseModel):
    niche: str = Field(min_length=1, max_length=120)
    signal_type: str = Field(default="general", min_length=1, max_length=80)
    query: str = Field(min_length=3, max_length=500)
    summary: str = Field(default="", max_length=5000)
    results: list[dict[str, Any]] = Field(default_factory=list, max_length=25)
    success: bool = True


class MarketEvidenceBatch(BaseModel):
    items: list[MarketEvidenceItem] = Field(min_length=1, max_length=100)


class MarketScoutRequest(BaseModel):
    niches: list[str] = Field(default_factory=list, max_length=20)
    shortlist_limit: int = Field(default=5, ge=1, le=10)

    @field_validator("niches")
    @classmethod
    def validate_niches(cls, niches: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(n.strip() for n in niches))
        if any(not n or len(n) > 120 for n in cleaned):
            raise ValueError("Each niche must contain 1 to 120 characters")
        return cleaned


DEFAULT_NICHES = [
    "roofing",
    "HVAC",
    "plumbing",
    "med spa",
    "dentist",
    "personal injury law",
    "home remodeling",
    "auto repair",
    "property management",
    "commercial cleaning",
]

SCOUT_SIGNALS = {
    "demand_spend": "lead generation digital marketing advertising demand",
    "hiring": "marketing sales lead generation automation hiring jobs",
    "competition": "marketing agencies lead generation automation providers",
}


@router.post("/scout/queries", dependencies=[Depends(require_api_key)])
def market_scout_queries(payload: MarketScoutRequest) -> dict[str, Any]:
    return {
        "items": [
            {
                "query": f"{niche} {phrase} United States",
                "context": {"niche": niche, "signal_type": signal_type},
            }
            for niche in payload.niches or DEFAULT_NICHES
            for signal_type, phrase in SCOUT_SIGNALS.items()
        ]
    }


@router.post("/scout", dependencies=[Depends(require_api_key)])
def run_market_scout(payload: MarketScoutRequest) -> dict[str, Any]:
    niches = payload.niches or DEFAULT_NICHES
    research = ResearchAgent()
    evidence: list[dict[str, Any]] = []
    failures = 0

    for niche in niches:
        for signal_type, phrase in SCOUT_SIGNALS.items():
            query = f"{niche} {phrase} United States"
            result = research.execute(query=query)
            if not result.success:
                failures += 1
            evidence.append(
                {
                    "niche": niche,
                    "signal_type": signal_type,
                    "query": query,
                    "summary": result.output,
                    "results": result.data or [],
                    "success": result.success,
                }
            )

    saved = ingest_evidence_batch(evidence)
    markets = shortlist(limit=payload.shortlist_limit)
    return {
        **saved,
        "researched_queries": len(evidence),
        "failed_queries": failures,
        "shortlist": markets,
        "decision_status": "HUMAN_REVIEW",
    }


@router.post("/evidence/batch", dependencies=[Depends(require_api_key)])
def ingest_market_evidence(payload: MarketEvidenceBatch) -> dict[str, Any]:
    normalized = [item.model_dump() for item in payload.items]
    result = ingest_evidence_batch(normalized)
    return {
        **result,
        "shortlist": shortlist(limit=5),
        "decision_status": "HUMAN_REVIEW",
        "researched_queries": len(normalized),
        "failed_queries": sum(not item["success"] for item in normalized),
    }


@router.get("/shortlist", dependencies=[Depends(require_api_key)])
def get_market_shortlist(limit: int = Query(default=5, ge=1, le=25)) -> dict[str, Any]:
    markets = shortlist(limit=limit)
    return {
        "markets": markets,
        "count": len(markets),
        "decision_status": "HUMAN_REVIEW",
    }


@router.get("/evidence", dependencies=[Depends(require_api_key)])
def get_market_evidence(
    niche: str = Query(min_length=1, max_length=120),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    evidence = list_evidence(niche=niche, limit=limit)
    return {
        "niche": niche,
        "evidence": evidence,
        "count": len(evidence),
    }
