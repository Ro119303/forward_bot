#!/usr/bin/env python3
"""
Spra3dnikom_bot + SOCKS5 (100% работает)
"""

import telebot
import aiosqlite
import logging
from pathlib import Path
from datetime import datetime
import os
from dotenv import load_dotenv


# Загружаем .env
load_dotenv()

# ЛОГИ
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# НАСТРОЙКИ из .env
BOT_TOKEN = os.getenv("BOT_TOKEN")
TARGET_CHAT_ID = int(os.getenv("TARGET_CHAT_ID"))
PROXY_URL = os.getenv("PROXY_URL")
DB_PATH = Path(os.getenv("DB_PATH", "forwards.db"))

# SOCKS5 для telebot
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


@bot.message_handler(func=lambda m: True)
def forward_handler(message):
    try:
        print(f"📨 '{message.text[:30]}...' от {message.from_user.id}")

        # 1. Сначала запись в БД
        import asyncio
        asyncio.run(save_to_db(message))

        # 2. Только после успешной записи пересылаем
        bot.forward_message(TARGET_CHAT_ID, message.chat.id, message.message_id)

        bot.reply_to(message, "Переслал, спс")
        print("✅ Forward OK")
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
