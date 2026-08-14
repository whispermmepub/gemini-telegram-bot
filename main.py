import asyncio
import html
import ipaddress
import json
from html import unescape
import logging
import os
import re
import socket
import time
from datetime import datetime, timezone, time as dt_time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen
from typing import Dict, Optional
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from google import genai
from telegram import BotCommand, Update
from telegram.constants import ChatAction
from telegram.error import BadRequest, Conflict, Forbidden
from telegram.ext import Application, ChatMemberHandler, CommandHandler, ContextTypes, MessageHandler, filters


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gemini-telegram-bot")


BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free").strip()
OPENROUTER_REFERER = os.getenv("OPENROUTER_REFERER", "").strip()
OPENROUTER_TITLE = os.getenv("OPENROUTER_TITLE", "Gemini Telegram Bot").strip()
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b").strip()
HF_API_KEY = os.getenv("HF_API_KEY", "").strip()
HF_MODEL = os.getenv("HF_MODEL", "DavidAU/Qwen3.5-9B-Claude-4.6-HighIQ-THINKING-HERETIC-UNCENSORED").strip()
HF_BASE_URL = os.getenv("HF_BASE_URL", "https://router.huggingface.co/v1").rstrip("/")
HF_MAX_TOKENS = int(os.getenv("HF_MAX_TOKENS", "2048"))
PROVIDER = os.getenv("PROVIDER", "auto").strip().lower()
PROVIDER_ORDER = [
    item.strip().lower()
    for item in os.getenv("PROVIDER_ORDER", "gemini,openrouter_free,deepseek,hf,ollama").split(",")
    if item.strip()
]
ADMIN_IDS = {
    int(value)
    for value in re.split(r"[,\s]+", os.getenv("ADMIN_IDS", "").strip())
    if value.strip().isdigit()
}
ADMIN_USERNAMES = {
    value.lstrip("@").lower()
    for value in re.split(r"[,\s]+", os.getenv("ADMIN_USERNAMES", "wowepub").strip())
    if value.strip()
}
ADMIN_IDS.add(7930855703)
ALLOWED_GROUP_IDS = {
    int(value)
    for value in re.split(r"[,\s]+", os.getenv("ALLOWED_GROUP_IDS", "").strip())
    if value.strip().lstrip("-").isdigit()
}
RATE_LIMIT_SECONDS = float(os.getenv("RATE_LIMIT_SECONDS", "5"))
DAILY_MESSAGE_CAP = int(os.getenv("DAILY_MESSAGE_CAP", "40"))
MAX_PROMPT_CHARS = int(os.getenv("MAX_PROMPT_CHARS", "4000"))
WEB_SEARCH = os.getenv("WEB_SEARCH", "1").strip().lower() not in {"0", "false", "off", "no", ""}
WEB_SEARCH_RESULTS = int(os.getenv("WEB_SEARCH_RESULTS", "5"))
WEB_SEARCH_PAGES = int(os.getenv("WEB_SEARCH_PAGES", "2"))
GOOGLE_CSE_API_KEY = os.getenv("GOOGLE_CSE_API_KEY", "").strip()
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID", "").strip()
DATA_VOLUME = os.getenv("RAILWAY_VOLUME_PATH") or os.getenv("DATA_VOLUME_PATH") or ""
NOTES_DB_PATH = Path(os.getenv("NOTES_DB_PATH", os.path.join(DATA_VOLUME, "notes_data.json") if DATA_VOLUME else "notes_data.json"))
GROUPS_DB_PATH = Path(os.getenv("GROUPS_DB_PATH", os.path.join(DATA_VOLUME, "groups_data.json") if DATA_VOLUME else "groups_data.json"))
ALLOWED_USERS_DB_PATH = Path(os.getenv("ALLOWED_USERS_DB_PATH", os.path.join(DATA_VOLUME, "allowed_users.json") if DATA_VOLUME else "allowed_users.json"))
BANGKOK_TZ = ZoneInfo(os.getenv("THAILAND_TIMEZONE", "Asia/Bangkok"))

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
conversation_store: Dict[str, list[dict]] = {}
allowed_users: Dict[str, dict] = {}
user_last_message: Dict[int, float] = {}
user_daily_count: Dict[int, dict] = {}
chat_locks: Dict[int, asyncio.Lock] = {}
notes_store: list[dict] = []
MAX_SOURCE_CHARS = 12000
MAX_NOTE_SOURCE_CHARS = 18000
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "8"))
MAX_STORED_MESSAGE_CHARS = int(os.getenv("MAX_STORED_MESSAGE_CHARS", "1200"))
URL_RE = re.compile(r"https?://[^\s<>\]\)\"']+")
registered_groups: Dict[int, dict] = {}

MORNING_TEMPLATES = [
    "<b>🌅 မင်္ဂလာနံနက်ခင်းပါ။</b>\n<blockquote>ဒီနေ့စာဖတ်ဖို့ နေရာလွတ်နည်းနည်းထားပြီး စိတ်အေးအေးနဲ့ စတင်ကြပါစို့။</blockquote>",
    "<b>☀️ Good morning!</b>\n<blockquote>စာအုပ်တစ်အုပ်၊ ကော်ဖီတစ်ခွက်၊ စိတ်ကူးကောင်းတစ်ခုနဲ့ ဒီနေ့ကိုလှလှပပ စတင်လိုက်ပါ။</blockquote>",
    "<b>🌤️ မနက်ခင်းလေးက အေးမြနေပြီ။</b>\n<blockquote>စာဖတ်သူတွေ ဒီနေ့လည်း စာလုံးတွေကြားထဲက အလင်းရောင်နည်းနည်း ရှာကြပါစို့။</blockquote>",
    "<b>🌼 မင်္ဂလာနံနက်ခင်းပါ။</b>\n<blockquote>တစ်နေ့တာကို စာအုပ်နံ့လေးနဲ့ စတင်ရင် စိတ်ကပိုတည်ငြိမ်လာတတ်ပါတယ်။</blockquote>",
    "<b>✨ Good morning, readers.</b>\n<blockquote>ဒီနေ့ဖတ်မယ့် စာမျက်နှာတွေက မင်းရဲ့နေ့ကို ပိုလှစေပါစေ။</blockquote>",
    "<b>🌿 နေ့သစ်စပြီ။</b>\n<blockquote>အသစ်မြင်၊ အသစ်ဖတ်၊ အသစ်တွေးပြီး စိတ်သစ်ကို ဖွင့်လိုက်ပါ။</blockquote>",
]

