"""cyber-intel-bot entry point.

Orchestrates the full pipeline: collect -> normalize -> deduplicate ->
enrich -> trim -> send.
"""

import sys

import config
from collectors.github_collector import collect_all_github
from collectors.reddit_collector import collect_reddit
from collectors.rss_collector import collect_rss
from output.telegram_sender import send_news
from processor.ai_summarizer import enrich_all
from processor.deduplicator import commit_seen, deduplicate
from processor.normalizer import normalize_all
from utils.logger import setup_logger

logger = setup_logger("main")


def validate_config():
    """Ensure required Telegram credentials are present."""
    missing = []
    if not config.TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not config.TELEGRAM_CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")

    if missing:
        logger.error("Missing required env vars: %s", ", ".join(missing))
        return False
    return True


def main():
    if not validate_config():
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("PHASE 1: COLLECTION")
    logger.info("=" * 60)
    raw = collect_rss() + collect_reddit() + collect_all_github()
    logger.info("Collected %d raw items", len(raw))

    logger.info("=" * 60)
    logger.info("PHASE 2: NORMALIZATION")
    logger.info("=" * 60)
    normalized = normalize_all(raw)

    logger.info("=" * 60)
    logger.info("PHASE 3: DEDUPLICATION")
    logger.info("=" * 60)
    unique = deduplicate(normalized)

    logger.info("=" * 60)
    logger.info("PHASE 4: AI ENRICHMENT")
    logger.info("=" * 60)
    enriched = enrich_all(unique)

    logger.info("=" * 60)
    logger.info("PHASE 5: TRIM & SEND")
    logger.info("=" * 60)
    enriched.sort(key=lambda i: i.get("importance", 0), reverse=True)
    final_items = enriched[: config.MAX_TOTAL_ITEMS]
    logger.info("Sending %d items", len(final_items))

    success = send_news(final_items)
    if success:
        # Only now mark the delivered items as seen, so a failed send is
        # retried on the next run instead of being silently dropped.
        commit_seen(final_items)
        logger.info("Digest sent successfully")
    else:
        logger.error("Digest sent with errors; not marking items as seen")


if __name__ == "__main__":
    main()
