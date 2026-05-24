"""Central configuration for revenue_os."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)


def _to_path(value: str | None, default: Path) -> Path:
    if value:
        return (BASE_DIR / value).resolve()
    return default


@dataclass(frozen=True)
class Settings:
    db_path: Path
    export_dir: Path
    log_dir: Path
    default_city: str
    default_niche: str
    daily_outreach_cap: int
    scoring_weights: Dict[str, float]
    openai_model_email: str
    openai_model_audit: str
    openai_model_scoring: str
    # Safety / operational controls
    dry_run: bool
    approval_mode: bool
    max_leads_per_run: int
    max_emails_per_day: int
    allow_external_send: bool
    allow_file_delete: bool
    allow_website_edit: bool
    allow_job_apply: bool
    # Optional integrations
    brave_api_key: str | None
    telegram_bot_token: str | None
    telegram_owner_id: str | None


_cached_settings: Settings | None = None


def get_settings() -> Settings:
    global _cached_settings
    if _cached_settings is not None:
        return _cached_settings

    export_dir = _to_path(os.getenv("EXPORT_DIR"), BASE_DIR / "exports")
    log_dir = _to_path(os.getenv("LOG_DIR"), BASE_DIR / "logs")

    export_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    (export_dir / "audits").mkdir(parents=True, exist_ok=True)

    _cached_settings = Settings(
        db_path=_to_path(os.getenv("DB_PATH"), BASE_DIR / "data" / "revenue_os.db"),
        export_dir=export_dir,
        log_dir=log_dir,
        default_city=os.getenv("DEFAULT_CITY", "Newark"),
        default_niche=os.getenv("DEFAULT_NICHE", "roofing"),
        daily_outreach_cap=int(os.getenv("DAILY_OUTREACH_CAP", "25")),
        scoring_weights={
            "has_website": float(os.getenv("WEIGHT_HAS_WEBSITE", "1")),
            "missing_website": float(os.getenv("WEIGHT_MISSING_WEBSITE", "-2")),
            "has_phone": float(os.getenv("WEIGHT_HAS_PHONE", "1")),
            "valid_phone_bonus": float(os.getenv("WEIGHT_VALID_PHONE", "1.5")),
            "short_phone_penalty": float(os.getenv("WEIGHT_SHORT_PHONE_PENALTY", "-0.5")),
            "niche_match": float(os.getenv("WEIGHT_NICHE_MATCH", "2")),
            "city_match": float(os.getenv("WEIGHT_CITY_MATCH", "2")),
            "city_mismatch_penalty": float(os.getenv("WEIGHT_CITY_MISMATCH", "-1.5")),
            "low_contact_penalty": float(os.getenv("WEIGHT_LOW_CONTACT", "-2")),
            "keyword_match": float(os.getenv("WEIGHT_KEYWORD_MATCH", "1")),
            "stub_penalty": float(os.getenv("WEIGHT_STUB_PENALTY", "-8")),
        },
        openai_model_email=os.getenv("OPENAI_MODEL_EMAIL", "gpt-4.1-mini"),
        openai_model_audit=os.getenv("OPENAI_MODEL_AUDIT", "gpt-4.1-mini"),
        openai_model_scoring=os.getenv("OPENAI_MODEL_SCORING", "gpt-4o-mini"),
        dry_run=os.getenv("DRY_RUN", "true").lower() == "true",
        approval_mode=os.getenv("APPROVAL_MODE", "true").lower() == "true",
        max_leads_per_run=int(os.getenv("MAX_LEADS_PER_RUN", "50")),
        max_emails_per_day=int(os.getenv("MAX_EMAILS_PER_DAY", "20")),
        allow_external_send=os.getenv("ALLOW_EXTERNAL_SEND", "false").lower() == "true",
        allow_file_delete=os.getenv("ALLOW_FILE_DELETE", "false").lower() == "true",
        allow_website_edit=os.getenv("ALLOW_WEBSITE_EDIT", "false").lower() == "true",
        allow_job_apply=os.getenv("ALLOW_JOB_APPLY", "false").lower() == "true",
        brave_api_key=os.getenv("BRAVE_API_KEY"),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
        telegram_owner_id=os.getenv("TELEGRAM_OWNER_ID"),
    )
    return _cached_settings



def has_openai_api_key() -> bool:
    """Return True when OPENAI_API_KEY is configured."""
    return bool(os.getenv("OPENAI_API_KEY"))



def require_openai_api_key() -> None:
    if not has_openai_api_key():
        raise RuntimeError("OPENAI_API_KEY is missing. Set it in .env or export it before running this command.")
