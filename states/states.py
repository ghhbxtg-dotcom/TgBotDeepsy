from aiogram.fsm.state import State, StatesGroup


class UserFlow(StatesGroup):
    # Пользователь ещё не прошёл проверку подписки
    waiting_subscription = State()

    # WAITING_MESSAGE: пользователь нажал «Написать мне» и ожидается его сообщение
    waiting_message = State()

    # WAITING_CONFIRMATION: пользователь проверяет сообщение перед отправкой админу
    waiting_confirmation = State()

    # WAITING_FAQ_SELECTION: пользователь выбирает вопрос из FAQ
    waiting_faq_selection = State()
