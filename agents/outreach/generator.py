"""Outreach agent for drafting emails."""
from __future__ import annotations

import json
import re
from typing import Dict, List, Sequence, Tuple

from jinja2 import Template
from openai import OpenAI

from core.config import BASE_DIR, get_settings, require_openai_api_key
from core.db import get_session
from core.logger import log_action
from core.models import LEAD_STATUS_RANK

PROMPT_PATH = BASE_DIR / "prompts" / "outreach_email.txt"
TARGETABLE_STATUSES: Tuple[str, ...] = ("qualified", "reviewed", "interested", "audit_ready")


def _load_prompt() -> Template:
    text = PROMPT_PATH.read_text(encoding="utf-8")
    return Template(text)


def _valid_phone_digits(phone: str | None) -> int:
    return sum(ch.isdigit() for ch in (phone or ""))


def _build_insight(row: Dict[str, str | None]) -> str:
    hints: List[str] = []
    if not row.get("website"):
        hints.append("We couldn't find a website, which costs leads.")
    if not row.get("phone"):
        hints.append("Calls-to-action are missing or hidden.")
    if row.get("city"):
        hints.append(f"Homeowners in {row['city']} still search Google first.")
    return hints[0] if hints else "Most sites like this still leak high-intent leads."


def _personalization_quality(row: Dict[str, str | None]) -> str:
    signals = 0
    if row.get("website"):
        signals += 1
    if row.get("phone") and _valid_phone_digits(row["phone"]) >= 10:
        signals += 1
    if row.get("city"):
        signals += 1
    if row.get("category"):
        signals += 1
    return "high" if signals >= 3 else "low"


def _has_reliable_contact(row: Dict[str, str | None]) -> bool:
    if row.get("website"):
        return True
    return bool(row.get("phone") and _valid_phone_digits(row["phone"]) >= 10)


def _proof_hint(row: Dict[str, str | None]) -> str:
    if not row.get("website"):
        return "Couldn't find a quote form or owned site."
    if not row.get("phone") or _valid_phone_digits(row.get("phone")) < 10:
        return "Google listing shows no tap-to-call number."
    if row.get("notes"):
        return row["notes"]
    return "Public listing shows no recent reviews or trust badges."


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


def _call_openai(template: Template, context: Dict[str, object]) -> Dict[str, str]:
    settings = get_settings()
    client = OpenAI()
    prompt = template.render(**context)
    try:
        response = client.responses.create(
            model=settings.openai_model_email,
            input=prompt,
            temperature=0.5,
        )
    except Exception as exc:  # pragma: no cover - network dependency
        raise RuntimeError(f"OpenAI request failed: {exc}") from exc
    content = _extract_response_text(response).strip()
    # Strip markdown code fences if the model wrapped the JSON
    if content.startswith("```"):
        content = re.sub(r"^```[a-z]*\n?", "", content)
        content = re.sub(r"\n?```$", "", content).strip()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        data = {"subject": "Quick idea", "body": content}
    return data


def _mock_email(context: Dict[str, object]) -> Dict[str, str]:
    lead = context["lead"]
    lead_name = lead.get("name") or "there"
    city = lead.get("city") or context.get("desired_niche") or "your area"
    niche = lead.get("category") or context.get("desired_niche") or "business"
    insight = context.get("insight") or "There are likely missed inbound leads."
    personalization = context.get("personalization_quality") or "low"
    proof_hint = context.get("proof_hint") or "Quick public scan only."

    subject = f"{city} {niche} lead gap"
    if personalization == "low":
        body = (
            f"I did a quick public scan for {lead_name} in {city} and need one more detail before I’d send a real outbound note. "
            f"Right now the best signal is: {insight}\n\n"
            "Marking this for manual review so we can confirm the contact path before sending anything."
        )
    else:
        body = (
            f"{lead_name} looks like it could be losing local calls because {insight.lower()} "
            f"One thing I noticed: {proof_hint}\n\n"
            f"I help {city} {niche} businesses tighten the contact path so leads turn into booked calls faster. "
            "Worth a 10-minute look this week?"
        )
    return {"subject": subject[:60], "body": body}


def _normalize_status(status: str | None) -> str:
    return (status or "").lower()


def _allowed_statuses(requested: str) -> Sequence[str]:
    requested = _normalize_status(requested)
    if requested not in LEAD_STATUS_RANK:
        requested = "qualified"
    merged = list(dict.fromkeys([requested, *TARGETABLE_STATUSES]))
    return merged


