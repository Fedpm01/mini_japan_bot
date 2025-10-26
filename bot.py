#!/usr/bin/env python3
# Mini Japan Telegram Bot — учебная версия
# Requirements:
# pip install aiogram==2.25.1 APScheduler python-dotenv aiohttp

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

# --- Глобальные данные ---
data = {"words": [], "facts": [], "proverbs": []}
jlpt_data = {}
pos_tags = {}

# --- Источники данных ---
CSV_URL = "https://raw.githubusercontent.com/Fedpm01/mini_japan_bot/main/data.csv"
JLPT_PARTS = [
    "https://raw.githubusercontent.com/AnchorI/jlpt-kanji-dictionary/main/dictionary_part_1.json",
    "https://raw.githubusercontent.com/AnchorI/jlpt-kanji-dictionary/main/dictionary_part_2.json",
    "https://raw.githubusercontent.com/AnchorI/jlpt-kanji-dictionary/main/dictionary_part_3.json",
    "https://raw.githubusercontent.com/AnchorI/jlpt-kanji-dictionary/main/dictionary_part_4.json",
]
TAGS_URL = "https://raw.githubusercontent.com/AnchorI/jlpt-kanji-dictionary/main/dictionary-tags.json"

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

# --- Транслитерация в ромадзи ---
HIRAGANA_ROMAJI = {
    "あ": "a", "い": "i", "う": "u", "え": "e", "お": "o",
    "か": "ka", "き": "ki", "く": "ku", "け": "ke", "こ": "ko",
    "さ": "sa", "し": "shi", "す": "su", "せ": "se", "そ": "so",
    "た": "ta", "ち": "chi", "つ": "tsu", "て": "te", "と": "to",
    "な": "na", "に": "ni", "ぬ": "nu", "ね": "ne", "の": "no",
    "は": "ha", "ひ": "hi", "ふ": "fu", "へ": "he", "ほ": "ho",
    "ま": "ma", "み": "mi", "む": "mu", "め": "me", "も": "mo",
    "や": "ya", "ゆ": "yu", "よ": "yo",
    "ら": "ra", "り": "ri", "る": "ru", "れ": "re", "ろ": "ro",
    "わ": "wa", "を": "o", "ん": "n",
    "が": "ga", "ぎ": "gi", "ぐ": "gu", "げ": "ge", "ご": "go",
    "ざ": "za", "じ": "ji", "ず": "zu", "ぜ": "ze", "ぞ": "zo",
    "だ": "da", "ぢ": "ji", "づ": "zu", "で": "de", "ど": "do",
    "ば": "ba", "び": "bi", "ぶ": "bu", "べ": "be", "ぼ": "bo",
    "ぱ": "pa", "ぴ": "pi", "ぷ": "pu", "ぺ": "pe", "ぽ": "po",
    "きゃ": "kya", "きゅ": "kyu", "きょ": "kyo",
    "しゃ": "sha", "しゅ": "shu", "しょ": "sho",
    "ちゃ": "cha", "ちゅ": "chu", "ちょ": "cho",
    "にゃ": "nya", "にゅ": "nyu", "にょ": "nyo",
    "ひゃ": "hya", "ひゅ": "hyu", "ひょ": "hyo",
    "みゃ": "mya", "みゅ": "myu", "みょ": "myo",
    "りゃ": "rya", "りゅ": "ryu", "りょ": "ryo",
}
def to_romaji(kana: str) -> str:
    romaji = kana
    for k, v in HIRAGANA_ROMAJI.items():
        romaji = romaji.replace(k, v)
    return romaji

# --- Загрузка POS-тегов ---
async def load_pos_tags():
    async with aiohttp.ClientSession() as session:
        async with session.get(TAGS_URL) as resp:
            if resp.status == 200:
                return await resp.json()
            print(f"⚠️ Failed to load POS tags ({resp.status})")
            return {}

# --- Загрузка CSV ---
async def load_data_from_github():
    async with aiohttp.ClientSession() as session:
        async with session.get(CSV_URL) as resp:
            if resp.status != 200:
                print(f"⚠️ CSV URL returned {resp.status}: {CSV_URL}")
                return {"words": [], "facts": [], "proverbs": []}
            text = await resp.text()
            reader = csv.DictReader(io.StringIO(text))
            data_map = {"words": [], "facts": [], "proverbs": []}
            for row in reader:
                cat = row.get("category", "").strip().lower()
                if cat == "fact":
                    data_map["facts"].append(row)
                elif cat == "proverb":
                    data_map["proverbs"].append(row)
                else:
                    data_map["words"].append(row)
            return data_map

