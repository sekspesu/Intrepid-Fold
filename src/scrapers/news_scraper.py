from __future__ import annotations
"""
Crypto news scraper — CryptoPanic API + RSS feeds.
Aggregates news from major crypto outlets, filters for SOL relevance.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
import feedparser
from bs4 import BeautifulSoup

from src.config import (
    CRYPTOPANIC_API_KEY,
    CRYPTOPANIC_BASE_URL,
    CRYPTOPANIC_CURRENCIES,
    NEWS_MAX_AGE_HOURS,
    NEWS_RSS_FEEDS,
)

logger = logging.getLogger(__name__)

# Keywords that indicate Solana relevance in general crypto news
SOL_KEYWORDS = [
    "solana", "sol ", "$sol", "sol/", "phantom", "jupiter",
    "raydium", "marinade", "jito", "tensor", "magic eden",
    "bonk", "wif", "pyth", "helium", "render",
    "solana mobile", "saga", "firedancer",
]


def _is_sol_relevant(text: str) -> bool:
    """Check if text is relevant to Solana ecosystem."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in SOL_KEYWORDS)


def _is_crypto_relevant(text: str) -> bool:
    """Check if text is relevant to crypto market broadly."""
    crypto_keywords = [
        "crypto", "bitcoin", "btc", "ethereum", "eth", "blockchain",
        "defi", "nft", "web3", "token", "altcoin", "market",
        "bull", "bear", "sec", "regulation", "fed", "interest rate",
    ]
    text_lower = text.lower()
    return any(kw in text_lower for kw in crypto_keywords)


async def fetch_cryptopanic_news(session: aiohttp.ClientSession) -> list[dict]:
    """Fetch SOL-specific news from CryptoPanic."""
    if not CRYPTOPANIC_API_KEY:
        return []

    params = {
        "auth_token": CRYPTOPANIC_API_KEY,
        "currencies": CRYPTOPANIC_CURRENCIES,
        "filter": "important",
        "public": "true",
    }

    try:
        async with session.get(CRYPTOPANIC_BASE_URL, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                logger.warning(f"CryptoPanic returned {resp.status}")
                return []

            data = await resp.json()

        articles = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=NEWS_MAX_AGE_HOURS)

        for item in data.get("results", []):
            published = item.get("published_at", "")
            try:
                pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                continue

            if pub_dt < cutoff:
                continue

            # CryptoPanic provides community votes
            votes = item.get("votes", {})
            positive = votes.get("positive", 0)
            negative = votes.get("negative", 0)

            articles.append({
                "source": "cryptopanic",
                "outlet": item.get("source", {}).get("title", "Unknown"),
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "published_at": published,
                "kind": item.get("kind", "news"),
                "positive_votes": positive,
                "negative_votes": negative,
                "vote_sentiment": (
                    "positive" if positive > negative
                    else "negative" if negative > positive
                    else "neutral"
                ),
                "sol_specific": True,
            })

        return articles

    except Exception as e:
        logger.error(f"Error fetching CryptoPanic: {e}")
        return []


async def fetch_rss_feed(session: aiohttp.ClientSession, feed_config: dict) -> list[dict]:
    """Fetch and parse a single RSS feed."""
    name = feed_config["name"]
    url = feed_config["url"]

    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                logger.warning(f"RSS {name} returned {resp.status}")
                return []
            content = await resp.text()

        feed = feedparser.parse(content)
        articles = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=NEWS_MAX_AGE_HOURS)

        for entry in feed.entries:
            # Parse publish date
            published = entry.get("published_parsed") or entry.get("updated_parsed")
            if published:
                try:
                    pub_dt = datetime(*published[:6], tzinfo=timezone.utc)
                except (TypeError, ValueError):
                    continue

                if pub_dt < cutoff:
                    continue
            else:
                # No date, include but flag it
                pub_dt = None

            title = entry.get("title", "")
            summary = entry.get("summary", "")

            # Clean HTML from summary
            if summary:
                summary = BeautifulSoup(summary, "html.parser").get_text()
                summary = summary[:500]

            combined_text = f"{title} {summary}"
            is_sol = _is_sol_relevant(combined_text)
            is_crypto = _is_crypto_relevant(combined_text)

            # Only include if it's at least crypto-relevant
            if not is_crypto and not is_sol:
                continue

            articles.append({
                "source": "rss",
                "outlet": name,
                "title": title,
                "summary": summary,
                "url": entry.get("link", ""),
                "published_at": pub_dt.isoformat() if pub_dt else None,
                "sol_specific": is_sol,
                "crypto_relevant": is_crypto,
            })

        return articles

    except Exception as e:
        logger.error(f"Error fetching RSS {name}: {e}")
        return []


async def scrape_news() -> dict[str, Any]:
    """Main entry point — aggregates news from all sources."""
    logger.info("📰 Scraping crypto news sources...")

    async with aiohttp.ClientSession() as session:
        # Fetch all sources in parallel
        tasks = [fetch_cryptopanic_news(session)]
        for feed_config in NEWS_RSS_FEEDS:
            tasks.append(fetch_rss_feed(session, feed_config))

        results = await asyncio.gather(*tasks)

    all_articles = []
    for articles in results:
        all_articles.extend(articles)

    # Deduplicate by title similarity
    seen_titles = set()
    unique_articles = []
    for article in all_articles:
        title_key = article["title"].lower()[:50]
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_articles.append(article)

    # Sort by SOL relevance first, then recency
    unique_articles.sort(key=lambda x: (
        not x.get("sol_specific", False),
        x.get("published_at", "") or "",
    ), reverse=False)

    sol_count = sum(1 for a in unique_articles if a.get("sol_specific"))
    crypto_count = len(unique_articles) - sol_count

    result = {
        "source": "news",
        "timestamp": datetime.utcnow().isoformat(),
        "total_articles": len(unique_articles),
        "sol_specific_count": sol_count,
        "crypto_general_count": crypto_count,
        "articles": unique_articles,
    }

    logger.info(f"  ✅ News: {len(unique_articles)} articles "
                f"({sol_count} SOL-specific, {crypto_count} general crypto)")

    return result


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    data = asyncio.run(scrape_news())
    summary = {k: v for k, v in data.items() if k != "articles"}
    summary["headlines"] = [a["title"] for a in data.get("articles", [])[:10]]
    print(json.dumps(summary, indent=2, default=str))
