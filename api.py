"""Local HTTP bridge between n8n and Revenue OS.

The bridge deliberately exposes only bounded, review-friendly operations.
It never sends outreach, edits websites, or bypasses the existing approval
controls.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from agents.audit_offer.audit import generate_audit
from agents.lead_hunter.lead_hunter import scrape_and_store
from agents.outreach.generator import generate_email_drafts
from agents.research.research_agent import ResearchAgent
from core.config import get_settings
from core.db import ensure_db_ready, get_session
from orchestrator.approval_manager import ApprovalManager
from orchestrator.mission_manager import MissionManager
from orchestrator.supreme_orchestrator import SupremeOrchestrator


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_db_ready()
    yield


app = FastAPI(
    title="Revenue OS / Digital Growth Engine Bridge",
    version="0.1.0",
    description="Stable local API boundary for n8n and Project 5 orchestration.",
    lifespan=lifespan,
)

orchestrator = SupremeOrchestrator()
missions = MissionManager()
approvals = ApprovalManager()
research = ResearchAgent()


def require_api_key(x_dge_api_key: Optional[str] = Header(default=None)) -> None:
    """Validate the shared bridge key when one is configured."""
    expected = os.getenv("DGE_API_KEY")
    if expected and x_dge_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")


class MissionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    department: Optional[str] = None
    input_data: Optional[dict[str, Any]] = None
    priority: int = Field(default=5, ge=1, le=10)
    approval_required: Optional[bool] = None


class LeadHuntRequest(BaseModel):
    city: str = Field(min_length=1, max_length=120)
    niche: str = Field(min_length=1, max_length=120)
    limit: int = Field(default=25, ge=1, le=50)


class DraftRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=50)
    status: str = Field(default="qualified", min_length=1, max_length=40)
    mock: bool = False


class AuditRequest(BaseModel):
    lead_id: int = Field(gt=0)
    mock: bool = False


class ResearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=500)


class ApprovalDecision(BaseModel):
    approved: bool
    reason: Optional[str] = Field(default=None, max_length=1000)


@app.get("/health", dependencies=[Depends(require_api_key)])
def health() -> dict[str, Any]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": "revenue_os",
        "api_version": "0.1.0",
        "dry_run": settings.dry_run,
        "approval_mode": settings.approval_mode,
        "allow_external_send": settings.allow_external_send,
    }


@app.get("/v1/summary", dependencies=[Depends(require_api_key)])
def summary() -> dict[str, str]:
    return {"summary": orchestrator.daily_summary()}


@app.post("/v1/missions", dependencies=[Depends(require_api_key)])
def create_mission(payload: MissionCreate) -> dict[str, Any]:
    mission_id = orchestrator.dispatch(
        title=payload.title,
        department=payload.department,
        input_data=payload.input_data,
        priority=payload.priority,
        approval_required=payload.approval_required,
    )
    row = missions.get(mission_id)
    return {"mission_id": mission_id, "status": row["status"] if row else "pending"}


@app.get("/v1/missions/{mission_id}", dependencies=[Depends(require_api_key)])
def get_mission(mission_id: int) -> dict[str, Any]:
    row = missions.get(mission_id)
    if not row:
        raise HTTPException(status_code=404, detail="Mission not found")
    return dict(row)


@app.post("/v1/research", dependencies=[Depends(require_api_key)])
def run_research(payload: ResearchRequest) -> dict[str, Any]:
    result = research.execute(query=payload.query)
    if not result.success:
        raise HTTPException(status_code=502, detail=result.output)
    return {
        "query": payload.query,
        "summary": result.output,
        "results": result.data or [],
        "next_action": result.next_action,
    }


@app.get("/v1/leads", dependencies=[Depends(require_api_key)])
def list_leads(
    status: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    query = "SELECT * FROM leads"
    params: list[Any] = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY score DESC, updated_at DESC LIMIT ?"
    params.append(limit)
    with get_session() as conn:
        rows = conn.execute(query, params).fetchall()
    return {"leads": [dict(row) for row in rows], "count": len(rows)}


@app.post("/v1/leads/hunt", dependencies=[Depends(require_api_key)])
def hunt_leads(payload: LeadHuntRequest) -> dict[str, Any]:
    settings = get_settings()
    limit = min(payload.limit, settings.max_leads_per_run)
    result = scrape_and_store(payload.city, payload.niche, limit=limit)
    return {
        "lead_ids": result.lead_ids,
        "count": len(result.lead_ids),
        "fallback_used": result.fallback_used,
        "city": payload.city,
        "niche": payload.niche,
    }


@app.get("/v1/outreach/drafts", dependencies=[Depends(require_api_key)])
def list_drafts(
    sendability: Optional[str] = None,
    require_email: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    query = """
        SELECT
            emails.id,
            emails.lead_id,
            emails.subject,
            emails.body,
            emails.status,
            emails.sendability,
            emails.notes,
            emails.created_at,
            leads.name AS lead_name,
            leads.email AS lead_email,
            leads.website AS lead_website,
            leads.city AS lead_city,
            leads.category AS lead_category
        FROM emails
        JOIN leads ON leads.id = emails.lead_id
        WHERE emails.status = 'draft'
    """
    params: list[Any] = []
    if sendability:
        query += " AND emails.sendability = ?"
        params.append(sendability)
    if require_email:
        query += " AND leads.email IS NOT NULL AND TRIM(leads.email) != ''"
    query += " ORDER BY emails.created_at DESC LIMIT ?"
    params.append(limit)
    with get_session() as conn:
        rows = conn.execute(query, params).fetchall()
    return {"drafts": [dict(row) for row in rows], "count": len(rows)}


@app.post("/v1/outreach/drafts", dependencies=[Depends(require_api_key)])
def create_drafts(payload: DraftRequest) -> dict[str, Any]:
    settings = get_settings()
    limit = min(payload.limit, settings.max_emails_per_day)
    try:
        created = generate_email_drafts(
            limit=limit,
            status=payload.status,
            mock=payload.mock,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "created": created,
        "status_filter": payload.status,
        "mock": payload.mock,
        "external_send_performed": False,
    }


@app.post("/v1/audits", dependencies=[Depends(require_api_key)])
def create_audit(payload: AuditRequest) -> dict[str, Any]:
    try:
        path = generate_audit(payload.lead_id, mock=payload.mock)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"lead_id": payload.lead_id, "file_path": str(path), "mock": payload.mock}


@app.get("/v1/approvals", dependencies=[Depends(require_api_key)])
def list_pending_approvals() -> dict[str, Any]:
    rows = approvals.list_pending()
    return {"approvals": [dict(row) for row in rows], "count": len(rows)}


@app.post("/v1/approvals/{approval_id}/decision", dependencies=[Depends(require_api_key)])
def decide_approval(approval_id: int, payload: ApprovalDecision) -> dict[str, Any]:
    if payload.approved:
        approvals.approve(approval_id, reason=payload.reason)
        status = "approved"
    else:
        approvals.reject(approval_id, reason=payload.reason)
        status = "rejected"
    return {"approval_id": approval_id, "status": status}
