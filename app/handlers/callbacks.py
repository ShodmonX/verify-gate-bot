import logging

from aiogram import Bot, Router
from aiogram.utils.deep_linking import create_start_link
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.db.models import VerificationSession
from app.security import decode_session_id, verify_callback_signature, build_start_payload
from app.texts import ALERT_TEXT

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(lambda c: c.data and c.data.startswith("agree:"))
async def on_agree_callback(
    callback: CallbackQuery, bot: Bot, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    logger.info("Handler on_agree_callback from_user=%s", callback.from_user.id if callback.from_user else None)
    if callback.message and callback.message.chat.id != settings.GROUP_ID:
        logger.info("on_agree_callback stop: wrong group")
        return

    data = callback.data.split(":", 3)
    if len(data) != 4:
        logger.info("on_agree_callback stop: bad callback format")
        return

    _, user_id_str, token, signature = data
    try:
        intended_user_id = int(user_id_str)
        session_id = decode_session_id(token)
    except Exception:
        logger.info("on_agree_callback stop: decode failed")
        return

    if callback.from_user.id != intended_user_id:
        await callback.answer(text=ALERT_TEXT, show_alert=True)
        logger.info("on_agree_callback stop: wrong user")
        return

    if not verify_callback_signature(
        settings.SECRET_KEY, settings.GROUP_ID, intended_user_id, session_id, signature
    ):
        await callback.answer()
        logger.info("on_agree_callback stop: signature invalid")
        return

    async with sessionmaker() as session:
        result = await session.get(VerificationSession, session_id)
        if not result:
            await callback.answer()
            logger.info("on_agree_callback stop: session not found")
            return
        if result.user_id != intended_user_id or result.group_id != settings.GROUP_ID:
            await callback.answer()
            logger.info("on_agree_callback stop: session mismatch")
            return

    payload = build_start_payload(settings.SECRET_KEY, settings.GROUP_ID, intended_user_id, session_id)
    deep_link = await create_start_link(bot, payload=f"agree_{payload}", encode=False)
    await callback.answer(url=deep_link)
    logger.info("Redirected user %s to DM", intended_user_id)
