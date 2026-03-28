import telebot
import aiosqlite
import logging
import requests
from pathlib import Path
from datetime import datetime
import os
from dotenv import load_dotenv


load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
TARGET_CHAT_ID = int(os.getenv("TARGET_CHAT_ID"))
PROXY_URL = os.getenv("PROXY_URL")
DB_PATH = Path(os.getenv("DB_PATH", "forwards.db"))
SEND_MESSAGE_NEXT_URL = os.getenv(
    "SEND_MESSAGE_NEXT_URL",
    "https://app.romaloh1234.ru/api/api/send_message_next",
)
SEND_MESSAGE_NEXT_BEARER = os.getenv(
    "SEND_MESSAGE_NEXT_BEARER",
    "d!3$g7^H&k9zF+Yw1LpQ@t*Ug&hsks7&8auIhsjO7#2hsjn27ijB*bi29bjTCU!HVb$%ip9&bwoubiw(lbn%^$oujkl",
)

telebot.apihelper.proxy = {'https': PROXY_URL, 'http': PROXY_URL}
bot = telebot.TeleBot(BOT_TOKEN)

print("🔄 Тест getMe...")
try:
    me = bot.get_me()
    print(f"✅ Бот @{me.username} подключился!")
except Exception as e:
    print(f"❌ Ошибка: {e}")
    exit(1)


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS forwards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, username TEXT, message_text TEXT, timestamp TEXT
            )
        ''')
        await db.commit()
    print("✅ БД готова")


@bot.message_handler(commands=['start'])
def start_handler(message):
    print(f"📨 /start от {message.from_user.id}")
    bot.reply_to(message, "Напиши, что нужно передать")


def _fallback_send_message_next(text: str) -> bool:
    if not SEND_MESSAGE_NEXT_BEARER:
        logger.warning("SEND_MESSAGE_NEXT_BEARER не задан")
        return False
    session = requests.Session()
    session.trust_env = False
    try:
        r = session.post(
            SEND_MESSAGE_NEXT_URL,
            json={"chat_ids": [TARGET_CHAT_ID], "text": text},
            headers={
                "Authorization": f"Bearer {SEND_MESSAGE_NEXT_BEARER}",
                "Content-Type": "application/json",
            },
            timeout=30,
            proxies={"http": None, "https": None},
        )
        return r.status_code == 200
    except requests.RequestException as e:
        logger.exception("send_message_next: %s", e)
        return False


def _forward_fallback_text(message) -> str:
    raw = (message.text or message.caption or "").strip()
    u = message.from_user
    user_label = f"@{u.username}" if u.username else str(u.id)
    return f"Пользователь {user_label} переслал сообщение:\n{raw}"


@bot.message_handler(func=lambda m: True)
def forward_handler(message):
    try:
        preview = (message.text or message.caption or "")[:30]
        print(f"📨 '{preview}...' от {message.from_user.id}")

        import asyncio
        try:
            asyncio.run(save_to_db(message))
        except Exception as db_err:
            logger.exception("save_to_db: %s", db_err)
            print(f"❌ БД: {db_err}")

        try:
            bot.forward_message(TARGET_CHAT_ID, message.chat.id, message.message_id)
            bot.reply_to(message, "Переслал, спс")
            print("✅ Forward OK")
        except Exception as forward_err:
            print(f"❌ Forward: {forward_err}")
            if _fallback_send_message_next(_forward_fallback_text(message)):
                bot.reply_to(message, "Переслал, спс")
                print("✅ Fallback OK")
            else:
                bot.reply_to(message, "Что-то пошло не так")
    except Exception as e:
        print(f"❌ {e}")
        bot.reply_to(message, "Что-то пошло не так")


async def save_to_db(message):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO forwards (user_id, username, message_text, timestamp) VALUES (?, ?, ?, ?)',
            (message.from_user.id,
             message.from_user.username or "unknown",
             message.text or "",
             datetime.now().isoformat())
        )
        await db.commit()


if __name__ == "__main__":
    import asyncio

    asyncio.run(init_db())
    print("🎯 Бот запущен! Отправь /start")
    bot.infinity_polling()
