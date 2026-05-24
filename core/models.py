"""Shared data models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Lead:
    id: Optional[int]
    name: str
    website: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    city: Optional[str]
    category: Optional[str]
    source: str
    score: float
    status: str = "new"
    notes: Optional[str] = None


@dataclass
class EmailDraft:
    id: Optional[int]
    lead_id: int
    subject: str
    body: str
    step: int = 1
    status: str = "draft"


@dataclass
class Audit:
    id: Optional[int]
    lead_id: int
    summary: str
    offer_angle: str
    file_path: str


LEAD_STATUSES = [
    "new",
    "qualified",
    "reviewed",
    "emailed",
    "replied",
    "interested",
    "audit_ready",
    "closed_lost",
    "closed_won",
    "stub",
]

LEAD_STATUS_RANK = {status: index for index, status in enumerate(LEAD_STATUSES)}

MISSION_STATUSES = [
    "pending",
    "running",
    "waiting_for_approval",
    "completed",
    "failed",
    "paused",
]

DEPARTMENTS = [
    "revenue",
    "it_ops",
    "seo_marketing",
    "job_acquisition",
    "productivity",
    "finance",
    "fitness",
    "research",
]


@dataclass
class Mission:
    id: Optional[int]
    title: str
    department: str
    agent: Optional[str] = None
    status: str = "pending"
    priority: int = 5
    input: Optional[str] = None
    output: Optional[str] = None
    next_action: Optional[str] = None
    approval_required: bool = False
    approved: bool = False
    error: Optional[str] = None


@dataclass
class Approval:
    id: Optional[int]
    mission_id: Optional[int]
    action: str
    payload: Optional[str] = None
    status: str = "pending"
    reason: Optional[str] = None


@dataclass
class Memory:
    id: Optional[int]
    namespace: str
    key: str
    value: Optional[str] = None
