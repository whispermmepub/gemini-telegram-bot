import asyncio
from html import unescape
import logging
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from typing import Dict, Optional

from bs4 import BeautifulSoup
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
MAX_SOURCE_CHARS = 12000
URL_RE = re.compile(r"https?://[^\s<>\]\)\"']+")
SOURCE_SYSTEM_PROMPT = (
    "You answer using only the provided webpage source text. "
    "If the source does not contain the answer, say so clearly. "
    "Do not invent facts. "
    "If the user did not ask a specific question, give a concise summary of the page. "
    "Reply in the same language as the user."
)

FAQ_RESPONSES = [
    (
        ("cantook",),
        (
            "Android မှာ EPUB ဖတ်ချင်ရင် `Cantook` app သို့မဟုတ် `Google Play Books` app သုံးလို့ရပါတယ်.\n\n"
            "Cantook app:\n"
            "https://play.google.com/store/apps/details?id=com.aldiko.android\n\n"
            "ပြီးရင် https://t.me/TheBookR ချန်နယ်ထဲက `epub` လို့ရေးထားတဲ့ဖိုင်ကိုဖွင့်ပြီး Cantook app ကိုရွေးဖွင့်လိုက်ပါ.\n\n"
            "Google Play Books app:\n"
            "https://play.google.com/store/apps/details?id=com.google.android.apps.books\n\n"
            "Play Books app နဲ့လည်း ဒီတိုင်းဖတ်လို့ရပါတယ်."
        ),
    ),
    (
        ("google play book",),
        (
            "Android မှာ EPUB ဖတ်ချင်ရင် `Cantook` app သို့မဟုတ် `Google Play Books` app သုံးလို့ရပါတယ်.\n\n"
            "Cantook app:\n"
            "https://play.google.com/store/apps/details?id=com.aldiko.android\n\n"
            "ပြီးရင် https://t.me/TheBookR ချန်နယ်ထဲက `epub` လို့ရေးထားတဲ့ဖိုင်ကိုဖွင့်ပြီး Cantook app ကိုရွေးဖွင့်လိုက်ပါ.\n\n"
            "Google Play Books app:\n"
            "https://play.google.com/store/apps/details?id=com.google.android.apps.books\n\n"
            "Play Books app နဲ့လည်း ဒီတိုင်းဖတ်လို့ရပါတယ်."
        ),
    ),
    (
        ("google play books",),
        (
            "Android မှာ EPUB ဖတ်ချင်ရင် `Cantook` app သို့မဟုတ် `Google Play Books` app သုံးလို့ရပါတယ်.\n\n"
            "Cantook app:\n"
            "https://play.google.com/store/apps/details?id=com.aldiko.android\n\n"
            "ပြီးရင် https://t.me/TheBookR ချန်နယ်ထဲက `epub` လို့ရေးထားတဲ့ဖိုင်ကိုဖွင့်ပြီး Cantook app ကိုရွေးဖွင့်လိုက်ပါ.\n\n"
            "Google Play Books app:\n"
            "https://play.google.com/store/apps/details?id=com.google.android.apps.books\n\n"
            "Play Books app နဲ့လည်း ဒီတိုင်းဖတ်လို့ရပါတယ်."
        ),
    ),
    (
        ("android", "epub"),
        (
            "Android မှာ EPUB ဖတ်ချင်ရင် `Cantook` app သို့မဟုတ် `Google Play Books` app သုံးလို့ရပါတယ်.\n\n"
            "Cantook app:\n"
            "https://play.google.com/store/apps/details?id=com.aldiko.android\n\n"
            "ပြီးရင် https://t.me/TheBookR ချန်နယ်ထဲက `epub` လို့ရေးထားတဲ့ဖိုင်ကိုဖွင့်ပြီး Cantook app ကိုရွေးဖွင့်လိုက်ပါ.\n\n"
            "Google Play Books app:\n"
            "https://play.google.com/store/apps/details?id=com.google.android.apps.books\n\n"
            "Play Books app နဲ့လည်း ဒီတိုင်းဖတ်လို့ရပါတယ်."
        ),
    ),
    (
        ("epub", "ဖတ်"),
        (
            "Android မှာ EPUB ဖတ်ချင်ရင် `Cantook` app သို့မဟုတ် `Google Play Books` app သုံးလို့ရပါတယ်.\n\n"
            "Cantook app:\n"
            "https://play.google.com/store/apps/details?id=com.aldiko.android\n\n"
            "ပြီးရင် https://t.me/TheBookR ချန်နယ်ထဲက `epub` လို့ရေးထားတဲ့ဖိုင်ကိုဖွင့်ပြီး Cantook app ကိုရွေးဖွင့်လိုက်ပါ.\n\n"
            "Google Play Books app:\n"
            "https://play.google.com/store/apps/details?id=com.google.android.apps.books\n\n"
            "Play Books app နဲ့လည်း ဒီတိုင်းဖတ်လို့ရပါတယ်."
        ),
    ),
]


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


