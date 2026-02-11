"""
On-chain analytics scraper — DexScreener + DefiLlama.
Tracks whale movements, DEX volume, TVL trends on Solana.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import aiohttp

from src.config import (
    DEFILLAMA_BASE_URL,
    DEFILLAMA_CHAIN,
    DEXSCREENER_BASE_URL,
    DEXSCREENER_CHAIN,
)

logger = logging.getLogger(__name__)


async def _fetch_json(session: aiohttp.ClientSession, url: str, params: Optional[dict] = None) -> Optional[Union[dict, list]]:
    """Generic async JSON fetcher."""
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status == 200:
                return await resp.json()
            logger.warning(f"HTTP {resp.status} from {url}")
            return None
    except Exception as e:
        logger.error(f"Error fetching {url}: {e}")
        return None


async def fetch_dex_data(session: aiohttp.ClientSession) -> dict[str, Any]:
    """Fetch top SOL trading pairs and volume from DexScreener."""
    # Search for SOL pairs
    url = f"{DEXSCREENER_BASE_URL}/dex/tokens/So11111111111111111111111111111111111111112"
    data = await _fetch_json(session, url)

    if not data or "pairs" not in data:
        return {}

    pairs = data.get("pairs", [])[:20]  # Top 20 pairs

    total_volume_24h = 0
    total_liquidity = 0
    top_pairs = []

    for pair in pairs:
        vol = float(pair.get("volume", {}).get("h24", 0) or 0)
        liq = float(pair.get("liquidity", {}).get("usd", 0) or 0)
        total_volume_24h += vol
        total_liquidity += liq

        price_change = pair.get("priceChange", {})

        top_pairs.append({
            "pair": pair.get("baseToken", {}).get("symbol", "?") + "/" + pair.get("quoteToken", {}).get("symbol", "?"),
            "dex": pair.get("dexId", "unknown"),
            "price_usd": pair.get("priceUsd"),
            "volume_24h": vol,
            "liquidity_usd": liq,
            "price_change_5m": price_change.get("m5"),
            "price_change_1h": price_change.get("h1"),
            "price_change_6h": price_change.get("h6"),
            "price_change_24h": price_change.get("h24"),
            "txns_buys_24h": pair.get("txns", {}).get("h24", {}).get("buys", 0),
            "txns_sells_24h": pair.get("txns", {}).get("h24", {}).get("sells", 0),
        })

    # Buy/sell ratio across all pairs
    total_buys = sum(p.get("txns_buys_24h", 0) for p in top_pairs)
    total_sells = sum(p.get("txns_sells_24h", 0) for p in top_pairs)
    buy_sell_ratio = total_buys / max(total_sells, 1)

    return {
        "total_volume_24h": total_volume_24h,
        "total_liquidity": total_liquidity,
        "total_buys_24h": total_buys,
        "total_sells_24h": total_sells,
        "buy_sell_ratio": round(buy_sell_ratio, 3),
        "buy_pressure": (
            "strong_buy" if buy_sell_ratio > 1.3
            else "buy" if buy_sell_ratio > 1.05
            else "sell" if buy_sell_ratio < 0.95
            else "strong_sell" if buy_sell_ratio < 0.7
            else "neutral"
        ),
        "top_pairs": top_pairs[:10],
    }


async def fetch_tvl_data(session: aiohttp.ClientSession) -> dict[str, Any]:
    """Fetch Solana TVL (Total Value Locked) from DefiLlama."""
    # Current TVL
    url = f"{DEFILLAMA_BASE_URL}/v2/chains"
    chains_data = await _fetch_json(session, url)

    if not chains_data:
        return {}

    solana_chain = None
    for chain in chains_data:
        if chain.get("name", "").lower() == DEFILLAMA_CHAIN.lower():
            solana_chain = chain
            break

    if not solana_chain:
        return {}

    # Historical TVL
    hist_url = f"{DEFILLAMA_BASE_URL}/v2/historicalChainTvl/{DEFILLAMA_CHAIN}"
    historical = await _fetch_json(session, hist_url)

    tvl_current = solana_chain.get("tvl", 0)
    tvl_history = []

    if historical and isinstance(historical, list):
        # Get last 30 data points
        recent = historical[-30:]
        tvl_history = [
            {
                "date": datetime.fromtimestamp(entry.get("date", 0)).strftime("%Y-%m-%d"),
                "tvl": entry.get("tvl", 0),
            }
            for entry in recent
        ]

        # Calculate TVL changes
        if len(recent) >= 7:
            tvl_7d_ago = recent[-7].get("tvl", tvl_current)
            tvl_change_7d = ((tvl_current - tvl_7d_ago) / max(tvl_7d_ago, 1)) * 100
        else:
            tvl_change_7d = 0

        if len(recent) >= 30:
            tvl_30d_ago = recent[0].get("tvl", tvl_current)
            tvl_change_30d = ((tvl_current - tvl_30d_ago) / max(tvl_30d_ago, 1)) * 100
        else:
            tvl_change_30d = 0
    else:
        tvl_change_7d = 0
        tvl_change_30d = 0

    return {
        "tvl_current": tvl_current,
        "tvl_change_7d_pct": round(tvl_change_7d, 2),
        "tvl_change_30d_pct": round(tvl_change_30d, 2),
        "tvl_trend": (
            "growing" if tvl_change_7d > 2
            else "declining" if tvl_change_7d < -2
            else "stable"
        ),
        "tvl_history_30d": tvl_history,
    }


async def fetch_protocol_data(session: aiohttp.ClientSession) -> list[dict]:
    """Fetch top Solana protocols by TVL from DefiLlama."""
    url = f"{DEFILLAMA_BASE_URL}/protocols"
    data = await _fetch_json(session, url)

    if not data:
        return []

    # Filter for Solana protocols
    sol_protocols = [
        p for p in data
        if DEFILLAMA_CHAIN.lower() in [c.lower() for c in p.get("chains", [])]
    ]

    # Sort by TVL
    sol_protocols.sort(key=lambda x: x.get("tvl", 0) or 0, reverse=True)

    return [
        {
            "name": p.get("name"),
            "category": p.get("category"),
            "tvl": p.get("tvl"),
            "tvl_change_1d_pct": p.get("change_1d"),
            "tvl_change_7d_pct": p.get("change_7d"),
        }
        for p in sol_protocols[:15]  # Top 15 protocols
    ]


async def scrape_onchain() -> dict[str, Any]:
    """Main entry point — collects all on-chain analytics."""
    logger.info("🔗 Fetching on-chain analytics (DexScreener + DefiLlama)...")

    async with aiohttp.ClientSession() as session:
        dex_data, tvl_data, protocols = await asyncio.gather(
            fetch_dex_data(session),
            fetch_tvl_data(session),
            fetch_protocol_data(session),
        )

    result = {
        "source": "onchain",
        "timestamp": datetime.utcnow().isoformat(),
        "dex": dex_data,
        "tvl": tvl_data,
        "top_protocols": protocols,
    }

    vol = dex_data.get("total_volume_24h", 0)
    tvl = tvl_data.get("tvl_current", 0)
    pressure = dex_data.get("buy_pressure", "N/A")
    logger.info(f"  ✅ DEX Volume 24h: ${vol:,.0f} | TVL: ${tvl:,.0f} | Buy Pressure: {pressure}")

    return result


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    data = asyncio.run(scrape_onchain())
    # Print without full history arrays
    summary = {
        "dex_volume_24h": data.get("dex", {}).get("total_volume_24h"),
        "buy_sell_ratio": data.get("dex", {}).get("buy_sell_ratio"),
        "buy_pressure": data.get("dex", {}).get("buy_pressure"),
        "tvl_current": data.get("tvl", {}).get("tvl_current"),
        "tvl_change_7d": data.get("tvl", {}).get("tvl_change_7d_pct"),
        "tvl_trend": data.get("tvl", {}).get("tvl_trend"),
        "top_protocols": [p["name"] for p in data.get("top_protocols", [])[:5]],
    }
    print(json.dumps(summary, indent=2, default=str))
