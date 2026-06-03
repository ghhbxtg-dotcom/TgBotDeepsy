import html
import logging
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import config
from database import Database
from keyboards import cancel_keyboard, main_menu_keyboard, message_confirmation_keyboard
from states import UserFlow
from utils import check_cooldown, format_user_display

logger = logging.getLogger(__name__)
router = Router(name="user_contact")

MEDIA_LABELS = {
    "text": "💬 Текст",
    "photo": "📷 Фото",
    "video": "🎬 Видео",
    "voice": "🎙 Голосовое",
    "document": "📎 Документ",
}


def _escape(value: object) -> str:
    return html.escape(str(value or ""))


def _shorten(value: str, limit: int = 2600) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _extract_payload(message: Message) -> dict | None:
    if message.text:
        return {
            "media_type": "text",
            "text": message.text,
            "caption": None,
            "file_id": None,
            "telegram_user_msg_id": message.message_id,
        }

    if message.photo:
        caption = message.caption or ""
        return {
            "media_type": "photo",
            "text": caption or "Фото без подписи",
            "caption": caption,
            "file_id": message.photo[-1].file_id,
            "telegram_user_msg_id": message.message_id,
        }

    if message.video:
        caption = message.caption or ""
        return {
            "media_type": "video",
            "text": caption or "Видео без подписи",
            "caption": caption,
            "file_id": message.video.file_id,
            "telegram_user_msg_id": message.message_id,
        }

    if message.voice:
        return {
            "media_type": "voice",
            "text": "Голосовое сообщение",
            "caption": None,
            "file_id": message.voice.file_id,
            "telegram_user_msg_id": message.message_id,
        }

    if message.document:
        caption = message.caption or ""
        file_name = message.document.file_name or "Документ"
        return {
            "media_type": "document",
            "text": caption or file_name,
            "caption": caption,
            "file_id": message.document.file_id,
            "telegram_user_msg_id": message.message_id,
        }

    return None


def _preview_text(payload: dict) -> str:
    label = MEDIA_LABELS.get(payload["media_type"], "Сообщение")
    body = _escape(_shorten(payload["text"], 2800))
    return (
        "🧠 <b>Проверьте сообщение:</b>\n\n"
        f"<b>{label}</b>\n"
        f"{body}\n\n"
        "Отправить?"
    )


def _build_admin_text(message_id: int, user, payload: dict, open_dialogs: int) -> str:
    display_name = _escape(format_user_display(user.username, user.first_name, user.last_name))
    username_line = f"@{_escape(user.username)}" if user.username else "отсутствует"
    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    label = MEDIA_LABELS.get(payload["media_type"], "Сообщение")
    priority_line = ""
    if open_dialogs:
        priority_line = f"\n🔥 <b>Приоритет:</b> повторное обращение, открытых диалогов: {open_dialogs}"

    return (
        "🔔 <b>Новый запрос</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🧷 <b>Message ID:</b> <code>{message_id}</code>\n"
        "🆕 <b>Статус:</b> New\n"
        f"👤 <b>Пользователь:</b> {display_name}\n"
        f"🆔 <b>User ID:</b> <code>{user.id}</code>\n"
        f"📛 <b>Username:</b> {username_line}\n"
        f"🕐 <b>Время:</b> {now_str}"
        f"{priority_line}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{label} <b>от пользователя:</b>\n"
        f"{_escape(_shorten(payload['text']))}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👀 /mark_seen {message_id}\n"
        f"❌ /close {message_id}\n"
        "↩️ <i>Ответьте reply на это сообщение, чтобы написать пользователю.</i>"
    )


async def _send_media_copy(admin_bot: Bot, payload: dict, message_id: int):
    media_type = payload["media_type"]
    file_id = payload["file_id"]
    label = MEDIA_LABELS.get(media_type, "Медиа")
    caption = f"{label} к обращению #{message_id}"
    user_caption = payload.get("caption")
    if user_caption:
        caption += f"\n\n{_escape(_shorten(user_caption, 750))}"

    if media_type == "photo":
        await admin_bot.send_photo(config.admin_id, photo=file_id, caption=caption, parse_mode="HTML")
    elif media_type == "video":
        await admin_bot.send_video(config.admin_id, video=file_id, caption=caption, parse_mode="HTML")
    elif media_type == "voice":
        await admin_bot.send_voice(config.admin_id, voice=file_id, caption=caption, parse_mode="HTML")
    elif media_type == "document":
        await admin_bot.send_document(config.admin_id, document=file_id, caption=caption, parse_mode="HTML")


