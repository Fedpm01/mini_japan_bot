
Mini Japan — Telegram bot template
Files created in this folder:
- data.json      : sample words/facts/proverbs (you can extend)
- bot.py         : the bot script (uses aiogram v2)
- .env.template  : put your TELEGRAM_TOKEN here and rename to .env
- subscribers.json : will be created automatically when users interact with bot

Quick start (local):
1. Install Python 3.8+
2. Create virtual env and activate it (recommended)
   python -m venv venv
   source venv/bin/activate  # or venv\Scripts\activate on Windows
3. Install deps:
   pip install aiogram==2.25.1 APScheduler python-dotenv
4. Create a bot with BotFather in Telegram and get token. Put in file .env (rename .env.template)
   TELEGRAM_TOKEN=123456:ABC-DEF...
5. Run the bot:
   python bot.py
6. In Telegram, open your bot (by username) and press /start to choose language and try buttons.
7. To allow daily messages, click "Подписаться/Unsubscribe" button in the bot menu.

Notes:
- The scheduled time for daily broadcast is set to 12:00 server time in bot.py (cron). Change if needed.
- You can edit data.json to add more words/facts/proverbs (make sure keys match).
- This template uses polling (executor.start_polling). For production, consider webhooks and proper hosting.
