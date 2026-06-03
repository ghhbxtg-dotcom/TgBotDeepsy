import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

MESSAGE_STATUSES = {"new", "seen", "answered", "closed"}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)

    @asynccontextmanager
    async def _conn(self):
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA foreign_keys=ON")
            yield conn

    async def init(self):
        async with self._conn() as conn:
            await conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id        INTEGER PRIMARY KEY,
                    username       TEXT,
                    first_name     TEXT,
                    last_name      TEXT,
                    phone          TEXT,
                    subscribed     INTEGER DEFAULT 0,
                    created_at     TEXT NOT NULL,
                    last_seen_at   TEXT,
                    message_count  INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id               INTEGER NOT NULL,
                    user_message          TEXT NOT NULL,
                    text                  TEXT,
                    admin_reply           TEXT,
                    status                TEXT DEFAULT 'new',
                    media_type            TEXT DEFAULT 'text',
                    file_id               TEXT,
                    caption               TEXT,
                    telegram_user_msg_id  INTEGER,
                    admin_msg_id          INTEGER,
                    sent_at               TEXT NOT NULL,
                    created_at            TEXT,
                    replied               INTEGER DEFAULT 0,
                    replied_at            TEXT,
                    updated_at            TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS cooldowns (
                    user_id     INTEGER PRIMARY KEY,
                    last_sent   TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS spam_controls (
                    user_id            INTEGER PRIMARY KEY,
                    last_message_time  TEXT,
                    spam_score         INTEGER DEFAULT 0,
                    banned_until       TEXT,
                    updated_at         TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS message_queue (
                    queue_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id    INTEGER NOT NULL UNIQUE,
                    user_id       INTEGER NOT NULL,
                    status        TEXT NOT NULL DEFAULT 'pending',
                    priority      INTEGER DEFAULT 0,
                    created_at    TEXT NOT NULL,
                    processed_at  TEXT,
                    error         TEXT,
                    FOREIGN KEY (message_id) REFERENCES messages(id),
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS stats_events (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER,
                    event       TEXT NOT NULL,
                    meta        TEXT,
                    created_at  TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id);
                CREATE INDEX IF NOT EXISTS idx_messages_status ON messages(status);
                CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
                CREATE INDEX IF NOT EXISTS idx_messages_admin_msg_id ON messages(admin_msg_id);
                CREATE INDEX IF NOT EXISTS idx_queue_status ON message_queue(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_events_event_created_at ON stats_events(event, created_at);
                CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
                CREATE INDEX IF NOT EXISTS idx_users_last_seen_at ON users(last_seen_at);
                """
            )
            await self._migrate_existing_schema(conn)
            await conn.commit()
        logger.info("База данных инициализирована: %s", self.db_path)

    async def _migrate_existing_schema(self, conn: aiosqlite.Connection):
        await self._ensure_columns(
            conn,
            "users",
            {
                "last_seen_at": "TEXT",
                "message_count": "INTEGER DEFAULT 0",
            },
        )
        await self._ensure_columns(
            conn,
            "messages",
            {
                "text": "TEXT",
                "admin_reply": "TEXT",
                "status": "TEXT DEFAULT 'new'",
                "media_type": "TEXT DEFAULT 'text'",
                "file_id": "TEXT",
                "caption": "TEXT",
                "telegram_user_msg_id": "INTEGER",
                "created_at": "TEXT",
                "updated_at": "TEXT",
            },
        )
        await conn.execute("UPDATE users SET last_seen_at = COALESCE(last_seen_at, created_at)")
        await conn.execute(
            """
            UPDATE messages
            SET
                text = COALESCE(text, user_message),
                created_at = COALESCE(created_at, sent_at),
                updated_at = COALESCE(updated_at, replied_at, sent_at),
                status = CASE
                    WHEN replied = 1 THEN 'answered'
                    WHEN status IS NOT NULL THEN status
                    ELSE 'new'
                END,
                media_type = COALESCE(media_type, 'text')
            """
        )
        await conn.execute(
            """
            UPDATE users
            SET message_count = (
                SELECT COUNT(*)
                FROM messages
                WHERE messages.user_id = users.user_id
            )
            """
        )

    async def _ensure_columns(
        self,
        conn: aiosqlite.Connection,
        table: str,
        columns: dict[str, str],
    ):
        cursor = await conn.execute(f"PRAGMA table_info({table})")
        existing = {row["name"] for row in await cursor.fetchall()}
        for column, ddl in columns.items():
            if column not in existing:
                await conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    async def upsert_user(self, user_id, username, first_name, last_name, phone=None):
        now = _now()
        async with self._conn() as conn:
            await conn.execute(
                """
                INSERT INTO users (
                    user_id, username, first_name, last_name, phone, created_at, last_seen_at
                )
                VALUES (:uid, :un, :fn, :ln, :ph, :ca, :ls)
                ON CONFLICT(user_id) DO UPDATE SET
                    username     = excluded.username,
                    first_name   = excluded.first_name,
                    last_name    = excluded.last_name,
                    phone        = COALESCE(excluded.phone, users.phone),
                    last_seen_at = excluded.last_seen_at
                """,
                {
                    "uid": user_id,
                    "un": username,
                    "fn": first_name,
                    "ln": last_name,
                    "ph": phone,
                    "ca": now,
                    "ls": now,
                },
            )
            await conn.commit()

    async def record_user_activity(self, user_id, username=None, first_name=None, last_name=None):
        now = _now()
        async with self._conn() as conn:
            await conn.execute(
                """
                INSERT INTO users (user_id, username, first_name, last_name, created_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username     = COALESCE(excluded.username, users.username),
                    first_name   = COALESCE(excluded.first_name, users.first_name),
                    last_name    = COALESCE(excluded.last_name, users.last_name),
                    last_seen_at = excluded.last_seen_at
                """,
                (user_id, username, first_name, last_name, now, now),
            )
            await conn.commit()

    async def record_event(self, event: str, user_id: int | None = None, meta: dict[str, Any] | None = None):
        async with self._conn() as conn:
            await conn.execute(
                "INSERT INTO stats_events (user_id, event, meta, created_at) VALUES (?, ?, ?, ?)",
                (user_id, event, json.dumps(meta or {}, ensure_ascii=False), _now()),
            )
            await conn.commit()

    async def set_subscribed(self, user_id: int, value: bool = True):
        async with self._conn() as conn:
            await conn.execute(
                "UPDATE users SET subscribed = ?, last_seen_at = ? WHERE user_id = ?",
                (int(value), _now(), user_id),
            )
            await conn.commit()

    async def get_user(self, user_id: int):
        async with self._conn() as conn:
            cursor = await conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            return await cursor.fetchone()

    async def find_user(self, query: str):
        normalized = query.strip().lstrip("@")
        async with self._conn() as conn:
            if normalized.isdigit():
                cursor = await conn.execute("SELECT * FROM users WHERE user_id = ?", (int(normalized),))
            else:
                cursor = await conn.execute(
                    "SELECT * FROM users WHERE lower(username) = lower(?)",
                    (normalized,),
                )
            return await cursor.fetchone()

    async def get_user_profile(self, user_id: int) -> dict[str, Any]:
        async with self._conn() as conn:
            user_cursor = await conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            user = await user_cursor.fetchone()
            if not user:
                return {}

            count_cursor = await conn.execute(
                "SELECT COUNT(*) AS total FROM messages WHERE user_id = ?",
                (user_id,),
            )
            total_messages = (await count_cursor.fetchone())["total"]

            status_cursor = await conn.execute(
                """
                SELECT status, COUNT(*) AS total
                FROM messages
                WHERE user_id = ?
                GROUP BY status
                """,
                (user_id,),
            )
            statuses = {row["status"]: row["total"] for row in await status_cursor.fetchall()}

            last_cursor = await conn.execute(
                """
                SELECT
                    id AS message_id,
                    COALESCE(text, user_message) AS text,
                    status,
                    media_type,
                    created_at
                FROM messages
                WHERE user_id = ?
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT 5
                """,
                (user_id,),
            )
            return {
                "user": user,
                "total_messages": total_messages,
                "statuses": statuses,
                "last_messages": await last_cursor.fetchall(),
            }

    async def save_message(
        self,
        user_id: int,
        user_message: str,
        admin_msg_id: int | None = None,
        *,
        media_type: str = "text",
        file_id: str | None = None,
        caption: str | None = None,
        telegram_user_msg_id: int | None = None,
        priority: int = 0,
    ) -> int:
        now = _now()
        async with self._conn() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO messages (
                    user_id,
                    user_message,
                    text,
                    admin_msg_id,
                    sent_at,
                    created_at,
                    updated_at,
                    status,
                    media_type,
                    file_id,
                    caption,
                    telegram_user_msg_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, ?, ?)
                """,
                (
                    user_id,
                    user_message,
                    user_message,
                    admin_msg_id,
                    now,
                    now,
                    now,
                    media_type,
                    file_id,
                    caption,
                    telegram_user_msg_id,
                ),
            )
            message_id = cursor.lastrowid
            await conn.execute(
                """
                INSERT INTO message_queue (message_id, user_id, status, priority, created_at)
                VALUES (?, ?, 'pending', ?, ?)
                """,
                (message_id, user_id, priority, now),
            )
            await conn.execute(
                """
                UPDATE users
                SET message_count = COALESCE(message_count, 0) + 1,
                    last_seen_at = ?
                WHERE user_id = ?
                """,
                (now, user_id),
            )
            await conn.commit()
            return message_id

    async def update_message_admin_msg_id(self, message_id: int, admin_msg_id: int):
        async with self._conn() as conn:
            await conn.execute(
                "UPDATE messages SET admin_msg_id = ?, updated_at = ? WHERE id = ?",
                (admin_msg_id, _now(), message_id),
            )
            await conn.commit()

    async def mark_queue_processed(self, message_id: int):
        async with self._conn() as conn:
            await conn.execute(
                """
                UPDATE message_queue
                SET status = 'sent', processed_at = ?, error = NULL
                WHERE message_id = ?
                """,
                (_now(), message_id),
            )
            await conn.commit()

    async def mark_queue_failed(self, message_id: int, error: str):
        async with self._conn() as conn:
            await conn.execute(
                """
                UPDATE message_queue
                SET status = 'failed', processed_at = ?, error = ?
                WHERE message_id = ?
                """,
                (_now(), error[:500], message_id),
            )
            await conn.commit()

    async def get_message_by_admin_msg_id(self, admin_msg_id: int):
        async with self._conn() as conn:
            cursor = await conn.execute(
                """
                SELECT
                    *,
                    id AS message_id,
                    COALESCE(text, user_message) AS display_text
                FROM messages
                WHERE admin_msg_id = ?
                """,
                (admin_msg_id,),
            )
            return await cursor.fetchone()

    async def get_message_by_id(self, message_id: int):
        async with self._conn() as conn:
            cursor = await conn.execute(
                """
                SELECT
                    *,
                    id AS message_id,
                    COALESCE(text, user_message) AS display_text
                FROM messages
                WHERE id = ?
                """,
                (message_id,),
            )
            return await cursor.fetchone()

    async def mark_replied(self, message_id: int, admin_reply: str | None = None):
        async with self._conn() as conn:
            await conn.execute(
                """
                UPDATE messages
                SET
                    replied = 1,
                    replied_at = ?,
                    updated_at = ?,
                    status = 'answered',
                    admin_reply = COALESCE(?, admin_reply)
                WHERE id = ?
                """,
                (_now(), _now(), admin_reply, message_id),
            )
            await conn.commit()

    async def set_message_status(self, message_id: int, status: str) -> bool:
        if status not in MESSAGE_STATUSES:
            raise ValueError(f"Unknown message status: {status}")
        async with self._conn() as conn:
            cursor = await conn.execute(
                "UPDATE messages SET status = ?, updated_at = ? WHERE id = ?",
                (status, _now(), message_id),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def count_open_messages_for_user(self, user_id: int) -> int:
        async with self._conn() as conn:
            cursor = await conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM messages
                WHERE user_id = ? AND status IN ('new', 'seen')
                """,
                (user_id,),
            )
            row = await cursor.fetchone()
            return int(row["total"])

    async def get_stats(self) -> dict[str, Any]:
        now = datetime.now()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        week_start = (now - timedelta(days=7)).isoformat()
        day_ago = (now - timedelta(days=1)).isoformat()
        days_7_ago = (now - timedelta(days=7)).isoformat()
        days_30_ago = (now - timedelta(days=30)).isoformat()

        async with self._conn() as conn:
            total_users = await self._scalar(conn, "SELECT COUNT(*) FROM users")
            messages_today = await self._scalar(
                conn,
                "SELECT COUNT(*) FROM messages WHERE datetime(created_at) >= datetime(?)",
                (day_start,),
            )
            messages_week = await self._scalar(
                conn,
                "SELECT COUNT(*) FROM messages WHERE datetime(created_at) >= datetime(?)",
                (week_start,),
            )
            contact_today = await self._scalar(
                conn,
                """
                SELECT COUNT(*)
                FROM stats_events
                WHERE event = 'contact_started' AND datetime(created_at) >= datetime(?)
                """,
                (day_start,),
            )
            contact_week = await self._scalar(
                conn,
                """
                SELECT COUNT(*)
                FROM stats_events
                WHERE event = 'contact_started' AND datetime(created_at) >= datetime(?)
                """,
                (week_start,),
            )
            contact_total = await self._scalar(
                conn,
                "SELECT COUNT(*) FROM stats_events WHERE event = 'contact_started'",
            )
            active_24h = await self._scalar(
                conn,
                "SELECT COUNT(*) FROM users WHERE datetime(last_seen_at) >= datetime(?)",
                (day_ago,),
            )
            active_7d = await self._scalar(
                conn,
                "SELECT COUNT(*) FROM users WHERE datetime(last_seen_at) >= datetime(?)",
                (days_7_ago,),
            )
            active_30d = await self._scalar(
                conn,
                "SELECT COUNT(*) FROM users WHERE datetime(last_seen_at) >= datetime(?)",
                (days_30_ago,),
            )

            status_cursor = await conn.execute(
                "SELECT status, COUNT(*) AS total FROM messages GROUP BY status"
            )
            by_status = {row["status"]: row["total"] for row in await status_cursor.fetchall()}

            media_cursor = await conn.execute(
                "SELECT media_type, COUNT(*) AS total FROM messages GROUP BY media_type"
            )
            by_media = {row["media_type"]: row["total"] for row in await media_cursor.fetchall()}

            queue_cursor = await conn.execute(
                "SELECT status, COUNT(*) AS total FROM message_queue GROUP BY status"
            )
            queue = {row["status"]: row["total"] for row in await queue_cursor.fetchall()}

            return {
                "total_users": total_users,
                "messages_today": messages_today,
                "messages_week": messages_week,
                "contact_today": contact_today,
                "contact_week": contact_week,
                "contact_total": contact_total,
                "active_24h": active_24h,
                "active_7d": active_7d,
                "active_30d": active_30d,
                "by_status": by_status,
                "by_media": by_media,
                "queue": queue,
            }

    async def _scalar(self, conn: aiosqlite.Connection, query: str, params: tuple[Any, ...] = ()):
        cursor = await conn.execute(query, params)
        row = await cursor.fetchone()
        return int(row[0] or 0)

    async def check_spam_limit(
        self,
        user_id: int,
        *,
        limit_seconds: int,
        max_score: int,
        ban_minutes: int,
    ) -> tuple[bool, str | None, int, int]:
        now = datetime.now()
        now_iso = now.isoformat(timespec="seconds")

        async with self._conn() as conn:
            cursor = await conn.execute(
                "SELECT * FROM spam_controls WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()

            if row and row["banned_until"]:
                banned_until = datetime.fromisoformat(row["banned_until"])
                if banned_until > now:
                    retry_after = max(1, int((banned_until - now).total_seconds()))
                    return False, "banned", retry_after, int(row["spam_score"] or 0)

            spam_score = int(row["spam_score"] or 0) if row else 0
            last_time = datetime.fromisoformat(row["last_message_time"]) if row and row["last_message_time"] else None

            if last_time and (now - last_time).total_seconds() < limit_seconds:
                spam_score += 1
                banned_until = None
                retry_after = max(1, int(limit_seconds - (now - last_time).total_seconds()))
                reason = "limited"

                if spam_score >= max_score:
                    banned_until = (now + timedelta(minutes=ban_minutes)).isoformat(timespec="seconds")
                    retry_after = ban_minutes * 60
                    reason = "banned"

                await conn.execute(
                    """
                    INSERT INTO spam_controls (
                        user_id, last_message_time, spam_score, banned_until, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        last_message_time = excluded.last_message_time,
                        spam_score = excluded.spam_score,
                        banned_until = excluded.banned_until,
                        updated_at = excluded.updated_at
                    """,
                    (user_id, now_iso, spam_score, banned_until, now_iso),
                )
                await conn.commit()
                return False, reason, retry_after, spam_score

            spam_score = max(0, spam_score - 1)
            await conn.execute(
                """
                INSERT INTO spam_controls (
                    user_id, last_message_time, spam_score, banned_until, updated_at
                )
                VALUES (?, ?, ?, NULL, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    last_message_time = excluded.last_message_time,
                    spam_score = excluded.spam_score,
                    banned_until = NULL,
                    updated_at = excluded.updated_at
                """,
                (user_id, now_iso, spam_score, now_iso),
            )
            await conn.commit()
            return True, None, 0, spam_score

    async def get_last_sent(self, user_id: int):
        async with self._conn() as conn:
            cursor = await conn.execute(
                "SELECT last_sent FROM cooldowns WHERE user_id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            if row:
                return datetime.fromisoformat(row["last_sent"])
            return None

    async def update_last_sent(self, user_id: int):
        async with self._conn() as conn:
            await conn.execute(
                """
                INSERT INTO cooldowns (user_id, last_sent) VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET last_sent = excluded.last_sent
                """,
                (user_id, _now()),
            )
            await conn.commit()
