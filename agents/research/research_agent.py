"""Research Agent — web search + summarize findings."""
from __future__ import annotations

import json
import os
from typing import Any

import httpx
from bs4 import BeautifulSoup

from agents.base_agent import AgentResult, BaseAgent
from core.db import get_session, memory_get, memory_set
from core.logger import log_action


class ResearchAgent(BaseAgent):
    name = "research"
    department = "research"
    description = "Research topics using Brave Search, summarize findings, save to memory."

    def execute(
        self,
        mission_id: int | None = None,
        query: str = "",
        **kwargs: Any,
    ) -> AgentResult:
        if not query:
            return AgentResult(success=False, output="No query provided.")

        # Check memory cache first
        cache_key = query.lower().strip()
        with get_session() as conn:
            cached = memory_get(conn, "research_cache", cache_key)
        if cached:
            payload = json.loads(cached)
            return AgentResult(
                success=True,
                output=f"[CACHED] {payload.get('summary', '')}",
                data=payload.get("results", []),
                next_action="Review findings and decide next step",
            )

        results = self._brave_search(query)
        if not results:
            results = self._searxng_search(query)
        if not results:
            results = self._ddg_search(query)
        if not results:
            results = self._bing_search(query)

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
                json.dumps({"query": query, "summary": summary, "results": results}),
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
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            log_action(self.name, "brave_search_error", {"error": str(exc)})
            return []

    def _searxng_search(self, query: str) -> list[dict]:
        """Local, free metasearch fallback exposed by the n8n Docker stack."""
        base_url = os.getenv("SEARXNG_URL", "http://127.0.0.1:8081").rstrip("/")
        try:
            resp = httpx.get(
                f"{base_url}/search",
                params={
                    "q": query,
                    "format": "json",
                    "language": "en",
                    "safesearch": 0,
                },
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            results: list[dict] = []
            for item in data.get("results", [])[:10]:
                results.append(
                    {
                        "title": item.get("title"),
                        "url": item.get("url"),
                        "description": item.get("content", ""),
                    }
                )
            return results
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            log_action(self.name, "searxng_search_error", {"error": str(exc)})
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
        except (httpx.HTTPError, ValueError, TypeError):
            return []

    def _bing_search(self, query: str) -> list[dict]:
        """Free HTML search fallback when API-backed search is unavailable."""
        try:
            resp = httpx.get(
                "https://www.bing.com/search",
                params={"q": query, "count": 10},
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/155.0.0.0 Safari/537.36"
                    )
                },
                timeout=15,
                follow_redirects=True,
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            results: list[dict] = []
            for item in soup.select("li.b_algo")[:10]:
                link = item.select_one("h2 a")
                if not link:
                    continue
                snippet = item.select_one(".b_caption p")
                results.append(
                    {
                        "title": link.get_text(" ", strip=True),
                        "url": link.get("href", ""),
                        "description": snippet.get_text(" ", strip=True) if snippet else "",
                    }
                )
            return results
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            log_action(self.name, "bing_search_error", {"error": str(exc)})
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
