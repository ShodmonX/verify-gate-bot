import asyncio
import contextlib
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiogram.client.default import DefaultBotProperties
from alembic import command
from alembic.config import Config

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.handlers import callbacks, dm_verify, group_events, start, prohibited_guard, admin_panel, ai_guard
from app.logging_config import setup_logging
from app.services.prohibited import ProhibitedCache, seed_from_file_if_empty
from app.services.ai_moderation import AiModerator
from app.services.runtime_settings import load_runtime_settings, apply_runtime_settings
from app.services.reminders import reminder_worker

logger = logging.getLogger(__name__)


def run_migrations() -> None:
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    command.upgrade(alembic_cfg, "head")


async def main() -> None:
    setup_logging()
    logger.info("Starting bot in polling mode")

    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    await bot.set_my_commands([BotCommand(command="start", description="Botni ishga tushurish")])
    dp = Dispatcher()
    dp["sessionmaker"] = AsyncSessionLocal
    await seed_from_file_if_empty(AsyncSessionLocal)
    async with AsyncSessionLocal() as session:
        overrides = await load_runtime_settings(session)
        apply_runtime_settings(overrides)
    prohibited_cache = ProhibitedCache(AsyncSessionLocal)
    await prohibited_cache.refresh()
    dp["prohibited_cache"] = prohibited_cache
    ai_moderator = AiModerator()
    dp["ai_moderator"] = ai_moderator

    dp.include_router(admin_panel.router)
    dp.include_router(group_events.router)
    dp.include_router(ai_guard.router)
    dp.include_router(callbacks.router)
    dp.include_router(start.router)
    dp.include_router(dm_verify.router)

    reminder_task = asyncio.create_task(reminder_worker(bot, AsyncSessionLocal))

    try:
        await dp.start_polling(bot)
    finally:
        reminder_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reminder_task
        await ai_moderator.close()
        await bot.session.close()


if __name__ == "__main__":
    run_migrations()
    asyncio.run(main())
