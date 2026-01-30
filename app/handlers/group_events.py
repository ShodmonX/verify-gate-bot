import logging
from datetime import datetime, timezone

from aiogram import Bot, Router, F
from aiogram.filters import BaseFilter
from aiogram.filters import ChatMemberUpdatedFilter
from aiogram.filters.chat_member_updated import IS_MEMBER, IS_NOT_MEMBER
from aiogram.types import ChatMemberUpdated, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings, get_admin_ids
from app.db.models import SessionState
from app.services.user_profiles import upsert_profile
from app.services.verification import (
    get_active_session,
    is_approved,
    restrict_user,
    upsert_session,
)
from app.texts import render_welcome
from app.services.reminders import build_agree_keyboard

logger = logging.getLogger(__name__)

router = Router()


class IsUnapproved(BaseFilter):
    async def __call__(self, message: Message, sessionmaker: async_sessionmaker[AsyncSession]) -> bool:
        if message.from_user is None or message.from_user.is_bot:
            return False
        if message.new_chat_members or message.left_chat_member:
            return False
        async with sessionmaker() as session:
            if await is_approved(session, settings.GROUP_ID, message.from_user.id):
                return False
            ver_session = await get_active_session(session, settings.GROUP_ID, message.from_user.id)
            if ver_session and ver_session.state == SessionState.CONFIRMED_UNLOCKED:
                return False
        return True


@router.chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def on_user_join(
    event: ChatMemberUpdated, bot: Bot, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    logger.info("Handler on_user_join chat_id=%s user_id=%s", event.chat.id, event.new_chat_member.user.id)
    if event.chat.id != settings.GROUP_ID:
        logger.info("on_user_join stop: not target group")
        return

    user = event.new_chat_member.user
    if user.is_bot:
        logger.info("on_user_join stop: user is bot")
        return

    async with sessionmaker() as session:
        await upsert_profile(session, user)
        if await is_approved(session, settings.GROUP_ID, user.id):
            logger.info("on_user_join stop: already approved")
            return

        ver_session = await upsert_session(session, settings.GROUP_ID, user.id)
        await session.commit()

    await restrict_user(bot, settings.GROUP_ID, user.id)

    try:
        message = await bot.send_message(
            chat_id=settings.GROUP_ID,
            text=render_welcome(user.id, user.full_name),
            parse_mode="HTML",
            reply_markup=build_agree_keyboard(ver_session),
        )
    except Exception:
        logger.exception("Failed to send welcome message")
        logger.info("on_user_join stop: welcome send failed")
        return

    async with sessionmaker() as session:
        existing = await get_active_session(session, settings.GROUP_ID, user.id)
        if existing and existing.state != SessionState.CONFIRMED_UNLOCKED:
            existing.welcome_message_id = message.message_id
            existing.updated_at = datetime.now(tz=timezone.utc)
            await session.commit()

    logger.info("New user %s locked in group %s", user.id, settings.GROUP_ID)


@router.message(
    (F.chat.id == settings.GROUP_ID) & (F.new_chat_members | F.left_chat_member)
)
async def delete_service_messages(message: Message, bot: Bot) -> None:
    logger.info("Handler delete_service_messages chat_id=%s message_id=%s", message.chat.id, message.message_id)
    try:
        await bot.delete_message(message.chat.id, message.message_id)
    except Exception:
        pass


@router.message(F.chat.id == settings.GROUP_ID, IsUnapproved())
async def delete_unapproved_messages(
    message: Message, bot: Bot, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    if message.from_user.id in get_admin_ids():
        logger.info("delete_unapproved_messages stop: admin user")
        return
    logger.info("Handler delete_unapproved_messages chat_id=%s message_id=%s", message.chat.id, message.message_id)
    try:
        await bot.delete_message(message.chat.id, message.message_id)
    except Exception:
        pass
