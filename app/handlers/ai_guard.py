import asyncio
import logging
import random
from datetime import datetime, timezone

from aiogram import Bot, Router, F
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.db.models import ModerationReason, UserProfile
from app.services.ai_moderation import AiModerator
from app.services.moderation import punish_user_for_message
from app.services.prohibited import ProhibitedCache
from app.services.user_profiles import get_profile, upsert_profile
from app.services.verification import is_approved

logger = logging.getLogger(__name__)

router = Router()


@router.message(F.chat.id == settings.GROUP_ID)
async def ai_guard(
    message: Message,
    bot: Bot,
    sessionmaker: async_sessionmaker[AsyncSession],
    prohibited_cache: ProhibitedCache,
    ai_moderator: AiModerator,
) -> None:
    logger.info("Handler ai_guard chat_id=%s message_id=%s", message.chat.id, message.message_id)
    if message.from_user is None or message.from_user.is_bot:
        logger.info("ai_guard stop: no user or bot")
        return

    if message.new_chat_members or message.left_chat_member:
        logger.info("ai_guard stop: service message")
        return

    text = message.text or message.caption or ""
    if not text:
        logger.info("ai_guard stop: no text")
        return

    # skip admins
    try:
        member = await bot.get_chat_member(settings.GROUP_ID, message.from_user.id)
        if member.status in {"administrator", "creator"}:
            logger.info("ai_guard stop: admin user")
            return
    except Exception:
        logger.exception("Failed to check member status for AI moderation")

    async with sessionmaker() as session:
        await upsert_profile(session, message.from_user)
        profile = await get_profile(session, message.from_user.id)
        if not profile:
            profile = UserProfile(user_id=message.from_user.id, first_name=message.from_user.first_name or "")
        approved = await is_approved(session, settings.GROUP_ID, message.from_user.id)
        await session.commit()

    if not approved:
        logger.info("ai_guard stop: not approved")
        return

    # keyword check first
    matched = prohibited_cache.match(text)
    if matched:
        async with sessionmaker() as session:
            await punish_user_for_message(
                bot=bot,
                session=session,
                message=message,
                reason=ModerationReason.KEYWORD,
                matched_word=matched.original,
            )
        return
    else:
        logger.info("locally: no keyword match")

    # AI moderation
    if not settings.AI_MODERATION_ENABLED:
        logger.info("ai_guard stop: AI moderation disabled")
        return

    if len(text) < settings.AI_MODERATION_MIN_CHARS:
        logger.info("ai_guard stop: too short")
        return

    if random.random() > settings.AI_MODERATION_SAMPLE_RATE:
        logger.info("ai_guard stop: sample skipped")
        return

    now = datetime.now(tz=timezone.utc)
    # cooldown (DB based via user_profiles)
    async with sessionmaker() as session:
        prof = await get_profile(session, message.from_user.id)
        if prof and prof.last_ai_check_at:
            delta = (now - prof.last_ai_check_at).total_seconds()
            if delta < settings.AI_MODERATION_COOLDOWN_SEC:
                logger.info("ai_guard stop: cooldown")
                return
        if prof:
            prof.last_ai_check_at = now
            await session.commit()

    try:
        decision = await ai_moderator.classify_text(text)
    except Exception:
        logger.exception("AI moderation failed")
        return

    if not decision:
        logger.info("ai_guard stop: no decision")
        return

    logger.info(
        "AI moderation decision user=%s label=%s confidence=%.2f prohibited=%s",
        message.from_user.id,
        decision.label,
        decision.confidence,
        decision.is_prohibited,
    )

    if not decision.is_prohibited:
        logger.info("ai_guard stop: not prohibited")
        return

    if decision.confidence < settings.AI_CONFIDENCE_THRESHOLD:
        logger.info("ai_guard stop: low confidence")
        return

    labels = {label.strip() for label in settings.AI_PROHIBITED_LABELS.split(",") if label.strip()}
    if decision.label not in labels:
        logger.info("ai_guard stop: label not allowed")
        return

    async with sessionmaker() as session:
        await punish_user_for_message(
            bot=bot,
            session=session,
            message=message,
            reason=ModerationReason.AI,
            ai_decision=decision,
        )

    logger.info(
        "AI moderation triggered user=%s label=%s confidence=%.2f",
        message.from_user.id,
        decision.label,
        decision.confidence,
    )
