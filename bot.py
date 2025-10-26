#!/usr/bin/env python3
# Mini Japan Telegram Bot (template)
# Requirements: aiogram, APScheduler, python-dotenv
# pip install aiogram==2.25.1 APScheduler python-dotenv

#!/usr/bin/env python3
# Mini Japan Telegram Bot (updated)
# Requirements: aiogram (v3), aiohttp, APScheduler, python-dotenv

import asyncio
import os
import json
import random
import logging
import aiohttp
import csv
import io

from aiogram import Bot, Dispatcher, F
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
SUBS_PATH = os.path.join(os.path.dirname(__file__), "subscribers.json")

# --- Глобальные переменные ---
data = {"words": [], "facts": [], "proverbs": []}
jlpt_data = {"N5": [], "N4": [], "N3": [], "N2": [], "N1": []}

# --- URL для загрузки (проверь, что файлы действительно есть в этих местах) ---
CSV_URL = "https://raw.githubusercontent.com/Fedpm01/mini_japan_bot/main/data.csv"
JLPT_FILES = [
    "https://raw.githubusercontent.com/AnchorI/jlpt-kanji-dictionary/main/dictionary_part_1.json",
    "https://raw.githubusercontent.com/AnchorI/jlpt-kanji-dictionary/main/dictionary_part_2.json",
    "https://raw.githubusercontent.com/AnchorI/jlpt-kanji-dictionary/main/dictionary_part_3.json",
    "https://raw.githubusercontent.com/AnchorI/jlpt-kanji-dictionary/main/dictionary_part_4.json",
]

# --- Работа с подписками ---
def load_subs():
    try:
        with open(SUBS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_subs(d):
    with open(SUBS_PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

# --- Загрузка JLPT (с частями) ---
async def load_jlpt_data():
    grouped = {"N5": [], "N4": [], "N3": [], "N2": [], "N1": []}
    async with aiohttp.ClientSession() as session:
        for url in JLPT_FILES:
            try:
                async with session.get(url, timeout=30) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        try:
                            part = json.loads(text)
                        except json.JSONDecodeError:
                            print(f"⚠️ Ошибка парсинга JSON из {url}")
                            continue

                        # Внутри part — список слов; у каждого есть поле "jlpt"
                        for item in part:
                            # пробуем несколько вариантов поля уровня
                            level = (
                                str(item.get("jlpt") or item.get("jlpt_level") or item.get("level") or "")
                                .upper()
                                .replace("JLPT", "")
                            )
                            if level in grouped:
                                grouped[level].append({
                                    "kanji": item.get("kanji") or item.get("word") or "",
                                    "reading": item.get("reading") or item.get("kana") or "",
                                    "translation": {
                                        "en": item.get("meaning") or item.get("english") or "",
                                        "ru": item.get("meaning_ru") or item.get("russian") or "",
                                    },
                                })

                        print(f"✅ Loaded {len(part)} items from {url.split('/')[-1]}")
                    else:
                        print(f"⚠️ {url} returned {resp.status}")
            except Exception as e:
                print(f"⚠️ Exception while loading {url}: {e}")
    print("📊 JLPT totals:", {k: len(v) for k, v in grouped.items()})
    return grouped

# --- Загрузка CSV контента из GitHub ---
async def load_data_from_github():
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(CSV_URL, timeout=30) as resp:
                if resp.status != 200:
                    print(f"⚠️ CSV URL returned {resp.status}: {CSV_URL}")
                    return {"words": [], "facts": [], "proverbs": []}
                text = await resp.text()
                reader = csv.DictReader(io.StringIO(text))
                data_map = {"words": [], "facts": [], "proverbs": []}
                for row in reader:
                    cat = (row.get("category") or "").strip().lower()
                    if cat == "fact":
                        data_map["facts"].append(row)
                    elif cat == "proverb":
                        data_map["proverbs"].append(row)
                    else:
                        data_map["words"].append(row)
                return data_map
        except Exception as e:
            print("⚠️ Exception while loading CSV:", e)
            return {"words": [], "facts": [], "proverbs": []}

# --- Форматирование сообщений ---
def format_word(item, lang="ru"):
    # handle both CSV row format and JLPT item format
    if "translation" in item:
        # JLPT item
        emoji = "📘"
        ja = item.get("kanji","")
        reading = item.get("reading","")
        trans = item["translation"].get(lang, "") if isinstance(item.get("translation"), dict) else item.get(lang,"")
        return f"{emoji} <b>{ja}</b> ({reading})\n{trans}"
    else:
        # CSV row
        trans = item.get(lang, "")
        return f"{item.get('emoji','')} <b>{item.get('ja','')}</b> ({item.get('reading','')})\n{trans}"

def format_fact(item, lang="ru"):
    return f"{item.get('emoji','')} {item.get(lang,'')}"

def format_proverb(item, lang="ru"):
    return f"{item.get('emoji','')} {item.get(lang,'')}"

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
        [InlineKeyboardButton(text="Слово дня / Word of the day", callback_data="daily"),
         InlineKeyboardButton(text="Факт / Fact", callback_data="fact")],
        [InlineKeyboardButton(text="Пословица / Proverb", callback_data="proverb"),
         InlineKeyboardButton(text="📘 JLPT Vocabulary", callback_data="jlpt")],
        [InlineKeyboardButton(text="Подписка / Subscription", callback_data="toggle_sub")]
    ])
    await call.message.answer("Отлично! 🌸 Я покажу японские слова и факты!", reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data.in_({"word", "fact", "proverb", "toggle_sub"}))
