#!/bin/bash
# Run UMAE Telegram Bot
cd "$(dirname "$0")"
source venv/bin/activate
export TELEGRAM_BOT_TOKEN="8895482996:AAGFtRTVQBGvyaf_kfu3O4KRkqkAFAW2pPU"
export DATABASE_URL="sqlite:///data/umae.db"
export PYTHONPATH=src
python run_bot.py
