import logging
from datetime import datetime, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import ChatPermissions, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings, get_primary_admin_id
from app.db.models import ModerationAction, ModerationEvent, ModerationReason
from app.services.ai_moderation import AiDecision
from app.services.user_profiles import format_user_admin_card, get_profile, upsert_profile

logger = logging.getLogger(__name__)


def format_until(dt_utc: datetime) -> str:
    tz = ZoneInfo(settings.TIMEZONE)
    local_dt = dt_utc.astimezone(tz)
    return local_dt.strftime("%Y-%m-%d %H:%M")


def html_mention(user_id: int, display_name: str) -> str:
    safe_name = escape(display_name)
    return f"<a href=\"tg://user?id={user_id}\">{safe_name}</a>"


def admin_ai_message(
    user_id: int,
    full_name: str,
    username: str | None,
    phone: str | None,
    label: str,
    confidence: float,
    reason: str,
    until_str: str,
    text_excerpt: str,
) -> str:
    name = escape(full_name) if full_name else f"ID:{user_id}"
    profile_link = f"<a href=\"tg://user?id={user_id}\">{name}</a>"
    username_display = f"@{escape(username)}" if username else "—"
    phone_display = escape(phone) if phone else "—"
    reason_display = escape(reason)
    label_display = escape(label)
    excerpt_display = escape(text_excerpt)

    return (
        "🤖 AI moderatsiya\n\n"
        f"👤 Foydalanuvchi: {profile_link}\n"
        f"• Full name: {name}\n"
        f"• Username: {username_display}\n"
        f"• ID: <code>{user_id}</code>\n"
        f"• Phone: {phone_display}\n\n"
        f"🧾 Aniqlangan mavzu: <b>{label_display}</b>\n"
        f"📈 Ishonchlilik: <b>{confidence:.2f}</b>\n"
        f"📝 Sabab: {reason_display}\n\n"
        f"⏳ Cheklov: <b>{escape(until_str)}</b> gacha\n\n"
        f"🧩 Matn: <code>{excerpt_display}</code>"
    )


async def punish_user_for_message(
    bot: Bot,
    session: AsyncSession,
    message: Message,
    reason: ModerationReason,
    matched_word: str | None = None,
    ai_decision: AiDecision | None = None,
) -> None:
    now = datetime.now(tz=timezone.utc)
    until = now + timedelta(minutes=settings.MUTE_MINUTES)
    until_str = format_until(until)

    admin_id = get_primary_admin_id()
    if admin_id is None:
        logger.exception("No admin id configured")
        return

    # Ensure profile exists and load phone data
    await upsert_profile(session, message.from_user)
    profile = await get_profile(session, message.from_user.id)
    await session.commit()

    # Forward original before deleting
    try:
        await bot.forward_message(
            chat_id=admin_id,
            from_chat_id=settings.GROUP_ID,
            message_id=message.message_id,
        )
    except Exception:
        logger.exception("Failed to forward offending message to admin")

    # Delete offending message
    try:
        await message.delete()
    except Exception:
        logger.warning("Failed to delete offending message user=%s", message.from_user.id)

    # Restrict user
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
        logger.exception("Failed to mute user")

    # Group notification
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
        logger.exception("Failed to send moderation group notification")

    # Admin detail message
    try:
        if reason == ModerationReason.KEYWORD:
            await bot.send_message(
                chat_id=admin_id,
                text=format_user_admin_card(
                    user=message.from_user,
                    profile=profile,
                    matched_word=matched_word or "",
                    until_dt=until,
                    group_id=settings.GROUP_ID,
                    until_str=until_str,
                ),
                parse_mode="HTML",
            )
        else:
            text_excerpt = (message.text or message.caption or "")[:200]
            full_name = message.from_user.full_name
            username = message.from_user.username or (profile.username if profile else None)
            phone = profile.phone_number if profile else None
            await bot.send_message(
                chat_id=admin_id,
                text=admin_ai_message(
                    user_id=message.from_user.id,
                    full_name=full_name,
                    username=username,
                    phone=phone,
                    label=ai_decision.label if ai_decision else "none",
                    confidence=ai_decision.confidence if ai_decision else 0.0,
                    reason=ai_decision.reason if ai_decision else "",
                    until_str=until_str,
                    text_excerpt=text_excerpt,
                ),
                parse_mode="HTML",
            )
    except Exception:
        logger.exception("Failed to send admin detail message")

    # Persist moderation event
    event = ModerationEvent(
        group_id=settings.GROUP_ID,
        user_id=message.from_user.id,
        message_id=message.message_id,
        action=ModerationAction.MUTED,
        reason_type=reason,
        matched_word=matched_word,
        ai_label=ai_decision.label if ai_decision else None,
        ai_confidence=ai_decision.confidence if ai_decision else None,
        ai_summary=ai_decision.reason if ai_decision else None,
        created_at=now,
    )
    session.add(event)
    await session.commit()
