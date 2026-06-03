from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
from faq_data import FAQ

def subscription_keyboard(channel_username: str) -> InlineKeyboardMarkup:
    """Клавиатура с кнопками подписки и проверки."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Подписаться",
                    url=f"https://t.me/{channel_username}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Проверить подписку",
                    callback_data="check_subscription",
                )
            ],
        ]
    )

def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❓ Частые вопросы")],
            [KeyboardButton(text="✉️ Написать мне")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие...",
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()

def faq_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=f"{i+1}. {item['question']}", callback_data=item["id"])]
        for i, item in enumerate(FAQ)
    ]
    buttons.append(
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_menu")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def faq_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад к вопросам", callback_data="show_faq")],
        ]
    )

def message_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, отправить", callback_data="confirm_message"),
                InlineKeyboardButton(text="✏️ Изменить", callback_data="edit_message"),
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_message")],
        ]
    )


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_message")]
        ]
    )
