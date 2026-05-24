"""Lead Hunter agent: scrape & score leads."""
from __future__ import annotations

import asyncio
import re
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Tuple

import httpx
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

from core.config import get_settings
from core.db import get_session, upsert_lead
from core.logger import log_action
from core.models import Lead

SOURCES = {
    "google_maps": "Google Maps",
}

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {
    "User-Agent": "revenue-os/1.0 (contact: noreply@revenue-os.local)",
    "Accept-Language": "en-US,en;q=0.8",
}
DISALLOWED_CLASSES = {"boundary", "landuse", "natural", "place", "railway", "highway"}
DISALLOWED_TYPES = {"neighbourhood", "residential", "suburb", "county", "postcode"}


@dataclass
class ScrapeResult:
    lead_ids: List[int]
    fallback_used: bool


def _valid_phone_digits(phone: str | None) -> int:
    return sum(ch.isdigit() for ch in (phone or ""))


def _has_reliable_contact(raw: Dict[str, str | None]) -> bool:
    if raw.get("website"):
        return True
    return bool(raw.get("phone") and _valid_phone_digits(raw["phone"]) >= 10)


def _derive_status(score: float, is_stub: bool) -> str:
    if is_stub:
        return "stub"
    if score >= 7.0:
        return "qualified"
    if score >= 5.0:
        return "reviewed"
    return "new"


_PHONE_RE = re.compile(r'[\(\d][\d\s\(\)\-\.]{7,}[\d]')


def _extract_phone_from_text(text: str) -> Optional[str]:
    match = _PHONE_RE.search(text)
    return match.group(0).strip() if match else None


async def _scrape_google_maps(city: str, niche: str, limit: int) -> List[Dict[str, str | None]]:
    query = f"{niche} in {city}"
    results: List[Dict[str, str | None]] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(f"https://www.google.com/maps/search/{query}", timeout=60000)
            await page.wait_for_timeout(4000)
            cards = await page.query_selector_all('div[role="article"]')
            for card in cards[:limit]:
                # Name lives in aria-label on the primary anchor
                a = await card.query_selector("a.hfpxzc")
                name = await a.get_attribute("aria-label") if a else None
                info = await card.inner_text()
                data = {
                    "name": name.strip() if name else None,
                    "phone": _extract_phone_from_text(info),
                    "website": None,
                    "city": city,
                    "category": niche,
                    "source": "google_maps",
                }
                if data["name"]:
                    results.append(data)
        finally:
            await browser.close()
    return results


def _nominatim_tokens(niche: str) -> List[str]:
    tokens = [tok for tok in re.split(r"\W+", niche.lower()) if len(tok) >= 4]
    if not tokens:
        tokens = [niche.lower()]
    return tokens


def _build_nominatim_entry(item: Dict[str, object], city: str, niche: str, tokens: List[str]) -> Tuple[Dict[str, str | None] | None, str | None]:
    extratags = item.get("extratags") or {}
    raw_name = item.get("name") or item.get("display_name") or ""
    name = raw_name.split(",")[0].strip()
    if not name:
        return None, "missing_name"
    place_class = (item.get("class") or "").lower()
    place_type = (item.get("type") or "").lower()
    if place_class in DISALLOWED_CLASSES:
        return None, f"class_block:{place_class}"
    if place_type in DISALLOWED_TYPES:
        return None, f"type_block:{place_type}"
    name_lower = name.lower()
    if tokens and not any(token in name_lower for token in tokens):
        return None, "niche_mismatch"
    phone = extratags.get("phone") or extratags.get("contact:phone")
    website = extratags.get("website") or extratags.get("contact:website")
    notes_bits = [f"class={place_class}", f"type={place_type}"]
    if not website:
        notes_bits.append("no_website")
    if not phone or _valid_phone_digits(phone) < 10:
        notes_bits.append("no_phone")
    entry = {
        "name": name,
        "website": website,
        "phone": phone,
        "city": city,
        "category": niche,
        "source": "nominatim",
        "notes": "nominatim:accepted:" + ",".join(notes_bits),
    }
    return entry, None


