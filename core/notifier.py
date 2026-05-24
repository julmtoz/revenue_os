"""Telegram notification system for Ozen alerts."""
from __future__ import annotations
import httpx
from core.config import get_settings
from core.logger import log_action


def send_telegram(message: str, silent: bool = False) -> bool:
    """Send a message to Julio via Telegram. Returns True on success."""
    settings = get_settings()
    token = settings.telegram_bot_token
    owner_id = settings.telegram_owner_id
    if not token or not owner_id:
        log_action("notifier", "skip", {"reason": "telegram not configured"})
        return False
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": owner_id, "text": message, "parse_mode": "HTML", "disable_notification": silent},
            timeout=10,
        )
        resp.raise_for_status()
        log_action("notifier", "sent", {"length": len(message)})
        return True
    except Exception as exc:
        log_action("notifier", "error", {"error": str(exc)})
        return False


def notify_mission_complete(mission_id: int, title: str, output_preview: str) -> None:
    msg = f"✅ <b>Mission #{mission_id} Complete</b>\n{title}\n\n{output_preview[:300]}"
    send_telegram(msg)


def notify_mission_failed(mission_id: int, title: str, error: str) -> None:
    msg = f"❌ <b>Mission #{mission_id} Failed</b>\n{title}\n\nError: {error[:200]}"
    send_telegram(msg)


def notify_approval_needed(approval_id: int, action: str, payload_preview: str) -> None:
    msg = f"⏳ <b>Approval Required #{approval_id}</b>\nAction: {action}\n{payload_preview[:200]}\n\nRun: <code>python cli.py approve {approval_id}</code>"
    send_telegram(msg)


def notify_kill_switch(activated: bool, reason: str = "") -> None:
    if activated:
        msg = f"🛑 <b>OZEN PAUSED</b>\nReason: {reason}\nRun: <code>python cli.py resume</code>"
    else:
        msg = "▶️ <b>OZEN RESUMED</b> — agents are active again"
    send_telegram(msg)


def send_daily_briefing(briefing_text: str) -> None:
    msg = f"<pre>{briefing_text[:3000]}</pre>"
    send_telegram(msg)
