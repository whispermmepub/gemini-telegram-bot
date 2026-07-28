import asyncio
import logging
import os
import re
from typing import Dict, Optional

from google import genai
from telegram import BotCommand, Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gemini-telegram-bot")


BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash").strip()

SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    (
        "You are a helpful Telegram assistant. "
        "Reply in the same language the user used. "
        "Keep responses concise unless the user asks for detail. "
        "If code is requested, give runnable code."
    ),
).strip()

MAX_TELEGRAM_MESSAGE = 4096
BOT_USERNAME = ""
user_sessions: Dict[str, str] = {}


def _require_env() -> None:
    missing = [name for name, value in {
        "TELEGRAM_BOT_TOKEN": BOT_TOKEN,
        "GEMINI_API_KEY": GEMINI_API_KEY,
    }.items() if not value]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


def _chunk_text(text: str, limit: int = MAX_TELEGRAM_MESSAGE) -> list[str]:
    text = text.strip()
    if len(text) <= limit:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            split_at = text.rfind("\n", start, end)
            if split_at <= start:
                split_at = text.rfind(" ", start, end)
            if split_at > start:
                end = split_at + 1
        chunks.append(text[start:end].strip())
        start = end
    return [chunk for chunk in chunks if chunk]


def _build_client() -> genai.Client:
    return genai.Client(api_key=GEMINI_API_KEY)


def _session_key(chat_id: int, user_id: int) -> str:
    return f"{chat_id}:{user_id}"


def _is_group_chat(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type in {"group", "supergroup"})


def _extract_group_prompt(text: str) -> Optional[str]:
    if not BOT_USERNAME:
        return None
    pattern = rf"(?i)(?:^|\s)@{re.escape(BOT_USERNAME)}(?:\b|$)"
    if not re.search(pattern, text):
        return None
    cleaned = re.sub(pattern, " ", text, count=1).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def _generate_reply_sync(client: genai.Client, session_key: str, prompt: str) -> tuple[str, Optional[str]]:
    previous_id = user_sessions.get(session_key)
    kwargs = {
        "model": GEMINI_MODEL,
        "input": prompt,
        "system_instruction": SYSTEM_PROMPT,
    }
    if previous_id:
        kwargs["previous_interaction_id"] = previous_id

    interaction = client.interactions.create(**kwargs)
    reply = (interaction.output_text or "").strip()
    return reply, interaction.id


async def _send_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    if not update.message:
        return
    for part in _chunk_text(text):
        await update.message.reply_text(part)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    await update.message.reply_text(
        "Gemini bot ready.\n"
        "စာရေးပြီးစကားပြောနိုင်ပါတယ်.\n"
        "/reset - စကားပြောမှတ်ဉာဏ်ဖျက်ရန်"
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    user = update.effective_user
    if user:
        user_sessions.pop(user.id, None)
    await update.message.reply_text("Conversation reset ပြီးပါပြီ။")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    if not user:
        return

    prompt = update.message.text.strip()
    if not prompt:
        return

    if _is_group_chat(update):
        replied_to_bot = bool(
            update.message.reply_to_message
            and update.message.reply_to_message.from_user
            and update.message.reply_to_message.from_user.is_bot
        )
        prompt = _extract_group_prompt(prompt) or (prompt if replied_to_bot else None)
        if not prompt:
            return

    session_key = _session_key(update.effective_chat.id, user.id)

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    client: genai.Client = context.application.bot_data["genai_client"]

    try:
        reply, interaction_id = await asyncio.to_thread(_generate_reply_sync, client, session_key, prompt)
        if interaction_id:
            user_sessions[session_key] = interaction_id
        if not reply:
            reply = "Gemini က response မပေးနိုင်ခဲ့ပါ။ နောက်တစ်ခါ ပြန်စမ်းပါ။"
        await _send_reply(update, context, reply)
    except Exception as exc:
        logger.exception("Gemini request failed")
        await update.message.reply_text(f"Error: {exc}")


async def post_init(application: Application) -> None:
    global BOT_USERNAME
    BOT_USERNAME = (application.bot.username or "").lstrip("@")

    commands = [
        BotCommand("start", "Bot စတင်ရန်"),
        BotCommand("reset", "Conversation history ဖျက်ရန်"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands registered for @%s", BOT_USERNAME or "unknown")


def main() -> None:
    _require_env()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )
    application.bot_data["genai_client"] = _build_client()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Starting bot with model=%s", GEMINI_MODEL)
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