def _scrape_nominatim(city: str, niche: str, limit: int) -> Tuple[List[Dict[str, str | None]], List[str]]:
    params = {
        "q": f"{niche} in {city}",
        "format": "jsonv2",
        "limit": limit,
        "extratags": 1,
        "email": "noreply@revenue-os.local",
    }
    try:
        resp = httpx.get(NOMINATIM_URL, params=params, headers=NOMINATIM_HEADERS, timeout=15)
        resp.raise_for_status()
    except httpx.HTTPError:
        return [], []
    data = resp.json()
    results: List[Dict[str, str | None]] = []
    rejected: List[str] = []
    tokens = _nominatim_tokens(niche)
    for item in data[:limit * 2]:  # fetch extra in case many are rejected
        entry, reason = _build_nominatim_entry(item, city, niche, tokens)
        if entry:
            results.append(entry)
            if len(results) >= limit:
                break
        else:
            rejected.append(reason or "unknown")
    return results, rejected


def _fallback_stub(city: str, niche: str, limit: int) -> List[Dict[str, str | None]]:
    demo = []
    for idx in range(min(limit, 5)):
        demo.append(
            {
                "name": f"{city} {niche.title()} Co {idx+1}",
                "website": None,
                "phone": "555-0101",
                "city": city,
                "category": niche,
                "source": "fallback_stub",
                "notes": "fallback_stub",
            }
        )
    return demo


def _score_lead(raw: Dict[str, str | None], city: str, niche: str) -> float:
    settings = get_settings()
    w = settings.scoring_weights
    score = 0.0
    website = raw.get("website")
    phone = raw.get("phone")
    source = raw.get("source") or ""
    name = (raw.get("name") or "").lower()

    if website:
        score += w["has_website"]
    else:
        score += w["missing_website"]

    if phone:
        score += w["has_phone"]
        digits = _valid_phone_digits(phone)
        if digits >= 10:
            score += w["valid_phone_bonus"]
        else:
            score += w["short_phone_penalty"]
    else:
        score += w["low_contact_penalty"]

    category = raw.get("category") or ""
    if category and category.lower() == niche.lower():
        score += w["niche_match"]

    lead_city = (raw.get("city") or "").lower()
    if lead_city and lead_city == city.lower():
        score += w["city_match"]
    elif lead_city:
        score += w["city_mismatch_penalty"]

    if niche.lower() in name:
        score += w["keyword_match"]

    if source == "fallback_stub":
        score += w["stub_penalty"]
    elif source == "nominatim":
        score -= 1.0  # keep low-trust fallback from outranking richer leads

    return score


def scrape_and_store(city: str, niche: str, limit: int = 25) -> ScrapeResult:
    raw_results: List[Dict[str, str | None]] = []
    fallback_used = False
    fallback_source: str | None = None
    nominatim_rejected: List[str] = []
    try:
        raw_results = asyncio.run(_scrape_google_maps(city, niche, limit))
    except (PlaywrightTimeoutError, Exception):
        raw_results = []

    if not raw_results:
        nom_results, rejected = _scrape_nominatim(city, niche, limit)
        nominatim_rejected = rejected
        if nom_results:
            raw_results = nom_results
            fallback_used = True
            fallback_source = "nominatim"

    if not raw_results:
        raw_results = _fallback_stub(city, niche, limit)
        fallback_used = True
        fallback_source = "fallback_stub"

    stored_ids: List[int] = []
    with get_session() as conn:
        for raw in raw_results:
            score = _score_lead(raw, city, niche)
            is_stub = (raw.get("source") == "fallback_stub")
            status = _derive_status(score, is_stub)
            if raw.get("source") == "nominatim" and status == "qualified" and not _has_reliable_contact(raw):
                status = "reviewed"
                if raw.get("notes"):
                    raw["notes"] += ";thin_contact"
                else:
                    raw["notes"] = "nominatim:thin_contact"
            lead = Lead(
                id=None,
                name=raw.get("name") or "Unknown",
                website=raw.get("website"),
                phone=raw.get("phone"),
                email=None,
                city=raw.get("city") or city,
                category=raw.get("category") or niche,
                source=raw.get("source") or "google_maps",
                score=score,
                status=status,
                notes=raw.get("notes"),
            )
            lead_dict = asdict(lead)
            lead_dict.pop("id")
            lead_id = upsert_lead(
                conn,
                {
                    **lead_dict,
                    "status": lead.status,
                    "notes": lead.notes,
                },
            )
            stored_ids.append(lead_id)
    log_action(
        "lead_hunter",
        "scrape",
        {
            "city": city,
            "niche": niche,
            "count": len(stored_ids),
            "fallback_used": fallback_used,
            "fallback_source": fallback_source,
            "nominatim_rejected": len(nominatim_rejected),
        },
    )
    return ScrapeResult(lead_ids=stored_ids, fallback_used=fallback_used)
