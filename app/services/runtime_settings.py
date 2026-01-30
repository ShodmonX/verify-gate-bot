import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import AppSetting

logger = logging.getLogger(__name__)

SUPPORTED_KEYS = {
    "REMIND_AFTER_MIN",
    "EXPIRE_AFTER_MIN",
    "MAX_REMINDERS",
    "ADMIN_IDS",
    "MUTE_MINUTES",
    "AI_MODERATION_ENABLED",
}


def parse_bool(value: str) -> bool:
    value = value.strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError("Invalid boolean")


def coerce_value(key: str, value: str) -> Any:
    if key in {"REMIND_AFTER_MIN", "EXPIRE_AFTER_MIN", "MAX_REMINDERS", "MUTE_MINUTES"}:
        return int(value)
    if key == "AI_MODERATION_ENABLED":
        return parse_bool(value)
    if key == "ADMIN_IDS":
        return value
    return value


def apply_runtime_settings(values: dict[str, str]) -> None:
    for key, raw in values.items():
        if key not in SUPPORTED_KEYS:
            continue
        try:
            coerced = coerce_value(key, raw)
            setattr(settings, key, coerced)
        except Exception:
            logger.exception("Failed to apply runtime setting %s", key)


def get_current_settings() -> dict[str, str]:
    return {key: str(getattr(settings, key)) for key in SUPPORTED_KEYS}


async def load_runtime_settings(session: AsyncSession) -> dict[str, str]:
    result = await session.execute(select(AppSetting).where(AppSetting.key.in_(SUPPORTED_KEYS)))
    rows = result.scalars().all()
    return {row.key: row.value for row in rows}


async def upsert_setting(session: AsyncSession, key: str, value: str, user_id: int) -> None:
    now = datetime.now(tz=timezone.utc)
    row = await session.get(AppSetting, key)
    if row:
        row.value = value
        row.updated_at = now
        row.updated_by = user_id
    else:
        session.add(AppSetting(key=key, value=value, updated_at=now, updated_by=user_id))
