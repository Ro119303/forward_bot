import asyncio
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path

import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.filters.command import Command

BOT_TOKEN = os.getenv("BOT_TOKEN")
TARGET_CHAT_ID = int(os.getenv("TARGET_CHAT_ID"))
DB_PATH = Path("data/bot.db")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS forwards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                message_text TEXT,
                timestamp TEXT
            )
        ''')
        await db.commit()

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    await message.answer("Отправь мне сообщение, которое нужно передать")

@dp.message()
async def forward_handler(message: types.Message):
    # Forward
    await bot.forward_message(chat_id=TARGET_CHAT_ID, from_chat_id=message.chat.id, message_id=message.message_id)
    # Save to DB
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO forwards (user_id, username, message_text, timestamp) VALUES (?, ?, ?, ?)',
            (message.from_user.id, message.from_user.username or "unknown", message.text or message.caption or "", datetime.now().isoformat())
        )
        await db.commit()
    await message.answer("Передал, спс")

async def main():
    DB_PATH.parent.mkdir(exist_ok=True)
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
