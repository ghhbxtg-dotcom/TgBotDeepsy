import logging
from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from config import config
from database import Database
from keyboards import subscription_keyboard, main_menu_keyboard
from states import UserFlow
from utils import check_subscription

logger = logging.getLogger(__name__)
router = Router(name="user_guard")


async def _is_subscribed(bot: Bot, db: Database, user_id: int) -> bool:
    user = await db.get_user(user_id)
    if user and user["subscribed"]:
        return True
    # Перепроверяем через API (на случай отписки)
    result = await check_subscription(bot, user_id)
    if result:
        await db.set_subscribed(user_id, True)
    return result


@router.message()
async def guard_message(message: Message, bot: Bot, state: FSMContext, db: Database):
    user = message.from_user
    if not user:
        return

    subscribed = await _is_subscribed(bot, db, user.id)
    if not subscribed:
        await state.set_state(UserFlow.waiting_subscription)
        await message.answer(
            "🔒 Для использования бота необходимо подписаться на канал.",
            reply_markup=subscription_keyboard(config.channel_username),
        )
        return

    # Если подписан, но нажал что-то неизвестное — показать меню
    await message.answer(
        "Используйте кнопки меню ниже 👇",
        reply_markup=main_menu_keyboard(),
    )


@router.callback_query()
async def guard_callback(callback: CallbackQuery, bot: Bot, state: FSMContext, db: Database):
    user = callback.from_user

    subscribed = await _is_subscribed(bot, db, user.id)
    if not subscribed:
        await state.set_state(UserFlow.waiting_subscription)
        await callback.answer(
            "Сначала подпишитесь на канал!",
            show_alert=True,
        )
        return

    await callback.answer()
