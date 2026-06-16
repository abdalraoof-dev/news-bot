"""GitHub collector.

Pulls two streams from the public GitHub API:

* security advisories (the GHSA database), and
* trending-ish security repositories (via the Search API, since GitHub has no
  trending API).

Both are best-effort: any failure is logged and yields an empty list rather
than crashing the pipeline.
"""

import hashlib

import requests

import config
from utils.logger import setup_logger

logger = setup_logger("github_collector")

GITHUB_HEADERS = {
    "User-Agent": config.USER_AGENT,
    "Accept": "application/vnd.github.v3+json",
}


def _check_rate_limit(response):
    """Warn when the GitHub rate limit budget is nearly exhausted."""
    remaining = response.headers.get("X-RateLimit-Remaining")
    if remaining is not None:
        try:
            if int(remaining) < 5:
                logger.warning("GitHub rate limit low: %s remaining", remaining)
        except (ValueError, TypeError):
            pass


def collect_github_advisories():
    """Collect recently updated, reviewed security advisories."""
    items = []
    try:
        response = requests.get(
            f"{config.GITHUB_API_URL}/advisories",
            headers=GITHUB_HEADERS,
            params={
                "per_page": 10,
                "sort": "updated",
                "direction": "desc",
                "type": "reviewed",
            },
            timeout=config.REQUEST_TIMEOUT,
        )
        _check_rate_limit(response)
        response.raise_for_status()

        for adv in response.json():
            ghsa_id = adv.get("ghsa_id", "")
            cve_id = adv.get("cve_id")
            adv_summary = adv.get("summary", "") or ""
            description = adv.get("description", "") or ""
            severity = (adv.get("severity") or "unknown")
            html_url = adv.get("html_url", "")
            if not html_url:
                continue

            vulns = adv.get("vulnerabilities") or []
            ecosystem = "unknown"
            if vulns:
                package = (vulns[0] or {}).get("package") or {}
                ecosystem = package.get("ecosystem", "unknown") or "unknown"

            if cve_id:
                title = f"[{cve_id}] {adv_summary}"
            else:
                title = f"[{ghsa_id}] {adv_summary}"

            summary = (
                f"Severity: {severity.upper()} | Ecosystem: {ecosystem} | "
                f"{description[:300]}"
            )

            items.append(
                {
                    "title": title,
                    "url": html_url,
                    "summary": summary,
                    "source": "GitHub Security Advisories",
                    "category": "vulnerability",
                    "published": adv.get("published_at", "") or "",
                    "hash": hashlib.md5(html_url.encode()).hexdigest(),
                }
            )

        logger.info("Collected %d GitHub advisories", len(items))
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to collect GitHub advisories: %s", exc)

    return items


def collect_github_security_repos():
    """Collect popular, recently updated security repositories via Search API."""
    items = []
    try:
        response = requests.get(
            f"{config.GITHUB_API_URL}/search/repositories",
            headers=GITHUB_HEADERS,
            params={
                "q": "topic:security topic:cybersecurity stars:>200",
                "sort": "updated",
                "per_page": 5,
            },
            timeout=config.REQUEST_TIMEOUT,
        )
        _check_rate_limit(response)
        response.raise_for_status()

        for repo in response.json().get("items", []):
            html_url = repo.get("html_url", "")
            if not html_url:
                continue
            full_name = repo.get("full_name", "")
            stars = repo.get("stargazers_count", 0) or 0
            description = repo.get("description", "") or ""
            language = repo.get("language", "Unknown") or "Unknown"

            title = f"[GitHub] {full_name} ⭐ {stars:,}"
            summary = f"{description} | Language: {language}"

            items.append(
                {
                    "title": title,
                    "url": html_url,
                    "summary": summary,
                    "source": "GitHub",
                    "category": "tools",
                    "published": repo.get("updated_at", "") or "",
                    "hash": hashlib.md5(html_url.encode()).hexdigest(),
                }
            )

        logger.info("Collected %d GitHub security repos", len(items))
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to collect GitHub security repos: %s", exc)

    return items


def collect_all_github():
    """Return advisories and repositories combined."""
    items = collect_github_advisories() + collect_github_security_repos()
    logger.info("GitHub total: %d items", len(items))
    return items
