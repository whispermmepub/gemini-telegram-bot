import asyncio
import html
import json
from html import unescape
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
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
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free").strip()
OPENROUTER_REFERER = os.getenv("OPENROUTER_REFERER", "").strip()
OPENROUTER_TITLE = os.getenv("OPENROUTER_TITLE", "Gemini Telegram Bot").strip()
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b").strip()
PROVIDER = os.getenv("PROVIDER", "auto").strip().lower()
PROVIDER_ORDER = [
    item.strip().lower()
    for item in os.getenv("PROVIDER_ORDER", "gemini,openrouter_free,deepseek,ollama").split(",")
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
NOTES_DB_PATH = Path(os.getenv("NOTES_DB_PATH", "notes_data.json"))

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
notes_store: list[dict] = []
MAX_SOURCE_CHARS = 12000
MAX_NOTE_SOURCE_CHARS = 18000
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "8"))
MAX_STORED_MESSAGE_CHARS = int(os.getenv("MAX_STORED_MESSAGE_CHARS", "1200"))
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


def _is_admin(update: Update) -> bool:
    user = update.effective_user
    if not user:
        return False
    username = (user.username or "").lstrip("@").lower()
    return bool(user.id in ADMIN_IDS or username in ADMIN_USERNAMES)


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

    for token in tokens:
        if token in title:
            score += 3
        if token in blob:
            score += 1

    phrase_hits = sum(
        1 for phrase in ("စာအုပ်", "book", "review", "summary", "အညွှန်း", "recommend", "ေရးသား", "author")
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


def _parse_note_addition(text: str) -> tuple[str, list[str], list[str]]:
    body = re.sub(r"^/addnote(?:@\w+)?\s*", "", text, flags=re.IGNORECASE).strip()
    parts = [part.strip() for part in body.split("|") if part.strip()]

    title = parts[0] if parts else ""
    url_section = parts[1] if len(parts) > 1 else body
    tag_section = parts[2] if len(parts) > 2 else ""

    urls = _extract_urls(url_section if parts else body)
    if not urls:
        urls = _extract_urls(body)

    if not title:
        cleaned = _remove_urls(body, urls)
        title = cleaned.split("|", 1)[0].strip()

    tag_text = tag_section
    if not tag_text and len(parts) >= 2:
        tag_text = parts[-1] if len(parts) > 2 else ""

    tags = [
        tag.strip()
        for tag in re.split(r"[,/;]+", tag_text)
        if tag.strip()
    ]
    return title.strip(), urls, tags


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
    return chain or ["gemini", "openrouter_free", "ollama"]


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


async def _send_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    if not update.message:
        return
    for part in _chunk_text(text):
        await update.message.reply_text(
            _format_telegram_html(part),
            parse_mode="HTML",
            disable_web_page_preview=False,
        )


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
        conversation_store.pop(_session_key(update.effective_chat.id, user.id), None)
    await update.message.reply_text("Conversation reset ပြီးပါပြီ။")


async def addnote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not _is_admin(update):
        await update.message.reply_text("ဒီ command ကို admin ပဲ သုံးလို့ရပါတယ်။")
        return

    title, urls, tags = _parse_note_addition(update.message.text or "")
    if update.message.reply_to_message and update.message.reply_to_message.text:
        urls = _merge_unique_urls(urls, _extract_urls(update.message.reply_to_message.text))

    if not title or not urls:
        await update.message.reply_text(
            "အသုံးပြုပုံ:\n"
            "/addnote ခေါင်းစဉ် | https://example.com/a https://example.com/b | tag1, tag2"
        )
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    await update.message.reply_text("Source တွေ ဖတ်နေပါတယ်... ခဏစောင့်ပါ။")

    try:
        sources = [await asyncio.to_thread(_collect_source_snippet, url) for url in urls]
        note = {
            "title": title,
            "urls": urls,
            "tags": tags,
            "sources": sources,
            "created_by": update.effective_user.id if update.effective_user else None,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        _upsert_note(note)
        await update.message.reply_text(
            f"Note သိမ်းပြီးပါပြီ။\n"
            f"Title: {title}\n"
            f"URLs: {len(urls)} ခု\n"
            f"Tags: {', '.join(tags) if tags else 'none'}"
        )
    except Exception as exc:
        logger.exception("Failed to add note")
        await update.message.reply_text(f"Note ထည့်မရပါ: {exc}")


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
        lines.append(f"{idx}. {note.get('title', 'Untitled')} ({len(note.get('urls', []))} URLs)")
    await update.message.reply_text("\n".join(lines))


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
            await update.message.reply_text(f"URL ဖတ်မရပါ: {exc}")
        except Exception as exc:
            logger.exception("URL processing failed")
            await update.message.reply_text(_friendly_model_error(exc))
        return

    matched_note = _best_note_match(prompt)
    if matched_note:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        client: genai.Client = context.application.bot_data["genai_client"]
        try:
            source_prompt = _format_note_for_answer(matched_note, prompt)
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

    session_key = _session_key(update.effective_chat.id, user.id)

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    client: genai.Client = context.application.bot_data["genai_client"]

    try:
        reply, _provider = await asyncio.to_thread(_generate_reply_sync, client, session_key, prompt)
        if not reply:
            reply = "Gemini က response မပေးနိုင်ခဲ့ပါ။ နောက်တစ်ခါ ပြန်စမ်းပါ။"
        await _send_reply(update, context, reply)
        _append_history(session_key, prompt, reply)
    except Exception as exc:
        logger.exception("Gemini request failed")
        await update.message.reply_text(_friendly_model_error(exc))


async def post_init(application: Application) -> None:
    global BOT_USERNAME
    BOT_USERNAME = (application.bot.username or "").lstrip("@")

    commands = [
        BotCommand("start", "Bot စတင်ရန်"),
        BotCommand("reset", "Conversation history ဖျက်ရန်"),
        BotCommand("addnote", "Admin only: source note ထည့်ရန်"),
        BotCommand("notes", "Admin only: note list ကြည့်ရန်"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands registered for @%s", BOT_USERNAME or "unknown")


def main() -> None:
    _require_env()
    _load_notes()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )
    application.bot_data["genai_client"] = _build_client()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("addnote", addnote))
    application.add_handler(CommandHandler("notes", notes))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Starting bot with model=%s", GEMINI_MODEL)
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
