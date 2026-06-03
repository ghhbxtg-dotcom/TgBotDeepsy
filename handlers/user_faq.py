import logging
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from faq_data import FAQ
from keyboards import faq_keyboard, faq_back_keyboard, main_menu_keyboard
from states import UserFlow

logger = logging.getLogger(__name__)
router = Router(name="user_faq")

_FAQ_INDEX: dict[str, dict] = {item["id"]: item for item in FAQ}


@router.message(F.text == "❓ Частые вопросы")
async def show_faq_menu(message: Message, state: FSMContext):
    await state.set_state(UserFlow.waiting_faq_selection)
    lines = "\n".join(f"{i+1}. {item['question']}" for i, item in enumerate(FAQ))
    text = f"📋 <b>Частые вопросы:</b>\n\n{lines}\n\nВыберите вопрос, чтобы узнать ответ:"
    await message.answer(text, reply_markup=faq_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "show_faq")
async def show_faq_callback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(UserFlow.waiting_faq_selection)
    lines = "\n".join(f"{i+1}. {item['question']}" for i, item in enumerate(FAQ))
    text = f"📋 <b>Частые вопросы:</b>\n\n{lines}\n\nВыберите вопрос, чтобы узнать ответ:"
    await callback.message.edit_text(text, reply_markup=faq_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("faq_"))
async def show_faq_answer(callback: CallbackQuery):
    faq_id = callback.data
    item = _FAQ_INDEX.get(faq_id)

    if not item:
        await callback.answer("Вопрос не найден.", show_alert=True)
        return

    text = (
        f"❓ <b>Вопрос:</b>\n{item['question']}\n\n"
        f"💬 <b>Ответ:</b>\n{item['answer']}"
    )
    await callback.message.edit_text(
        text, reply_markup=faq_back_keyboard(), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        "🏠 Главное меню", reply_markup=main_menu_keyboard()
    )
    await callback.answer()
