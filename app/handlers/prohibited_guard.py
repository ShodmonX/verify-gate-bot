import logging
from datetime import datetime, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo

from aiogram import Bot, Router, F
from aiogram.types import ChatPermissions, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings, get_primary_admin_id
from app.services.prohibited import ProhibitedCache
from app.services.user_profiles import format_user_admin_card, get_profile, upsert_profile
from app.services.verification import is_approved

logger = logging.getLogger(__name__)

router = Router()


class Throttle:
    def __init__(self, window_seconds: int = 30) -> None:
        self.window_seconds = window_seconds
        self.last: dict[int, datetime] = {}

    def should_notify(self, user_id: int, now: datetime) -> bool:
        last = self.last.get(user_id)
        if last and (now - last).total_seconds() < self.window_seconds:
            return False
        self.last[user_id] = now
        return True


throttle = Throttle(window_seconds=30)


def html_mention(user_id: int, display_name: str) -> str:
    return f"<a href=\"tg://user?id={user_id}\">{escape(display_name)}</a>"


def format_until(dt_utc: datetime) -> str:
    tz = ZoneInfo(settings.TIMEZONE)
    local_dt = dt_utc.astimezone(tz)
    return local_dt.strftime("%Y-%m-%d %H:%M")


@router.message(F.chat.id == settings.GROUP_ID)
async def prohibited_guard(
    message: Message,
    bot: Bot,
    sessionmaker: async_sessionmaker[AsyncSession],
    prohibited_cache: ProhibitedCache,
) -> None:
    logger.info("Handler prohibited_guard chat_id=%s message_id=%s", message.chat.id, message.message_id)
    if message.from_user is None or message.from_user.is_bot:
        logger.info("prohibited_guard stop: no user or bot")
        return

    text = message.text or message.caption or ""
    if not text:
        logger.info("prohibited_guard stop: no text")
        return

    async with sessionmaker() as session:
        await upsert_profile(session, message.from_user)
        approved = await is_approved(session, settings.GROUP_ID, message.from_user.id)
        profile = await get_profile(session, message.from_user.id)
        await session.commit()
    if not approved:
        logger.info("prohibited_guard stop: not approved")
        return

    matched = prohibited_cache.match(text)
    if not matched:
        logger.info("prohibited_guard stop: no match")
        return

    now = datetime.now(tz=timezone.utc)
    until = now + timedelta(minutes=settings.MUTE_MINUTES)
    until_str = format_until(until)

    is_admin = False
    try:
        member = await bot.get_chat_member(settings.GROUP_ID, message.from_user.id)
        if member.status in {"administrator", "creator"}:
            is_admin = True
    except Exception:
        logger.exception("Failed to get chat member for prohibited moderation")

    if not is_admin:
        try:
            await bot.restrict_chat_member(
                chat_id=settings.GROUP_ID,
                user_id=message.from_user.id,
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
                until_date=until,
            )
        except Exception:
            logger.exception("Failed to mute user for prohibited words")

    if throttle.should_notify(message.from_user.id, now):
        try:
            await bot.send_message(
                chat_id=settings.GROUP_ID,
                text=(
                    f"{html_mention(message.from_user.id, message.from_user.full_name)} "
                    f"guruhda taqiqlangan mavzudagi gaplari uchun {until_str} gacha "
                    f"guruhda yozishdan cheklab qo'yildi."
                ),
                parse_mode="HTML",
            )
        except Exception:
            logger.exception("Failed to send prohibited group notification")

    admin_id = get_primary_admin_id()
    if admin_id is None:
        logger.exception("No admin id configured")
        return

    try:
        await bot.forward_message(
            chat_id=admin_id,
            from_chat_id=settings.GROUP_ID,
            message_id=message.message_id,
        )
    except Exception:
        logger.exception("Failed to forward offending message to admin")

    try:
        await bot.send_message(
            chat_id=admin_id,
            text=format_user_admin_card(
                user=message.from_user,
                profile=profile,
                matched_word=matched.original,
                until_dt=until,
                group_id=settings.GROUP_ID,
                until_str=until_str,
            ),
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("Failed to send admin moderation message")

    try:
        await message.delete()
    except Exception:
        logger.warning("Failed to delete prohibited message user=%s", message.from_user.id)

    logger.info("Prohibited word matched user=%s word=%s", message.from_user.id, matched)