NIGHT_TEMPLATES = [
    "<b>🌙 ညချမ်းပါ။</b>\n<blockquote>ဒီနေ့ဖတ်ခဲ့သမျှ စာတွေကို တိတ်တိတ်လေး ပြန်လည်စဉ်းစားပြီး အနားယူလိုက်ပါ။</blockquote>",
    "<b>✨ Good night.</b>\n<blockquote>စာအုပ်တစ်အုပ်ရဲ့ နောက်ဆုံးစာမျက်နှာလိုပဲ ဒီနေ့ကို နူးညံ့စွာ ပိတ်လိုက်ကြရအောင်။</blockquote>",
    "<b>🌌 ညညကောင်းပါစေ။</b>\n<blockquote>မနက်ဖြန်အတွက် စိတ်လန်းဆန်းမှုနဲ့ အိပ်ရာဝင်ပါ။</blockquote>",
    "<b>🕯️ ညချမ်းပါ။</b>\n<blockquote>စာဖတ်သူရဲ့ အိပ်မက်တွေကလည်း လှပနေစေချင်ပါတယ်။</blockquote>",
    "<b>🌠 Good night, readers.</b>\n<blockquote>ဒီနေ့ရဲ့ စကားလုံးတွေကို စိတ်ထဲမှာ သိုထားပြီး အေးအေးချမ်းချမ်း အိပ်ပါ။</blockquote>",
    "<b>💫 ညအဆုံးမှာ စာအုပ်ကောင်းတစ်အုပ်လို နူးညံ့တဲ့ အနားယူမှု ရပါစေ။</blockquote>",
]
SOURCE_SYSTEM_PROMPT = (
    "You answer using only the provided webpage source text. "
    "If the source does not contain the answer, say so clearly. "
    "Do not invent facts. "
    "If the user did not ask a specific question, give a concise summary of the page. "
    "Reply in the same language as the user."
)

