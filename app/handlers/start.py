import logging
from datetime import datetime, timezone

from aiogram import Bot, Router
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.db.models import SessionState, VerificationSession
from app.security import parse_start_payload, verify_start_payload
from app.services.verification import update_session_state
from app.texts import render_rules

logger = logging.getLogger(__name__)

router = Router()


@router.message(CommandStart(deep_link=True))
async def on_start(
    message: Message, bot: Bot, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    logger.info("Handler on_start chat_id=%s user_id=%s", message.chat.id, message.from_user.id if message.from_user else None)
    if message.chat.type != "private":
        logger.info("Start ignored: not private chat id=%s", message.chat.id)
        return

    payload = extract_start_args(message.text)
    logger.info("Received /start command. text=%r payload=%r", message.text, payload)
    if not payload.startswith("agree_"):
        logger.info("Start ignored: payload missing agree_ prefix")
        return

    parsed = parse_start_payload(settings.SECRET_KEY, payload.replace("agree_", "", 1))
    if not parsed:
        logger.info("Start ignored: payload parse failed")
        return
    _group_id, _user_id, session_id = parsed

    if message.from_user is None:
        logger.info("Start ignored: no from_user")
        return

    async with sessionmaker() as session:
        ver_session = await session.get(VerificationSession, session_id)
        if not ver_session:
            logger.info("Start ignored: session not found session_id=%s", session_id)
            return
        if ver_session.group_id != settings.GROUP_ID:
            logger.info(
                "Start ignored: group mismatch session_group=%s expected=%s",
                ver_session.group_id,
                settings.GROUP_ID,
            )
            return
        if message.from_user.id != ver_session.user_id:
            logger.info(
                "Start ignored: user mismatch session_user=%s from_user=%s",
                ver_session.user_id,
                message.from_user.id,
            )
            return
        if not verify_start_payload(
            settings.SECRET_KEY,
            ver_session.group_id,
            ver_session.user_id,
            ver_session.id,
            payload.replace("agree_", "", 1),
        ):
            logger.info("Start ignored: payload signature invalid session_id=%s", session_id)
            return

        if ver_session.state == SessionState.CONFIRMED_UNLOCKED:
            logger.info("Start ignored: already confirmed session_id=%s", session_id)
            return
        if ver_session.expires_at <= datetime.now(tz=timezone.utc):
            logger.info("Start ignored: session expired session_id=%s", session_id)
            return
        await update_session_state(session, session_id, SessionState.WAITING_DM_CONFIRM)
        await session.commit()

    await bot.send_message(
        chat_id=message.from_user.id,
        text=render_rules(ver_session.magic_word),
        parse_mode="HTML",
    )

    logger.info("Sent rules to user %s", message.from_user.id)


def extract_start_args(text: str | None) -> str:
    if not text:
        return ""
    if not text.startswith("/start"):
        return ""
    parts = text.split(maxsplit=1)
    if len(parts) == 1:
        return ""
    return parts[1].strip()


@router.message(CommandStart())
async def on_start_no_payload(message: Message) -> None:
    logger.info("Handler on_start_no_payload chat_id=%s user_id=%s", message.chat.id, message.from_user.id if message.from_user else None)
    if message.chat.type != "private":
        logger.info("Start ignored: not private chat id=%s", message.chat.id)
        return

    await message.reply(
        "Assalomu alaykum! Xush kelibsiz!\n\nHozirda sizda hech qanday faol tasdiqlash sessiyasi topilmadi. Iltimos, guruhdagi ko'rsatmalarga amal qiling va qayta urinib ko'ring.",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )
    logger.info("Sent welcome message to user %s", message.from_user.id if message.from_user else None)