"""Audit / offer agent."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List

import httpx
from bs4 import BeautifulSoup
from jinja2 import Template
from openai import OpenAI

from core.config import BASE_DIR, get_settings, require_openai_api_key
from core.db import get_session
from core.logger import log_action
from core.models import LEAD_STATUS_RANK

PROMPT_PATH = BASE_DIR / "prompts" / "audit.txt"

CTA_KEYWORDS = ["call", "book", "estimate", "quote", "schedule"]


def _recommended_move(findings: Dict[str, bool]) -> str:
    if not findings.get("cta"):
        return "Add a sticky click-to-call or quote button on every page."
    if not findings.get("page_loaded"):
        return "Launch a simple landing page with a working contact form."
    if not findings.get("https"):
        return "Fix the SSL/mixed-content issues so browsers stop warning visitors."
    if not findings.get("page_title") or not findings.get("meta_description"):
        return "Refresh the title + meta copy to match local service keywords."
    return "Drop a proof block near the hero so homeowners see reviews immediately."


def _load_template() -> Template:
    return Template(PROMPT_PATH.read_text(encoding="utf-8"))


def _fetch_page(url: str) -> str:
    try:
        response = httpx.get(url, timeout=15)
        response.raise_for_status()
        return response.text
    except Exception:
        return ""


def _run_checks(html: str, url: str) -> Dict[str, bool]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    meta_desc = ""
    desc_tag = soup.find("meta", attrs={"name": "description"})
    if desc_tag and desc_tag.get("content"):
        meta_desc = desc_tag["content"].strip()
    body_text = soup.get_text(" ") if soup else ""
    has_cta = any(keyword in body_text.lower() for keyword in CTA_KEYWORDS)
    https = url.startswith("https://")
    findings = {
        "page_title": bool(title),
        "meta_description": bool(meta_desc),
        "https": https,
        "cta": has_cta,
        "page_loaded": bool(html),
    }
    return findings


def _format_findings(findings: Dict[str, bool]) -> str:
    lines = []
    for key, value in findings.items():
        state = "PASS" if value else "MISSING"
        lines.append(f"{key}: {state}")
    return "\n".join(lines)


def _extract_response_text(response) -> str:
    if hasattr(response, "output_text") and response.output_text:
        if isinstance(response.output_text, str):
            return response.output_text
        if isinstance(response.output_text, list):
            return "\n".join(str(chunk) for chunk in response.output_text if chunk)
    if getattr(response, "output", None):
        chunks: List[str] = []
        for item in response.output:
            for content in getattr(item, "content", []) or []:
                text = getattr(content, "text", None)
                if text:
                    chunks.append(text)
        if chunks:
            return "\n".join(chunks)
    return "{}"


def _call_openai(template: Template, context: Dict[str, object]) -> Dict[str, object]:
    settings = get_settings()
    client = OpenAI()
    prompt = template.render(**context)
    try:
        response = client.responses.create(
            model=settings.openai_model_audit,
            input=prompt,
            temperature=0.4,
        )
    except Exception as exc:  # pragma: no cover - network dependency
        raise RuntimeError(f"OpenAI request failed: {exc}") from exc
    content = _extract_response_text(response).strip()
    # Strip markdown code fences if the model wrapped the JSON
    if content.startswith("```"):
        content = re.sub(r"^```[a-z]*\n?", "", content)
        content = re.sub(r"\n?```$", "", content).strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {
            "summary": content,
            "broken": [],
            "impact": [],
            "angle": "",
        }


def _mock_audit_payload(lead: Dict[str, object], findings: Dict[str, bool]) -> Dict[str, object]:
    name = lead.get("name") or "This business"
    city = lead.get("city") or "the local market"
    niche = lead.get("category") or "service business"
    broken: List[str] = []
    impact: List[str] = []

    if not findings.get("page_loaded"):
        broken.append("No reliable live website or landing page is available.")
        impact.append("Search traffic has nowhere to convert, so prospects default to competitors.")
    if not findings.get("cta"):
        broken.append("The page lacks a clear quote or call action near the top.")
        impact.append("Homeowners have to guess the next step, which drops call volume.")
    if not findings.get("page_title"):
        broken.append("The page title is missing or too weak to signal local relevance.")
        impact.append("Searchers get less confidence that the business serves their area.")
    if not findings.get("meta_description"):
        broken.append("Meta description copy is missing, so listings look unfinished.")
        impact.append("Low-trust listings lose clicks before visitors even reach the site.")
    if not findings.get("https"):
        broken.append("The site is not fully secure.")
        impact.append("Security warnings make prospects hesitate before submitting a form.")

    if not broken:
        broken.append("The site is live but still hides the main contact path.")
        impact.append("Visitors can land on the site and still leave without calling.")

    summary = (
        f"{name} has a usable web presence, but the current {city} {niche} flow still leaves easy leads on the table."
        if findings.get("page_loaded")
        else f"{name} has little to no dependable web presence, which makes it hard for {city} prospects to trust and contact the business."
    )
    angle = (
        "The fastest win is a lightweight lead-capture page with a visible CTA, live routing, and basic proof so every visit has a clear next step. "
        "That gives you something concrete to pitch without overbuilding."
    )
    return {
        "summary": summary,
        "broken": broken[:4],
        "impact": impact[:4],
        "angle": angle,
    }


def _should_promote(current: str | None, desired: str) -> bool:
    return LEAD_STATUS_RANK.get(desired, -1) > LEAD_STATUS_RANK.get((current or "").lower(), -1)


def generate_audit(lead_id: int, mock: bool = False) -> Path:
    if not mock:
        require_openai_api_key()
        template = _load_template()
    else:
        template = None
    with get_session() as conn:
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        if not row:
            raise ValueError(f"Lead {lead_id} not found")
        website = row["website"]
        html = _fetch_page(website) if website else ""
        findings = _run_checks(html, website or "")
        findings_text = _format_findings(findings)
        context = {
            "lead": dict(row),
            "desired_niche": row["category"],
            "findings_text": findings_text,
        }
        data = _mock_audit_payload(dict(row), findings) if mock else _call_openai(template, context)
        audits_dir = get_settings().export_dir / "audits"
        audits_dir.mkdir(parents=True, exist_ok=True)
        file_path = audits_dir / f"lead-{lead_id}.md"
        summary = data.get("summary", "")
        broken_items = data.get("broken") or data.get("issues") or []
        impact_items = data.get("impact") or []
        angle = data.get("angle") or data.get("offer_angle") or ""
        recommended_move = _recommended_move(findings)
        body = [
            f"# Opportunity Memo for {row['name']}",
            "",
            "## Snapshot",
            summary,
            "",
            "## What's Broken",
        ]
        if broken_items:
            body.extend(f"- {item}" for item in broken_items)
        else:
            body.append("- Not enough public data to confirm issues yet.")
        body.extend(
            [
                "",
                "## Why It Costs Leads",
            ]
        )
        if impact_items:
            body.extend(f"- {item}" for item in impact_items)
        else:
            body.append("- Missing basics likely pushes homeowners to competitors.")
        body.extend(
            [
                "",
                "## Improvement Angle",
                angle,
                "",
                "**Recommended Next Move:** " + recommended_move,
                "",
                "## Quick Findings",
                findings_text,
            ]
        )
        file_path.write_text("\n".join(body), encoding="utf-8")
        conn.execute(
            """
            INSERT INTO audits(lead_id, summary, offer_angle, file_path)
            VALUES (?, ?, ?, ?)
            """,
            (lead_id, summary, angle, str(file_path)),
        )
        if _should_promote(row["status"], "audit_ready"):
            conn.execute("UPDATE leads SET status = ? WHERE id = ?", ("audit_ready", lead_id))
    log_action("audit_offer", "generate_audit", {"lead_id": lead_id, "mode": "mock" if mock else "openai"})
    return file_path
