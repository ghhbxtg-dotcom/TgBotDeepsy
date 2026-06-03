"""
utils/helpers.py — Вспомогательные функции.
"""

import logging
from datetime import datetime
from aiogram import Bot
from aiogram.enums import ChatMemberStatus

from config import config
from database import Database

logger = logging.getLogger(__name__)


async def check_subscription(bot: Bot, user_id: int) -> bool:
    """
    Проверить реальную подписку пользователя на канал.
    Администратор всегда проходит проверку автоматически.
    """
    # Администратор всегда имеет доступ
    if user_id == config.admin_id:
        return True

    try:
        member = await bot.get_chat_member(chat_id=config.channel_id, user_id=user_id)
        allowed_statuses = {
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR,
        }
        return member.status in allowed_statuses
    except Exception as exc:
        logger.warning("Ошибка при проверке подписки user_id=%s: %s", user_id, exc)
        return False


async def check_cooldown(db: Database, user_id: int) -> tuple[bool, int]:
    """
    Проверить cooldown для пользователя.
    Возвращает (can_send: bool, seconds_left: int).
    """
    last_sent = await db.get_last_sent(user_id)
    if last_sent is None:
        return True, 0

    elapsed = (datetime.now() - last_sent).total_seconds()
    if elapsed >= config.cooldown_seconds:
        return True, 0

    seconds_left = int(config.cooldown_seconds - elapsed)
    return False, seconds_left


def format_user_display(username: str | None, first_name: str, last_name: str | None) -> str:
    """Красивое отображение имени пользователя."""
    full_name = first_name
    if last_name:
        full_name += f" {last_name}"
    if username:
        return f"{full_name} (@{username})"
    return f"{full_name} (без username)"


def format_datetime(dt_str: str) -> str:
    """Форматировать ISO datetime в читаемый вид."""
    if not dt_str:
        return "—"
    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return dt_str


def setup_logging(level: str = "INFO"):
    """Настроить логирование для всего приложения."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
