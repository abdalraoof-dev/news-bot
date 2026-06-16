"""Central configuration for cyber-intel-bot.

All secrets are loaded from environment variables only. Everything else is a
hard-coded constant so the bot behaves identically across local runs and CI.
"""

import os

# --- Secrets (environment variables only) -----------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# --- Sources ----------------------------------------------------------------
RSS_FEEDS = {
    "The Hacker News": "https://feeds.feedburner.com/TheHackersNews",
    "BleepingComputer": "https://www.bleepingcomputer.com/feed/",
    "SecurityWeek": "https://www.securityweek.com/feed/",
    "Krebs on Security": "https://krebsonsecurity.com/feed/",
}

REDDIT_FEEDS = {
    "r/cybersecurity": "https://www.reddit.com/r/cybersecurity/.rss",
    "r/netsec": "https://www.reddit.com/r/netsec/.rss",
    "r/blueteamsec": "https://www.reddit.com/r/blueteamsec/.rss",
    "r/malware": "https://www.reddit.com/r/malware/.rss",
}

GITHUB_API_URL = "https://api.github.com"

# --- Collection limits ------------------------------------------------------
MAX_ITEMS_PER_SOURCE = 10
MAX_REDDIT_ITEMS = 5
MAX_GITHUB_ITEMS = 10
MAX_TOTAL_ITEMS = 30

# --- Deduplication ----------------------------------------------------------
SEEN_URLS_FILE = "seen_urls.json"
DEDUP_RETENTION_DAYS = 7

# --- Telegram / network -----------------------------------------------------
TELEGRAM_MAX_LENGTH = 4000
TELEGRAM_DELAY = 2.0
REQUEST_TIMEOUT = 15

USER_AGENT = "Mozilla/5.0 (compatible; CyberIntelBot/1.0)"
