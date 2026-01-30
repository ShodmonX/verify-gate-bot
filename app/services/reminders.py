import asyncio
import logging
from datetime import datetime, timezone, timedelta

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.db.models import SessionState, VerificationSession
from app.security import build_callback_signature, encode_session_id
from app.texts import render_reminder

logger = logging.getLogger(__name__)


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def build_agree_keyboard(session: VerificationSession) -> InlineKeyboardMarkup:
    sig = build_callback_signature(settings.SECRET_KEY, session.group_id, session.user_id, session.id)
    token = encode_session_id(session.id)
    callback_data = f"agree:{session.user_id}:{token}:{sig}"
    button = InlineKeyboardButton(text="Bu yerga bosing", callback_data=callback_data)
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


async def handle_due_session(bot: Bot, session_db: AsyncSession, session: VerificationSession) -> None:
    if session.state == SessionState.CONFIRMED_UNLOCKED:
        return

    if session.reminder_count >= settings.MAX_REMINDERS:
        return

    if session.expires_at <= now_utc():
        return

    display_name = "User"
    try:
        member = await bot.get_chat_member(session.group_id, session.user_id)
        display_name = member.user.full_name
        if member.status in {"left", "kicked"}:
            session.reminder_count = settings.MAX_REMINDERS
            session.remind_at = session.expires_at
            session.updated_at = now_utc()
            return
    except Exception:
        logger.exception("Failed to check chat member for reminder")

    try:
        await bot.send_message(
            chat_id=session.group_id,
            text=render_reminder(session.user_id, display_name),
            parse_mode="HTML",
            reply_markup=build_agree_keyboard(session),
        )
        session.reminder_count += 1
        session.remind_at = now_utc() + timedelta(minutes=settings.REMIND_AFTER_MIN)
        session.updated_at = now_utc()
        logger.info("Sent reminder to user %s in group %s", session.user_id, session.group_id)
    except Exception:
        logger.exception("Failed to send reminder for user %s", session.user_id)


async def reminder_worker(bot: Bot, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    while True:
        try:
            async with sessionmaker() as session:
                now = now_utc()
                result = await session.execute(
                    select(VerificationSession).where(
                        VerificationSession.state != SessionState.CONFIRMED_UNLOCKED,
                        VerificationSession.remind_at <= now,
                        VerificationSession.reminder_count < settings.MAX_REMINDERS,
                        VerificationSession.expires_at > now,
                    )
                )
                sessions = result.scalars().all()
                for item in sessions:
                    await handle_due_session(bot, session, item)
                await session.commit()
        except Exception:
            logger.exception("Reminder worker loop error")

        await asyncio.sleep(20)
