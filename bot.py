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

KANJI_URL = "https://raw.githubusercontent.com/AnchorI/jlpt-kanji-dictionary/main/jlpt-kanji.json"
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
    # Заменяем более длинные ключи первыми, чтобы 'きゃ' не превратилось в 'ki'+'ya'
    romaji = kana
    # Сортируем ключи по длине убыванию
    for k in sorted(HIRAGANA_ROMAJI.keys(), key=lambda x: -len(x)):
        romaji = romaji.replace(k, HIRAGANA_ROMAJI[k])
    return romaji

# --- DeepL переводчик ---
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY")

# --- DeepL переводчик с простым in-memory кэшем ---
_translation_cache = {}

async def deepl_translate(text: str, target_lang: str = "RU") -> str:
    """Переводит текст через DeepL API (если ключ есть). Возвращает пустую строку при ошибке."""
    if not text or not DEEPL_API_KEY:
        return ""
    key = (text, target_lang)
    if key in _translation_cache:
        return _translation_cache[key]

    url = "https://api-free.deepl.com/v2/translate"
    params = {
        "auth_key": DEEPL_API_KEY,
        "text": text,
        "target_lang": target_lang,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=params, timeout=10) as resp:
                if resp.status != 200:
                    print("⚠️ DeepL returned status", resp.status)
                    return ""
                data = await resp.json()
                if "translations" in data and len(data["translations"]) > 0:
                    out = data["translations"][0]["text"]
                    _translation_cache[key] = out
                    return out
    except Exception as e:
        print("⚠️ DeepL translation error:", e)
    return ""




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

