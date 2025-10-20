#!/usr/bin/env python3
# Mini Japan Telegram Bot (template)
# Requirements: aiogram, APScheduler, python-dotenv
# pip install aiogram==2.25.1 APScheduler python-dotenv

import asyncio
import os
import json
import random
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

# --- Инициализация окружения ---
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    print("❌ ERROR: Set TELEGRAM_TOKEN in .env file")
    exit(1)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# --- Пути к файлам ---
DATA_PATH = os.path.join(os.path.dirname(__file__), "data.json")
SUBS_PATH = os.path.join(os.path.dirname(__file__), "subscribers.json")

# --- Загрузка контента ---
with open(DATA_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

def load_subs():
    try:
        with open(SUBS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_subs(d):
    with open(SUBS_PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

# --- Форматирование сообщений ---
def format_word(item, lang="ru"):
    trans = item.get(lang, "")
    return f"{item.get('emoji','')} <b>{item.get('ja')}</b> ({item.get('reading')})\n{trans}"

def format_fact(item, lang="ru"):
    return f"{item.get('emoji','')} {item.get(lang,'')}"

def format_proverb(item, lang="ru"):
    trans = item.get(lang, "")
    return f"{item.get('emoji','')} <b>{item.get('ja')}</b> ({item.get('reading')})\n{trans}"

# --- Команды ---
@dp.message(Command("start"))
async def cmd_start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Русский 🇷🇺", callback_data="lang_ru"),
         InlineKeyboardButton(text="English 🇺🇸", callback_data="lang_en")]
    ])
    await message.answer("Konnichiwa! 👋\nВыберите язык / Choose language:", reply_markup=kb)

@dp.callback_query(F.data.startswith("lang_"))
async def process_lang(call: CallbackQuery):
    lang = call.data.split("_", 1)[1]
    user_id = str(call.from_user.id)
    subs = load_subs()
    subs[user_id] = {"lang": lang, "subscribed": False}
    save_subs(subs)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Слово дня / Word of the day", callback_data="word"),
         InlineKeyboardButton(text="Факт / Fact", callback_data="fact")],
        [InlineKeyboardButton(text="Пословица / Proverb", callback_data="proverb"),
         InlineKeyboardButton(text="Подписка / Subscription", callback_data="toggle_sub")]
    ])
    await call.message.answer("Отлично! 🌸 Я покажу японские слова и факты!", reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data.in_({"word", "fact", "proverb", "toggle_sub"}))
async def inline_actions(call: CallbackQuery):
    user_id = str(call.from_user.id)
    subs = load_subs()
    user_lang = subs.get(user_id, {}).get("lang", "ru")

    if call.data == "word":
        item = random.choice(data["words"])
        await call.message.answer(format_word(item, lang=user_lang), parse_mode="HTML")

    elif call.data == "fact":
        item = random.choice(data["facts"])
        await call.message.answer(format_fact(item, lang=user_lang))

    elif call.data == "proverb":
        item = random.choice(data["proverbs"])
        await call.message.answer(format_proverb(item, lang=user_lang), parse_mode="HTML")

    elif call.data == "toggle_sub":
        cur = subs.get(user_id, {"lang": user_lang, "subscribed": False}).get("subscribed", False)
        subs[user_id] = {"lang": user_lang, "subscribed": not cur}
        save_subs(subs)
        await call.message.answer("Подписка обновлена: " + ("✅ Включена" if not cur else "❌ Выключена"))

    await call.answer()

# --- Ежедневная рассылка ---
async def daily_broadcast(bot: Bot):
    subs = load_subs()
    for uid, info in subs.items():
        if info.get("subscribed"):
            lang = info.get("lang", "ru")
            item = random.choice(data["words"])
            try:
                await bot.send_message(int(uid), format_word(item, lang=lang), parse_mode="HTML")
            except Exception as e:
                print("Send failed to", uid, e)

# --- Планировщик ---
def setup_scheduler():
    scheduler.add_job(lambda: asyncio.create_task(daily_broadcast(bot)), "cron", hour=9, minute=0)
    scheduler.start()
    print("✅ Scheduler started!")

# --- Основная функция ---
async def main():
    print("🚀 Bot started...")
    setup_scheduler()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())


