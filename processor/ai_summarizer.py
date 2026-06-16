"""AI summarizer.

Optionally enriches items with Gemini (via the modern ``google-genai`` SDK,
not the deprecated ``google-generativeai`` package). If the SDK is missing or
no API key is configured, items pass through unchanged so the pipeline keeps
working without AI.
"""

import json
import time

import config
from utils.logger import setup_logger

logger = setup_logger("ai_summarizer")

try:
    from google import genai

    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False

_MODEL = "gemini-2.0-flash-lite"


def _init_client():
    """Return a configured Gemini client, or None if unavailable."""
    if not _GENAI_AVAILABLE:
        logger.warning("google-genai not installed; skipping AI enrichment")
        return None
    if not config.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set; skipping AI enrichment")
        return None
    try:
        return genai.Client(api_key=config.GEMINI_API_KEY)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to init Gemini client: %s", exc)
        return None


def _strip_fences(text):
    """Remove ```json ... ``` style markdown fences from a response."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # Drop the opening fence (``` or ```json).
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        # Drop the closing fence.
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def _enrich_item(item, client):
    """Ask Gemini to summarize/classify a single item; merge results in.

    Returns the original item unchanged on any failure.
    """
    prompt = (
        "You are a cybersecurity news analyst writing for an Arabic-speaking "
        "audience. Analyze the item below and respond with ONLY a JSON object "
        "(no markdown, no prose) with exactly these keys:\n"
        '  "title": the headline translated into clear Modern Standard Arabic '
        "(keep CVE IDs, product names, and brand names in their original "
        "form)\n"
        '  "summary": a concise 2-3 sentence summary IN ARABIC, max 350 '
        "characters\n"
        '  "category": one of breach, vulnerability, threat_intel, tools, '
        "general\n"
        '  "importance": an integer 0-100\n'
        '  "entities": a list (max 5) of notable CVEs, companies, or malware '
        "names (keep these in their original Latin form)\n\n"
        f"Title: {item.get('title', '')}\n"
        f"Summary: {item.get('summary', '')}\n"
        f"Source: {item.get('source', '')}\n"
    )

    try:
        response = client.models.generate_content(model=_MODEL, contents=prompt)
        raw = _strip_fences(response.text or "")
        data = json.loads(raw)

        if isinstance(data.get("title"), str) and data["title"].strip():
            item["title"] = data["title"].strip()
        if isinstance(data.get("summary"), str) and data["summary"].strip():
            item["summary"] = data["summary"][:350]
        if isinstance(data.get("category"), str) and data["category"].strip():
            item["category"] = data["category"].strip()
        if "importance" in data:
            try:
                item["importance"] = max(0, min(100, int(data["importance"])))
            except (ValueError, TypeError):
                pass
        if isinstance(data.get("entities"), list):
            item["entities"] = [str(e) for e in data["entities"][:5]]

        return item
    except Exception as exc:  # noqa: BLE001
        logger.warning("Enrichment failed for '%s': %s", item.get("title", ""), exc)
        return item


def enrich_all(items):
    """Enrich every item with Gemini, respecting a basic rate limit."""
    client = _init_client()
    if client is None:
        return items

    enriched = []
    for index, item in enumerate(items):
        enriched.append(_enrich_item(item, client))
        # Rate limit: pause after every 10 items.
        if (index + 1) % 10 == 0:
            time.sleep(5)

    enriched.sort(key=lambda i: i.get("importance", 0), reverse=True)
    logger.info("Enriched %d items with AI", len(enriched))
    return enriched
