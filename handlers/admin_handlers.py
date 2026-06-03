import html
import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from config import config
from database import Database
from utils import format_datetime

logger = logging.getLogger(__name__)
router = Router(name="admin")

STATUS_ICONS = {
    "new": "🆕",
    "seen": "👀",
    "answered": "✅",
    "closed": "❌",
}

MEDIA_ICONS = {
    "text": "💬",
    "photo": "📷",
    "video": "🎬",
    "voice": "🎙",
    "document": "📎",
}


def _is_admin(user_id: int) -> bool:
    return user_id == config.admin_id


def _escape(value: object) -> str:
    return html.escape(str(value or ""))


def _shorten(value: str, limit: int = 700) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _reply_summary(message: Message) -> str:
    if message.text:
        return message.text
    if message.caption:
        return message.caption
    if message.photo:
        return "Фото"
    if message.video:
        return "Видео"
    if message.voice:
        return "Голосовое сообщение"
    if message.document:
        return message.document.file_name or "Документ"
    return "Медиафайл"


def _status_line(counts: dict) -> str:
    parts = []
    for status in ("new", "seen", "answered", "closed"):
        total = counts.get(status, 0)
        parts.append(f"{STATUS_ICONS[status]} {status}: <b>{total}</b>")
    return "\n".join(parts)


@router.message(Command("start"))
async def admin_start(message: Message):
    if not _is_admin(message.from_user.id):
        return
    await message.answer(
        "👋 <b>Админ-бот активен!</b>\n\n"
        "Команды:\n"
        "📊 /stats — статистика\n"
        "🔍 /find username_or_id - профиль и последние сообщения\n"
        "👀 /mark_seen id - отметить обращение просмотренным\n"
        "❌ /close id - закрыть обращение\n\n"
        "Чтобы ответить пользователю, сделайте <b>reply</b> на уведомление о запросе.",
        parse_mode="HTML",
    )


@router.message(Command("stats"))
async def admin_stats(message: Message, db: Database):
    if not _is_admin(message.from_user.id):
        return

    stats = await db.get_stats()
    media = stats["by_media"]
    queue = stats["queue"]
    text = (
        "📊 <b>Статистика бота</b>\n\n"
        f"👥 Пользователей: <b>{stats['total_users']}</b>\n"
        f"💬 Сообщений сегодня: <b>{stats['messages_today']}</b>\n"
        f"💬 Сообщений за 7 дней: <b>{stats['messages_week']}</b>\n\n"
        "✉️ <b>«Написать мне»</b>\n"
        f"Сегодня: <b>{stats['contact_today']}</b>\n"
        f"За 7 дней: <b>{stats['contact_week']}</b>\n"
        f"Всего: <b>{stats['contact_total']}</b>\n\n"
        "🔥 <b>Активные пользователи</b>\n"
        f"24 часа: <b>{stats['active_24h']}</b>\n"
        f"7 дней: <b>{stats['active_7d']}</b>\n"
        f"30 дней: <b>{stats['active_30d']}</b>\n\n"
        "🧭 <b>Статусы</b>\n"
        f"{_status_line(stats['by_status'])}\n\n"
        "📎 <b>Медиа</b>\n"
        f"💬 text: <b>{media.get('text', 0)}</b>\n"
        f"📷 photo: <b>{media.get('photo', 0)}</b>\n"
        f"🎬 video: <b>{media.get('video', 0)}</b>\n"
        f"🎙 voice: <b>{media.get('voice', 0)}</b>\n"
        f"📎 document: <b>{media.get('document', 0)}</b>\n\n"
        "🧷 <b>Очередь</b>\n"
        f"pending: <b>{queue.get('pending', 0)}</b>\n"
        f"sent: <b>{queue.get('sent', 0)}</b>\n"
        f"failed: <b>{queue.get('failed', 0)}</b>"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("find"))
async def admin_find(message: Message, command: CommandObject, db: Database):
    if not _is_admin(message.from_user.id):
        return

    query = (command.args or "").strip()
    if not query:
        await message.answer("Использование: <code>/find username_or_id</code>", parse_mode="HTML")
        return

    user = await db.find_user(query)
    if not user:
        await message.answer("Пользователь не найден.")
        return

    profile = await db.get_user_profile(user["user_id"])
    statuses = profile["statuses"]
    last_messages = profile["last_messages"]
    username = f"@{_escape(user['username'])}" if user["username"] else "отсутствует"
    full_name = " ".join(part for part in [user["first_name"], user["last_name"]] if part) or "без имени"
    subscription = "да" if user["subscribed"] else "нет"

    lines = [
        "🔍 <b>Профиль пользователя</b>",
        "",
        f"🆔 ID: <code>{user['user_id']}</code>",
        f"📛 Username: {username}",
        f"👤 Имя: {_escape(full_name)}",
        f"📅 Первый вход: {format_datetime(user['created_at'])}",
        f"🕐 Активность: {format_datetime(user['last_seen_at'])}",
        f"💬 Сообщений: <b>{profile['total_messages']}</b>",
        f"📢 Подписка: <b>{subscription}</b>",
        "",
        "🧭 <b>Статусы диалогов</b>",
        _status_line(statuses),
        "",
        "🕘 <b>Последние сообщения</b>",
    ]

    if last_messages:
        for item in last_messages:
            icon = STATUS_ICONS.get(item["status"], "•")
            media_icon = MEDIA_ICONS.get(item["media_type"], "💬")
            lines.append(
                f"{icon} #{item['message_id']} {media_icon} "
                f"{format_datetime(item['created_at'])}: "
                f"{_escape(_shorten(item['text'], 120))}"
            )
    else:
        lines.append("Сообщений пока нет.")

    await message.answer("\n".join(lines), parse_mode="HTML")


