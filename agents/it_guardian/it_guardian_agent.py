"""IT Guardian Agent — SOP generation, incident tracking, documentation."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from agents.base_agent import BaseAgent, AgentResult
from core.db import get_session, memory_set, memory_get, get_connection
from core.logger import log_action


class ITGuardianAgent(BaseAgent):
    name = "it_guardian"
    department = "it_ops"
    description = "Generate SOPs, track incidents, document IT environment."

    SOP_TEMPLATES: dict[str, str] = {
        "new_device": (
            "# SOP: New Device Setup\n\n"
            "## Scope\nApplies to all new student/staff devices.\n\n"
            "## Steps\n"
            "1. Asset tag applied\n"
            "2. Device enrolled in MDM (Intune/Endpoint Central)\n"
            "3. Software packages deployed\n"
            "4. User account created in Google Workspace / AD\n"
            "5. Device added to inventory spreadsheet\n"
            "6. Test connectivity: Wi-Fi, printing, apps\n"
            "7. Handoff to user with orientation\n\n"
            "## Owner\nIT Department\n\n"
            "## Review\nAnnually or after major OS update"
        ),
        "wifi_issue": (
            "# SOP: Wi-Fi Troubleshooting\n\n"
            "## Common Causes\n"
            "- Channel congestion\n"
            "- Roaming issues between APs\n"
            "- IP conflicts\n"
            "- Client driver issues\n\n"
            "## Steps\n"
            "1. Identify affected device + location\n"
            "2. Check UniFi dashboard for AP status\n"
            "3. Check client association + signal strength\n"
            "4. Try forget + rejoin network\n"
            "5. Check DHCP lease (WAC dashboard)\n"
            "6. If AP-specific: check AP load, restart if needed\n"
            "7. Escalate to network review if widespread\n\n"
            "## Escalation\nIf >3 devices affected in same area — escalate to network review"
        ),
        "incident_report": (
            "# Incident Report\n\n"
            "**Date:** {date}\n"
            "**Reported By:** \n"
            "**Affected System:** \n"
            "**Severity:** Low / Medium / High\n\n"
            "## Description\n\n\n"
            "## Impact\n\n\n"
            "## Root Cause\n\n\n"
            "## Steps Taken\n"
            "1. \n"
            "2. \n"
            "3. \n\n"
            "## Resolution\n\n\n"
            "## Prevention\n\n"
        ),
        "inventory_template": (
            "# Device Inventory\n\n"
            "| Asset Tag | Device Type | Model | Serial | User | Location | OS | MDM Status | Notes |\n"
            "|-----------|-------------|-------|--------|------|----------|----|------------|-------|\n"
            "| | | | | | | | | |\n"
        ),
    }

    def execute(
        self,
        mission_id: Optional[int] = None,
        task: str = "sop",
        topic: str = "",
        **kwargs: Any,
    ) -> AgentResult:
        if task == "sop":
            return self._generate_sop(topic)
        elif task == "incident":
            return self._create_incident_report(topic)
        elif task == "inventory":
            return self._get_inventory_template()
        elif task == "log_issue":
            return self._log_recurring_issue(topic, kwargs.get("details", ""))
        elif task == "summary":
            return self._generate_summary()
        return AgentResult(
            success=False,
            output=f"Unknown task: {task}. Options: sop, incident, inventory, log_issue, summary",
        )

    def _generate_sop(self, topic: str) -> AgentResult:
        topic_lower = topic.lower()
        for key, template in self.SOP_TEMPLATES.items():
            if key in topic_lower or any(word in topic_lower for word in key.split("_")):
                return AgentResult(
                    success=True,
                    output=template,
                    next_action="Review SOP and save to IT documentation folder",
                )

        generic = (
            f"# SOP: {topic.title()}\n\n"
            "## Purpose\n[Describe purpose]\n\n"
            "## Scope\n[Who this applies to]\n\n"
            "## Prerequisites\n- [Item 1]\n- [Item 2]\n\n"
            "## Procedure\n1. [Step 1]\n2. [Step 2]\n3. [Step 3]\n\n"
            "## Verification\n[How to confirm successful completion]\n\n"
            "## Rollback\n[How to undo if needed]\n\n"
            f"## Owner\nIT Department — {datetime.now().strftime('%Y-%m-%d')}\n"
        )
        return AgentResult(
            success=True,
            output=generic,
            next_action="Fill in the blanks and save to documentation",
        )

    def _create_incident_report(self, description: str) -> AgentResult:
        report = self.SOP_TEMPLATES["incident_report"].format(
            date=datetime.now().strftime("%Y-%m-%d %H:%M")
        )
        if description:
            report = report.replace("## Description\n\n", f"## Description\n{description}\n")

        with get_session() as conn:
            existing = memory_get(conn, "it_incidents", "count") or "0"
            count = int(existing) + 1
            memory_set(conn, "it_incidents", "count", str(count))
            memory_set(
                conn,
                "it_incidents",
                f"incident_{count}",
                json.dumps(
                    {
                        "date": datetime.now().isoformat(),
                        "description": description[:200],
                    }
                ),
            )

        return AgentResult(
            success=True,
            output=report,
            next_action="Fill in details, save to incidents folder, notify stakeholders if high severity",
        )

    def _get_inventory_template(self) -> AgentResult:
        return AgentResult(
            success=True,
            output=self.SOP_TEMPLATES["inventory_template"],
            next_action="Export to Google Sheets or Excel and share with IT team",
        )

    def _log_recurring_issue(self, issue: str, details: str) -> AgentResult:
        with get_session() as conn:
            key = issue.lower().strip()[:50]
            existing_raw = memory_get(conn, "recurring_issues", key)
            existing: dict = (
                json.loads(existing_raw)
                if existing_raw
                else {"issue": issue, "count": 0, "occurrences": []}
            )
            existing["count"] += 1
            existing["occurrences"].append(
                {"date": datetime.now().isoformat(), "details": details[:200]}
            )
            existing["occurrences"] = existing["occurrences"][-10:]  # keep last 10
            memory_set(conn, "recurring_issues", key, json.dumps(existing))

        msg = f"Logged recurring issue: '{issue}' (occurrence #{existing['count']})"
        if existing["count"] >= 3:
            msg += (
                f"\nThis issue has occurred {existing['count']} times. "
                "Consider creating an SOP or permanent fix."
            )
        return AgentResult(
            success=True,
            output=msg,
            next_action="Review recurring issues weekly for patterns",
        )

    def _generate_summary(self) -> AgentResult:
        with get_session() as conn:
            incident_count = memory_get(conn, "it_incidents", "count") or "0"

        conn2 = get_connection()
        try:
            rows = conn2.execute(
                "SELECT key, value FROM memory WHERE namespace = 'recurring_issues'"
            ).fetchall()
        finally:
            conn2.close()

        issues: list[str] = []
        for row in rows:
            try:
                data = json.loads(row["value"])
                issues.append(f"  - {data['issue']}: {data['count']} occurrences")
            except Exception:
                pass

        lines = [
            "=== IT OPERATIONS SUMMARY ===",
            f"Total Incidents Logged: {incident_count}",
            f"\nRecurring Issues ({len(issues)} tracked):",
        ] + issues[:10] + ["\nRecommendation: Review any issue with 3+ occurrences for permanent fix."]

        return AgentResult(success=True, output="\n".join(lines))
