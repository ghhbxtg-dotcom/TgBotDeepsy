"""
main.py — Точка входа. Запускает два бота одновременно.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import config
from database import Database
from middlewares import AntiSpamMiddleware
from handlers import user_start, user_faq, user_contact, user_guard, admin_handlers
from utils import setup_logging

logger = logging.getLogger(__name__)


def make_session() -> AiohttpSession | None:
    """Создать сессию с прокси если задан PROXY_URL, иначе None (дефолтная сессия)."""
    if config.proxy_url:
        logger.info("Используется прокси: %s", config.proxy_url)
        return AiohttpSession(proxy=config.proxy_url)
    return None


def build_user_dispatcher(db: Database, admin_bot: Bot) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.outer_middleware(AntiSpamMiddleware(db))
    dp["db"] = db
    dp["admin_bot"] = admin_bot
    dp.include_router(user_start.router)
    dp.include_router(user_faq.router)
    dp.include_router(user_contact.router)
    dp.include_router(user_guard.router)
    return dp


def build_admin_dispatcher(db: Database, user_bot: Bot) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp["db"] = db
    dp["user_bot"] = user_bot
    dp.include_router(admin_handlers.router)
    return dp


async def main():
    setup_logging(config.log_level)
    logger.info("Запуск ботов...")

    db = Database(config.db_path)
    await db.init()

    session = make_session()

    user_bot = Bot(
        token=config.user_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )
    admin_bot = Bot(
        token=config.admin_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )

    user_dp = build_user_dispatcher(db, admin_bot)
    admin_dp = build_admin_dispatcher(db, user_bot)

    await user_bot.delete_webhook(drop_pending_updates=True)
    await admin_bot.delete_webhook(drop_pending_updates=True)

    user_info = await user_bot.get_me()
    admin_info = await admin_bot.get_me()
    logger.info("Основной бот:  @%s", user_info.username)
    logger.info("Админ-бот:     @%s", admin_info.username)
    logger.info("Polling запущен. Нажмите Ctrl+C для остановки.")

    try:
        await asyncio.gather(
            user_dp.start_polling(user_bot, allowed_updates=user_dp.resolve_used_update_types()),
            admin_dp.start_polling(admin_bot, allowed_updates=admin_dp.resolve_used_update_types()),
        )
    finally:
        await user_bot.session.close()
        if admin_bot.session is not user_bot.session:
            await admin_bot.session.close()
        logger.info("Боты остановлены.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Прерывание пользователем.")
