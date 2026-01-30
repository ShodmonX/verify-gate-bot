# Verify Gate Bot (Aiogram v3, Polling)

Telegram supergroup verification bot that restricts new users until they accept rules via DM by sending a random Uzbek word.

## Environment
Create a `.env` file based on the example:

```
BOT_TOKEN=123456:ABCDEF
GROUP_ID=-1001234567890
SECRET_KEY=super-secret-key
REMIND_AFTER_MIN=10
EXPIRE_AFTER_MIN=60
MAX_REMINDERS=2
DATABASE_URL=postgresql+asyncpg://botuser:botpass@db:5432/botdb
ADMIN_ID=123456789
PROHIBITED_WORDS_PATH=data/prohibited_words.txt
MUTE_MINUTES=10
TIMEZONE=Asia/Tashkent
CASE_INSENSITIVE=true
ADMIN_IDS=123456789,987654321
ADMIN_PANEL_ENABLED=true
OPENROUTER_API_KEY=your-key
OPENROUTER_MODEL=openai/gpt-4o-mini
OPENROUTER_TIMEOUT_SEC=8
AI_MODERATION_ENABLED=true
AI_MODERATION_SAMPLE_RATE=1.0
AI_MODERATION_MIN_CHARS=12
AI_MODERATION_COOLDOWN_SEC=30
AI_PROHIBITED_LABELS=gambling,fraud
AI_CONFIDENCE_THRESHOLD=0.7
```

## Local run (venv)
```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

## Docker
```
docker compose up --build -d
docker compose logs -f bot
```

## Bot permissions
- Add the bot to the target supergroup as admin.
- Required permissions: **Restrict Members** and **Delete Messages**.
- For prohibited words moderation, **Restrict Members** and **Delete Messages** are also required.

## Prohibited words moderation
- Edit `data/prohibited_words.txt` (one word/phrase per line, `#` comments allowed). If the database is empty, the bot seeds initial words from this file at startup.
- You can also point `PROHIBITED_WORDS_PATH` to a JSON file with `{ "words": [...] }`.
- The admin specified by `ADMIN_ID` will receive forwarded offending messages and a moderation note.
- Phone number is only available if the user explicitly shares their contact with the bot in DM.
 - Bad words source:
```
https://github.com/milliytech/uzbek-badwords
```

## AI moderation (OpenRouter)
- Set `OPENROUTER_API_KEY` to enable AI checks; if the API fails/timeouts, no action is taken.
- You can reduce costs with `AI_MODERATION_SAMPLE_RATE` (e.g., 0.2).
- Disable completely with `AI_MODERATION_ENABLED=false`.
- The AI only runs if no keyword matched, message length ≥ `AI_MODERATION_MIN_CHARS`, and per-user cooldown allows.
## Admin panel (/admin)
- Only `ADMIN_ID` or `ADMIN_IDS` can use the admin panel.
- Run `/admin` in the bot’s private chat to manage prohibited words.
- Features: list (paginated), add, remove (disable), search, bulk import, export.
- Use `/cancel` to exit a flow and return to the menu.

## Settings (runtime, DB-backed)
- You can edit these keys from the admin panel: `REMIND_AFTER_MIN`, `EXPIRE_AFTER_MIN`, `MAX_REMINDERS`, `ADMIN_IDS`, `MUTE_MINUTES`, `AI_MODERATION_ENABLED`.
- Changes are stored in DB and applied immediately.

## Notes
- The bot operates only for the single `GROUP_ID` specified in `.env`.
- It uses polling mode only (`python -m app.main`).

## How to get GROUP_ID
- `GROUP_ID`: add the bot to the target supergroup and send any message, then use a small script or another bot like `@userinfobot` to read the chat ID (it will look like `-100...`).
