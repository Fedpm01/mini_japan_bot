#!/usr/bin/env python3
# Mini Japan Telegram Bot (template)
# Requirements: aiogram, APScheduler, python-dotenv
# pip install aiogram==2.25.1 APScheduler python-dotenv

import logging, json, os, random, asyncio
from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

load_dotenv()  # expects .env with TELEGRAM_TOKEN=your_token_here
print("Loaded token:", os.getenv("TELEGRAM_TOKEN"))

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    print("ERROR: Set TELEGRAM_TOKEN in .env file")
    exit(1)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)
scheduler = AsyncIOScheduler()

DATA_PATH = os.path.join(os.path.dirname(__file__), "data.json")
SUBS_PATH = os.path.join(os.path.dirname(__file__), "subscribers.json")

# Load content
with open(DATA_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

def load_subs():
    try:
        with open(SUBS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_subs(d):
    with open(SUBS_PATH, "w", encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

# Helper to format messages
def format_word(item, lang='ru'):
    # show ja + reading + translation in chosen lang
    if lang == 'en':
        trans = item.get('en','')
    else:
        trans = item.get('ru','')
    text = f"{item.get('emoji','')} <b>{item.get('ja')}</b> ({item.get('reading')})\n{trans}"
    return text

def format_fact(item, lang='ru'):
    return f"{item.get('emoji','')} {item.get(lang,'')}"

def format_proverb(item, lang='ru'):
    if lang == 'en':
        trans = item.get('en','')
    else:
        trans = item.get('ru','')
    return f"{item.get('emoji','')} <b>{item.get('ja')}</b> ({item.get('reading')})\n{trans}"

# Start command: choose language
@dp.message_handler(commands=['start', 'help'])
async def cmd_start(message: types.Message):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("Русский 🇷🇺", callback_data="lang_ru"),
           InlineKeyboardButton("English 🇺🇸", callback_data="lang_en"))
    await message.answer("Konnichiwa! 👋\nВыберите язык / Choose language:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('lang_'))
async def process_lang(call: types.CallbackQuery):
    lang = call.data.split('_',1)[1]
    user_id = str(call.from_user.id)
    subs = load_subs()
    if user_id not in subs:
        subs[user_id] = {"lang": lang, "subscribed": False}
    else:
        subs[user_id]["lang"] = lang
    save_subs(subs)
    # Main menu
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("Слово дня / Word of the day", callback_data="word"),
           InlineKeyboardButton("Факт / Fact", callback_data="fact"))
    kb.add(InlineKeyboardButton("Пословица / Proverb", callback_data="proverb"),
           InlineKeyboardButton("Подписаться/Unsubscribe", callback_data="toggle_sub"))
    await call.message.answer("Отлично! Я буду показывать японские слова и факты 🌸", reply_markup=kb)
    await call.answer()

@dp.callback_query_handler(lambda c: c.data in ['word','fact','proverb','toggle_sub'])
async def inline_actions(call: types.CallbackQuery):
    user_id = str(call.from_user.id)
    subs = load_subs()
    user_lang = subs.get(user_id, {}).get("lang","ru")
    if call.data == 'word':
        item = random.choice(data['words'])
        await call.message.answer(format_word(item, lang=user_lang), parse_mode='HTML')
    elif call.data == 'fact':
        item = random.choice(data['facts'])
        await call.message.answer(format_fact(item, lang=user_lang))
    elif call.data == 'proverb':
        item = random.choice(data['proverbs'])
        await call.message.answer(format_proverb(item, lang=user_lang), parse_mode='HTML')
    elif call.data == 'toggle_sub':
        cur = subs.get(user_id, {"lang":user_lang, "subscribed":False}).get("subscribed", False)
        subs.setdefault(user_id, {"lang":user_lang, "subscribed":False})
        subs[user_id]['subscribed'] = not cur
        save_subs(subs)
        await call.message.answer("Подписка обновлена: " + ("ON" if not cur else "OFF"))
    await call.answer()

# Daily broadcast job - sends "word of the day" to subscribed users
async def daily_broadcast():
    subs = load_subs()
    for uid, info in subs.items():
        if info.get("subscribed"):
            lang = info.get("lang","ru")
            item = random.choice(data['words'])
            try:
                await bot.send_message(int(uid), format_word(item, lang=lang), parse_mode='HTML')
            except Exception as e:
                print("Send failed to", uid, e)

# Schedule daily broadcast at 12:00 server time (change time as needed)
def setup_scheduler():
    # Schedule at 09:00 daily
    scheduler.add_job(lambda: asyncio.create_task(daily_broadcast()), 'cron', hour=9, minute=0)

async def on_startup(_):
    setup_scheduler()
    scheduler.start()
    print("✅ Scheduler started!")

if __name__ == '__main__':
    from aiogram.utils import executor
    print("🚀 Bot starting...")
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)