# --- Загрузка JLPT (с автопереводом через DeepL) ---
async def load_jlpt_data():
    grouped = {"N5": [], "N4": [], "N3": [], "N2": [], "N1": []}
    async with aiohttp.ClientSession() as session:
        for url in JLPT_PARTS:
            async with session.get(url) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    try:
                        part = json.loads(text)
                    except json.JSONDecodeError:
                        print(f"⚠️ Ошибка парсинга {url}")
                        continue

                    for item in part:
                        level = str(item.get("jlpt") or "").upper()
                        if not level or level not in grouped:
                            continue

                        # English meaning
                        en_val = item.get("glossary_en") or item.get("glossary") or ""
                        if isinstance(en_val, list):
                            en_text = "; ".join(str(x) for x in en_val)
                        else:
                            en_text = str(en_val)

                        # Russian if present
                        ru_val = item.get("glossary_ru", "")
                        if isinstance(ru_val, list):
                            ru_text = "; ".join(str(x) for x in ru_val)
                        else:
                            ru_text = str(ru_val or "")

                        # if no ru — translate
                        if not ru_text.strip() and en_text.strip():
                            ru_text = await deepl_translate(en_text)

                        grouped[level].append({
                            "kanji": item.get("kanji") or item.get("word") or "",
                            "reading": item.get("reading") or item.get("kana") or "",
                            "translation": {"en": en_text, "ru": ru_text},
                            "pos": item.get("pos", ""),
                            "strokes": item.get("strokes", "—"),
                            "frequency": item.get("frequency", "—")
                        })
                    print(f"✅ Loaded {len(part)} items from {url.split('/')[-1]}")
                else:
                    print(f"⚠️ Failed to load {url} ({resp.status})")

        # kanji file
        async with session.get(KANJI_URL) as resp:
            if resp.status == 200:
                text = await resp.text()
                try:
                    kanji_data = json.loads(text)
                    for item in kanji_data:
                        level = str(item.get("jlpt") or "").upper()
                        if level in grouped:
                            en_desc = item.get("description", "")
                            ru_desc = await deepl_translate(en_desc) if en_desc else ""
                            grouped[level].append({
                                "kanji": item.get("kanji"),
                                "reading": item.get("reading", "") or "",
                                "translation": {"en": en_desc, "ru": ru_desc},
                                "strokes": item.get("strokes", "—"),
                                "frequency": item.get("frequency", "—")
                            })
                    print(f"✅ Loaded {len(kanji_data)} kanji from jlpt-kanji.json")
                except json.JSONDecodeError:
                    print("⚠️ Ошибка парсинга jlpt-kanji.json")

    print("📊 JLPT totals:", {k: len(v) for k, v in grouped.items()})
    return grouped



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
        [InlineKeyboardButton(text="Слово / Word", callback_data="daily"),
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

# --- Учебные карточки JLPT ---
@dp.callback_query(F.data.startswith("jlpt_N"))
async def send_jlpt_word(call: CallbackQuery):
    level = call.data.split("_")[1]
    words = jlpt_data.get(level, [])
    if not words:
        await call.message.answer("⏳ JLPT-данные ещё загружаются. Попробуйте через минуту.")
        return
    await send_formatted_jlpt_card(call, level)

@dp.callback_query(F.data.startswith("next_"))
async def next_jlpt_word(call: CallbackQuery):
    level = call.data.split("_")[1]
    await send_formatted_jlpt_card(call, level, edit=True)

async def send_formatted_jlpt_card(call: CallbackQuery, level: str, edit: bool = False):
    words = jlpt_data.get(level, [])
    if not words:
        await call.message.answer(f"⚠️ Нет данных для уровня {level}.")
        return

    word = random.choice(words)
    kanji = word.get("kanji", "—")
    reading = word.get("reading", "—")
    romaji = to_romaji(reading)
    en = word.get("translation", {}).get("en", "—")
    ru = word.get("translation", {}).get("ru", "(нет перевода)")
    strokes = word.get("strokes", "—")
    freq = word.get("frequency", "—")
    pos_code = word.get("pos", "") or ""
    pos_full = pos_tags.get(pos_code, pos_code) if pos_tags else pos_code


    examples = [
        {"ja": f"{kanji}が好きです。", "ru": f"Мне нравится {kanji}.", "en": f"I like {kanji}."},
        {"ja": f"{kanji}を勉強しています。", "ru": f"Я изучаю {kanji}.", "en": f"I’m studying {kanji}."},
        {"ja": f"{kanji}は難しいですが、面白いです。", "ru": f"{kanji} сложный, но интересный.", "en": f"{kanji} is difficult but interesting."}
    ]
    example = random.choice(examples)

    text = (
        f"📘 <b>{kanji}</b>（{reading}）\n"
        f"📖 <b>Чтение:</b> {reading} [{romaji}]\n"
        f"🈶 <b>Уровень JLPT:</b> {level}\n"
        f"✍️ <b>Количество черт:</b> {strokes}\n"
        f"📊 <b>Частотность:</b> {freq}\n\n"
        f"🧩 <b>Часть речи:</b> {pos_full}\n"
        f"🇬🇧 {en}\n"
        f"🇷🇺 {ru}\n\n"
        f"📚 <b>Пример:</b>\n"
        f"🇯🇵 {example['ja']}\n"
        f"🇷🇺 {example['ru']}\n"
        f"🇬🇧 {example['en']}\n\n"
        f"🌸 <i>Совет:</i> Используй {kanji} в своём следующем предложении!"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Следующее слово", callback_data=f"next_{level}")],
        [InlineKeyboardButton(text="⬅️ Назад к уровням", callback_data="jlpt")]
    ])

    if edit:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await call.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await call.answer()

# --- Ежедневная рассылка ---
async def daily_broadcast(bot):
    subs = load_subs()
    for uid, info in subs.items():
        if info.get("subscribed"):
            lang = info.get("lang", "ru")
            item = random.choice(data["words"]) if data["words"] else None
            if not item:
                continue
            try:
                await bot.send_message(int(uid), f"{item.get('emoji','')} {item.get(lang,'')}", parse_mode="HTML")
            except Exception as e:
                print("Send failed to", uid, e)

async def refresh_data():
    global data
    print("🔄 Refreshing data from GitHub...")
    data = await load_data_from_github()
    print("✅ Data updated!")

def setup_scheduler():
    # Для AsyncIOScheduler можно передать coroutine в add_job — он выполнится в loop
    # Запускаем ежедневную рассылку и обновление данных
    scheduler.add_job(daily_broadcast, "cron", hour=9, args=[bot], id="daily_broadcast")
    scheduler.add_job(refresh_data, "cron", hour=6, id="refresh_data")
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




