"""Job Scout Agent — find and score IT/sysadmin job opportunities."""
from __future__ import annotations

import json
import re
from typing import Any, Optional

import httpx

from agents.base_agent import BaseAgent, AgentResult
from core.db import get_session, memory_set
from core.logger import log_action


PRIORITY_ROLES = [
    "system administrator",
    "sysadmin",
    "it administrator",
    "it manager",
    "cloud engineer",
    "network administrator",
    "it support",
    "help desk manager",
    "it director",
    "devops",
    "cloud administrator",
    "cybersecurity",
    "information technology",
]

PRIORITY_EMPLOYERS = [
    "school district",
    "county",
    "city of",
    "state of",
    "department of",
    "hospital",
    "health system",
    "university",
    "college",
    "government",
    "municipal",
]

AVOID_KEYWORDS = ["intern", "unpaid", "entry level only", "no benefits"]


class JobScoutAgent(BaseAgent):
    name = "job_scout"
    department = "job_acquisition"
    description = "Search job boards, score listings, save high-value IT job opportunities."

    def execute(
        self,
        mission_id: Optional[int] = None,
        role: str = "IT Systems Administrator",
        location: str = "New Jersey",
        remote: bool = True,
        **kwargs: Any,
    ) -> AgentResult:
        results = self._search_jobs(role, location, remote)
        if not results:
            return AgentResult(
                success=False,
                output="No jobs found. Check network or try different search terms.",
            )

        scored = self._score_jobs(results)
        scored.sort(key=lambda x: x["score"], reverse=True)
        top = scored[:10]

        with get_session() as conn:
            memory_set(conn, "job_search", f"{role}_{location}", json.dumps(top[:5]))

        output_lines = [
            f"Job Search: {role} | {location}",
            f"Found {len(results)} listings, top {len(top)} scored:\n",
        ]
        for j in top:
            output_lines.append(f"[{j['score']}/10] {j['title']} — {j['company']}")
            output_lines.append(
                f"  {j.get('location', '')} | {j.get('salary', 'Salary not listed')}"
            )
            output_lines.append(f"  {j.get('url', '')}\n")

        log_action(
            self.name,
            "search_complete",
            {"role": role, "location": location, "count": len(results)},
        )
        return AgentResult(
            success=True,
            output="\n".join(output_lines),
            data=top,
            next_action="Review top jobs, run resume_tailor for target roles",
        )

    def _search_jobs(self, role: str, location: str, remote: bool) -> list[dict]:
        results: list[dict] = []
        results.extend(self._search_brave(role, location, remote))
        return results

    def _search_brave(self, role: str, location: str, remote: bool) -> list[dict]:
        api_key = self.settings.brave_api_key
        if not api_key:
            return []
        query = (
            f'"{role}" jobs {location} site:linkedin.com OR site:indeed.com OR site:glassdoor.com'
        )
        if remote:
            query += " OR remote"
        try:
            resp = httpx.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": api_key,
                },
                params={"q": query, "count": 20},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            results: list[dict] = []
            for r in data.get("web", {}).get("results", []):
                results.append(
                    {
                        "title": r.get("title", ""),
                        "company": self._extract_company(
                            r.get("title", ""), r.get("description", "")
                        ),
                        "description": r.get("description", ""),
                        "url": r.get("url", ""),
                        "location": location,
                        "salary": self._extract_salary(r.get("description", "")),
                    }
                )
            return results
        except Exception as exc:
            log_action(self.name, "brave_error", {"error": str(exc)})
            return []

    def _extract_company(self, title: str, description: str) -> str:
        if " at " in title:
            return title.split(" at ")[-1].strip()
        if " - " in title:
            return title.split(" - ")[-1].strip()
        return "Unknown"

    def _extract_salary(self, text: str) -> str:
        match = re.search(
            r'\$[\d,]+(?:\s*[-–]\s*\$[\d,]+)?(?:\s*/\s*(?:yr|year|hr|hour))?', text
        )
        return match.group(0) if match else ""

    def _score_jobs(self, jobs: list[dict]) -> list[dict]:
        for job in jobs:
            score = 5  # baseline
            title_lower = job.get("title", "").lower()
            desc_lower = job.get("description", "").lower()
            company_lower = job.get("company", "").lower()
            combined = title_lower + " " + desc_lower + " " + company_lower

            # Priority role match
            if any(r in title_lower for r in PRIORITY_ROLES):
                score += 2
            # Priority employer
            if any(e in company_lower for e in PRIORITY_EMPLOYERS):
                score += 2
            # Salary signals
            salary = job.get("salary", "")
            if salary:
                nums = re.findall(r"\d+", salary.replace(",", ""))
                if nums:
                    max_sal = max(int(n) for n in nums)
                    if max_sal >= 80000:
                        score += 1
                    if max_sal >= 100000:
                        score += 1
            # Avoid keywords
            if any(a in combined for a in AVOID_KEYWORDS):
                score -= 3

            job["score"] = max(0, min(10, score))
        return jobs
