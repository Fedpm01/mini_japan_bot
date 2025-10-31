#!/usr/bin/env python3
# bot_fixed.py — Mini Japan Telegram Bot (aiogram v2.25.1)
# pip install aiogram==2.25.1 APScheduler python-dotenv aiohttp

import asyncio
import os
import json
import random
import logging
import aiohttp
import csv
import io
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY")

if not TELEGRAM_TOKEN:
    print("❌ Set TELEGRAM_TOKEN in .env")
    raise SystemExit(1)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)
scheduler = AsyncIOScheduler()

# --- Paths & constants ---
BASE_DIR = os.path.dirname(__file__)
SUBS_PATH = os.path.join(BASE_DIR, "subscribers.json")
CACHE_PATH = os.path.join(BASE_DIR, "translation_cache.json")
KANJI_READINGS_PATH = os.path.join(BASE_DIR, "kanji_readings.json")

CSV_URL = "https://raw.githubusercontent.com/Fedpm01/mini_japan_bot/main/data.csv"
JLPT_PARTS = [
    "https://raw.githubusercontent.com/AnchorI/jlpt-kanji-dictionary/main/dictionary_part_1.json",
    "https://raw.githubusercontent.com/AnchorI/jlpt-kanji-dictionary/main/dictionary_part_2.json",
    "https://raw.githubusercontent.com/AnchorI/jlpt-kanji-dictionary/main/dictionary_part_3.json",
    "https://raw.githubusercontent.com/AnchorI/jlpt-kanji-dictionary/main/dictionary_part_4.json",
]
KANJI_URL = "https://raw.githubusercontent.com/AnchorI/jlpt-kanji-dictionary/main/jlpt-kanji.json"
TAGS_URL = "https://raw.githubusercontent.com/AnchorI/jlpt-kanji-dictionary/main/dictionary-tags.json"

# --- Globals ---
data = {"words": [], "facts": [], "proverbs": []}
jlpt_data = {"N5": [], "N4": [], "N3": [], "N2": [], "N1": []}
pos_tags = {}
kanji_readings = {}
translation_cache = {}

# --- Helpers: file subs/cache ---
def load_json_safe(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        print("⚠️ load_json_safe error:", e)
        return {}

def save_json_safe(path, obj):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("⚠️ save_json_safe error:", e)

def load_subs():
    return load_json_safe(SUBS_PATH)

def save_subs(d):
    save_json_safe(SUBS_PATH, d)

# --- Romaji helper (simple) ---
HIRAGANA_ROMAJI = {
    "きゃ":"kya","きゅ":"kyu","きょ":"kyo",
    "しゃ":"sha","しゅ":"shu","しょ":"sho",
    "ちゃ":"cha","ちゅ":"chu","ちょ":"cho",
    "にゃ":"nya","にゅ":"nyu","にょ":"nyo",
    "ひゃ":"hya","ひゅ":"hyu","ひょ":"hyo",
    "みゃ":"mya","みゅ":"myu","みょ":"myo",
    "りゃ":"rya","りゅ":"ryu","りょ":"ryo",
    "あ":"a","い":"i","う":"u","え":"e","お":"o",
    "か":"ka","き":"ki","く":"ku","け":"ke","こ":"ko",
    "さ":"sa","し":"shi","す":"su","せ":"se","そ":"so",
    "た":"ta","ち":"chi","つ":"tsu","て":"te","と":"to",
    "な":"na","に":"ni","ぬ":"nu","ね":"ne","の":"no",
    "は":"ha","ひ":"hi","ふ":"fu","へ":"he","ほ":"ho",
    "ま":"ma","み":"mi","む":"mu","め":"me","も":"mo",
    "や":"ya","ゆ":"yu","よ":"yo",
    "ら":"ra","り":"ri","る":"ru","れ":"re","ろ":"ro",
    "わ":"wa","を":"o","ん":"n",
    "が":"ga","ぎ":"gi","ぐ":"gu","げ":"ge","ご":"go",
    "ざ":"za","じ":"ji","ず":"zu","ぜ":"ze","ぞ":"zo",
    "だ":"da","ぢ":"ji","づ":"zu","で":"de","ど":"do",
    "ば":"ba","び":"bi","ぶ":"bu","べ":"be","ぼ":"bo",
    "ぱ":"pa","ぴ":"pi","ぷ":"pu","ぺ":"pe","ぽ":"po",
}
def to_romaji(kana: str) -> str:
    if not kana:
        return ""
    romaji = kana
    # replace longer keys first
    for k in sorted(HIRAGANA_ROMAJI.keys(), key=lambda x: -len(x)):
        romaji = romaji.replace(k, HIRAGANA_ROMAJI[k])
    return romaji

# --- DeepL translate with cache ---
def load_translation_cache():
    global translation_cache
    translation_cache = load_json_safe(CACHE_PATH)
load_translation_cache()

async def deepL_translate_once(text: str, target="RU"):
    """Call DeepL (free) and cache result; returns empty string on failure."""
    if not text:
        return ""
    if text in translation_cache:
        return translation_cache[text]
    if not DEEPL_API_KEY:
        # no key: return empty and don't cache
        return ""
    url = "https://api-free.deepl.com/v2/translate"
    data_payload = {"auth_key": DEEPL_API_KEY, "text": text, "target_lang": target}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data_payload, timeout=30) as resp:
                if resp.status != 200:
                    print("⚠️ DeepL status", resp.status)
                    return ""
                resp_json = await resp.json()
                translated = resp_json.get("translations", [{}])[0].get("text", "")
                if translated:
                    translation_cache[text] = translated
                    save_json_safe(CACHE_PATH, translation_cache)
                return translated
    except Exception as e:
        print("⚠️ DeepL error:", e)
        return ""

