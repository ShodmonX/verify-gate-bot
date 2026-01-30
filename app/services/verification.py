import logging
from datetime import datetime, timedelta, timezone
from random import choice
from typing import Optional
from uuid import UUID

from aiogram import Bot
from aiogram.types import ChatPermissions
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import ApprovedMember, SessionState, VerificationSession
from app.words import WORDS

logger = logging.getLogger(__name__)


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


async def is_approved(session: AsyncSession, group_id: int, user_id: int) -> bool:
    result = await session.execute(
        select(ApprovedMember).where(
            ApprovedMember.group_id == group_id, ApprovedMember.user_id == user_id
        )
    )
    return result.scalar_one_or_none() is not None


async def upsert_session(session: AsyncSession, group_id: int, user_id: int) -> VerificationSession:
    result = await session.execute(
        select(VerificationSession).where(
            VerificationSession.group_id == group_id, VerificationSession.user_id == user_id
        )
    )
    existing = result.scalar_one_or_none()
    if existing and existing.state == SessionState.CONFIRMED_UNLOCKED:
        return existing

    magic_word = choice(WORDS)
    now = now_utc()
    remind_at = now + timedelta(minutes=settings.REMIND_AFTER_MIN)
    expires_at = now + timedelta(minutes=settings.EXPIRE_AFTER_MIN)

    if existing:
        existing.state = SessionState.JOINED_LOCKED
        existing.magic_word = magic_word
        existing.reminder_count = 0
        existing.remind_at = remind_at
        existing.expires_at = expires_at
        existing.updated_at = now
        return existing

    new_session = VerificationSession(
        group_id=group_id,
        user_id=user_id,
        state=SessionState.JOINED_LOCKED,
        magic_word=magic_word,
        reminder_count=0,
        remind_at=remind_at,
        expires_at=expires_at,
        created_at=now,
        updated_at=now,
    )
    session.add(new_session)
    return new_session


async def restrict_user(bot: Bot, group_id: int, user_id: int) -> None:
    try:
        await bot.restrict_chat_member(
            chat_id=group_id,
            user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_change_info=False,
                can_invite_users=False,
                can_pin_messages=False,
            ),
        )
        logger.info("Restricted user %s in group %s", user_id, group_id)
    except Exception:
        logger.exception("Failed to restrict user %s in group %s", user_id, group_id)


async def unrestrict_user(bot: Bot, group_id: int, user_id: int) -> None:
    try:
        await bot.restrict_chat_member(
            chat_id=group_id,
            user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_change_info=False,
                can_invite_users=True,
                can_pin_messages=False,
            ),
        )
        logger.info("Unrestricted user %s in group %s", user_id, group_id)
    except Exception:
        logger.exception("Failed to unrestrict user %s in group %s", user_id, group_id)


async def mark_approved(session: AsyncSession, group_id: int, user_id: int) -> None:
    now = now_utc()
    result = await session.execute(
        select(ApprovedMember).where(
            ApprovedMember.group_id == group_id, ApprovedMember.user_id == user_id
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return
    session.add(ApprovedMember(group_id=group_id, user_id=user_id, approved_at=now))


async def get_active_session(
    session: AsyncSession, group_id: int, user_id: int
) -> Optional[VerificationSession]:
    result = await session.execute(
        select(VerificationSession).where(
            VerificationSession.group_id == group_id, VerificationSession.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def update_session_state(
    session: AsyncSession, session_id: UUID, state: SessionState
) -> None:
    result = await session.execute(
        select(VerificationSession).where(VerificationSession.id == session_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        return
    item.state = state
    item.updated_at = now_utc()
