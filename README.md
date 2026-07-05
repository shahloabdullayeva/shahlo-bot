# telegram-assistant

A personal Telegram auto-responder that covers your messages while you're away. Built with Telethon and the Anthropic API. It reads incoming DMs and group mentions, replies briefly in a tone you configure, and gives you a private control panel in your own Saved Messages.

## What it does

- Auto-replies to DMs and group @mentions while active
- Introduces itself once per conversation, then talks normally
- Answers using details you put in the system prompt
- Private control panel in Saved Messages via slash commands
- Persists notes, memories, blocklist, and on/off state to a local JSON file

## Commands

Send to your own Saved Messages: /on /off /info /note <text> /notes /block <name> /unblock <name> /clearnotes

## Setup

1. pip install -r requirements.txt
2. cp .env.example .env  then fill in your keys
3. Set MY_ID in bot.py to your Telegram user ID
4. Edit SYSTEM_PROMPT in bot.py with your own details
5. set -a; source .env; set +a  then  python bot.py

## Never commit

.env, *.session, bot_context.json

## Tech

Python, Telethon, Anthropic API.