# --- Load kanji readings from local file if present ---
def load_kanji_readings():
    global kanji_readings
    if os.path.exists(KANJI_READINGS_PATH):
        try:
            kanji_readings = load_json_safe(KANJI_READINGS_PATH)
            print("✅ Loaded kanji_readings:", len(kanji_readings))
        except Exception as e:
            print("⚠️ Failed to load kanji_readings:", e)
            kanji_readings = {}
    else:
        print("⚠️ kanji_readings.json not found; readings will be filled from JLPT JSON only (if present).")
        kanji_readings = {}

# --- Load POS tags (dictionary-tags.json) ---
async def load_pos_tags():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(TAGS_URL) as resp:
                if resp.status == 200:
                    return await resp.json()
                print("⚠️ POS tags load failed:", resp.status)
    except Exception as e:
        print("⚠️ POS tags exception:", e)
    return {}

# --- Load CSV from GitHub ---
async def load_csv_from_github():
    print("📥 Loading CSV from GitHub:", CSV_URL)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(CSV_URL, timeout=30) as resp:
                if resp.status != 200:
                    print("⚠️ CSV URL returned", resp.status)
                    return {"words": [], "facts": [], "proverbs": []}
                txt = await resp.text()
    except Exception as e:
        print("⚠️ CSV fetch error:", e)
        return {"words": [], "facts": [], "proverbs": []}

    reader = csv.DictReader(io.StringIO(txt))
    buckets = {"words": [], "facts": [], "proverbs": []}
    seen = set()
    for row in reader:
        # normalize keys: word, reading, en, ru, category, emoji
        word = (row.get("word") or row.get("ja") or "").strip()
        if not word:
            continue
        key = (word, (row.get("reading") or "").strip())
        if key in seen:
            continue
        seen.add(key)
        cat = (row.get("category") or "").strip().lower()
        item = {
            "ja": word,
            "reading": row.get("reading") or "",
            "en": (row.get("en") or "").strip(),
            "ru": (row.get("ru") or "").strip(),
            "emoji": (row.get("emoji") or "").strip(),
            "category": cat
        }
        if cat == "fact":
            buckets["facts"].append(item)
        elif cat == "proverb":
            buckets["proverbs"].append(item)
        else:
            buckets["words"].append(item)
    return buckets