async def _set_status(message: Message, command: CommandObject, db: Database, status: str):
    if not _is_admin(message.from_user.id):
        return

    raw_id = (command.args or "").strip()
    if not raw_id.isdigit():
        await message.answer(f"Использование: <code>/{'mark_seen' if status == 'seen' else 'close'} id</code>", parse_mode="HTML")
        return

    message_id = int(raw_id)
    db_message = await db.get_message_by_id(message_id)
    if not db_message:
        await message.answer(f"Обращение #{message_id} не найдено.")
        return

    await db.set_message_status(message_id, status)
    icon = STATUS_ICONS[status]
    await message.answer(f"{icon} Обращение #{message_id} теперь в статусе <b>{status}</b>.", parse_mode="HTML")


@router.message(Command("mark_seen"))
async def admin_mark_seen(message: Message, command: CommandObject, db: Database):
    await _set_status(message, command, db, "seen")


@router.message(Command("close"))
async def admin_close(message: Message, command: CommandObject, db: Database):
    await _set_status(message, command, db, "closed")


@router.message(F.reply_to_message)
async def handle_admin_reply(message: Message, db: Database, user_bot):
    if not _is_admin(message.from_user.id):
        return
    if not message.reply_to_message:
        return

    admin_msg_id = message.reply_to_message.message_id
    db_message = await db.get_message_by_admin_msg_id(admin_msg_id)

    if not db_message:
        await message.answer(
            "⚠️ Не удалось найти обращение для этого сообщения.\n"
            "Отвечайте reply на основное уведомление с Message ID."
        )
        return

    user_id = db_message["user_id"]
    message_id = db_message["message_id"]
    original_text = db_message["display_text"]
    sent_at = format_datetime(db_message["created_at"] or db_message["sent_at"])
    admin_reply = _reply_summary(message)

    reply_text = (
        f"📩 <b>Ответ на ваше сообщение</b> от <i>{sent_at}</i>\n\n"
        f"<i>Ваше сообщение:</i>\n{_escape(_shorten(original_text, 900))}\n\n"
        "─────────────────\n\n"
        f"<b>Ответ:</b>\n{_escape(_shorten(admin_reply, 2500))}"
    )

    try:
        await user_bot.send_message(chat_id=user_id, text=reply_text, parse_mode="HTML")

        if message.photo:
            await user_bot.send_photo(
                chat_id=user_id,
                photo=message.photo[-1].file_id,
                caption=_escape(message.caption) if message.caption else None,
                parse_mode="HTML",
            )
        elif message.document:
            await user_bot.send_document(
                chat_id=user_id,
                document=message.document.file_id,
                caption=_escape(message.caption) if message.caption else None,
                parse_mode="HTML",
            )
        elif message.voice:
            await user_bot.send_voice(chat_id=user_id, voice=message.voice.file_id)
        elif message.video:
            await user_bot.send_video(
                chat_id=user_id,
                video=message.video.file_id,
                caption=_escape(message.caption) if message.caption else None,
                parse_mode="HTML",
            )

        await db.mark_replied(message_id, admin_reply)

        await message.answer(
            f"✅ Ответ доставлен пользователю (ID: <code>{user_id}</code>). "
            f"Обращение #{message_id} отмечено как answered.",
            parse_mode="HTML",
        )
        logger.info("Ответ отправлен: admin → user_id=%s message_id=%s", user_id, message_id)

    except Exception as exc:
        logger.error("Ошибка при отправке ответа пользователю %s: %s", user_id, exc)
        await message.answer(
            f"❌ Не удалось доставить ответ пользователю.\nОшибка: <code>{_escape(exc)}</code>",
            parse_mode="HTML",
        )


@router.message()
async def admin_unknown(message: Message):
    if not _is_admin(message.from_user.id):
        return
    await message.answer(
        "ℹ️ Сделайте reply на обращение, чтобы ответить пользователю, или используйте /stats и /find.",
        parse_mode="HTML",
    )
