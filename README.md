# Telegram Bot
Прямо сейчас бот в телеграмм уже работает - @De3psybot, но вы можете использовать некоторые детали кода в своих проектах

## Структура
tgbot/
├── main.py                  # Точка входа, запуск двух ботов
├── config.py                # Конфигурация из .env
├── faq_data.py              # Редактируемые FAQ
├── requirements.txt
├── .env.example
│
├── handlers/
│   ├── user_start.py        # /start и проверка подписки
│   ├── user_faq.py          # Раздел «Частые вопросы»
│   ├── user_contact.py      # Раздел «Написать мне»
│   ├── user_guard.py        # Защита от неподписанных пользователей
│   └── admin_handlers.py    # Обработка ответов администратора
│
├── keyboards/
│   └── keyboards.py         # Все клавиатуры проекта
│
├── database/
│   └── db.py                # Работа с SQLite (aiosqlite)
│
├── states/
│   └── states.py            # FSM-состояния
│
├── middlewares/
│   └── anti_spam.py         # Защита от спама
│
└── utils/
    └── helpers.py           # Вспомогательные функции
```
## Шаг 1 - Выдать боту права администратора в канале

Основной бот **обязательно** должен быть администратором канала, иначе не сможет проверять подписку.

1. Откройте ваш канал - **Управление каналом**
2. **Администраторы** - **Добавить администратора**
3. Найдите вашего основного бота по username
4. Выдайте права (можно минимальные - достаточно просто добавить)
5. Сохраните

## Шаг 2 - Настройка .env
```bash
# Откройте .env и заполните значения
nano .env   # или любой редактор
```

Пример заполненного `.env`:
```env
USER_BOT_TOKEN=1234567890:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ADMIN_BOT_TOKEN=9876543210:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ADMIN_ID=123456789
CHANNEL_ID=-1001234567890
CHANNEL_USERNAME=De3ps1
COOLDOWN_SECONDS=60
DB_PATH=database/bot.db
LOG_LEVEL=INFO
SPAM_LIMIT_SECONDS=10
SPAM_MAX_SCORE=3
SPAM_BAN_MINUTES=5
```
## Шаг 6 - Установка и запуск
```bash
# Создать виртуальное окружение (рекомендуется)
python3 -m venv venv
source venv/bin/activate      # Linux/Mac
# venv\Scripts\activate       # Windows

# Установить зависимости
pip install -r requirements.txt

# Запустить
python main.py
```

## Шаг 7 = Проверка работы

1. Откройте **основной бот** в Telegram
2. Отправьте `/start` - должна появиться картинка с кнопками подписки
3. Подпишитесь на канал, нажмите «Проверить подписку»
4. Появится главное меню
5. Нажмите «Написать мне», отправьте тестовое сообщение
6. Откройте **админ-бот** - там должно появиться форматированное сообщение
7. Сделайте **reply** на это сообщение в админ-боте
8. Пользователь получит ответ в основном боте ✅

## Админ-команды и мини-CRM

В админ-боте доступны команды:

```text
/stats              # статистика пользователей, сообщений, активности и очереди
/find <username|id> # профиль пользователя, последние сообщения и статусы диалогов
/mark_seen <id>     # статус обращения: seen
/close <id>         # статус обращения: closed
```

Каждое обращение сохраняется в SQLite в таблице `messages`:

```text
message_id / id
user_id
text
admin_reply
status: new / seen / answered / closed
media_type: text / photo / video / voice / document
created_at
```

Перед отправкой обращения пользователь видит предпросмотр и выбирает:
`Да, отправить`, `Изменить` или `Отмена`.

Поддерживаются текст, фото, видео, голосовые сообщения и документы. Медиа сохраняются с типом и `file_id`, а админ получает отдельное уведомление с Message ID.

---

## Антиспам

Rate limiting работает на уровне middleware до входа в хендлеры. Настройки:

```env
SPAM_LIMIT_SECONDS=10  # минимальный интервал между пользовательскими сообщениями
SPAM_MAX_SCORE=3       # сколько нарушений допускается до временного бана
SPAM_BAN_MINUTES=5     # длительность временного бана
```

Техническая информация хранится в таблице `spam_controls`: `user_id`, `last_message_time`, `spam_score`, `banned_until`.

---

## Редактирование FAQ

Откройте файл `faq_data.py` и отредактируйте список `FAQ`:

```python
FAQ = [
    {
        "id": "faq_1",           # уникальный ID (не меняйте формат)
        "question": "Ваш вопрос здесь?",
        "answer": "Ваш ответ здесь.",
    },
    # добавьте сколько нужно...
]
```

---

## Замена картинки при старте

В файле `handlers/user_start.py` найдите:

```python
WELCOME_IMAGE_URL = "https://telegra.ph/file/d3feec3dd0a831a23c7d6.jpg"
```

Замените на:
- **URL** своей картинки, загруженной в Telegraph или другой хостинг, **или**
- **file_id** из Telegram (получить можно, отправив картинку боту @getidsbot)

---

## Запуск как systemd-сервис (Linux, для production)

```ini
# /etc/systemd/system/tgbot.service
[Unit]
Description=Telegram Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/tgbot
ExecStart=/home/ubuntu/tgbot/venv/bin/python main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable tgbot
sudo systemctl start tgbot
sudo systemctl status tgbot
```

---

## Часто задаваемые вопросы

**Q: Бот не проверяет подписку**
A: Убедитесь, что бот является администратором канала (Шаг 4) и `CHANNEL_ID` указан правильно с минусом.

**Q: Ответ администратора не доходит до пользователя**
A: Проверьте, что вы делаете именно reply (ответ) на сообщение, а не просто пишете текст в бот.

**Q: Ошибка `CHANNEL_ID`**
A: ID канала всегда отрицательный и начинается с `-100`. Например: `-1001234567890`.

**Q: Как добавить нового администратора?**
A: В текущей версии поддерживается один администратор. Для нескольких - измените `_is_admin()` в `admin_handlers.py`.
