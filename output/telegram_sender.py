"""Telegram sender.

Formats enriched items as HTML messages and delivers them to a Telegram chat,
grouped by category. Handles message chunking (Telegram has a hard length
limit) and 429 rate-limit responses.
"""

import time

import requests

import config
from utils.logger import setup_logger

logger = setup_logger("telegram_sender")

# Category -> display label, in the order categories should be sent.
_CATEGORY_LABELS = {
    "breach": "🚨 Breaches & Incidents",
    "vulnerability": "⚠️ Vulnerabilities & CVEs",
    "threat_intel": "🧠 Threat Intelligence",
    "tools": "🛠 Tools & Frameworks",
    "github": "💻 GitHub Updates",
    "general": "📰 General Cybersecurity News",
}

_CATEGORY_ORDER = ["breach", "vulnerability", "threat_intel", "tools", "github", "general"]


def _escape_html(text):
    """Escape the three characters Telegram's HTML parse mode cares about."""
    if not text:
        return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _chunk_text(text, max_len=config.TELEGRAM_MAX_LENGTH):
    """Split text into chunks no longer than ``max_len``, on newline boundaries."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    current = ""
    for line in text.split("\n"):
        # A single line longer than max_len must be hard-split.
        while len(line) > max_len:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:max_len])
            line = line[max_len:]

        candidate = line if not current else f"{current}\n{line}"
        if len(candidate) > max_len:
            chunks.append(current)
            current = line
        else:
            current = candidate

    if current:
        chunks.append(current)
    return chunks


def _send_raw(text, token, chat_id):
    """Send a single message; retry once on a 429. Return True on HTTP 200."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        response = requests.post(url, json=payload, timeout=config.REQUEST_TIMEOUT)
        if response.status_code == 429:
            retry_after = 1
            try:
                retry_after = response.json().get("parameters", {}).get(
                    "retry_after", 1
                )
            except (ValueError, AttributeError):
                pass
            logger.warning("Telegram rate limited, retrying after %ss", retry_after)
            time.sleep(retry_after)
            response = requests.post(
                url, json=payload, timeout=config.REQUEST_TIMEOUT
            )

        if response.status_code == 200:
            return True

        logger.error(
            "Telegram send failed (HTTP %d): %s",
            response.status_code,
            response.text[:200],
        )
        return False
    except Exception as exc:  # noqa: BLE001
        logger.error("Telegram send error: %s", exc)
        return False


def _send(text):
    """Validate credentials, chunk if needed, and send each chunk."""
    token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        logger.error("Missing Telegram credentials; cannot send")
        return False

    ok = True
    chunks = _chunk_text(text)
    for index, chunk in enumerate(chunks):
        if not _send_raw(chunk, token, chat_id):
            ok = False
        if index < len(chunks) - 1:
            time.sleep(config.TELEGRAM_DELAY)
    return ok


def _format_item(item):
    """Render a single item as a Telegram HTML message."""
    importance = item.get("importance", 50)
    if importance >= 80:
        emoji = "🔴"
    elif importance >= 60:
        emoji = "🟡"
    else:
        emoji = "🟢"

    title = _escape_html(item.get("title", "Untitled"))
    summary = _escape_html(item.get("summary", "")[:400])
    source = _escape_html(item.get("source", "Unknown"))
    url = item.get("url", "")

    entities = item.get("entities", []) or []
    hashtags = ""
    if entities:
        tags = []
        for entity in entities[:5]:
            tag = "".join(ch for ch in str(entity) if ch.isalnum())
            if tag:
                tags.append(f"#{tag}")
        if tags:
            hashtags = " ".join(tags)

    lines = [
        f"{emoji} <b>{title}</b>",
        f"<i>{summary}</i>",
    ]
    if hashtags:
        lines.append(hashtags)
    lines.append(f"📌 <b>Source:</b> {source}")
    lines.append(f'🔗 <a href="{_escape_html(url)}">Read More</a>')

    return "\n".join(lines)


def send_news(items):
    """Send all items to Telegram, grouped and ordered by category."""
    if not items:
        return _send("No new items this cycle.")

    # Group items by category.
    grouped = {}
    for item in items:
        category = item.get("category", "general")
        if category not in _CATEGORY_LABELS:
            category = "general"
        grouped.setdefault(category, []).append(item)

    ok = True

    header = (
        "🛡 <b>Cyber Intelligence Digest</b>\n"
        f"<i>{len(items)} new items this cycle</i>"
    )
    if not _send(header):
        ok = False
    time.sleep(config.TELEGRAM_DELAY)

    for category in _CATEGORY_ORDER:
        bucket = grouped.get(category)
        if not bucket:
            continue

        if not _send(f"<b>{_CATEGORY_LABELS[category]}</b>"):
            ok = False
        time.sleep(config.TELEGRAM_DELAY)

        for item in bucket:
            if not _send(_format_item(item)):
                ok = False
            time.sleep(config.TELEGRAM_DELAY)

    footer = "✅ <i>End of digest. Stay safe.</i>"
    if not _send(footer):
        ok = False

    return ok
