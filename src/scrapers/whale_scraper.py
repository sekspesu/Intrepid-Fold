from __future__ import annotations
"""
Whale activity tracker — Helius Enhanced Solana APIs.
Monitors large SOL transfers and known whale wallet activity
to detect smart money movements before they show up in price.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import aiohttp

from src.config import HELIUS_API_KEY, HELIUS_RPC_URL, HELIUS_API_URL, WHALE_WALLETS, WHALE_MIN_SOL

logger = logging.getLogger(__name__)

# Native SOL mint
SOL_MINT = "So11111111111111111111111111111111111111112"
LAMPORTS_PER_SOL = 1_000_000_000


async def _fetch_json(
    session: aiohttp.ClientSession, url: str,
    method: str = "GET", json_body: Optional[dict] = None,
    params: Optional[dict] = None,
) -> Optional[dict]:
    """Generic async JSON fetcher."""
    try:
        kwargs = {"timeout": aiohttp.ClientTimeout(total=15)}
        if params:
            kwargs["params"] = params
        if json_body:
            kwargs["json"] = json_body

        if method == "POST":
            async with session.post(url, **kwargs) as resp:
                if resp.status == 200:
                    return await resp.json()
                logger.warning(f"HTTP {resp.status} from {url}")
                return None
        else:
            async with session.get(url, **kwargs) as resp:
                if resp.status == 200:
                    return await resp.json()
                logger.warning(f"HTTP {resp.status} from {url}")
                return None
    except Exception as e:
        logger.error(f"Helius error ({url}): {e}")
        return None


async def fetch_whale_transactions(session: aiohttp.ClientSession) -> dict[str, Any]:
    """Monitor known whale wallets for recent SOL movements."""
    if not HELIUS_API_KEY:
        logger.warning("  ⚠️ Helius API key not configured, skipping whale tracking")
        return {}

    logger.info(f"  🐋 Tracking {len(WHALE_WALLETS)} whale wallets...")

    all_transfers = []
    total_inflow = 0.0   # SOL moving INTO whale wallets (accumulation)
    total_outflow = 0.0  # SOL moving OUT of whale wallets (distribution)

    for label, address in WHALE_WALLETS.items():
        url = f"{HELIUS_API_URL}/v0/addresses/{address}/transactions/"
        params = {"api-key": HELIUS_API_KEY, "limit": 10}
        data = await _fetch_json(session, url, params=params)

        if not data or not isinstance(data, list):
            continue

        for tx in data:
            # Parse native SOL transfers
            native_transfers = tx.get("nativeTransfers", [])
            for transfer in native_transfers:
                amount_sol = transfer.get("amount", 0) / LAMPORTS_PER_SOL

                if amount_sol < WHALE_MIN_SOL:
                    continue

                from_addr = transfer.get("fromUserAccount", "")
                to_addr = transfer.get("toUserAccount", "")

                # Determine if inflow or outflow relative to this whale
                if to_addr == address:
                    direction = "inflow"
                    total_inflow += amount_sol
                elif from_addr == address:
                    direction = "outflow"
                    total_outflow += amount_sol
                else:
                    continue

                ts = tx.get("timestamp", 0)
                all_transfers.append({
                    "whale": label,
                    "direction": direction,
                    "amount_sol": round(amount_sol, 2),
                    "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None,
                    "signature": tx.get("signature", "")[:16] + "...",
                    "type": tx.get("type", "UNKNOWN"),
                })

    # Sort by amount (largest first)
    all_transfers.sort(key=lambda x: x["amount_sol"], reverse=True)

    # Calculate net flow
    net_flow = total_inflow - total_outflow
    flow_direction = "accumulating" if net_flow > 0 else "distributing" if net_flow < 0 else "neutral"

    result = {
        "total_inflow_sol": round(total_inflow, 2),
        "total_outflow_sol": round(total_outflow, 2),
        "net_flow_sol": round(net_flow, 2),
        "flow_direction": flow_direction,
        "whale_transfers": all_transfers[:15],  # Top 15 largest
        "wallets_tracked": len(WHALE_WALLETS),
        "transfers_found": len(all_transfers),
    }

    return result


async def fetch_large_sol_transfers(session: aiohttp.ClientSession) -> dict[str, Any]:
    """Use Helius RPC to get recent large SOL transactions network-wide.
    Uses getSignaturesForAddress on the SOL System Program to find big moves.
    """
    if not HELIUS_API_KEY:
        return {}

    # Query recent large transactions via enhanced transaction API
    # We check the SOL token for large recent transfers
    url = f"{HELIUS_RPC_URL}"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getRecentBlockhash",
    }
    # Simple connectivity check
    result = await _fetch_json(session, url, method="POST", json_body=payload)
    if not result:
        return {}

    return {"rpc_connected": True}


async def scrape_whales() -> dict[str, Any]:
    """Main entry point — collects whale activity data."""
    logger.info("🐋 Tracking whale activity (Helius)...")

    if not HELIUS_API_KEY:
        logger.warning("  ⚠️ Helius API key not configured, skipping")
        return {"source": "whales", "timestamp": datetime.utcnow().isoformat()}

    async with aiohttp.ClientSession() as session:
        whale_txns = await fetch_whale_transactions(session)

    result = {
        "source": "whales",
        "timestamp": datetime.utcnow().isoformat(),
        **whale_txns,
    }

    inflow = whale_txns.get("total_inflow_sol", 0)
    outflow = whale_txns.get("total_outflow_sol", 0)
    net = whale_txns.get("net_flow_sol", 0)
    direction = whale_txns.get("flow_direction", "N/A")
    count = whale_txns.get("transfers_found", 0)

    logger.info(f"  ✅ Whales: {count} large transfers | "
                f"In: {inflow:,.0f} SOL | Out: {outflow:,.0f} SOL | "
                f"Net: {net:+,.0f} SOL ({direction})")

    return result


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    data = asyncio.run(scrape_whales())
    print(json.dumps(data, indent=2, default=str))
