"""Reddit collector.

Reddit blocks generic Python User-Agents, so we present a browser UA. Each
subreddit RSS feed is fetched independently; rate-limited or forbidden
responses are skipped rather than aborting the whole run.
"""

import calendar
import hashlib
import re
from datetime import datetime, timezone

import feedparser
import requests

import config
from utils.logger import setup_logger

logger = setup_logger("reddit_collector")

REDDIT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) "
    "Gecko/20100101 Firefox/120.0"
}

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


def collect_reddit():
    """Collect items from all subreddit feeds defined in ``config.REDDIT_FEEDS``."""
    items = []
    for source, url in config.REDDIT_FEEDS.items():
        try:
            response = requests.get(
                url, headers=REDDIT_HEADERS, timeout=config.REQUEST_TIMEOUT
            )

            if response.status_code in (429, 403):
                logger.warning(
                    "Reddit blocked %s (HTTP %d), skipping",
                    source,
                    response.status_code,
                )
                continue

            response.raise_for_status()
            feed = feedparser.parse(response.text)

            count = 0
            for entry in feed.entries:
                if count >= config.MAX_REDDIT_ITEMS:
                    break

                link = getattr(entry, "link", "")
                # Only keep real posts, not subreddit/profile links.
                if not link or "/comments/" not in link:
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
        except Exception as exc:  # noqa: BLE001 - isolate failures per subreddit
            logger.error("Failed to collect from %s: %s", source, exc)
            continue

    logger.info("Reddit total: %d items", len(items))
    return items
