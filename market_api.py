"""Market-intelligence routes for the Digital Growth Engine bridge."""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from agents.market_intelligence.service import (
    ingest_evidence_batch,
    list_evidence,
    shortlist,
)

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
class MarketEvidenceBatch(BaseModel):
    items: list[MarketEvidenceItem] = Field(min_length=1, max_length=100)


@router.post("/evidence/batch", dependencies=[Depends(require_api_key)])
def ingest_market_evidence(payload: MarketEvidenceBatch) -> dict[str, Any]:
    normalized = [item.model_dump() for item in payload.items]
    result = ingest_evidence_batch(normalized)
    return {
        **result,
        "shortlist": shortlist(limit=5),
        "decision_status": "HUMAN_REVIEW",
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
