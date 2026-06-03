import logging
from aiogram import Router, Bot, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from config import config
from database import Database
from keyboards import subscription_keyboard, main_menu_keyboard
from states import UserFlow
from utils import check_subscription

logger = logging.getLogger(__name__)
router = Router(name="user_start")

# Приветственное изображение — замените на свою картинку (URL или file_id)
WELCOME_IMAGE_URL = ""


async def _send_subscription_request(message: Message):
    text = (
        "👋 <b>Добро пожаловать!</b>\n\n"
        "Для использования бота необходимо подписаться на наш Telegram-канал.\n\n"
        f"📢 Канал: @{config.channel_username}\n\n"
        "После подписки нажмите кнопку <b>«Проверить подписку»</b>."
    )
    try:
        await message.answer_photo(
            photo=WELCOME_IMAGE_URL,
            caption=text,
            reply_markup=subscription_keyboard(config.channel_username),
            parse_mode="HTML",
        )
    except Exception:
        # Если картинка недоступна — отправляем только текст
        await message.answer(
            text,
            reply_markup=subscription_keyboard(config.channel_username),
            parse_mode="HTML",
        )


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot, state: FSMContext, db: Database):
    user = message.from_user
    if not user:
        return

    # Сохраняем/обновляем пользователя в БД
    await db.upsert_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    logger.info("Старт: user_id=%s username=%s", user.id, user.username)

    # Проверяем реальную подписку
    is_subscribed = await check_subscription(bot, user.id)

    if is_subscribed:
        await db.set_subscribed(user.id, True)
        await state.clear()
        await message.answer(
            "✅ <b>Подписка подтверждена!</b>\n\nТеперь вы можете пользоваться ботом.",
            reply_markup=main_menu_keyboard(),
            parse_mode="HTML",
        )
    else:
        await state.set_state(UserFlow.waiting_subscription)
        await _send_subscription_request(message)


@router.callback_query(F.data == "check_subscription")
async def check_sub_callback(callback: CallbackQuery, bot: Bot, state: FSMContext, db: Database):
    user = callback.from_user

    is_subscribed = await check_subscription(bot, user.id)

    if is_subscribed:
        await db.set_subscribed(user.id, True)
        await state.clear()
        try:
            await callback.message.delete()
        except Exception:
            pass

        await callback.message.answer(
            "✅ <b>Подписка подтверждена!</b>\n\nТеперь вы можете пользоваться ботом.",
            reply_markup=main_menu_keyboard(),
            parse_mode="HTML",
        )
        logger.info("Подписка подтверждена: user_id=%s", user.id)
    else:
        await callback.answer(
            "❌ Вы ещё не подписались на канал. Подпишитесь и попробуйте снова.",
            show_alert=True,
        )