def _should_promote(current: str | None, desired: str) -> bool:
    return LEAD_STATUS_RANK.get(desired, -1) > LEAD_STATUS_RANK.get(_normalize_status(current), -1)


def _classify_sendability(lead: Dict[str, object], personalization: str, has_contact: bool) -> str:
    if (lead.get("source") == "fallback_stub") or (_normalize_status(lead.get("status")) == "stub"):
        return "do_not_send"
    if not has_contact:
        return "do_not_send"
    score = lead.get("score") or 0
    if personalization == "high" and score >= 7:
        return "sendable"
    return "needs_edit"


def _append_lead_note(existing: str | None, note: str) -> str:
    if not existing:
        return note
    if note in existing:
        return existing
    return f"{existing} | {note}"


def generate_email_drafts(limit: int = 20, status: str = "qualified", mock: bool = False) -> int:
    if not mock:
        require_openai_api_key()
        template = _load_prompt()
    else:
        template = None
    created = 0
    failures = 0
    with get_session() as conn:
        allowed_statuses = _allowed_statuses(status)
        placeholders = ",".join(["?"] * len(allowed_statuses))
        query = f"""
            SELECT * FROM leads
            WHERE status IN ({placeholders})
              AND source != 'fallback_stub'
            ORDER BY score DESC
            LIMIT ?
        """
        rows = conn.execute(query, (*allowed_statuses, limit)).fetchall()
        for row in rows:
            lead_dict = dict(row)
            personalization = _personalization_quality(lead_dict)
            has_contact = _has_reliable_contact(lead_dict)
            proof_hint = _proof_hint(lead_dict)
            sendability = _classify_sendability(lead_dict, personalization, has_contact)
            note = ""
            if personalization == "low":
                log_action(
                    "outreach",
                    "low_personalization_warning",
                    {"lead_id": row["id"], "status": row["status"]},
                )
            if personalization == "low" and not has_contact:
                note = "Needs research: missing website/valid phone."
                subject = f"[Research needed] {lead_dict.get('city') or lead_dict.get('category') or 'Lead'}"
                body = "Insufficient public data to personalize. Add a working site or phone before outreach."
                conn.execute(
                    """
                    INSERT INTO emails(lead_id, subject, body, step, status, sendability, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (row["id"], subject, body, 1, "draft", "do_not_send", note),
                )
                lead_note = _append_lead_note(row["notes"], note)
                if _should_promote(row["status"], "reviewed"):
                    conn.execute(
                        "UPDATE leads SET status = ?, notes = ? WHERE id = ?",
                        ("reviewed", lead_note, row["id"]),
                    )
                log_action(
                    "outreach",
                    "deferred_lead",
                    {"lead_id": row["id"], "reason": note},
                )
                created += 1
                continue
            context = {
                "lead": lead_dict,
                "desired_niche": row["category"] or status,
                "insight": _build_insight(lead_dict),
                "personalization_quality": personalization,
                "score": row["score"],
                "current_status": row["status"],
                "proof_hint": proof_hint,
            }
            try:
                email = _mock_email(context) if mock else _call_openai(template, context)
            except RuntimeError as exc:
                failures += 1
                log_action(
                    "outreach",
                    "generate_email_error",
                    {"lead_id": row["id"], "error": str(exc)},
                )
                continue
            sendability = _classify_sendability(lead_dict, personalization, has_contact)
            if mock and sendability == "needs_edit":
                note = _append_lead_note(note or None, "Generated in mock mode for manual review.")
            elif mock:
                note = _append_lead_note(note or None, "Generated in mock mode.")
            conn.execute(
                """
                INSERT INTO emails(lead_id, subject, body, step, status, sendability, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (row["id"], email.get("subject"), email.get("body"), 1, "draft", sendability, note),
            )
            if sendability == "sendable" and _should_promote(row["status"], "emailed"):
                conn.execute("UPDATE leads SET status = ? WHERE id = ?", ("emailed", row["id"]))
            elif sendability == "needs_edit" and _should_promote(row["status"], "reviewed"):
                conn.execute("UPDATE leads SET status = ? WHERE id = ?", ("reviewed", row["id"]))
            created += 1
    if created:
        log_action("outreach", "generate_email", {"count": created, "status": status, "mode": "mock" if mock else "openai"})
    if failures and not created:
        raise RuntimeError("OpenAI failed for every lead. Check your API key, billing, or model limits.")
    return created