# --- Load JLPT parts and kanji, translate missing ru via DeepL at startup ---
async def load_jlpt_and_translate():
    print("📚 Loading JLPT parts (this may take a while if translations needed)...")
    grouped = {"N5": [], "N4": [], "N3": [], "N2": [], "N1": []}
    async with aiohttp.ClientSession() as session:
        for url in JLPT_PARTS:
            try:
                async with session.get(url, timeout=60) as resp:
                    if resp.status != 200:
                        print("⚠️ JLPT part fetch failed:", url, resp.status)
                        continue
                    text = await resp.text()
            except Exception as e:
                print("⚠️ JLPT fetch exception:", e)
                continue

            try:
                part = json.loads(text)
            except Exception:
                print("⚠️ Can't parse JLPT part", url)
                continue

            for item in part:
                level = str(item.get("jlpt") or "").upper()
                if not level or level not in grouped:
                    continue
                # english gloss may be list or field names differ
                en_val = item.get("glossary_en") or item.get("glossary") or item.get("meaning") or item.get("meaning_en") or ""
                if isinstance(en_val, list):
                    en_text = "; ".join(map(str, en_val))[:800]  # limit length
                else:
                    en_text = str(en_val or "")
                ru_val = item.get("glossary_ru") or item.get("meaning_ru") or ""
                if isinstance(ru_val, list):
                    ru_text = "; ".join(map(str, ru_val))
                else:
                    ru_text = str(ru_val or "")

                # If ru missing, translate via DeepL (and cache)
                if (not ru_text.strip()) and en_text.strip():
                    ru_text = await deepL_translate_once(en_text)

                grouped[level].append({
                    "kanji": item.get("kanji") or item.get("word") or "",
                    "reading": item.get("reading") or item.get("kana") or "",
                    "translation": {"en": en_text, "ru": ru_text},
                    "pos": item.get("pos", ""),
                    "strokes": item.get("strokes", "—"),
                    "frequency": item.get("frequency", "—")
                })
        # kanji file
        try:
            async with aiohttp.ClientSession() as session2:
                async with session2.get(KANJI_URL, timeout=60) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        try:
                            kanji_list = json.loads(text)
                        except Exception:
                            kanji_list = []
                        for item in kanji_list:
                            level = str(item.get("jlpt") or "").upper()
                            if level in grouped:
                                en_desc = item.get("description", "") or ""
                                ru_desc = item.get("description_ru", "") or ""
                                if not ru_desc and en_desc:
                                    ru_desc = await deepL_translate_once(en_desc)
                                grouped[level].append({
                                    "kanji": item.get("kanji"),
                                    "reading": item.get("reading", "") or "",
                                    "translation": {"en": en_desc, "ru": ru_desc},
                                    "strokes": item.get("strokes", "—"),
                                    "frequency": item.get("frequency", "—")
                                })
        except Exception as e:
            print("⚠️ Kanji file fetch error:", e)

    # attach global
    return grouped

# --- Format JLPT card & natural examples ---
def build_examples(kanji, en, ru, pos_full):
    pos = (pos_full or "").lower()
    examples = []
    # noun default
    if "verb" in pos or pos.startswith("v"):
        examples = [
            {"ja": f"毎日{kanji}ます。", "ru": f"Я {ru.lower()} каждый день.", "en": f"I {en} every day."},
            {"ja": f"{kanji}ことが好きです。", "ru": f"Мне нравится {ru.lower()}.", "en": f"I like to {en}."}
        ]
    elif "adj" in pos or "adjective" in pos or pos.startswith("adj"):
        examples = [
            {"ja": f"この人はとても{kanji}です。", "ru": f"Этот человек очень {ru.lower()}.", "en": f"This person is very {en}."},
            {"ja": f"{kanji}ですね。", "ru": f"Ты {ru.lower()}, правда?", "en": f"You're {en}, aren't you?"}
        ]
    else:
        examples = [
            {"ja": f"{kanji}が大切です。", "ru": f"{ru.capitalize()} очень важно.", "en": f"{en.capitalize()} is important."},
            {"ja": f"{kanji}を持っています。", "ru": f"У меня есть {ru.lower()}.", "en": f"I have {en.lower()}."},
            {"ja": f"{kanji}について話しましょう。", "ru": f"Давай поговорим о {ru.lower()}.", "en": f"Let's talk about {en.lower()}."},
        ]
    return random.choice(examples)

