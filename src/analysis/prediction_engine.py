"""
Prediction Engine — Weighted Signal Aggregation.
Combines all analysis signals into a final LONG/SHORT/NEUTRAL prediction
with confidence score and reasoning.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from src.config import CONFIDENCE_HIGH, CONFIDENCE_LOW, CONFIDENCE_MEDIUM, SIGNAL_WEIGHTS

logger = logging.getLogger(__name__)


def _normalize_score(score: Optional[float]) -> float:
    """Normalize any score to [-1.0, +1.0] range."""
    if score is None:
        return 0.0
    return max(-1.0, min(1.0, float(score)))


def _fear_greed_to_score(fg_data: dict) -> float:
    """Convert Fear & Greed Index to a contrarian trading score.
    
    Logic: Extreme fear = bullish contrarian signal, extreme greed = bearish.
    """
    value = fg_data.get("current_value", 50)
    if value is None:
        return 0.0

    # Contrarian: fear is a buy signal, greed is a sell signal
    # 0 = extreme fear → +1.0 (very bullish contrarian)
    # 50 = neutral → 0.0
    # 100 = extreme greed → -1.0 (very bearish contrarian)
    score = (50 - value) / 50
    return round(score, 3)


def _onchain_to_score(onchain_data: dict) -> float:
    """Convert on-chain metrics to a sentiment score."""
    dex = onchain_data.get("dex", {})
    tvl = onchain_data.get("tvl", {})

    scores = []

    # Buy/sell ratio
    buy_pressure = dex.get("buy_pressure", "neutral")
    pressure_map = {
        "strong_buy": 0.8,
        "buy": 0.4,
        "neutral": 0.0,
        "sell": -0.4,
        "strong_sell": -0.8,
    }
    scores.append(pressure_map.get(buy_pressure, 0))

    # TVL trend
    tvl_trend = tvl.get("tvl_trend", "stable")
    trend_map = {"growing": 0.5, "stable": 0.0, "declining": -0.5}
    scores.append(trend_map.get(tvl_trend, 0))

    # TVL 7d change
    tvl_change = tvl.get("tvl_change_7d_pct", 0) or 0
    if tvl_change > 5:
        scores.append(0.4)
    elif tvl_change > 2:
        scores.append(0.2)
    elif tvl_change < -5:
        scores.append(-0.4)
    elif tvl_change < -2:
        scores.append(-0.2)
    else:
        scores.append(0)

    return round(sum(scores) / max(len(scores), 1), 3)


def _whale_to_score(whale_data: dict) -> float:
    """Convert whale activity to a sentiment score.
    
    Whales accumulating = bullish, distributing = bearish.
    """
    flow = whale_data.get("flow_direction", "neutral")
    net_sol = whale_data.get("net_flow_sol", 0)

    if flow == "accumulating":
        # Scale by size: >5000 SOL = strong signal
        if abs(net_sol) > 5000:
            return 0.8
        elif abs(net_sol) > 1000:
            return 0.5
        return 0.3
    elif flow == "distributing":
        if abs(net_sol) > 5000:
            return -0.8
        elif abs(net_sol) > 1000:
            return -0.5
        return -0.3
    return 0.0


def generate_prediction(
    technical_result: dict,
    ai_analysis: dict,
    fear_greed_data: dict,
    onchain_data: dict,
    whale_data: dict,
    price_data: dict,
) -> dict[str, Any]:
    """Generate the final LONG/SHORT/NEUTRAL prediction with confidence.
    
    Combines all signals using configured weights:
    - Technical Analysis: 25%
    - On-Chain Data: 17%
    - Whale Activity: 13%
    - News Sentiment: 15%
    - Social Sentiment: 13%
    - Fear & Greed: 10%
    - YouTube Analysts: 7%
    """
    logger.info("🎯 Generating prediction from all signals...")

    # Extract individual scores
    scores = {
        "technical": _normalize_score(
            technical_result.get("technical_score")
        ),
        "onchain": _normalize_score(
            _onchain_to_score(onchain_data)
        ),
        "whales": _normalize_score(
            _whale_to_score(whale_data)
        ),
        "news": _normalize_score(
            ai_analysis.get("news_sentiment", {}).get("sentiment_score")
        ),
        "social": _normalize_score(
            ai_analysis.get("social_sentiment", {}).get("sentiment_score")
        ),
        "fear_greed": _normalize_score(
            _fear_greed_to_score(fear_greed_data)
        ),
        "youtube": _normalize_score(
            ai_analysis.get("youtube_sentiment", {}).get("sentiment_score")
        ),
    }

    # Weighted aggregation
    weighted_score = sum(
        scores[key] * SIGNAL_WEIGHTS.get(key, 0)
        for key in scores
    )
    weighted_score = round(weighted_score, 3)

    # Determine direction
    if weighted_score > 0.15:
        direction = "LONG"
    elif weighted_score < -0.15:
        direction = "SHORT"
    else:
        direction = "NEUTRAL"

    # Calculate confidence (0-100%)
    # Higher absolute score = higher confidence
    # Also factor in signal agreement
    abs_score = abs(weighted_score)
    base_confidence = abs_score * 100

    # Signal agreement bonus: if most signals agree, boost confidence
    positive_signals = sum(1 for s in scores.values() if s > 0.05)
    negative_signals = sum(1 for s in scores.values() if s < -0.05)
    total_active = positive_signals + negative_signals

    if total_active > 0:
        agreement = max(positive_signals, negative_signals) / total_active
    else:
        agreement = 0.5

    confidence = min(100, base_confidence * (0.7 + 0.3 * agreement))
    confidence = round(confidence, 1)

    # Determine strength label
    if confidence >= CONFIDENCE_HIGH:
        strength = "STRONG"
    elif confidence >= CONFIDENCE_MEDIUM:
        strength = "MODERATE"
    elif confidence >= CONFIDENCE_LOW:
        strength = "WEAK"
    else:
        strength = "VERY WEAK"

    # Build key factors (top 3 most influential signals)
    factor_details = []
    for key, score in sorted(scores.items(), key=lambda x: abs(x[1]), reverse=True):
        weight = SIGNAL_WEIGHTS.get(key, 0)
        contribution = round(score * weight, 3)
        signal_dir = "bullish" if score > 0 else "bearish" if score < 0 else "neutral"

        detail = _get_factor_description(key, score, technical_result, ai_analysis, fear_greed_data, onchain_data, whale_data)
        factor_details.append({
            "source": key,
            "score": round(score, 3),
            "weight": weight,
            "contribution": contribution,
            "direction": signal_dir,
            "description": detail,
        })

    # Current price info
    cg = price_data.get("coingecko", {})
    bt = price_data.get("binance_ticker", {})
    current_price = cg.get("price_usd") or bt.get("last_price")
    price_change_24h = cg.get("price_change_24h_pct")

    prediction = {
        "timestamp": datetime.utcnow().isoformat(),
        "direction": direction,
        "confidence": confidence,
        "strength": strength,
        "weighted_score": weighted_score,
        "current_price_usd": current_price,
        "price_change_24h_pct": price_change_24h,
        "timeframe": "24h",
        "signal_scores": scores,
        "signal_weights": dict(SIGNAL_WEIGHTS),
        "factors": factor_details[:6],
        "top_factors": factor_details[:3],
        "signals_bullish": positive_signals,
        "signals_bearish": negative_signals,
        "signal_agreement": round(agreement, 2),
    }

    logger.info(f"  🎯 PREDICTION: {direction} ({confidence}% confidence, {strength})")
    logger.info(f"     Weighted Score: {weighted_score}")
    logger.info(f"     Signal Agreement: {agreement:.0%}")
    for f in factor_details[:3]:
        logger.info(f"     • {f['source']}: {f['description']}")

    return prediction


def _get_factor_description(
    key: str, score: float,
    technical: dict, ai_analysis: dict,
    fear_greed: dict, onchain: dict,
    whale_data: Optional[dict] = None,
) -> str:
    """Generate human-readable description for each factor."""
    direction = "bullish" if score > 0 else "bearish" if score < 0 else "neutral"

    if key == "technical":
        rsi_val = technical.get("rsi", {}).get("value", "N/A")
        macd_sig = technical.get("macd", {}).get("signal", "N/A")
        return f"TA {direction} — RSI: {rsi_val}, MACD: {macd_sig}"

    elif key == "onchain":
        pressure = onchain.get("dex", {}).get("buy_pressure", "N/A")
        tvl_trend = onchain.get("tvl", {}).get("tvl_trend", "N/A")
        return f"On-chain {direction} — Buy pressure: {pressure}, TVL: {tvl_trend}"

    elif key == "news":
        analysis = ai_analysis.get("news_sentiment", {}).get("analysis", "")
        return f"News {direction} — {analysis[:80]}" if analysis else f"News sentiment {direction}"

    elif key == "social":
        analysis = ai_analysis.get("social_sentiment", {}).get("analysis", "")
        return f"Social {direction} — {analysis[:80]}" if analysis else f"Social sentiment {direction}"

    elif key == "fear_greed":
        val = fear_greed.get("current_value", "N/A")
        cls = fear_greed.get("classification", "N/A")
        return f"Fear & Greed: {val} ({cls}) → contrarian {direction}"

    elif key == "youtube":
        count = ai_analysis.get("youtube_sentiment", {}).get("videos_analyzed", 0)
        return f"YouTube {direction} — {count} analyst videos analyzed"

    elif key == "whales":
        wd = whale_data or {}
        net = wd.get("net_flow_sol", 0)
        flow = wd.get("flow_direction", "unknown")
        count = wd.get("transfers_found", 0)
        return f"Whales {flow} — Net flow: {net:+,.0f} SOL ({count} large transfers)"

    return f"{key}: {direction} (score: {score:.3f})"