async def inline_actions(call: CallbackQuery):
    user_id = str(call.from_user.id)
    subs = load_subs()
    user_lang = subs.get(user_id, {}).get("lang", "ru")

    if call.data == "word":
        if not data["words"]:
            await call.message.answer("⏳ Данные пока не загружены. Попробуйте чуть позже.")
            await call.answer()
            return
        item = random.choice(data["words"])
        await call.message.answer(format_word(item, lang=user_lang), parse_mode="HTML")

    elif call.data == "fact":
        if not data["facts"]:
            await call.message.answer("⏳ Факты пока не загружены.")
            await call.answer()
            return
        item = random.choice(data["facts"])
        await call.message.answer(format_fact(item, lang=user_lang))

    elif call.data == "proverb":
        if not data["proverbs"]:
            await call.message.answer("⏳ Пословицы пока не загружены.")
            await call.answer()
            return
        item = random.choice(data["proverbs"])
        await call.message.answer(format_proverb(item, lang=user_lang), parse_mode="HTML")

    elif call.data == "toggle_sub":
        cur = subs.get(user_id, {"lang": user_lang, "subscribed": False}).get("subscribed", False)
        subs[user_id] = {"lang": user_lang, "subscribed": not cur}
        save_subs(subs)
        await call.message.answer("Подписка обновлена: " + ("✅ Включена" if not cur else "❌ Выключена"))
    await call.answer()

# --- JLPT меню ---
@dp.callback_query(F.data == "jlpt")
async def choose_jlpt_level(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="N5", callback_data="jlpt_N5"),
         InlineKeyboardButton(text="N4", callback_data="jlpt_N4")],
        [InlineKeyboardButton(text="N3", callback_data="jlpt_N3"),
         InlineKeyboardButton(text="N2", callback_data="jlpt_N2")],
        [InlineKeyboardButton(text="N1", callback_data="jlpt_N1")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")]
    ])
    await call.message.answer("Выберите уровень JLPT:", reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data.startswith("jlpt_N"))
async def send_jlpt_word(call: CallbackQuery):
    level = call.data.split("_")[1]
    # guard: jlpt_data may be empty while loading
    if not any(len(v) for v in jlpt_data.values()):
        await call.message.answer("⏳ JLPT-данные ещё загружаются. Попробуйте через минуту.")
        await call.answer()
        return

    words = jlpt_data.get(level, [])
    if not words:
        await call.message.answer(f"⚠️ Нет данных для уровня {level}.")
        await call.answer()
        return

    word = random.choice(words)
    ja = word.get("kanji") or ""
    reading = word.get("reading") or ""
    en = word.get("translation", {}).get("en", "")
    ru = word.get("translation", {}).get("ru", "")
    emoji = "📘"

    text = f"{emoji} <b>{ja}</b> ({reading})\n🇬🇧 {en}\n🇷🇺 {ru}"
    await call.message.answer(text, parse_mode="HTML")
    await call.answer()

# --- Ежедневная рассылка ---
async def daily_broadcast(bot: Bot):
    subs = load_subs()
    for uid, info in subs.items():
        if info.get("subscribed"):
            lang = info.get("lang", "ru")
            if not data["words"]:
                continue
            item = random.choice(data["words"])
            try:
                await bot.send_message(int(uid), format_word(item, lang=lang), parse_mode="HTML")
            except Exception as e:
                print("Send failed to", uid, e)

# --- Обновление данных раз в сутки ---
async def refresh_data():
    global data
    print("🔄 Refreshing data from GitHub...")
    data = await load_data_from_github()
    print("✅ Data updated!")

# --- Планировщик ---
def setup_scheduler():
    scheduler.add_job(lambda: asyncio.create_task(daily_broadcast(bot)), "cron", hour=9, minute=0)
    scheduler.add_job(lambda: asyncio.create_task(refresh_data()), "cron", hour=6)
    scheduler.start()
    print("✅ Scheduler started!")

# --- Основная функция ---
async def main():
    global data, jlpt_data
    print("🚀 Bot starting...")

    # Загрузка CSV и JLPT (делаем параллельно)
    try:
        data_task = asyncio.create_task(load_data_from_github())
        jlpt_task = asyncio.create_task(load_jlpt_data())
        data = await data_task
        jlpt_data = await jlpt_task
    except Exception as e:
        print("⚠️ Error during initial load:", e)

    print(f"📊 JLPT totals: { {k: len(v) for k, v in jlpt_data.items()} }")
    print(f"✅ CSV: {len(data.get('words',[]))} words, {len(data.get('facts',[]))} facts, {len(data.get('proverbs',[]))} proverbs")

    setup_scheduler()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())