# --- Bot handlers ---
@dp.message_handler(commands=["start","help"])
def cmd_start(message):
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("Русский 🇷🇺", callback_data="lang_ru"),
           types.InlineKeyboardButton("English 🇺🇸", callback_data="lang_en"))
    message.reply("Konnichiwa! 👋\nВыберите язык / Choose language:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("lang_"))
def process_lang(call):
    lang = call.data.split("_",1)[1]
    subs = load_subs()
    subs[str(call.from_user.id)] = {"lang": lang, "subscribed": False}
    save_subs(subs)
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(types.InlineKeyboardButton("Слово / Word", callback_data="daily"),
           types.InlineKeyboardButton("Факт / Fact", callback_data="fact"))
    kb.row(types.InlineKeyboardButton("Пословица / Proverb", callback_data="proverb"),
           types.InlineKeyboardButton("📘 JLPT Vocabulary", callback_data="jlpt"))
    kb.row(types.InlineKeyboardButton("Подписка / Subscription", callback_data="toggle_sub"))
    call.message.reply("Отлично! 🌸 Я покажу японские слова и факты!", reply_markup=kb)
    call.answer()

@dp.callback_query_handler(lambda c: c.data == "jlpt")
def choose_jlpt_level(call):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(types.InlineKeyboardButton("N5", callback_data="jlpt_N5"),
           types.InlineKeyboardButton("N4", callback_data="jlpt_N4"))
    kb.row(types.InlineKeyboardButton("N3", callback_data="jlpt_N3"),
           types.InlineKeyboardButton("N2", callback_data="jlpt_N2"))
    kb.row(types.InlineKeyboardButton("N1", callback_data="jlpt_N1"))
    kb.row(types.InlineKeyboardButton("⬅️ Назад", callback_data="menu"))
    call.message.reply("Выберите уровень JLPT:", reply_markup=kb)
    call.answer()

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("jlpt_N"))
def send_jlpt_word(call):
    level = call.data.split("_",1)[1]
    words = jlpt_data.get(level, [])
    if not words:
        call.message.reply("⏳ JLPT-данные ещё загружаются. Попробуйте через минуту.")
        call.answer()
        return
    word = random.choice(words)
    kanji = word.get("kanji","—")
    reading = word.get("reading","") or ""
    if not reading and kanji and kanji in kanji_readings:
        r = kanji_readings.get(kanji, {})
        reading = ", ".join(r.get("on",[]) + r.get("kun",[]))
    romaji = to_romaji(reading)
    en = (word.get("translation",{}).get("en") or "").strip() or "—"
    ru = (word.get("translation",{}).get("ru") or "").strip() or "(нет перевода)"
    pos_code = word.get("pos","")
    pos_full = pos_tags.get(pos_code, pos_code) if pos_tags else pos_code
    strokes = word.get("strokes","—")
    freq = word.get("frequency","—")

    example = build_examples(kanji, en, ru, pos_full)
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
        f"🌸 <i>Совет:</i> Используй <b>{kanji}</b> в своём следующем предложении!"
    )
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("🔁 Следующее слово", callback_data=f"jlpt_N{level}"))
    kb.row(types.InlineKeyboardButton("⬅️ Назад к уровням", callback_data="jlpt"))
    call.message.reply(text, parse_mode="HTML", reply_markup=kb)
    call.answer()

# --- scheduler jobs
async def daily_broadcast_job():
    subs = load_subs()
    for uid, info in subs.items():
        if info.get("subscribed"):
            # send a random daily word
            if data["words"]:
                item = random.choice(data["words"])
                try:
                    await bot.send_message(int(uid), f"{item.get('emoji','')} {item.get('ja','')} — {item.get('ru') or item.get('en','')}")
                except Exception as e:
                    print("⚠️ failed send to", uid, e)

async def refresh_data_job():
    global data, jlpt_data, pos_tags, kanji_readings
    print("🔄 Refreshing data from GitHub & JLPT...")
    data = await load_csv_from_github()
    jlpt_data = await load_jlpt_and_translate()
    pos_tags = await load_pos_tags()
    # don't reload kanji_readings automatically (it's local file)
    print("✅ Refresh complete.")

# --- startup helper to run heavy tasks synchronously at bot start ---
def start_background_tasks(loop):
    # run expensive startup coroutines sequentially in the running loop
    asyncio.run_coroutine_threadsafe(startup_sequence(), loop)

async def startup_sequence():
    global data, jlpt_data, pos_tags, kanji_readings
    print("🚀 Startup sequence: loading CSV, JLPT and translations (may take minutes)...")
    load_kanji_readings()
    data = await load_csv_from_github()
    jlpt_data = await load_jlpt_and_translate()
    pos_tags = await load_pos_tags()
    print("✅ Startup sequence finished.")
    # schedule periodic jobs (must be added after loop exists)
    scheduler.add_job(lambda: asyncio.ensure_future(daily_broadcast_job()), "cron", hour=9, id="daily")
    scheduler.add_job(lambda: asyncio.ensure_future(refresh_data_job()), "cron", hour=6, id="refresh")
    scheduler.start()

# --- run ---
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    # start background heavy work once loop runs
    start_background_tasks(loop)
    # start polling (this blocks)
    executor.start_polling(dp, skip_updates=True)





