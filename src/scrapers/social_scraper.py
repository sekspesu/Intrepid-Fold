"""
Social sentiment scraper — LunarCrush API.
Aggregates social metrics from Twitter/X, Reddit, YouTube, and more.
Provides Galaxy Score, AltRank, social volume, and sentiment data.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import aiohttp

from src.config import LUNARCRUSH_API_KEY, LUNARCRUSH_BASE_URL

logger = logging.getLogger(__name__)


async def _fetch_lunarcrush(session: aiohttp.ClientSession, endpoint: str, params: Optional[dict] = None) -> Optional[Union[dict, list]]:
    """Fetch data from LunarCrush API."""
    url = f"{LUNARCRUSH_BASE_URL}/{endpoint}"
    headers = {
        "Authorization": f"Bearer {LUNARCRUSH_API_KEY}",
    }

    try:
        async with session.get(url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status == 200:
                return await resp.json()
            logger.warning(f"LunarCrush {endpoint} returned {resp.status}")
            return None
    except Exception as e:
        logger.error(f"Error fetching LunarCrush {endpoint}: {e}")
        return None


async def fetch_sol_metrics(session: aiohttp.ClientSession) -> dict[str, Any]:
    """Fetch SOL social metrics from LunarCrush."""
    # Get coin metrics
    data = await _fetch_lunarcrush(session, "coins/sol/v1")

    if not data or not isinstance(data, dict):
        return {}

    coin_data = data.get("data", data)

    return {
        "galaxy_score": coin_data.get("galaxy_score"),
        "alt_rank": coin_data.get("alt_rank"),
        "social_volume": coin_data.get("social_volume"),
        "social_volume_change_24h": coin_data.get("social_volume_24h_change"),
        "social_dominance": coin_data.get("social_dominance"),
        "social_score": coin_data.get("social_score"),
        "sentiment": coin_data.get("sentiment"),
        "bullish_sentiment_pct": coin_data.get("bullish_sentiment"),
        "bearish_sentiment_pct": coin_data.get("bearish_sentiment"),
        "news_articles": coin_data.get("news"),
        "social_contributors": coin_data.get("social_contributors"),
        "social_mentions": coin_data.get("social_mentions"),
        "tweet_sentiment": coin_data.get("tweet_sentiment"),
        "market_dominance": coin_data.get("market_dominance"),
    }


async def fetch_social_feed(session: aiohttp.ClientSession) -> list[dict]:
    """Fetch recent social posts about SOL from LunarCrush."""
    data = await _fetch_lunarcrush(session, "coins/sol/feed/v1")

    if not data:
        return []

    posts = data.get("data", [])
    return [
        {
            "text": p.get("body", p.get("title", ""))[:300],
            "source": p.get("social_type", "unknown"),
            "sentiment": p.get("sentiment"),
            "interactions": p.get("interactions_total", 0),
            "created_at": p.get("time"),
        }
        for p in posts[:20]  # Top 20 social posts
    ]


async def scrape_social() -> dict[str, Any]:
    """Main entry point — collects all social metrics from LunarCrush."""
    logger.info("📱 Fetching social sentiment from LunarCrush...")

    if not LUNARCRUSH_API_KEY:
        logger.warning("  ⚠️ LunarCrush API key not configured, skipping")
        return {"metrics": {}, "feed": []}

    async with aiohttp.ClientSession() as session:
        metrics, feed = await asyncio.gather(
            fetch_sol_metrics(session),
            fetch_social_feed(session),
        )

    # Determine overall social sentiment
    bullish_pct = metrics.get("bullish_sentiment_pct", 50)
    if bullish_pct and bullish_pct > 60:
        overall = "bullish"
    elif bullish_pct and bullish_pct < 40:
        overall = "bearish"
    else:
        overall = "neutral"

    result = {
        "source": "lunarcrush",
        "timestamp": datetime.utcnow().isoformat(),
        "metrics": metrics,
        "top_social_posts": feed[:10],
        "overall_sentiment": overall,
    }

    galaxy = metrics.get("galaxy_score", "N/A")
    social_vol = metrics.get("social_volume", "N/A")
    logger.info(f"  ✅ Galaxy Score: {galaxy} | Social Volume: {social_vol} | Sentiment: {overall}")

    return result


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    data = asyncio.run(scrape_social())
    print(json.dumps(data, indent=2, default=str))