# --- Загрузка JLPT ---
# --- Загрузка JLPT ---
async def load_jlpt_data():
    grouped = {"N5": [], "N4": [], "N3": [], "N2": [], "N1": []}
    async with aiohttp.ClientSession() as session:
        for url in JLPT_PARTS:
            async with session.get(url) as resp:
                if resp.status == 200:
                    text = await resp.text()  # 🟢 вместо resp.json()
                    try:
                        part = json.loads(text)
                    except json.JSONDecodeError:
                        print(f"⚠️ Ошибка парсинга JSON: {url}")
                        continue

                    for item in part:
                        level = item.get("jlpt", "")
                        if not level:
                            continue
                        level = level.upper()
                        if level in grouped:
                            grouped[level].append({
                                "kanji": item.get("kanji") or item.get("word") or "",
                                "reading": item.get("reading") or "",
                                "pos": item.get("pos") or "",
                                "translation": {
                                    "en": item.get("glossary_en", ""),
                                    "ru": item.get("glossary_ru", ""),
                                },
                            })
                    print(f"✅ Loaded {len(part)} items from {url.split('/')[-1]}")
                else:
                    print(f"⚠️ Ошибка загрузки {url} ({resp.status})")

    print("📊 JLPT totals:", {k: len(v) for k, v in grouped.items()})
    return grouped

# --- Форматирование ---
def format_word(item, lang="ru"):
    trans = item.get(lang, "")
    return f"{item.get('emoji','')} <b>{item.get('ja')}</b> ({item.get('reading')})\n{trans}"

def format_fact(item, lang="ru"):
    return f"{item.get('emoji','')} {item.get(lang,'')}"

def format_proverb(item, lang="ru"):
    trans = item.get(lang, "")
    return f"{item.get('emoji','')} <b>{item.get('ja')}</b> ({item.get('reading')})\n{trans}"

# --- Telegram команды ---
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
        [InlineKeyboardButton(text="Слово дня / Word", callback_data="word"),
         InlineKeyboardButton(text="Факт / Fact", callback_data="fact")],
        [InlineKeyboardButton(text="Пословица / Proverb", callback_data="proverb"),
         InlineKeyboardButton(text="📘 JLPT Vocabulary", callback_data="jlpt")],
        [InlineKeyboardButton(text="Подписка / Subscription", callback_data="toggle_sub")]
    ])
    await call.message.answer("Отлично! 🌸 Я покажу японские слова и факты!", reply_markup=kb)
    await call.answer()

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
    words = jlpt_data.get(level, [])
    if not words:
        await call.message.answer("⏳ JLPT-данные ещё загружаются. Попробуйте через минуту.")
        return

    word = random.choice(words)
    kanji = word.get("kanji", "")
    reading = word.get("reading", "")
    pos = word.get("pos", "")
    en = word.get("translation", {}).get("en", "")
    ru = word.get("translation", {}).get("ru", "")
    romaji = to_romaji(reading)
    pos_full = pos_tags.get(pos, pos)

    text = (
        f"📘 <b>{kanji}</b>（{reading}）\n"
        f"📖 Чтение: {reading} [{romaji}]\n"
        f"🧩 Часть речи: {pos_full}\n"
        f"🇬🇧 {en}\n"
        f"🇷🇺 {ru or '(нет перевода)'}"
    )
    await call.message.answer(text, parse_mode="HTML")
    await call.answer()

# --- Рассылка и обновление ---
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

async def refresh_data():
    global data
    print("🔄 Refreshing data from GitHub...")
    data = await load_data_from_github()
    print("✅ Data updated!")

def setup_scheduler():
    scheduler.add_job(lambda: asyncio.create_task(daily_broadcast(bot)), "cron", hour=9)
    scheduler.add_job(lambda: asyncio.create_task(refresh_data()), "cron", hour=6)
    scheduler.start()
    print("✅ Scheduler started!")

# --- Главная функция ---
async def main():
    global data, jlpt_data, pos_tags
    print("🚀 Bot starting...")
    data = await load_data_from_github()
    jlpt_data = await load_jlpt_data()
    pos_tags = await load_pos_tags()
    print("✅ POS tags loaded!")
    print(f"✅ CSV: {len(data['words'])} words, {len(data['facts'])} facts, {len(data['proverbs'])} proverbs")
    setup_scheduler()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())




