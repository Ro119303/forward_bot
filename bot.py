

import telebot
from telebot import apihelper
import aiosqlite
import logging
from pathlib import Path
from datetime import datetime
import os
import time
from urllib.parse import urlsplit
from typing import Optional, Dict
from dotenv import load_dotenv
import requests


load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
TARGET_CHAT_ID = int(os.getenv("TARGET_CHAT_ID"))
PROXY_URL = os.getenv("PROXY_URL")
DB_PATH = Path(os.getenv("DB_PATH", "forwards.db"))
STARTUP_CHECK_RETRIES = int(os.getenv("STARTUP_CHECK_RETRIES", "5"))
STARTUP_BACKOFF_SECONDS = float(os.getenv("STARTUP_BACKOFF_SECONDS", "2"))
ALLOW_DIRECT_FALLBACK = os.getenv("ALLOW_DIRECT_FALLBACK", "0") == "1"
PREFER_SOCKS5H = os.getenv("PREFER_SOCKS5H", "1") == "1"

# Network settings for unstable connections/proxies.
apihelper.CONNECT_TIMEOUT = int(os.getenv("CONNECT_TIMEOUT", "30"))
apihelper.READ_TIMEOUT = int(os.getenv("READ_TIMEOUT", "60"))
apihelper.RETRY_ON_ERROR = True
apihelper.RETRY_TIMEOUT = int(os.getenv("RETRY_TIMEOUT", "5"))
apihelper.MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))

def _mask_proxy_url(raw_url: str) -> str:
    if not raw_url:
        return ""
    try:
        parsed = urlsplit(raw_url)
        if parsed.username and parsed.password:
            safe_netloc = f"{parsed.username}:***@{parsed.hostname}:{parsed.port}"
            return f"{parsed.scheme}://{safe_netloc}"
        return raw_url
    except Exception:
        return "<invalid_proxy_url>"


def _validate_proxy_url(raw_url: str) -> None:
    parsed = urlsplit(raw_url)
    if parsed.scheme not in {"socks5", "socks5h"}:
        raise ValueError("PROXY_URL должен начинаться с socks5:// или socks5h://")
    if not parsed.hostname or not parsed.port:
        raise ValueError("В PROXY_URL обязателен host:port")
    if not parsed.username or not parsed.password:
        raise ValueError("В PROXY_URL обязателен user:password")


def _normalize_proxy_url(raw_url: str) -> str:
    # socks5h resolves DNS via proxy and is usually more stable in containers.
    if PREFER_SOCKS5H and raw_url.startswith("socks5://"):
        return "socks5h://" + raw_url[len("socks5://"):]
    return raw_url


def _build_requests_proxies(proxy_url: Optional[str]) -> Optional[Dict[str, str]]:
    if not proxy_url:
        return None
    return {"http": proxy_url, "https": proxy_url}


def _configure_proxy() -> None:
    if PROXY_URL:
        normalized_proxy_url = _normalize_proxy_url(PROXY_URL)
        _validate_proxy_url(normalized_proxy_url)
        apihelper.proxy = {"https": normalized_proxy_url, "http": normalized_proxy_url}
        print(f"🌐 Прокси включен: {_mask_proxy_url(normalized_proxy_url)}")
    else:
        apihelper.proxy = None
        print("🌐 Прокси отключен, прямое подключение")


def _test_proxy_transport() -> None:
    active_proxy = None
    if apihelper.proxy and isinstance(apihelper.proxy, dict):
        active_proxy = apihelper.proxy.get("https") or apihelper.proxy.get("http")
    proxies = _build_requests_proxies(active_proxy)
    response = requests.get(
        "https://api.telegram.org",
        timeout=(apihelper.CONNECT_TIMEOUT, apihelper.READ_TIMEOUT),
        proxies=proxies,
    )
    response.raise_for_status()


def _startup_bot_check() -> telebot.types.User:
    last_err = None
    for attempt in range(1, STARTUP_CHECK_RETRIES + 1):
        try:
            _test_proxy_transport()
            return bot.get_me(timeout=apihelper.READ_TIMEOUT)
        except Exception as err:
            last_err = err
            print(f"⚠️ Попытка {attempt}/{STARTUP_CHECK_RETRIES} не удалась: {err}")
            if attempt < STARTUP_CHECK_RETRIES:
                sleep_seconds = STARTUP_BACKOFF_SECONDS * attempt
                print(f"⏳ Ждем {sleep_seconds:.1f}с и пробуем снова...")
                time.sleep(sleep_seconds)
    raise RuntimeError(f"Стартовая проверка сети не прошла: {last_err}") from last_err


_configure_proxy()

bot = telebot.TeleBot(BOT_TOKEN)

print("🔄 Тест getMe...")
try:
    me = _startup_bot_check()
    print(f"✅ Бот @{me.username} подключился!")
except Exception as e:
    print(f"❌ Ошибка: {e}")
    recovered = False
    if PROXY_URL and ALLOW_DIRECT_FALLBACK:
        print("↪️ Переключаемся на прямое подключение (ALLOW_DIRECT_FALLBACK=1)")
        apihelper.proxy = None
        try:
            me = _startup_bot_check()
            print(f"✅ Бот @{me.username} подключился без прокси!")
            recovered = True
        except Exception as direct_error:
            print(f"❌ Ошибка без прокси: {direct_error}")
    if not recovered:
        print("💡 Проверь PROXY_URL или временно убери его из .env для прямого подключения")
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

        import asyncio
        asyncio.run(save_to_db(message))

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
    bot.infinity_polling(timeout=apihelper.READ_TIMEOUT, long_polling_timeout=30)
