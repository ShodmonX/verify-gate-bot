import logging
from datetime import datetime, timezone
from html import escape
from typing import Optional

from aiogram.types import User as TgUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UserProfile

logger = logging.getLogger(__name__)


def full_name_from_user(user: TgUser) -> str:
    name = user.first_name or ""
    if user.last_name:
        name = f"{name} {user.last_name}".strip()
    return name or f"ID:{user.id}"


async def upsert_profile(
    session: AsyncSession, user: TgUser, phone_number: Optional[str] = None
) -> UserProfile:
    result = await session.execute(select(UserProfile).where(UserProfile.user_id == user.id))
    profile = result.scalar_one_or_none()
    now = datetime.now(tz=timezone.utc)

    if profile:
        profile.first_name = user.first_name or ""
        profile.last_name = user.last_name
        profile.username = user.username
        if phone_number:
            profile.phone_number = phone_number
        profile.updated_at = now
        return profile

    profile = UserProfile(
        user_id=user.id,
        first_name=user.first_name or "",
        last_name=user.last_name,
        username=user.username,
        phone_number=phone_number,
        updated_at=now,
    )
    session.add(profile)
    return profile


async def get_profile(session: AsyncSession, user_id: int) -> Optional[UserProfile]:
    result = await session.execute(select(UserProfile).where(UserProfile.user_id == user_id))
    return result.scalar_one_or_none()


def format_user_admin_card(
    user: TgUser,
    profile: Optional[UserProfile],
    matched_word: str,
    until_dt: datetime,
    group_id: int,
    until_str: str,
) -> str:
    name = full_name_from_user(user)
    safe_name = escape(name)
    profile_link = f"<a href=\"tg://user?id={user.id}\">{safe_name}</a>"

    username = user.username or (profile.username if profile else None)
    username_display = f"@{escape(username)}" if username else "—"

    phone = profile.phone_number if profile and profile.phone_number else None
    phone_display = escape(phone) if phone else "—"

    matched_display = escape(matched_word)

    return (
        "🚫 Taqiqlangan so‘z ishlatildi\n\n"
        f"👤 Foydalanuvchi: {profile_link}\n"
        f"• Full name: {safe_name}\n"
        f"• Username: {username_display}\n"
        f"• ID: <code>{user.id}</code>\n"
        f"• Phone: {phone_display}\n\n"
        f"🧾 Sabab: <b>{matched_display}</b>\n"
        f"⏳ Cheklov: <b>{escape(until_str)}</b> gacha\n\n"
        f"Guruh: <code>{group_id}</code>"
    )
