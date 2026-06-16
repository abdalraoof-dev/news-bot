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


_BATCH_SIZE = 15
_MAX_RETRIES = 3

_BATCH_INSTRUCTIONS = (
    "You are a cybersecurity news analyst writing for an Arabic-speaking "
    "audience. You will receive a JSON array of news items. For EACH item, "
    "produce one JSON object with exactly these keys:\n"
    '  "index": the same integer index given in the input item\n'
    '  "title": the headline translated into clear Modern Standard Arabic '
    "(keep CVE IDs, product names, and brand names in their original Latin "
    "form)\n"
    '  "summary": a concise 2-3 sentence summary IN ARABIC, max 350 '
    "characters\n"
    '  "category": one of breach, vulnerability, threat_intel, tools, '
    "general\n"
    '  "importance": an integer 0-100\n'
    '  "entities": a list (max 5) of notable CVEs, companies, or malware '
    "names (keep these in their original Latin form)\n\n"
    "Respond with ONLY a JSON array of these objects, in the same order, with "
    "no markdown fences and no extra prose.\n\n"
    "Input items:\n"
)


def _generate_with_retry(client, prompt):
    """Call Gemini, retrying with exponential backoff on transient errors."""
    delay = 5
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=_MODEL, contents=prompt
            )
            return response.text or ""
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            transient = "429" in message or "RESOURCE_EXHAUSTED" in message or (
                "503" in message
            )
            if attempt < _MAX_RETRIES and transient:
                logger.warning(
                    "Gemini transient error (attempt %d/%d), retrying in %ds",
                    attempt,
                    _MAX_RETRIES,
                    delay,
                )
                time.sleep(delay)
                delay *= 2
                continue
            logger.warning("Gemini call failed: %s", message)
            return ""
    return ""


def _merge_enrichment(item, data):
    """Merge a single AI result object into an item in place."""
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


def _enrich_batch(batch, client):
    """Enrich a list of items with a single Gemini call.

    The original items are returned unchanged if the call or parsing fails.
    """
    payload = [
        {
            "index": idx,
            "title": item.get("title", ""),
            "summary": item.get("summary", ""),
            "source": item.get("source", ""),
        }
        for idx, item in enumerate(batch)
    ]
    prompt = _BATCH_INSTRUCTIONS + json.dumps(payload, ensure_ascii=False)

    raw = _generate_with_retry(client, prompt)
    if not raw:
        return batch

    try:
        results = json.loads(_strip_fences(raw))
    except (ValueError, TypeError) as exc:
        logger.warning("Could not parse AI batch response: %s", exc)
        return batch

    if not isinstance(results, list):
        return batch

    for result in results:
        if not isinstance(result, dict):
            continue
        try:
            idx = int(result.get("index"))
        except (ValueError, TypeError):
            continue
        if 0 <= idx < len(batch):
            _merge_enrichment(batch[idx], result)

    return batch


def enrich_all(items):
    """Enrich items with Gemini in batches to conserve API quota."""
    client = _init_client()
    if client is None or not items:
        return items

    enriched = []
    for start in range(0, len(items), _BATCH_SIZE):
        batch = items[start : start + _BATCH_SIZE]
        enriched.extend(_enrich_batch(batch, client))
        # Brief pause between batches to respect per-minute limits.
        if start + _BATCH_SIZE < len(items):
            time.sleep(5)

    enriched.sort(key=lambda i: i.get("importance", 0), reverse=True)
    logger.info("Enriched %d items with AI", len(enriched))
    return enriched
