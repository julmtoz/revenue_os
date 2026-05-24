"""Research Agent — web search + summarize findings."""
from __future__ import annotations

import json
from typing import Any, Optional

import httpx

from agents.base_agent import BaseAgent, AgentResult
from core.db import get_session, memory_set, memory_get
from core.logger import log_action


class ResearchAgent(BaseAgent):
    name = "research"
    department = "research"
    description = "Research topics using Brave Search, summarize findings, save to memory."

    def execute(
        self,
        mission_id: Optional[int] = None,
        query: str = "",
        **kwargs: Any,
    ) -> AgentResult:
        if not query:
            return AgentResult(success=False, output="No query provided.")

        # Check memory cache first
        cache_key = query.lower().strip()[:100]
        with get_session() as conn:
            cached = memory_get(conn, "research_cache", cache_key)
        if cached:
            return AgentResult(
                success=True,
                output=f"[CACHED] {cached}",
                data=json.loads(cached),
            )

        results = self._brave_search(query)
        if not results:
            results = self._ddg_search(query)

        if not results:
            return AgentResult(
                success=False,
                output="No results found. Check BRAVE_API_KEY or network.",
            )

        summary = self._summarize(query, results)

        with get_session() as conn:
            memory_set(
                conn,
                "research_cache",
                cache_key,
                json.dumps({"query": query, "summary": summary, "results": results[:5]}),
            )

        log_action(self.name, "research_complete", {"query": query, "result_count": len(results)})
        return AgentResult(
            success=True,
            output=summary,
            data=results,
            next_action="Review findings and decide next step",
        )

    def _brave_search(self, query: str) -> list[dict]:
        api_key = self.settings.brave_api_key
        if not api_key:
            return []
        try:
            resp = httpx.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": api_key,
                },
                params={"q": query, "count": 10},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            return [
                {
                    "title": r.get("title"),
                    "url": r.get("url"),
                    "description": r.get("description"),
                }
                for r in data.get("web", {}).get("results", [])
            ]
        except Exception as exc:
            log_action(self.name, "brave_search_error", {"error": str(exc)})
            return []

    def _ddg_search(self, query: str) -> list[dict]:
        """DuckDuckGo fallback (no key required)."""
        try:
            resp = httpx.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
                timeout=10,
            )
            data = resp.json()
            results: list[dict] = []
            if data.get("Abstract"):
                results.append(
                    {
                        "title": data.get("Heading", query),
                        "url": data.get("AbstractURL", ""),
                        "description": data["Abstract"],
                    }
                )
            for r in data.get("RelatedTopics", [])[:5]:
                if isinstance(r, dict) and r.get("Text"):
                    results.append(
                        {
                            "title": r.get("Text", "")[:80],
                            "url": r.get("FirstURL", ""),
                            "description": r.get("Text", ""),
                        }
                    )
            return results
        except Exception:
            return []

    def _summarize(self, query: str, results: list[dict]) -> str:
        lines = [f"Research: {query}", ""]
        for i, r in enumerate(results[:8], 1):
            lines.append(f"{i}. {r.get('title', 'No title')}")
            if r.get("description"):
                lines.append(f"   {r['description'][:200]}")
            if r.get("url"):
                lines.append(f"   {r['url']}")
            lines.append("")
        return "\n".join(lines)
