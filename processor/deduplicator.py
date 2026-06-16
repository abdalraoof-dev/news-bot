"""Deduplicator.

GitHub Actions runners are ephemeral, so the set of already-seen URLs must be
persisted to ``seen_urls.json`` (committed back to the repo by the workflow).

File format:: ``{"md5_hash": "2024-01-15T10:30:00"}``
"""

import json
from datetime import datetime, timedelta

import config
from utils.logger import setup_logger

logger = setup_logger("deduplicator")


def load_seen(filepath):
    """Load the seen-URL map, returning {} if the file is missing or corrupt."""
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, dict):
                return data
            logger.warning("Seen file %s is not a dict, ignoring", filepath)
            return {}
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read seen file %s: %s", filepath, exc)
        return {}


def save_seen(seen, filepath):
    """Persist the seen-URL map as pretty-printed JSON."""
    try:
        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump(seen, fh, indent=2)
    except OSError as exc:
        logger.error("Could not write seen file %s: %s", filepath, exc)


def prune_expired(seen, days):
    """Drop entries older than ``days``.

    Entries whose timestamps cannot be parsed are kept (we never want to lose
    dedup state because of a malformed value).
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    pruned = {}
    for url_hash, timestamp in seen.items():
        try:
            seen_at = datetime.fromisoformat(timestamp)
        except (ValueError, TypeError):
            # Unparseable timestamp -> keep it to be safe.
            pruned[url_hash] = timestamp
            continue
        if seen_at >= cutoff:
            pruned[url_hash] = timestamp
    return pruned


def deduplicate(items):
    """Return only items not previously seen.

    This is read-only with respect to the persistent store: items are NOT
    marked as seen here. Call :func:`commit_seen` once the items have actually
    been delivered, so that a failed send is retried on the next run instead of
    being silently dropped.
    """
    persistent = load_seen(config.SEEN_URLS_FILE)
    persistent = prune_expired(persistent, config.DEDUP_RETENTION_DAYS)

    seen_this_run = set()
    unique = []

    for item in items:
        url_hash = item.get("hash")
        if not url_hash:
            continue
        if url_hash in persistent or url_hash in seen_this_run:
            continue

        seen_this_run.add(url_hash)
        unique.append(item)

    logger.info("Deduplicated to %d new items", len(unique))
    return unique


def commit_seen(items):
    """Persist the given items as seen, after they have been delivered.

    Loads the current store, prunes expired entries, records each item's hash
    with the current timestamp, and saves. Safe to call with an empty list.
    """
    persistent = load_seen(config.SEEN_URLS_FILE)
    persistent = prune_expired(persistent, config.DEDUP_RETENTION_DAYS)

    now = datetime.utcnow().isoformat()
    added = 0
    for item in items:
        url_hash = item.get("hash")
        if not url_hash:
            continue
        if url_hash not in persistent:
            added += 1
        persistent[url_hash] = now

    save_seen(persistent, config.SEEN_URLS_FILE)
    logger.info("Committed %d items to the seen store", added)
