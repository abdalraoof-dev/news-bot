"""RSS collector.

Fetches each configured RSS feed and returns a normalized list of item dicts.

RULE: never call ``feedparser.parse(url)`` directly. Always fetch the raw bytes
with ``requests`` first (so we control the User-Agent and timeout), then hand
the text to ``feedparser.parse``.
"""

import calendar
import hashlib
import re
from datetime import datetime, timezone

import feedparser
import requests

import config
from utils.logger import setup_logger

logger = setup_logger("rss_collector")

_TAG_RE = re.compile(r"<[^>]+>")

_ENTITIES = {
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&#39;": "'",
    "&nbsp;": " ",
}


def _clean_text(text):
    """Strip HTML tags and decode a handful of common entities."""
    if not text:
        return ""
    text = _TAG_RE.sub("", text)
    for entity, replacement in _ENTITIES.items():
        text = text.replace(entity, replacement)
    return text.strip()


def _parse_date(entry):
    """Return an ISO timestamp from ``published_parsed`` or fall back to now."""
    parsed = getattr(entry, "published_parsed", None)
    if parsed:
        try:
            return datetime.fromtimestamp(
                calendar.timegm(parsed), tz=timezone.utc
            ).isoformat()
        except (ValueError, OverflowError, TypeError):
            pass
    return datetime.utcnow().isoformat()


def collect_rss():
    """Collect items from all RSS feeds defined in ``config.RSS_FEEDS``."""
    items = []
    for source, url in config.RSS_FEEDS.items():
        try:
            response = requests.get(
                url,
                headers={"User-Agent": config.USER_AGENT},
                timeout=config.REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            feed = feedparser.parse(response.text)

            count = 0
            for entry in feed.entries[: config.MAX_ITEMS_PER_SOURCE]:
                link = getattr(entry, "link", "")
                if not link:
                    continue
                title = _clean_text(getattr(entry, "title", ""))
                raw_summary = getattr(entry, "summary", "") or getattr(
                    entry, "description", ""
                )
                summary = _clean_text(raw_summary)

                items.append(
                    {
                        "title": title,
                        "url": link,
                        "summary": summary,
                        "source": source,
                        "category": "general",
                        "published": _parse_date(entry),
                        "hash": hashlib.md5(link.encode()).hexdigest(),
                    }
                )
                count += 1

            logger.info("Collected %d items from %s", count, source)
        except Exception as exc:  # noqa: BLE001 - never let one feed kill the run
            logger.error("Failed to collect from %s: %s", source, exc)
            continue

    logger.info("RSS total: %d items", len(items))
    return items
