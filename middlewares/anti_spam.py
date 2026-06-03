import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from config import config
from database import Database

logger = logging.getLogger(__name__)

MENU_TEXTS = {
    "✉️ Написать мне",
    "❓ Частые вопросы",
}


class AntiSpamMiddleware(BaseMiddleware):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        update: Update | None = data.get("event_update")  # type: ignore
        if not update:
            return await handler(event, data)

        user = None
        message = None
        if update.message and update.message.from_user:
            message = update.message
            user = update.message.from_user
        elif update.callback_query and update.callback_query.from_user:
            user = update.callback_query.from_user

        if user:
            await self.db.record_user_activity(
                user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
            )

        if not user or not message or user.id == config.admin_id:
            return await handler(event, data)

        if message.text in MENU_TEXTS or (message.text and message.text.startswith("/")):
            return await handler(event, data)

        allowed, reason, retry_after, spam_score = await self.db.check_spam_limit(
            user.id,
            limit_seconds=config.spam_limit_seconds,
            max_score=config.spam_max_score,
            ban_minutes=config.spam_ban_minutes,
        )
        if allowed:
            return await handler(event, data)

        if reason == "banned":
            minutes = max(1, retry_after // 60)
            await message.answer(
                f"⛔ Слишком много сообщений подряд. Пауза на {minutes} мин. "
                f"Нарушений: {spam_score}."
            )
        else:
            await message.answer(
                f"⏳ Не так быстро. Можно отправлять 1 сообщение раз в "
                f"{config.spam_limit_seconds} сек. Попробуйте через {retry_after} сек."
            )

        logger.info("Spam blocked: user_id=%s reason=%s score=%s", user.id, reason, spam_score)
        return None