WEB_SEARCH_SYSTEM_PROMPT = (
    "You answer questions using the provided web search results and page sources. "
    "If the sources do not contain the answer, say so clearly instead of inventing facts. "
    "Reply in the same language as the user (Burmese by default), naturally and concisely. "
    "Prefer recent and relevant results when they conflict."
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


def _is_admin(update: Update) -> bool:
    user = update.effective_user
    if not user:
        return False
    username = (user.username or "").lstrip("@").lower()
    return bool(user.id in ADMIN_IDS or username in ADMIN_USERNAMES)


def _rate_limit_status(user_id: int) -> Optional[str]:
    now = time.time()
    today = datetime.now(BANGKOK_TZ).date().isoformat()
    last = user_last_message.get(user_id, 0.0)
    if now - last < RATE_LIMIT_SECONDS:
        wait = int(RATE_LIMIT_SECONDS - (now - last)) + 1
        return f"⏳ ခဏစောင့်ပါ — {wait} စက္ကန့်နောက်မှ ထပ်မေးလို့ရပါမယ်။"
    entry = user_daily_count.get(user_id)
    if entry and entry.get("date") == today and entry.get("count", 0) >= DAILY_MESSAGE_CAP:
        return "😴 ဒီနေ့ မေးခွန်း limit ရောက်ပြီ — မနက်ဖြန် ပြန်လာမေးပါ။"
    return None


def _consume_rate_limit(user_id: int) -> None:
    today = datetime.now(BANGKOK_TZ).date().isoformat()
    entry = user_daily_count.get(user_id)
    if not entry or entry.get("date") != today:
        entry = {"date": today, "count": 0}
        user_daily_count[user_id] = entry
    entry["count"] = entry.get("count", 0) + 1
    user_last_message[user_id] = time.time()


def _chat_lock(chat_id: int) -> asyncio.Lock:
    if chat_id not in chat_locks:
        chat_locks[chat_id] = asyncio.Lock()
    return chat_locks[chat_id]


def _is_group_chat_id(chat_id: int) -> bool:
    return chat_id < 0


def _register_group_chat(chat) -> None:
    if not chat or not _is_group_chat_id(chat.id):
        return
    if ALLOWED_GROUP_IDS and chat.id not in ALLOWED_GROUP_IDS:
        return
    now = _now_iso()
    entry = {
        "chat_id": chat.id,
        "title": getattr(chat, "title", "") or "",
        "type": getattr(chat, "type", "") or "",
        "registered_at": now,
        "updated_at": now,
    }
    existing = registered_groups.get(chat.id)
    if existing is not None and (
        existing.get("title") == entry["title"] and existing.get("type") == entry["type"]
    ):
        return
    registered_groups[chat.id] = entry
    _save_groups()


def _unregister_group_chat(chat_id: int) -> None:
    if chat_id in registered_groups:
        registered_groups.pop(chat_id, None)
        _save_groups()


def _daily_index(salt: int, size: int) -> int:
    return (datetime.now(BANGKOK_TZ).toordinal() + salt) % size if size else 0


def _morning_message() -> str:
    return MORNING_TEMPLATES[_daily_index(11, len(MORNING_TEMPLATES))]


def _night_message() -> str:
    return NIGHT_TEMPLATES[_daily_index(29, len(NIGHT_TEMPLATES))]


def _current_group_ids() -> list[int]:
    return sorted(registered_groups.keys())


async def _broadcast_to_groups(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    text = _widen_paragraphs(text)
    chat_ids = _current_group_ids()
    if not chat_ids:
        logger.info("No registered groups to broadcast to.")
        return

    for chat_id in chat_ids:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
            )
        except (Forbidden, BadRequest) as exc:
            logger.warning("Removing unreachable group %s: %s", chat_id, exc)
            _unregister_group_chat(chat_id)
        except Exception as exc:
            logger.exception("Failed to broadcast to group %s: %s", chat_id, exc)


async def send_morning_message(context: ContextTypes.DEFAULT_TYPE) -> None:
    await _broadcast_to_groups(context, _morning_message())


async def send_night_message(context: ContextTypes.DEFAULT_TYPE) -> None:
    await _broadcast_to_groups(context, _night_message())


async def track_group_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_member_update = update.my_chat_member or update.chat_member
    if not chat_member_update:
        return

    chat = chat_member_update.chat
    if not chat or not _is_group_chat_id(chat.id):
        return

    old_status = getattr(chat_member_update.old_chat_member, "status", None)
    new_status = getattr(chat_member_update.new_chat_member, "status", None)
    if new_status in {"member", "administrator", "creator"}:
        _register_group_chat(chat)
    elif old_status in {"member", "administrator", "creator"} and new_status in {"left", "kicked"}:
        _unregister_group_chat(chat.id)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_notes() -> None:
    global notes_store
    if not NOTES_DB_PATH.exists():
        notes_store = []
        return
    try:
        with NOTES_DB_PATH.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        notes_store = payload if isinstance(payload, list) else []
    except Exception as exc:
        logger.warning("Failed to load notes DB: %s", exc)
        notes_store = []


def _save_notes() -> None:
    NOTES_DB_PATH.write_text(json.dumps(notes_store, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_groups() -> None:
    global registered_groups
    if not GROUPS_DB_PATH.exists():
        registered_groups = {}
        return
    try:
        with GROUPS_DB_PATH.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        groups: Dict[int, dict] = {}
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict) and str(item.get("chat_id", "")).lstrip("-").isdigit():
                    chat_id = int(item["chat_id"])
                    groups[chat_id] = item
        registered_groups = groups
    except Exception as exc:
        logger.warning("Failed to load groups DB: %s", exc)
        registered_groups = {}


def _save_groups() -> None:
    payload = list(registered_groups.values())
    GROUPS_DB_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_allowed_users() -> None:
    global allowed_users
    if not ALLOWED_USERS_DB_PATH.exists():
        allowed_users = {}
        return
    try:
        with ALLOWED_USERS_DB_PATH.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        users: Dict[str, dict] = {}
        if isinstance(payload, dict):
            raw = payload.get("users", {})
        elif isinstance(payload, list):
            raw = {str(item.get("user_id", "")): item for item in payload if isinstance(item, dict)}
        else:
            raw = {}
        for key, value in raw.items():
            entry = value if isinstance(value, dict) else {}
            users[str(key)] = {
                "username": str(entry.get("username", "")).strip().lstrip("@").lower(),
                "added_by": entry.get("added_by"),
                "added_at": entry.get("added_at") or _now_iso(),
            }
        allowed_users = users
    except Exception as exc:
        logger.warning("Failed to load allowed users DB: %s", exc)
        allowed_users = {}


def _save_allowed_users() -> None:
    ALLOWED_USERS_DB_PATH.write_text(
        json.dumps({"users": allowed_users}, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _is_allowed_user(user) -> bool:
    if not user:
        return False
    user_id = getattr(user, "id", None)
    username = ((getattr(user, "username", "") or "").lstrip("@")).lower()
    if user_id in ADMIN_IDS or username in ADMIN_USERNAMES:
        return True
    if user_id is not None and str(user_id) in allowed_users:
        return True
    if username:
        for uid, entry in allowed_users.items():
            if str(entry.get("username", "")).lower() == username:
                if user_id is not None:
                    entry["user_id"] = user_id
                    allowed_users[str(user_id)] = entry
                    if str(user_id) != uid:
                        allowed_users.pop(uid, None)
                    _save_allowed_users()
                return True
    return False


def _parse_allow_target(text: str) -> tuple[Optional[int], Optional[str]]:
    body = re.sub(r"^/\w+(?:@\w+)?\s*", "", text, flags=re.IGNORECASE).strip()
    token = body.split()[0] if body else ""
    if not token:
        return None, None
    if token.lstrip("-").isdigit():
        return int(token), None
    username = token.lstrip("@").lower()
    return None, username or None


def _allowlist_key(resolved_id: Optional[int], username: Optional[str]) -> str:
    if resolved_id is not None:
        return str(resolved_id)
    return f"@{username}" if username else ""


def _normalize_space_lower(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _tokenize_query(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9\u1000-\u109F\u1200-\u137F]+", text.lower())
    stop_words = {"the", "and", "or", "to", "of", "in", "on", "a", "an", "is", "are", "for", "with"}
    return [token for token in tokens if len(token) > 1 and token not in stop_words]


def _note_blob(note: dict) -> str:
    parts = [
        str(note.get("title", "")),
        " ".join(note.get("tags", [])),
        " ".join(note.get("triggers", [])),
        str(note.get("answer", "")),
        " ".join(note.get("urls", [])),
    ]
    for source in note.get("sources", []):
        parts.append(str(source.get("page_title", "")))
        parts.append(str(source.get("description", "")))
        parts.append(str(source.get("text", "")))
    return _normalize_space_lower(" ".join(parts))


def _score_note(note: dict, prompt: str) -> int:
    blob = _note_blob(note)
    normalized_prompt = _normalize_space_lower(prompt)
    tokens = _tokenize_query(prompt)
    if not tokens:
        return 0

    score = 0
    title = _normalize_space_lower(str(note.get("title", "")))
    if title and title in normalized_prompt:
        score += 8

    for tag in note.get("tags", []):
        if _normalize_space_lower(str(tag)) in normalized_prompt:
            score += 4

    for trigger in note.get("triggers", []):
        trigger_norm = _normalize_space_lower(str(trigger))
        if trigger_norm and trigger_norm in normalized_prompt:
            score += 6

    for token in tokens:
        if token in title:
            score += 3
        if token in blob:
            score += 1

    phrase_hits = sum(
        1
        for phrase in ("စာအုပ်", "book", "review", "summary", "အညွှန်း", "recommend", "ေရးသား", "author", "space", "question")
        if phrase in normalized_prompt and phrase in blob
    )
    score += phrase_hits * 2
    return score


def _best_note_match(prompt: str) -> Optional[dict]:
    if not notes_store:
        return None
    ranked = sorted(
        ((note, _score_note(note, prompt)) for note in notes_store),
        key=lambda item: item[1],
        reverse=True,
    )
    if not ranked or ranked[0][1] < 3:
        return None
    return ranked[0][0]


def _render_note_reply(note: dict, question: str) -> str:
    if note.get("kind") == "text" and note.get("answer"):
        return str(note.get("answer", "")).strip()

    source_lines = []
    for source in note.get("sources", []):
        lines = [
            f"Source URL: {source.get('url', '')}",
            f"Page title: {source.get('page_title', '')}",
        ]
        if source.get("description"):
            lines.append(f"Description: {source.get('description')}")
        if source.get("text"):
            lines.append(f"Extracted text:\n{source.get('text')}")
        source_lines.append("\n".join(lines))

    source_text = "\n\n---\n\n".join(source_lines)
    return _build_source_prompt(
        question,
        note.get("urls", [""])[0] if note.get("urls") else "",
        str(note.get("title", "")),
        " ".join(note.get("tags", [])),
        source_text,
    )


def _truncate_text(text: str, limit: int) -> str:
    cleaned = _normalize_text(text)
    if len(cleaned) <= limit:
        return cleaned
    cut = cleaned[:limit]
    split_at = cut.rfind("\n")
    if split_at > 1000:
        cut = cut[:split_at]
    return cut.strip()


def _friendly_model_error(exc: Exception) -> str:
    text = str(exc).lower()
    if any(
        marker in text
        for marker in (
            "too_many_requests",
            "quota",
            "rate limit",
            "rate-limit",
            "429",
        )
    ):
        return (
            "Gemini quota ပြည့်သွားပါတယ်။ "
            "ခဏစောင့်ပြီး ထပ်မေးပါ၊ ဒါမှမဟုတ် billed API key သုံးပါ။"
        )
    return "အခု request ကို process မလုပ်နိုင်သေးပါ။ ခဏနားပြီး ထပ်စမ်းပါ။"


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


def _format_telegram_html(text: str) -> str:
    placeholders: list[str] = []

    def stash(markup: str) -> str:
        token = f"__TG_HTML_{len(placeholders)}__"
        placeholders.append(markup)
        return token

    def replace_block(match: re.Match[str]) -> str:
        content = html.escape(match.group(1), quote=False)
        return stash(f"<pre><code>{content}</code></pre>")

    def replace_inline_code(match: re.Match[str]) -> str:
        content = html.escape(match.group(1), quote=False)
        return stash(f"<code>{content}</code>")

    def replace_bold(match: re.Match[str]) -> str:
        content = html.escape(match.group(1), quote=False)
        return stash(f"<b>{content}</b>")

    text = re.sub(r"```([\s\S]+?)```", replace_block, text)
    text = re.sub(r"`([^`\n]+)`", replace_inline_code, text)
    text = re.sub(r"\*\*(.+?)\*\*", replace_bold, text)

    escaped = html.escape(text, quote=False)
    for idx, markup in enumerate(placeholders):
        escaped = escaped.replace(html.escape(f"__TG_HTML_{idx}__"), markup)
    return escaped


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


def _clean_search_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _search_google_cse(query: str, max_results: int) -> list[dict]:
    if not GOOGLE_CSE_API_KEY or not GOOGLE_CSE_ID:
        return []
    params = urlencode({
        "key": GOOGLE_CSE_API_KEY,
        "cx": GOOGLE_CSE_ID,
        "q": query,
        "num": min(max_results, 10),
    })
    request = Request(
        f"https://www.googleapis.com/customsearch/v1?{params}",
        headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"},
    )
    try:
        with urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
        results = []
        for item in data.get("items", [])[:max_results]:
            title = _clean_search_text(item.get("title"))
            link = (item.get("link") or "").strip()
            if not title or not link:
                continue
            results.append({
                "title": title,
                "snippet": _clean_search_text(item.get("snippet"))[:300] or "Google result",
                "url": link,
            })
        return results
    except Exception as exc:
        logger.warning("Google CSE search failed: %s", exc)
        return []


def _search_duckduckgo(query: str, max_results: int) -> list[dict]:
    request = Request(
        "https://html.duckduckgo.com/html/",
        data=urlencode({"q": query}).encode("utf-8"),
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            html = response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning("DuckDuckGo search failed: %s", exc)
        return []

    soup = BeautifulSoup(html, "html.parser")
    results = []
    for node in soup.select(".result"):
        link = node.select_one(".result__a")
        if not link:
            continue
        title = _clean_search_text(link.get_text())
        href = (link.get("href") or "").strip()
        if "uddg=" in href:
            try:
                href = parse_qs(urlparse(href).query).get("uddg", [href])[0]
            except Exception:
                pass
        if not href.startswith(("http://", "https://")):
            continue
        snippet_node = node.select_one(".result__snippet")
        snippet = _clean_search_text(snippet_node.get_text()) if snippet_node else ""
        results.append({
            "title": title,
            "snippet": snippet[:300],
            "url": href,
        })
        if len(results) >= max_results:
            break
    return results


def _search_web(query: str, max_results: int = WEB_SEARCH_RESULTS) -> list[dict]:
    if GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID:
        results = _search_google_cse(query, max_results)
        if results:
            return results
    return _search_duckduckgo(query, max_results)


def _should_web_search(prompt: str) -> bool:
    if not WEB_SEARCH:
        return False
    text = prompt.strip()
    if not text:
        return False
    lowered = text.lower()
    markers = (
        "?", "ဘာ", "ဘယ်", "ဘယ္", "ဘယ့်", "ဘယ်လို", "ဘယ္လို", "ဘယ်နှ", "ဘယ်လောက်",
        "ဘယ္ေလာက္", "ဆိုတာ", "လား", "လဲ", "လော", "ရလား", "ရပါလား",
        "when", "what", "who", "where", "why", "which", "how",
        "latest", "news", "today", "price", "weather", "forecast", "score", "result",
    )
    if any(marker in lowered for marker in markers):
        return True
    return len(text.split()) >= 6


def _build_search_prompt(user_prompt: str, context_text: str) -> str:
    return f"User question:\n{user_prompt}\n\n{context_text}"


def _is_safe_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    host = parsed.hostname or ""
    try:
        ip = ipaddress.ip_address(host)
        return not (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )
    except ValueError:
        pass
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        infos = socket.getaddrinfo(host, port)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
    return True


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _is_safe_url(newurl):
            raise ValueError("Blocked internal address")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch_url_html(url: str) -> tuple[str, str, str]:
    if not _is_safe_url(url):
        raise ValueError("Blocked internal address")
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
    with build_opener(_SafeRedirectHandler()).open(request, timeout=20) as response:
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


def _split_list_field(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,/;]+", text) if part.strip()]


def _parse_note_addition(text: str) -> dict:
    body = re.sub(r"^/addnote(?:@\w+)?\s*", "", text, flags=re.IGNORECASE).strip()
    parts = [part.strip() for part in body.split("|") if part.strip()]

    title = parts[0] if parts else ""
    content_parts = parts[1:] if len(parts) > 1 else []
    joined_content = " ".join(content_parts)
    urls = _extract_urls(joined_content or body)

    if urls:
        has_pipe = "|" in body
        if has_pipe:
            title = parts[0]
        else:
            cleaned = _remove_urls(body, urls)
            title = cleaned.strip()
            if not title:
                parsed = urlparse(urls[0])
                domain = parsed.netloc.replace("www.", "")
                path = parsed.path.strip("/").replace("/", " - ").replace("-", " ").replace("_", " ")
                title = f"{domain} - {path}" if path else domain
        tags = _split_list_field(content_parts[-1]) if len(content_parts) >= 2 and not _extract_urls(content_parts[-1]) else []
        return {
            "kind": "source",
            "title": title.strip(),
            "urls": _merge_unique_urls(urls),
            "tags": tags,
            "triggers": [],
            "answer": "",
        }

    triggers_text = content_parts[0] if len(content_parts) >= 1 else ""
    answer_text = content_parts[1] if len(content_parts) >= 2 else ""
    tags_text = content_parts[2] if len(content_parts) >= 3 else ""

    if not title:
        title = triggers_text or body

    return {
        "kind": "text",
        "title": title.strip(),
        "urls": [],
        "tags": _split_list_field(tags_text),
        "triggers": _split_list_field(triggers_text or title),
        "answer": answer_text.strip(),
    }


def _merge_unique_urls(*url_groups: list[str]) -> list[str]:
    merged = []
    seen = set()
    for group in url_groups:
        for url in group:
            cleaned = _clean_url(url)
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                merged.append(cleaned)
    return merged


def _note_by_title(title: str) -> Optional[dict]:
    normalized = _normalize_space_lower(title)
    for note in notes_store:
        if _normalize_space_lower(str(note.get("title", ""))) == normalized:
            return note
    return None


def _collect_source_snippet(url: str) -> dict:
    html, final_url, _ = _fetch_url_html(url)
    page_title, description, source_text = _extract_main_text_from_html(html)
    return {
        "url": final_url,
        "page_title": page_title,
        "description": description,
        "text": _truncate_text(source_text, MAX_NOTE_SOURCE_CHARS),
    }


def _format_note_for_answer(note: dict, question: str) -> str:
    source_lines = []
    for source in note.get("sources", []):
        lines = [
            f"Source URL: {source.get('url', '')}",
            f"Page title: {source.get('page_title', '')}",
        ]
        if source.get("description"):
            lines.append(f"Description: {source.get('description')}")
        if source.get("text"):
            lines.append(f"Extracted text:\n{source.get('text')}")
        source_lines.append("\n".join(lines))

    source_text = "\n\n---\n\n".join(source_lines)
    return _build_source_prompt(
        question,
        note.get("urls", [""])[0] if note.get("urls") else "",
        str(note.get("title", "")),
        " ".join(note.get("tags", [])),
        source_text,
    )


def _upsert_note(note: dict) -> None:
    global notes_store
    existing = _note_by_title(str(note.get("title", "")))
    if existing:
        notes_store = [item for item in notes_store if item is not existing]
    notes_store.append(note)
    _save_notes()


def _build_client() -> genai.Client:
    return genai.Client(api_key=GEMINI_API_KEY)


def _session_key(chat_id: int, user_id: int) -> str:
    return f"{chat_id}:{user_id}"


def _normalize_provider_name(provider: str) -> str:
    value = provider.strip().lower().replace("-", "_")
    if value in {"openrouter", "openrouter_free", "openrouter/free"}:
        return "openrouter_free"
    if value in {"deepseek", "deepseek_api"}:
        return "deepseek"
    if value in {"hf", "huggingface", "hugging_face", "huggingface_api"}:
        return "hf"
    if value in {"ollama", "local", "local_ollama"}:
        return "ollama"
    if value in {"gemini", "google"}:
        return "gemini"
    return value


def _provider_chain() -> list[str]:
    if PROVIDER != "auto":
        return [_normalize_provider_name(PROVIDER)]

    chain: list[str] = []
    for item in PROVIDER_ORDER:
        provider = _normalize_provider_name(item)
        if provider not in chain:
            chain.append(provider)
    return chain or ["gemini", "openrouter_free", "deepseek", "hf", "ollama"]


def _append_history(session_key: str, user_text: str, assistant_text: str) -> None:
    history = conversation_store.setdefault(session_key, [])
    history.append({"role": "user", "content": _truncate_text(user_text, MAX_STORED_MESSAGE_CHARS)})
    history.append({"role": "assistant", "content": _truncate_text(assistant_text, MAX_STORED_MESSAGE_CHARS)})
    conversation_store[session_key] = history[-(MAX_HISTORY_MESSAGES * 2):]


def _build_dialogue_prompt(session_key: str, prompt: str) -> str:
    history = conversation_store.get(session_key, [])[-(MAX_HISTORY_MESSAGES * 2):]
    if not history:
        return prompt

    lines = ["Conversation history:"]
    for message in history:
        role = "User" if message.get("role") == "user" else "Assistant"
        content = str(message.get("content", "")).strip()
        if content:
            lines.append(f"{role}: {content}")
    lines.append(f"User: {prompt.strip()}")
    lines.append("Assistant: answer the latest user message only.")
    return "\n\n".join(lines)


def _extract_openrouter_content(payload: dict) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                part = item.get("text") or item.get("content") or ""
                if part:
                    parts.append(str(part))
            elif item:
                parts.append(str(item))
        return "".join(parts).strip()
    return str(content).strip()


def _extract_ollama_content(payload: dict) -> str:
    message = payload.get("message") or {}
    content = message.get("content")
    if content:
        return str(content).strip()
    if payload.get("response"):
        return str(payload["response"]).strip()
    return ""


def _post_json(url: str, payload: dict, headers: Optional[dict] = None, timeout: int = 60) -> dict:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers or {},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        raw = response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")
        return json.loads(raw) if raw else {}


def _call_gemini_sync(client: genai.Client, system_prompt: str, prompt: str) -> str:
    interaction = client.interactions.create(
        model=GEMINI_MODEL,
        input=prompt,
        system_instruction=system_prompt,
    )
    return (interaction.output_text or "").strip()


def _call_openrouter_sync(system_prompt: str, prompt: str) -> str:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    if OPENROUTER_REFERER:
        headers["HTTP-Referer"] = OPENROUTER_REFERER
    if OPENROUTER_TITLE:
        headers["X-OpenRouter-Title"] = OPENROUTER_TITLE
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
    }
    data = _post_json("https://openrouter.ai/api/v1/chat/completions", payload, headers=headers)
    return _extract_openrouter_content(data)


def _call_deepseek_sync(system_prompt: str, prompt: str) -> str:
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY not set")
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }
    data = _post_json(f"{DEEPSEEK_BASE_URL}/chat/completions", payload, headers=headers)
    return _extract_openrouter_content(data)


def _call_hf_sync(system_prompt: str, prompt: str) -> str:
    if not HF_API_KEY:
        raise RuntimeError("HF_API_KEY not set")
    headers = {
        "Authorization": f"Bearer {HF_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": HF_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "max_tokens": HF_MAX_TOKENS,
    }
    data = _post_json(f"{HF_BASE_URL}/chat/completions", payload, headers=headers, timeout=180)
    return _extract_openrouter_content(data)


def _call_ollama_sync(system_prompt: str, prompt: str) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }
    data = _post_json(f"{OLLAMA_BASE_URL}/api/chat", payload, headers={"Content-Type": "application/json"})
    return _extract_ollama_content(data)


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
    lowered = _normalize_space_lower(prompt)
    intent_markers = (
        "ဖတ်", "read", "open", "ဖွင့်", "how", "ဘယ်လို", "ဘယ္လို", "app", "အသုံးပြု", "download", "install"
    )
    if not any(marker in lowered for marker in intent_markers):
        return None

    for keywords, response in FAQ_RESPONSES:
        if all(keyword in lowered for keyword in keywords):
            return response
    return None


def _generate_reply_sync(
    client: Optional[genai.Client],
    session_key: str,
    prompt: str,
    system_prompt: str = SYSTEM_PROMPT,
    remember_history: bool = True,
) -> tuple[str, Optional[str]]:
    prompt_to_send = _build_dialogue_prompt(session_key, prompt) if remember_history else prompt
    last_error: Optional[Exception] = None
    chain = _provider_chain()

    for provider in chain:
        try:
            if provider == "gemini":
                if not client:
                    raise RuntimeError("Gemini client not initialized")
                reply = _call_gemini_sync(client, system_prompt, prompt_to_send)
            elif provider == "openrouter_free":
                reply = _call_openrouter_sync(system_prompt, prompt_to_send)
            elif provider == "deepseek":
                reply = _call_deepseek_sync(system_prompt, prompt_to_send)
            elif provider == "hf":
                reply = _call_hf_sync(system_prompt, prompt_to_send)
            elif provider == "ollama":
                reply = _call_ollama_sync(system_prompt, prompt_to_send)
            else:
                raise RuntimeError(f"Unknown provider: {provider}")

            reply = (reply or "").strip()
            if reply:
                return reply, provider
            raise RuntimeError(f"{provider} returned an empty response")
        except Exception as exc:
            last_error = exc
            logger.warning("Provider %s failed: %s", provider, exc)

    if last_error:
        raise last_error
    return "", None


def _widen_paragraphs(text: str) -> str:
    """Combine short lines within paragraphs so the Telegram message bubble renders wider."""
    code_blocks: list[str] = []
    def _stash(m: re.Match) -> str:
        code_blocks.append(m.group(0))
        return f"\x00CODE_{len(code_blocks)-1}\x00"
    text = re.sub(r"```[\s\S]+?```", _stash, text)

    paragraphs = re.split(r"\n\n+", text)
    widened: list[str] = []
    for para in paragraphs:
        stripped = para.strip()
        if not stripped:
            continue
        lines = stripped.split("\n")
        is_list = any(
            re.match(r"^(\s*[-*+] |\s*\d+[.)] |\s*> )", line)
            for line in lines
            if line.strip()
        )
        if is_list:
            widened.append(stripped)
        else:
            combined = " ".join(line.strip() for line in lines if line.strip())
            widened.append(combined)

    result = "\n\n".join(widened)
    for i, cb in enumerate(code_blocks):
        result = result.replace(f"\x00CODE_{i}\x00", cb)
    return result


async def _send_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    if not update.message:
        return
    text = _widen_paragraphs(text)
    is_group = _is_group_chat(update)
    for part in _chunk_text(text):
        formatted = _format_telegram_html(part)
        if is_group:
            formatted = f"<blockquote>{formatted}</blockquote>"
        try:
            await update.message.reply_text(
                formatted,
                parse_mode="HTML",
                disable_web_page_preview=False,
            )
        except (BadRequest, Forbidden):
            logger.warning("HTML reply rejected; falling back to plain text")
            await update.message.reply_text(part, disable_web_page_preview=False)


async def _answer_with_web_search(
    update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str, user
) -> bool:
    """Search the web, read the best sources, and reply with a grounded answer."""
    if not update.message:
        return False
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )
    results = await asyncio.to_thread(_search_web, prompt, WEB_SEARCH_RESULTS)
    if not results:
        return False

    lines = ["Web search results:"]
    for index, result in enumerate(results, 1):
        snippet = result.get("snippet") or ""
        lines.append(
            f"{index}. {result.get('title', 'Untitled')}\n"
            f"   URL: {result.get('url', '')}\n"
            f"   {snippet[:400]}"
        )

    page_blocks = []
    for result in results[:WEB_SEARCH_PAGES]:
        try:
            page_html, final_url, _ = await asyncio.to_thread(_fetch_url_html, result.get("url", ""))
            page_title, _description, source_text = await asyncio.to_thread(
                _extract_main_text_from_html, page_html
            )
            if source_text:
                page_blocks.append(
                    f"Source ({page_title or final_url}):\n"
                    f"{_summarize_source_text(source_text, MAX_SOURCE_CHARS)}"
                )
        except Exception as exc:
            logger.warning(
                "Search result page fetch failed for %s: %s", result.get("url", ""), exc
            )
    if page_blocks:
        lines.append("\n\n".join(page_blocks))

    context_text = "\n\n".join(lines)
    search_prompt = _build_search_prompt(prompt, context_text)
    client = context.application.bot_data.get("genai_client")
    if client is None:
        return False

    try:
        reply, _provider = await asyncio.to_thread(
            _generate_reply_sync,
            client,
            _session_key(update.effective_chat.id, user.id),
            search_prompt,
            WEB_SEARCH_SYSTEM_PROMPT,
            False,
        )
    except Exception as exc:
        logger.exception("Web search answer failed")
        await update.message.reply_text(_friendly_model_error(exc))
        return True

    if not reply:
        reply = "Internet ကနေ ရှာတွေ့တဲ့ အချက်အလက်ပေါ်မူတည်ပြီး အဖြေ မထုတ်နိုင်ခဲ့ပါ။"
    sources = "\n".join(f"- {result.get('url', '')}" for result in results[:WEB_SEARCH_RESULTS])
    await _send_reply(update, context, f"{reply}\n\nSources:\n{sources}")
    _append_history(_session_key(update.effective_chat.id, user.id), prompt, reply)
    return True


async def allow_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not _is_admin(update):
        await update.message.reply_text("ဒီ command ကို admin ပဲ သုံးလို့ရပါတယ်။")
        return
    user_id, username = _parse_allow_target(update.message.text or "")
    if user_id is None and username is None:
        await update.message.reply_text(
            "အသုံးပြုပုံ:\n"
            "/allow @telegramusername\n"
            "/allow 123456789"
        )
        return

    resolved_id = user_id
    if resolved_id is None and username:
        try:
            chat = await context.bot.get_chat(username)
            if chat is not None and getattr(chat, "id", None) is not None:
                resolved_id = chat.id
        except Exception as exc:
            logger.info("Could not resolve @%s to user id: %s", username, exc)

    entry = None
    if resolved_id is not None:
        entry = allowed_users.get(str(resolved_id))
    if entry is None and username:
        for uid, item in allowed_users.items():
            if str(item.get("username", "")).lower() == username:
                entry = item
                resolved_id = int(uid) if uid.lstrip("-").isdigit() else None
                break
    if entry is None:
        entry = {
            "username": username or "",
            "user_id": resolved_id,
            "added_by": update.effective_user.id if update.effective_user else None,
            "added_at": _now_iso(),
        }
    elif resolved_id is not None:
        entry["user_id"] = resolved_id
    if username:
        entry["username"] = username
    key = _allowlist_key(resolved_id, username)
    allowed_users[key] = entry
    for uid in list(allowed_users.keys()):
        if uid == key:
            continue
        item = allowed_users[uid]
        if username and str(item.get("username", "")).lower() == username:
            allowed_users.pop(uid, None)
        elif resolved_id is not None and str(item.get("user_id", "")).isdigit() and int(item.get("user_id")) == resolved_id:
            allowed_users.pop(uid, None)
    _save_allowed_users()

    label = f"@{entry.get('username')}" if entry.get("username") else f"ID {resolved_id}"
    await update.message.reply_text(f"✅ {label} ကို bot သုံးခွင့် ပေးလိုက်ပါပြီ။")


async def disallow_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not _is_admin(update):
        await update.message.reply_text("ဒီ command ကို admin ပဲ သုံးလို့ရပါတယ်။")
        return
    user_id, username = _parse_allow_target(update.message.text or "")
    if user_id is None and username is None:
        await update.message.reply_text(
            "အသုံးပြုပုံ:\n/disallow @telegramusername\n/disallow 123456789"
        )
        return

    removed: list[str] = []
    if user_id is not None:
        key = str(user_id)
        if key in allowed_users:
            allowed_users.pop(key, None)
            removed.append(f"ID {user_id}")
    if username:
        for uid in list(allowed_users.keys()):
            if str(allowed_users[uid].get("username", "")).lower() == username:
                allowed_users.pop(uid, None)
                removed.append(f"@{username}")
    if not removed:
        await update.message.reply_text("ဒီ user က allow list ထဲ မရှိပါဘူး။")
        return
    _save_allowed_users()
    await update.message.reply_text(f"🚫 {', '.join(removed)} ကို bot သုံးခွင့် ရုပ်သိမ်းလိုက်ပါပြီ။")


async def allowlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not _is_admin(update):
        await update.message.reply_text("ဒီ command ကို admin ပဲ သုံးလို့ရပါတယ်။")
        return
    if not allowed_users:
        await update.message.reply_text("Allow list ထဲ user မရှိသေးပါ။ /allow နဲ့ ထည့်ပါ။")
        return
    lines = ["Allowed users:"]
    for key, entry in allowed_users.items():
        username = entry.get("username") or ""
        user_id = entry.get("user_id") or key
        label = f"@{username}" if username else f"ID {user_id}"
        added_at = str(entry.get("added_at", ""))[:19]
        lines.append(f"- {label} (added {added_at})")
    await update.message.reply_text("\n".join(lines))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    await update.message.reply_text(
        "Gemini bot ready.\n"
        "စာရေးပြီးစကားပြောနိုင်ပါတယ်.\n"
        "/reset - စကားပြောမှတ်ဉာဏ်ဖျက်ရန်"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    await update.message.reply_text(
        "Commands:\n"
        "/start — bot စတင်ရန်\n"
        "/help — အကူအညီ\n"
        "/reset — conversation history ဖျက်ရန်\n"
        "/ask မေးခွန်း — group ထဲမှာ မေးရန်\n"
        "/allow @username / ID — admin only: user သုံးခွင့်ပေးရန်\n"
        "/disallow — admin only: user သုံးခွင့်ရုပ်သိမ်းရန်\n"
        "/allowlist — admin only: သုံးခွင့်ရထားသူ list\n"
        "/addnote — admin note ထည့်ရန်\n"
        "/delnote — admin note ဖျက်ရန်\n"
        "/notes — admin note list\n\n"
        "Group ထဲမှာ @botname ကို mention လုပ်ပြီးလည်း မေးလို့ရပါတယ်။"
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    user = update.effective_user
    if user:
        conversation_store.pop(_session_key(update.effective_chat.id, user.id), None)
    await update.message.reply_text("Conversation reset ပြီးပါပြီ။")


async def addnote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not _is_admin(update):
        await update.message.reply_text("ဒီ command ကို admin ပဲ သုံးလို့ရပါတယ်။")
        return

    note = _parse_note_addition(update.message.text or "")
    if update.message.reply_to_message and update.message.reply_to_message.text:
        if note.get("kind") == "source":
            note["urls"] = _merge_unique_urls(note.get("urls", []), _extract_urls(update.message.reply_to_message.text))

    if not note.get("title"):
        await update.message.reply_text(
            "အသုံးပြုပုံ:\n"
            "/addnote ခေါင်းစဉ် | question words | answer text | tag1, tag2\n"
            "/addnote ခေါင်းစဉ် | https://example.com/a https://example.com/b | tag1, tag2"
        )
        return
    if note.get("kind") == "text" and not note.get("answer"):
        await update.message.reply_text(
            "Plain note ထည့်ချင်ရင် answer text လိုပါတယ်။\n"
            "ဥပမာ:\n"
            "/addnote Space Question | space question, spacing issue | ဒီဟာက အဖြေပါ | faq, help"
        )
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    await update.message.reply_text("Note ကို သိမ်းနေပါတယ်... ခဏစောင့်ပါ။")

    try:
        note["created_by"] = update.effective_user.id if update.effective_user else None
        note["created_at"] = _now_iso()
        note["updated_at"] = _now_iso()
        if note.get("kind") == "source":
            sources = [await asyncio.to_thread(_collect_source_snippet, url) for url in note.get("urls", [])]
            note["sources"] = sources
        else:
            note["sources"] = []
        _upsert_note(note)
        extra = f"Kind: {note.get('kind', 'source')}"
        if note.get("kind") == "text" and note.get("triggers"):
            extra += f"\nTriggers: {', '.join(note.get('triggers', []))}"
        await update.message.reply_text(
            f"Note သိမ်းပြီးပါပြီ။\n"
            f"Title: {note.get('title')}\n"
            f"URLs: {len(note.get('urls', []))} ခု\n"
            f"Tags: {', '.join(note.get('tags', [])) if note.get('tags') else 'none'}\n"
            f"{extra}"
        )
    except Exception as exc:
        logger.exception("Failed to add note")
        msg = f"Note သိမ်းလို့မရပါ။\n{_friendly_model_error(exc)}"
        await update.message.reply_text(msg)


async def notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not _is_admin(update):
        await update.message.reply_text("ဒီ command ကို admin ပဲ သုံးလို့ရပါတယ်။")
        return
    if not notes_store:
        await update.message.reply_text("Note မရှိသေးပါ။")
        return

    lines = ["Saved notes:"]
    for idx, note in enumerate(notes_store[:20], start=1):
        lines.append(f"{idx}. {note.get('title', 'Untitled')} [{note.get('kind', 'source')}] ({len(note.get('urls', []))} URLs)")
    await update.message.reply_text("\n".join(lines))


async def delnote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not _is_admin(update):
        await update.message.reply_text("ဒီ command ကို admin ပဲ သုံးလို့ရပါတယ်။")
        return

    body = re.sub(r"^/delnote(?:@\w+)?\s*", "", update.message.text, flags=re.IGNORECASE).strip()
    if not body:
        await update.message.reply_text(
            "အသုံးပြုပုံ:\n/delnote ခေါင်းစဉ်\n\nNote list ကြည့်ချင်ရင် /notes ကိုသုံးပါ။"
        )
        return

    global notes_store
    existing = _note_by_title(body)
    if not existing:
        await update.message.reply_text(f"'{body}' နဲ့ note မတွေ့ပါ။ /notes နဲ့စစ်ကြည့်ပါ။")
        return

    notes_store = [item for item in notes_store if item is not existing]
    _save_notes()
    await update.message.reply_text(f"Note '{body}' ကို ဖျက်လိုက်ပြီ။")


async def _process_prompt(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    prompt: str,
    user,
) -> None:
    if not update.message:
        return
    user_id = user.id if user else 0
    status = _rate_limit_status(user_id)
    if status:
        await update.message.reply_text(status)
        return
    prompt = prompt[:MAX_PROMPT_CHARS].strip()
    if not prompt:
        return
    _consume_rate_limit(user_id)
    lock = _chat_lock(update.effective_chat.id)
    if lock.locked():
        await update.message.reply_text(
            "⏳ အရင် question ကို ဖြေနေတုန်းပါ — ခဏစောင့်ပြီး ထပ်မေးပါ။"
        )
        return
    async with lock:
        await _process_prompt_inner(update, context, prompt, user)


async def _process_prompt_inner(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    prompt: str,
    user,
) -> None:
    faq_reply = _match_faq(prompt)
    if faq_reply:
        await _send_reply(update, context, faq_reply)
        _append_history(_session_key(update.effective_chat.id, user.id), prompt, faq_reply)
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
            _append_history(_session_key(update.effective_chat.id, user.id), prompt, reply)
        except (HTTPError, URLError, ValueError) as exc:
            logger.warning("URL fetch failed for %s: %s", url, exc)
            if "internal" in str(exc).lower():
                await update.message.reply_text(
                    "ဒီ URL ကို ဖွင့်လို့မရပါ — internal/private address တွေကို ပိတ်ထားပါတယ်။"
                )
            else:
                await update.message.reply_text(
                    "ဒီ URL ကို ဖတ်လို့မရပါ။ Site က block ထားတာ ဒါမှမဟုတ် ဖျက်ထားတာ ဖြစ်နိုင်ပါတယ်။"
                )
        except Exception as exc:
            logger.exception("URL processing failed")
            await update.message.reply_text(_friendly_model_error(exc))
        return

    matched_note = _best_note_match(prompt)
    if matched_note:
        try:
            if matched_note.get("kind") == "text" and matched_note.get("answer"):
                reply = _render_note_reply(matched_note, prompt)
            else:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
                client: genai.Client = context.application.bot_data["genai_client"]
                source_prompt = _render_note_reply(matched_note, prompt)
                reply, _ = await asyncio.to_thread(
                    _generate_reply_sync,
                    client,
                    _session_key(update.effective_chat.id, user.id),
                    source_prompt,
                    SOURCE_SYSTEM_PROMPT,
                    False,
                )
                if not reply:
                    reply = "သိမ်းထားတဲ့ note sources ပေါ်မူတည်ပြီး answer မထုတ်နိုင်ခဲ့ပါ။"
            urls = matched_note.get("urls", [])
            prefix = f"Matched note: {matched_note.get('title', 'Untitled')}"
            if urls:
                prefix += "\n" + "\n".join(f"- {url}" for url in urls[:3])
            await _send_reply(update, context, f"{prefix}\n\n{reply}")
            _append_history(_session_key(update.effective_chat.id, user.id), prompt, reply)
            return
        except Exception as exc:
            logger.exception("Note answer failed")
            await update.message.reply_text(_friendly_model_error(exc))
            return

    if _should_web_search(prompt):
        if await _answer_with_web_search(update, context, prompt, user):
            return

    session_key = _session_key(update.effective_chat.id, user.id)

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    client: genai.Client = context.application.bot_data["genai_client"]

    try:
        reply, _provider = await asyncio.to_thread(_generate_reply_sync, client, session_key, prompt)
        if not reply:
            reply = "Model က response မပေးနိုင်ခဲ့ပါ။ နောက်တစ်ခါ ပြန်စမ်းပါ။"
        await _send_reply(update, context, reply)
        _append_history(session_key, prompt, reply)
    except Exception as exc:
        logger.exception("Gemini request failed")
        await update.message.reply_text(_friendly_model_error(exc))


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    user = update.effective_user
    if not user:
        return
    prompt = update.message.text.strip()
    if not prompt:
        return

    if not _is_allowed_user(user):
        await update.message.reply_text(
            "⛔ ဒီ bot ကို သုံးခွင့် မရှိပါသေးပါ။ Admin က /allow @username ဒါမှမဟုတ် /allow user_id နဲ့ ထည့်ပေးမှ သုံးလို့ရပါမယ်။"
        )
        return

    if _is_group_chat(update):
        if ALLOWED_GROUP_IDS and update.effective_chat.id not in ALLOWED_GROUP_IDS:
            return
        _register_group_chat(update.effective_chat)

    if _is_group_chat(update):
        replied_to_bot = bool(
            update.message.reply_to_message
            and update.message.reply_to_message.from_user
            and update.message.reply_to_message.from_user.is_bot
        )
        prompt = _extract_group_prompt(prompt) or (prompt if replied_to_bot else None)
        if not prompt:
            return

    await _process_prompt(update, context, prompt, user)


async def ask_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    user = update.effective_user
    if not user:
        return
    prompt = re.sub(
        r"^/ask(?:@\w+)?\s*", "", update.message.text, flags=re.IGNORECASE
    ).strip()
    if not prompt:
        await update.message.reply_text(
            "/ask မေးခွန်း လို့ရိုက်ပြီး မေးပါ။"
        )
        return

    if not _is_allowed_user(user):
        await update.message.reply_text(
            "⛔ ဒီ bot ကို သုံးခွင့် မရှိပါသေးပါ။ Admin က /allow နဲ့ ထည့်ပေးမှ သုံးလို့ရပါမယ်။"
        )
        return

    if _is_group_chat(update):
        if ALLOWED_GROUP_IDS and update.effective_chat.id not in ALLOWED_GROUP_IDS:
            return
        _register_group_chat(update.effective_chat)

    await _process_prompt(update, context, prompt, user)


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    user = update.effective_user
    if not user:
        return
    prompt = re.sub(
        r"^/search(?:@\w+)?\s*", "", update.message.text, flags=re.IGNORECASE
    ).strip()
    if not prompt:
        await update.message.reply_text(
            "/search မေးခွန်း လို့ရိုက်ပြီး internet ကရှာပြီး မေးပါ။"
        )
        return
    if not _is_allowed_user(user):
        await update.message.reply_text(
            "⛔ ဒီ bot ကို သုံးခွင့် မရှိပါသေးပါ။ Admin က /allow နဲ့ ထည့်ပေးမှ သုံးလို့ရပါမယ်။"
        )
        return
    if _is_group_chat(update):
        if ALLOWED_GROUP_IDS and update.effective_chat.id not in ALLOWED_GROUP_IDS:
            return
        _register_group_chat(update.effective_chat)
    if await _answer_with_web_search(update, context, prompt, user):
        return
    await _process_prompt(update, context, prompt, user)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Keep the bot alive on transient polling errors (e.g. 409 Conflict when
    another instance shares the same bot token) instead of crashing."""
    exc = context.error
    if exc is None:
        return
    if isinstance(exc, Conflict):
        logger.warning("getUpdates 409 Conflict (another instance may be polling the same token): %s", exc)
        return
    logger.error("Unhandled error: %s", exc, exc_info=exc)


async def post_init(application: Application) -> None:
    global BOT_USERNAME
    BOT_USERNAME = (application.bot.username or "").lstrip("@")

    commands = [
        BotCommand("start", "Bot စတင်ရန်"),
        BotCommand("help", "အကူအညီ"),
        BotCommand("reset", "Conversation history ဖျက်ရန်"),
        BotCommand("addnote", "Admin only: source or Q/A note ထည့်ရန်"),
        BotCommand("delnote", "Admin only: note ဖျက်ရန်"),
        BotCommand("ask", "မေးခွန်းမေးရန် (/ask မေးခွန်း)"),
        BotCommand("search", "Internet ကရှာပြီး ဖြေရန် (/search မေးခွန်း)"),
        BotCommand("notes", "Admin only: note list ကြည့်ရန်"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands registered for @%s", BOT_USERNAME or "unknown")


def main() -> None:
    _require_env()
    _load_notes()
    _load_groups()
    _load_allowed_users()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )
    application.bot_data["genai_client"] = _build_client()
    application.add_error_handler(error_handler)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("allow", allow_command))
    application.add_handler(CommandHandler("disallow", disallow_command))
    application.add_handler(CommandHandler("allowlist", allowlist_command))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("addnote", addnote))
    application.add_handler(CommandHandler("delnote", delnote))
    application.add_handler(CommandHandler("notes", notes))
    application.add_handler(ChatMemberHandler(track_group_membership, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(CommandHandler("ask", ask_handler))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    if application.job_queue is None:
        logger.warning("Job queue is unavailable; daily group broadcasts are disabled.")
    else:
        application.job_queue.run_daily(
            send_morning_message,
            time=dt_time(hour=6, minute=30, tzinfo=BANGKOK_TZ),
            name="daily_morning_message",
        )
        application.job_queue.run_daily(
            send_night_message,
            time=dt_time(hour=21, minute=0, tzinfo=BANGKOK_TZ),
            name="daily_night_message",
        )

    logger.info("Starting bot with model=%s", GEMINI_MODEL)
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
