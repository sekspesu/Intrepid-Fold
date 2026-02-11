"""
Price data scraper — CoinGecko + Binance.
Fetches SOL price, volume, OHLCV candles, and market metrics.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import aiohttp

from src.config import (
    BINANCE_BASE_URL,
    BINANCE_SYMBOL,
    COINGECKO_API_KEY,
    COINGECKO_BASE_URL,
    COINGECKO_COIN_ID,
)

logger = logging.getLogger(__name__)


async def _fetch_json(session: aiohttp.ClientSession, url: str, params: Optional[dict] = None, headers: Optional[dict] = None) -> Optional[Union[dict, list]]:
    """Generic async JSON fetcher with error handling."""
    try:
        async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                return await resp.json()
            logger.warning(f"HTTP {resp.status} from {url}")
            return None
    except Exception as e:
        logger.error(f"Error fetching {url}: {e}")
        return None


async def fetch_coingecko_data(session: aiohttp.ClientSession) -> dict[str, Any]:
    """Fetch comprehensive SOL data from CoinGecko."""
    headers = {}
    if COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

    # Current price + market data
    market_url = f"{COINGECKO_BASE_URL}/coins/{COINGECKO_COIN_ID}"
    params = {
        "localization": "false",
        "tickers": "false",
        "community_data": "true",
        "developer_data": "false",
        "sparkline": "true",
    }
    data = await _fetch_json(session, market_url, params=params, headers=headers)

    if not data:
        return {}

    market_data = data.get("market_data", {})
    return {
        "source": "coingecko",
        "timestamp": datetime.utcnow().isoformat(),
        "price_usd": market_data.get("current_price", {}).get("usd"),
        "price_btc": market_data.get("current_price", {}).get("btc"),
        "market_cap_usd": market_data.get("market_cap", {}).get("usd"),
        "market_cap_rank": market_data.get("market_cap_rank"),
        "total_volume_usd": market_data.get("total_volume", {}).get("usd"),
        "price_change_24h_pct": market_data.get("price_change_percentage_24h"),
        "price_change_7d_pct": market_data.get("price_change_percentage_7d"),
        "price_change_30d_pct": market_data.get("price_change_percentage_30d"),
        "ath_usd": market_data.get("ath", {}).get("usd"),
        "ath_change_pct": market_data.get("ath_change_percentage", {}).get("usd"),
        "circulating_supply": market_data.get("circulating_supply"),
        "total_supply": market_data.get("total_supply"),
        "sparkline_7d": market_data.get("sparkline_7d", {}).get("price", []),
        "community_reddit_subscribers": data.get("community_data", {}).get("reddit_subscribers"),
    }


async def fetch_binance_candles(session: aiohttp.ClientSession, interval: str = "4h", limit: int = 50) -> list[dict]:
    """Fetch OHLCV candlestick data from Binance."""
    url = f"{BINANCE_BASE_URL}/klines"
    params = {
        "symbol": BINANCE_SYMBOL,
        "interval": interval,
        "limit": limit,
    }
    data = await _fetch_json(session, url, params=params)

    if not data:
        return []

    candles = []
    for c in data:
        candles.append({
            "timestamp": c[0],
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
            "volume": float(c[5]),
            "close_time": c[6],
            "quote_volume": float(c[7]),
            "trades": c[8],
        })
    return candles


async def fetch_binance_ticker(session: aiohttp.ClientSession) -> dict[str, Any]:
    """Fetch 24h ticker statistics from Binance."""
    url = f"{BINANCE_BASE_URL}/ticker/24hr"
    params = {"symbol": BINANCE_SYMBOL}
    data = await _fetch_json(session, url, params=params)

    if not data:
        return {}

    return {
        "source": "binance",
        "symbol": BINANCE_SYMBOL,
        "price_change_pct": float(data.get("priceChangePercent", 0)),
        "weighted_avg_price": float(data.get("weightedAvgPrice", 0)),
        "last_price": float(data.get("lastPrice", 0)),
        "volume": float(data.get("volume", 0)),
        "quote_volume": float(data.get("quoteVolume", 0)),
        "open_price": float(data.get("openPrice", 0)),
        "high_price": float(data.get("highPrice", 0)),
        "low_price": float(data.get("lowPrice", 0)),
        "count": int(data.get("count", 0)),
    }


async def scrape_price_data() -> dict[str, Any]:
    """Main entry point — collects all price data."""
    logger.info("📊 Fetching price data from CoinGecko + Binance...")

    async with aiohttp.ClientSession() as session:
        coingecko_task = fetch_coingecko_data(session)
        binance_ticker_task = fetch_binance_ticker(session)
        binance_candles_4h_task = fetch_binance_candles(session, "4h", 50)
        binance_candles_1d_task = fetch_binance_candles(session, "1d", 30)

        coingecko, binance_ticker, candles_4h, candles_1d = await asyncio.gather(
            coingecko_task, binance_ticker_task, binance_candles_4h_task, binance_candles_1d_task
        )

    result = {
        "coingecko": coingecko,
        "binance_ticker": binance_ticker,
        "candles_4h": candles_4h,
        "candles_1d": candles_1d,
    }

    price = coingecko.get("price_usd") or binance_ticker.get("last_price")
    logger.info(f"  ✅ SOL Price: ${price} | 24h: {coingecko.get('price_change_24h_pct', 'N/A')}%")
    logger.info(f"  ✅ Candles: {len(candles_4h)} (4h), {len(candles_1d)} (1d)")

    return result


# Allow running standalone for testing
if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    data = asyncio.run(scrape_price_data())
    # Print summary, not full candle data
    summary = {k: v for k, v in data.items() if k not in ("candles_4h", "candles_1d")}
    summary["candles_4h_count"] = len(data.get("candles_4h", []))
    summary["candles_1d_count"] = len(data.get("candles_1d", []))
    print(json.dumps(summary, indent=2, default=str))
