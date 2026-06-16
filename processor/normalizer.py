"""Normalizer.

Cleans, classifies and scores collected items into a single comparable shape,
then sorts them by importance so downstream stages see the best items first.
"""

import re

from utils.logger import setup_logger

logger = setup_logger("normalizer")

_TAG_RE = re.compile(r"<[^>]+>")

_ENTITIES = {
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&#39;": "'",
    "&nbsp;": " ",
}

CATEGORY_KEYWORDS = {
    "breach": [
        "breach",
        "data leak",
        "exposed",
        "stolen",
        "hacked",
        "ransomware",
        "compromised",
    ],
    "vulnerability": [
        "cve-",
        "vulnerability",
        "exploit",
        "zero-day",
        "0day",
        "rce",
        "patch",
        "advisory",
        "privilege escalation",
    ],
    "threat_intel": [
        "apt",
        "malware",
        "botnet",
        "phishing",
        "nation-state",
        "c2",
        "ioc",
        "trojan",
        "spyware",
    ],
    "tools": [
        "tool",
        "framework",
        "scanner",
        "pentest",
        "red team",
        "blue team",
        "osint",
        "forensics",
    ],
}

# (keyword, delta) pairs applied to a base importance score.
_IMPORTANCE_RULES = [
    ("zero-day", 15),
    ("actively exploited", 20),
    ("critical", 15),
    ("ransomware", 12),
    ("nation-state", 12),
    ("rce", 10),
    ("data breach", 10),
    ("supply chain", 10),
    ("tutorial", -5),
    ("opinion", -5),
    ("podcast", -5),
]


def _clean_html(text):
    """Strip HTML tags and decode common entities."""
    if not text:
        return ""
    text = _TAG_RE.sub("", text)
    for entity, replacement in _ENTITIES.items():
        text = text.replace(entity, replacement)
    return text.strip()


def classify_item(item):
    """Classify an item into a category.

    Source overrides win first; otherwise we score keyword hits across the
    title and summary and pick the highest-scoring category.
    """
    source = item.get("source", "")
    if source == "GitHub Security Advisories":
        return "vulnerability"
    if source == "GitHub":
        return "tools"

    text = f"{item.get('title', '')} {item.get('summary', '')}".lower()

    best_category = "general"
    best_score = 0
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > best_score:
            best_score = score
            best_category = category

    return best_category if best_score > 0 else "general"


def score_importance(item):
    """Score importance from 0-100, starting from a base of 50."""
    text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    score = 50
    for keyword, delta in _IMPORTANCE_RULES:
        if keyword in text:
            score += delta
    return max(0, min(100, score))


def normalize_all(items):
    """Clean, re-classify and re-score every item, then sort by importance."""
    normalized = []
    for item in items:
        if not item.get("url"):
            continue

        item["title"] = _clean_html(item.get("title", ""))
        item["summary"] = _clean_html(item.get("summary", ""))
        item["category"] = classify_item(item)
        item["importance"] = score_importance(item)
        normalized.append(item)

    normalized.sort(key=lambda i: i.get("importance", 0), reverse=True)
    logger.info("Normalized %d items", len(normalized))
    return normalized