@router.message(F.text == "✉️ Написать мне")
async def start_contact(message: Message, state: FSMContext, db: Database):
    user = message.from_user
    if user:
        await db.record_event("contact_started", user.id)

    await state.set_state(UserFlow.waiting_message)
    await message.answer(
        "✉️ <b>Написать мне</b>\n\n"
        "Отправьте сообщение: текст, фото, видео, голосовое или документ. "
        "Перед отправкой я покажу предпросмотр, чтобы вы могли всё проверить.",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "cancel_message")
async def cancel_contact(callback: CallbackQuery, state: FSMContext):
    """Отмена отправки сообщения."""
    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        "❌ Отправка отменена. Возвращаемся в главное меню.",
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(UserFlow.waiting_confirmation, F.data == "edit_message")
async def edit_contact_message(callback: CallbackQuery, state: FSMContext):
    await state.set_state(UserFlow.waiting_message)
    await callback.message.edit_text(
        "✏️ Хорошо, отправьте новый вариант сообщения.",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(UserFlow.waiting_message)
async def receive_user_message(message: Message, state: FSMContext):
    payload = _extract_payload(message)
    if not payload:
        await message.answer(
            "⚠️ Поддерживаются текст, фото, видео, голосовые и документы. "
            "Отправьте один из этих типов или нажмите «Отмена».",
            reply_markup=cancel_keyboard(),
        )
        return

    await state.update_data(contact_payload=payload)
    await state.set_state(UserFlow.waiting_confirmation)
    await message.answer(
        _preview_text(payload),
        reply_markup=message_confirmation_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(UserFlow.waiting_confirmation, F.data == "confirm_message")
async def confirm_user_message(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    admin_bot: Bot,
):
    user = callback.from_user
    data = await state.get_data()
    payload = data.get("contact_payload")
    if not payload:
        await state.set_state(UserFlow.waiting_message)
        await callback.message.edit_text(
            "⚠️ Не нашёл сообщение для отправки. Пожалуйста, отправьте его ещё раз.",
            reply_markup=cancel_keyboard(),
        )
        await callback.answer()
        return

    can_send, seconds_left = await check_cooldown(db, user.id)
    if not can_send:
        await callback.answer(
            f"Подождите ещё {seconds_left} сек. перед следующим обращением.",
            show_alert=True,
        )
        return

    open_dialogs = await db.count_open_messages_for_user(user.id)
    priority = 1 if open_dialogs else 0
    message_id = await db.save_message(
        user_id=user.id,
        user_message=payload["text"],
        media_type=payload["media_type"],
        file_id=payload.get("file_id"),
        caption=payload.get("caption"),
        telegram_user_msg_id=payload.get("telegram_user_msg_id"),
        priority=priority,
    )

    admin_text = _build_admin_text(message_id, user, payload, open_dialogs)
    try:
        sent = await admin_bot.send_message(
            chat_id=config.admin_id,
            text=admin_text,
            parse_mode="HTML",
        )
        await db.update_message_admin_msg_id(message_id, sent.message_id)

        if payload["media_type"] != "text":
            await _send_media_copy(admin_bot, payload, message_id)

        await db.mark_queue_processed(message_id)
        await db.update_last_sent(user.id)
        await db.record_event(
            "message_submitted",
            user.id,
            {"message_id": message_id, "media_type": payload["media_type"]},
        )
    except Exception as exc:
        logger.error("Ошибка отправки сообщения в админ-бот: %s", exc)
        await db.mark_queue_failed(message_id, str(exc))
        await callback.message.edit_text(
            "⚠️ Сообщение сохранено в очереди, но уведомление админу сейчас не отправилось. "
            "Попробуйте чуть позже.",
            reply_markup=None,
        )
        await state.clear()
        await callback.answer()
        return

    await state.clear()
    await callback.message.edit_text(
        "✅ <b>Сообщение успешно отправлено!</b>\n\n"
        "Ожидайте ответ. Я свяжусь с вами как можно скорее.",
        parse_mode="HTML",
    )
    await callback.message.answer("🏠 Главное меню", reply_markup=main_menu_keyboard())
    await callback.answer()
    logger.info("Сообщение сохранено и отправлено админу: user_id=%s message_id=%s", user.id, message_id)
