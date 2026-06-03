"""
config.py — Централизованная конфигурация проекта.
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise ValueError(f"Обязательная переменная окружения '{key}' не задана. Проверьте .env файл.")
    return value


@dataclass(frozen=True)
class Config:
    user_bot_token: str
    admin_bot_token: str
    admin_id: int
    channel_id: int
    channel_username: str
    cooldown_seconds: int
    spam_limit_seconds: int
    spam_max_score: int
    spam_ban_minutes: int
    db_path: str
    log_level: str
    proxy_url: str | None  # например: socks5://127.0.0.1:2080


def load_config() -> Config:
    return Config(
        user_bot_token=_require("USER_BOT_TOKEN"),
        admin_bot_token=_require("ADMIN_BOT_TOKEN"),
        admin_id=int(_require("ADMIN_ID")),
        channel_id=int(_require("CHANNEL_ID")),
        channel_username=os.getenv("CHANNEL_USERNAME", "channel"),
        cooldown_seconds=int(os.getenv("COOLDOWN_SECONDS", "60")),
        spam_limit_seconds=int(os.getenv("SPAM_LIMIT_SECONDS", "10")),
        spam_max_score=int(os.getenv("SPAM_MAX_SCORE", "3")),
        spam_ban_minutes=int(os.getenv("SPAM_BAN_MINUTES", "5")),
        db_path=os.getenv("DB_PATH", "database/bot.db"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        proxy_url=os.getenv("PROXY_URL"),  # None если не задан
    )


config = load_config()