def _normalize_text(text: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def _clean_url(url: str) -> str:
    return url.rstrip(".,!?;:)]}\"'")


def _extract_urls(text: str) -> list[str]:
    urls = []
    for match in URL_RE.finditer(text):
        url = _clean_url(match.group(0))
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            urls.append(url)
    return urls


def _remove_urls(text: str, urls: list[str]) -> str:
    result = text
    for url in urls:
        result = result.replace(url, " ")
    return re.sub(r"\s+", " ", result).strip()


def _fetch_url_html(url: str) -> tuple[str, str, str]:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen(request, timeout=20) as response:
        content_type = response.headers.get_content_type()
        if content_type not in {"text/html", "application/xhtml+xml"}:
            raise ValueError(f"Unsupported content type: {content_type}")
        charset = response.headers.get_content_charset() or "utf-8"
        raw = response.read(2_000_000)
        html = raw.decode(charset, errors="replace")
        return html, response.geturl(), response.headers.get("content-type", "")


def _extract_main_text_from_html(html: str) -> tuple[str, str, str]:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside", "form", "svg", "canvas"]):
        tag.decompose()

    title = ""
    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
    if not title and soup.title and soup.title.string:
        title = soup.title.string.strip()

    description = ""
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        description = meta_desc["content"].strip()

    selectors = [
        "article",
        "main",
        "[role=main]",
        ".post-content",
        ".entry-content",
        ".article-content",
        ".content",
        ".post",
        ".article",
    ]

    candidates = [node for selector in selectors for node in soup.select(selector)]
    if not candidates:
        body = soup.body or soup
        candidates = [body]

    def candidate_score(node) -> tuple[int, str]:
        text = node.get_text("\n", strip=True)
        normalized = _normalize_text(unescape(text))
        return len(normalized), normalized

    scored = [candidate_score(node) for node in candidates]
    scored.sort(key=lambda item: item[0], reverse=True)
    main_text = scored[0][1] if scored else ""

    if not main_text:
        main_text = _normalize_text(unescape((soup.body or soup).get_text("\n", strip=True)))

    return title, description, main_text


def _summarize_source_text(text: str, limit: int = MAX_SOURCE_CHARS) -> str:
    cleaned = _normalize_text(text)
    if len(cleaned) <= limit:
        return cleaned
    cut = cleaned[:limit]
    split_at = cut.rfind("\n")
    if split_at > 1000:
        cut = cut[:split_at]
    return cut.strip()


def _build_source_prompt(user_prompt: str, url: str, title: str, description: str, source_text: str) -> str:
    question = user_prompt.strip() or "Summarize this page and give the main points."
    return (
        f"Page URL: {url}\n"
        f"Page title: {title or 'Unknown'}\n"
        f"Page description: {description or 'Not provided'}\n\n"
        f"Source text:\n{source_text}\n\n"
        f"User question:\n{question}"
    )


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


def _match_faq(prompt: str) -> Optional[str]:
    lowered = prompt.lower()
    for keywords, response in FAQ_RESPONSES:
        if all(keyword in lowered for keyword in keywords):
            return response
    return None


def _generate_reply_sync(
    client: genai.Client,
    session_key: str,
    prompt: str,
    system_prompt: str = SYSTEM_PROMPT,
    remember_history: bool = True,
) -> tuple[str, Optional[str]]:
    previous_id = user_sessions.get(session_key) if remember_history else None
    kwargs = {
        "model": GEMINI_MODEL,
        "input": prompt,
        "system_instruction": system_prompt,
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

    faq_reply = _match_faq(prompt)
    if faq_reply:
        await _send_reply(update, context, faq_reply)
        return

    urls = _extract_urls(prompt)
    if urls:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        url = urls[0]
        question = _remove_urls(prompt, urls)
        client: genai.Client = context.application.bot_data["genai_client"]
        try:
            html, final_url, content_type = await asyncio.to_thread(_fetch_url_html, url)
            title, description, source_text = await asyncio.to_thread(_extract_main_text_from_html, html)
            source_text = _summarize_source_text(source_text)
            if not source_text:
                await update.message.reply_text("ဒီ URL ကနေ ဖတ်လို့ရတဲ့ အကြောင်းအရာ မတွေ့ပါဘူး။")
                return

            source_prompt = _build_source_prompt(question, final_url, title, description, source_text)
            reply, _ = await asyncio.to_thread(
                _generate_reply_sync,
                client,
                _session_key(update.effective_chat.id, user.id),
                source_prompt,
                SOURCE_SYSTEM_PROMPT,
                False,
            )
            if not reply:
                reply = "ဒီ page ထဲက data ပေါ်မူတည်ပြီး answer မထုတ်နိုင်ခဲ့ပါ။"
            header = f"Source: {final_url}"
            await _send_reply(update, context, f"{header}\n\n{reply}")
        except (HTTPError, URLError, ValueError) as exc:
            logger.warning("URL fetch failed for %s: %s", url, exc)
            await update.message.reply_text(f"URL ဖတ်မရပါ: {exc}")
        except Exception as exc:
            logger.exception("URL processing failed")
            await update.message.reply_text(f"URL processing error: {exc}")
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
