import logging
from datetime import datetime, timezone

from aiogram import Bot, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.db.models import SessionState
from app.services.user_profiles import upsert_profile
from app.services.verification import (
    get_active_session,
    mark_approved,
    unrestrict_user,
)
from app.texts import render_success, DM_SUCCESS_TEXT

logger = logging.getLogger(__name__)

router = Router()


def normalize_word(text: str) -> str:
    # Case-insensitive match with trimmed spaces as required.
    return text.strip().lower()


@router.message()
async def on_dm_message(
    message: Message, bot: Bot, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    logger.info("Handler on_dm_message chat_id=%s user_id=%s", message.chat.id, message.from_user.id if message.from_user else None)
    if message.chat.type != "private":
        logger.info("on_dm_message stop: not private")
        return

    if message.from_user is None:
        logger.info("on_dm_message stop: no from_user")
        return

    phone_number = None
    if message.contact and message.contact.user_id == message.from_user.id:
        phone_number = message.contact.phone_number

    async with sessionmaker() as session:
        await upsert_profile(session, message.from_user, phone_number=phone_number)
        ver_session = await get_active_session(session, settings.GROUP_ID, message.from_user.id)
        if not ver_session:
            await session.commit()
            logger.info("on_dm_message stop: no session")
            return

        if ver_session.state not in {SessionState.WAITING_DM_CONFIRM, SessionState.JOINED_LOCKED}:
            await session.commit()
            logger.info("on_dm_message stop: wrong state")
            return

        if ver_session.expires_at <= datetime.now(tz=timezone.utc):
            await session.commit()
            logger.info("on_dm_message stop: expired")
            return

        if normalize_word(message.text or "") != normalize_word(ver_session.magic_word):
            await session.commit()
            logger.info("on_dm_message stop: word mismatch")
            return

        await unrestrict_user(bot, settings.GROUP_ID, message.from_user.id)
        await mark_approved(session, settings.GROUP_ID, message.from_user.id)
        ver_session.state = SessionState.CONFIRMED_UNLOCKED
        ver_session.updated_at = datetime.now(tz=timezone.utc)
        ver_session.reminder_count = settings.MAX_REMINDERS
        ver_session.remind_at = ver_session.expires_at
        await session.commit()

    try:
        if ver_session.welcome_message_id:
            await bot.edit_message_text(
                chat_id=settings.GROUP_ID,
                message_id=ver_session.welcome_message_id,
                text=render_success(message.from_user.id, message.from_user.full_name),
                parse_mode="HTML",
            )
        else:
            await bot.send_message(
                chat_id=settings.GROUP_ID,
                text=render_success(message.from_user.id, message.from_user.full_name),
                parse_mode="HTML",
            )
    except Exception:
        await bot.send_message(
            chat_id=settings.GROUP_ID,
            text=render_success(message.from_user.id, message.from_user.full_name),
            parse_mode="HTML",
        )

    try:
        await bot.send_message(
            chat_id=message.from_user.id,
            text=DM_SUCCESS_TEXT,
        )
    except Exception:
        pass

    logger.info("User %s approved", message.from_user.id)
