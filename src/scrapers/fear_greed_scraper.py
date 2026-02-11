"""
Fear & Greed Index scraper — Alternative.me API.
Fetches the Crypto Fear & Greed Index as a contrarian indicator.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

import aiohttp

from src.config import FEAR_GREED_URL

logger = logging.getLogger(__name__)


async def scrape_fear_greed() -> dict[str, Any]:
    """Fetch the Crypto Fear & Greed Index with historical data."""
    logger.info("😱 Fetching Fear & Greed Index...")

    try:
        async with aiohttp.ClientSession() as session:
            # Current + last 30 days
            params = {"limit": 30, "format": "json"}
            async with session.get(FEAR_GREED_URL, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    logger.warning(f"Fear & Greed API returned {resp.status}")
                    return {}

                data = await resp.json()

        entries = data.get("data", [])
        if not entries:
            return {}

        current = entries[0]
        current_value = int(current.get("value", 50))
        current_class = current.get("value_classification", "Unknown")

        # Calculate historical averages
        values = [int(e.get("value", 50)) for e in entries]
        avg_7d = sum(values[:7]) / min(len(values), 7) if values else 50
        avg_30d = sum(values) / len(values) if values else 50

        # Trend: is fear/greed increasing or decreasing?
        if len(values) >= 7:
            recent_avg = sum(values[:3]) / 3
            older_avg = sum(values[4:7]) / 3
            trend = "increasing" if recent_avg > older_avg else "decreasing"
        else:
            trend = "unknown"

        result = {
            "source": "alternative.me",
            "timestamp": datetime.utcnow().isoformat(),
            "current_value": current_value,
            "classification": current_class,
            "avg_7d": round(avg_7d, 1),
            "avg_30d": round(avg_30d, 1),
            "trend": trend,
            "history": [
                {
                    "value": int(e.get("value", 0)),
                    "classification": e.get("value_classification", ""),
                    "date": datetime.fromtimestamp(int(e.get("timestamp", 0))).strftime("%Y-%m-%d"),
                }
                for e in entries[:7]
            ],
        }

        logger.info(f"  ✅ Fear & Greed: {current_value} ({current_class}) | 7d avg: {avg_7d:.0f} | Trend: {trend}")
        return result

    except Exception as e:
        logger.error(f"Error fetching Fear & Greed Index: {e}")
        return {}


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    data = asyncio.run(scrape_fear_greed())
    print(json.dumps(data, indent=2))
