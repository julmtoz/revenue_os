"""SEO Auditor Agent — technical SEO analysis."""
from __future__ import annotations

from typing import Any, Optional

import httpx
from bs4 import BeautifulSoup

from agents.base_agent import BaseAgent, AgentResult
from core.logger import log_action


class SEOAuditorAgent(BaseAgent):
    name = "seo_auditor"
    department = "seo_marketing"
    description = "Audit websites for technical SEO issues and generate prioritized fix lists."

    def execute(
        self,
        mission_id: Optional[int] = None,
        url: str = "",
        **kwargs: Any,
    ) -> AgentResult:
        if not url:
            return AgentResult(success=False, output="No URL provided.")
        if not url.startswith("http"):
            url = "https://" + url

        html, final_url, status_code = self._fetch(url)
        if not html:
            return AgentResult(
                success=False,
                output=f"Could not fetch {url} (status {status_code})",
            )

        findings = self._audit(html, final_url)
        report = self._format_report(url, findings)

        score = self._calculate_score(findings)
        issues = len([f for f in findings if not f["passed"]])
        log_action(self.name, "audit_complete", {"url": url, "score": score, "issues": issues})

        return AgentResult(
            success=True,
            output=report,
            data=findings,
            next_action="Send audit report to client or use for outreach",
        )

    def _fetch(self, url: str) -> tuple[str, str, int]:
        try:
            resp = httpx.get(
                url,
                timeout=15,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; OzenSEOBot/1.0)"},
            )
            return resp.text, str(resp.url), resp.status_code
        except Exception:
            return "", url, 0

    def _audit(self, html: str, url: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        findings: list[dict] = []

        # Title tag
        title = soup.find("title")
        title_text = title.get_text().strip() if title else ""
        findings.append(
            {
                "check": "Title Tag",
                "passed": bool(title_text),
                "value": title_text[:60] or "MISSING",
                "priority": "HIGH",
                "fix": "Add a descriptive title tag (50-60 chars) with primary keyword",
            }
        )

        # Meta description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        desc_content = meta_desc.get("content", "").strip() if meta_desc else ""
        findings.append(
            {
                "check": "Meta Description",
                "passed": bool(desc_content),
                "value": desc_content[:80] or "MISSING",
                "priority": "HIGH",
                "fix": "Add meta description (150-160 chars) with call to action",
            }
        )

        # H1
        h1 = soup.find("h1")
        h1_text = h1.get_text().strip() if h1 else ""
        findings.append(
            {
                "check": "H1 Tag",
                "passed": bool(h1_text),
                "value": h1_text[:60] or "MISSING",
                "priority": "HIGH",
                "fix": "Add one H1 tag with your primary keyword",
            }
        )

        # HTTPS
        findings.append(
            {
                "check": "HTTPS",
                "passed": url.startswith("https://"),
                "value": url[:50],
                "priority": "HIGH",
                "fix": "Install SSL certificate and redirect HTTP to HTTPS",
            }
        )

        # Canonical
        canonical = soup.find("link", rel="canonical")
        findings.append(
            {
                "check": "Canonical Tag",
                "passed": bool(canonical),
                "value": canonical.get("href", "") if canonical else "MISSING",
                "priority": "MEDIUM",
                "fix": "Add canonical tag to prevent duplicate content issues",
            }
        )

        # Open Graph
        og_title = soup.find("meta", property="og:title")
        findings.append(
            {
                "check": "Open Graph Tags",
                "passed": bool(og_title),
                "value": "Present" if og_title else "MISSING",
                "priority": "MEDIUM",
                "fix": "Add og:title, og:description, og:image for social sharing",
            }
        )

        # Viewport
        viewport = soup.find("meta", attrs={"name": "viewport"})
        findings.append(
            {
                "check": "Mobile Viewport",
                "passed": bool(viewport),
                "value": "Present" if viewport else "MISSING",
                "priority": "HIGH",
                "fix": "Add <meta name='viewport' content='width=device-width, initial-scale=1'>",
            }
        )

        # Images with alt text
        images = soup.find_all("img")
        imgs_without_alt = [img for img in images if not img.get("alt")]
        findings.append(
            {
                "check": "Image Alt Text",
                "passed": len(imgs_without_alt) == 0,
                "value": f"{len(imgs_without_alt)}/{len(images)} missing alt",
                "priority": "MEDIUM",
                "fix": f"Add descriptive alt text to {len(imgs_without_alt)} image(s)",
            }
        )

        # Schema markup
        schema = soup.find("script", type="application/ld+json")
        findings.append(
            {
                "check": "Schema Markup",
                "passed": bool(schema),
                "value": "Present" if schema else "MISSING",
                "priority": "MEDIUM",
                "fix": "Add LocalBusiness or Service schema markup for rich results",
            }
        )

        # Body text length
        body_text = soup.get_text(separator=" ").strip()
        word_count = len(body_text.split())
        findings.append(
            {
                "check": "Content Length",
                "passed": word_count >= 300,
                "value": f"{word_count} words",
                "priority": "MEDIUM",
                "fix": "Add more content — aim for 500+ words on key pages",
            }
        )

        return findings

    def _calculate_score(self, findings: list[dict]) -> int:
        passed = sum(1 for f in findings if f["passed"])
        return round((passed / len(findings)) * 100) if findings else 0

    def _format_report(self, url: str, findings: list[dict]) -> str:
        passed = [f for f in findings if f["passed"]]
        failed = [f for f in findings if not f["passed"]]
        score = self._calculate_score(findings)

        lines = [
            f"=== SEO AUDIT: {url} ===",
            f"Score: {score}/100 | Passed: {len(passed)} | Issues: {len(failed)}",
            "",
            "ISSUES TO FIX (Priority Order):",
        ]

        for priority in ["HIGH", "MEDIUM", "LOW"]:
            issues = [f for f in failed if f.get("priority") == priority]
            for f in issues:
                lines.append(f"  [{priority}] {f['check']}: {f['value']}")
                lines.append(f"         Fix: {f['fix']}")

        lines += ["", "PASSING:"]
        for f in passed:
            lines.append(f"  OK {f['check']}: {f['value']}")

        return "\n".join(lines)
