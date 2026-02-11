from __future__ import annotations
"""
Technical Analysis Calculator.
Computes RSI, MACD, Bollinger Bands, EMA crossovers from OHLCV data.
Uses pandas + ta library for indicator calculations.
"""

import logging
from typing import Any

import numpy as np
import pandas as pd
import ta

from src.config import (
    TA_BB_PERIOD,
    TA_BB_STD,
    TA_EMA_LONG,
    TA_EMA_MEDIUM,
    TA_EMA_SHORT,
    TA_EMA_VERY_LONG,
    TA_MACD_FAST,
    TA_MACD_SIGNAL,
    TA_MACD_SLOW,
    TA_RSI_PERIOD,
)

logger = logging.getLogger(__name__)


def _candles_to_df(candles: list[dict]) -> pd.DataFrame:
    """Convert candle data to pandas DataFrame."""
    if not candles:
        return pd.DataFrame()

    df = pd.DataFrame(candles)
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def calculate_rsi(df: pd.DataFrame) -> dict[str, Any]:
    """Calculate RSI (Relative Strength Index)."""
    if df.empty or len(df) < TA_RSI_PERIOD + 1:
        return {"value": None, "signal": "neutral"}

    rsi = ta.momentum.RSIIndicator(df["close"], window=TA_RSI_PERIOD)
    rsi_value = rsi.rsi().iloc[-1]

    if pd.isna(rsi_value):
        return {"value": None, "signal": "neutral"}

    rsi_value = round(float(rsi_value), 2)

    if rsi_value >= 70:
        signal = "overbought"
        score = -0.5 - ((rsi_value - 70) / 30) * 0.5  # -0.5 to -1.0
    elif rsi_value <= 30:
        signal = "oversold"
        score = 0.5 + ((30 - rsi_value) / 30) * 0.5  # +0.5 to +1.0
    elif rsi_value >= 60:
        signal = "bullish"
        score = 0.2
    elif rsi_value <= 40:
        signal = "bearish"
        score = -0.2
    else:
        signal = "neutral"
        score = 0.0

    return {"value": rsi_value, "signal": signal, "score": round(score, 3)}


def calculate_macd(df: pd.DataFrame) -> dict[str, Any]:
    """Calculate MACD (Moving Average Convergence Divergence)."""
    if df.empty or len(df) < TA_MACD_SLOW + TA_MACD_SIGNAL:
        return {"signal": "neutral", "score": 0}

    macd_indicator = ta.trend.MACD(
        df["close"],
        window_slow=TA_MACD_SLOW,
        window_fast=TA_MACD_FAST,
        window_sign=TA_MACD_SIGNAL,
    )

    macd_line = macd_indicator.macd().iloc[-1]
    signal_line = macd_indicator.macd_signal().iloc[-1]
    histogram = macd_indicator.macd_diff().iloc[-1]

    if pd.isna(macd_line) or pd.isna(signal_line):
        return {"signal": "neutral", "score": 0}

    # Check for crossover
    prev_macd = macd_indicator.macd().iloc[-2]
    prev_signal = macd_indicator.macd_signal().iloc[-2]

    bullish_crossover = prev_macd < prev_signal and macd_line > signal_line
    bearish_crossover = prev_macd > prev_signal and macd_line < signal_line

    if bullish_crossover:
        signal = "bullish_crossover"
        score = 0.8
    elif bearish_crossover:
        signal = "bearish_crossover"
        score = -0.8
    elif macd_line > signal_line and histogram > 0:
        signal = "bullish"
        score = 0.4
    elif macd_line < signal_line and histogram < 0:
        signal = "bearish"
        score = -0.4
    else:
        signal = "neutral"
        score = 0.0

    return {
        "macd_line": round(float(macd_line), 6),
        "signal_line": round(float(signal_line), 6),
        "histogram": round(float(histogram), 6),
        "signal": signal,
        "score": round(score, 3),
    }


def calculate_bollinger_bands(df: pd.DataFrame) -> dict[str, Any]:
    """Calculate Bollinger Bands."""
    if df.empty or len(df) < TA_BB_PERIOD:
        return {"signal": "neutral", "score": 0}

    bb = ta.volatility.BollingerBands(
        df["close"], window=TA_BB_PERIOD, window_dev=TA_BB_STD
    )

    upper = bb.bollinger_hband().iloc[-1]
    middle = bb.bollinger_mavg().iloc[-1]
    lower = bb.bollinger_lband().iloc[-1]
    current_price = df["close"].iloc[-1]
    bandwidth = bb.bollinger_wband().iloc[-1]

    if pd.isna(upper) or pd.isna(lower):
        return {"signal": "neutral", "score": 0}

    # Position within bands (0 = lower, 1 = upper)
    band_range = upper - lower
    if band_range > 0:
        position = (current_price - lower) / band_range
    else:
        position = 0.5

    # Narrow bandwidth = potential breakout
    squeeze = bandwidth < 0.05  # Tight squeeze

    if current_price >= upper:
        signal = "overbought"
        score = -0.5
    elif current_price <= lower:
        signal = "oversold"
        score = 0.5
    elif squeeze:
        signal = "squeeze"
        score = 0.0  # Direction unclear, but volatility incoming
    elif position > 0.7:
        signal = "upper_zone"
        score = -0.2
    elif position < 0.3:
        signal = "lower_zone"
        score = 0.2
    else:
        signal = "middle"
        score = 0.0

    return {
        "upper": round(float(upper), 4),
        "middle": round(float(middle), 4),
        "lower": round(float(lower), 4),
        "position": round(float(position), 3),
        "bandwidth": round(float(bandwidth), 6),
        "squeeze": squeeze,
        "signal": signal,
        "score": round(score, 3),
    }


def calculate_ema_crossovers(df: pd.DataFrame) -> dict[str, Any]:
    """Calculate EMA crossovers (9/21 and 50/200)."""
    signals = {}

    if len(df) < TA_EMA_VERY_LONG:
        # Can still calculate short EMAs
        pass

    ema_configs = [
        ("short", TA_EMA_SHORT, TA_EMA_MEDIUM),    # 9/21
        ("long", TA_EMA_LONG, TA_EMA_VERY_LONG),   # 50/200
    ]

    total_score = 0
    count = 0

    for name, fast_period, slow_period in ema_configs:
        if len(df) < slow_period + 2:
            continue

        ema_fast = df["close"].ewm(span=fast_period, adjust=False).mean()
        ema_slow = df["close"].ewm(span=slow_period, adjust=False).mean()

        curr_fast = ema_fast.iloc[-1]
        curr_slow = ema_slow.iloc[-1]
        prev_fast = ema_fast.iloc[-2]
        prev_slow = ema_slow.iloc[-2]

        golden_cross = prev_fast < prev_slow and curr_fast > curr_slow
        death_cross = prev_fast > prev_slow and curr_fast < curr_slow

        if golden_cross:
            signal = "golden_cross"
            score = 0.7 if name == "long" else 0.5
        elif death_cross:
            signal = "death_cross"
            score = -0.7 if name == "long" else -0.5
        elif curr_fast > curr_slow:
            signal = "bullish"
            score = 0.3
        else:
            signal = "bearish"
            score = -0.3

        signals[f"ema_{name}"] = {
            f"ema_{fast_period}": round(float(curr_fast), 4),
            f"ema_{slow_period}": round(float(curr_slow), 4),
            "signal": signal,
            "score": round(score, 3),
        }
        total_score += score
        count += 1

    avg_score = total_score / max(count, 1)
    signals["combined_score"] = round(avg_score, 3)

    return signals


def calculate_volume_analysis(df: pd.DataFrame) -> dict[str, Any]:
    """Analyze volume patterns for unusual activity."""
    if df.empty or len(df) < 10:
        return {"signal": "neutral", "score": 0}

    volumes = df["volume"].values
    current_vol = volumes[-1]
    avg_vol_10 = np.mean(volumes[-10:])
    avg_vol_20 = np.mean(volumes[-20:]) if len(volumes) >= 20 else avg_vol_10

    vol_ratio = current_vol / max(avg_vol_10, 1)

    # Price direction with volume
    price_change = (df["close"].iloc[-1] - df["close"].iloc[-2]) / max(df["close"].iloc[-2], 0.01)
    price_up = price_change > 0

    if vol_ratio > 2.0:
        if price_up:
            signal = "high_volume_rally"
            score = 0.6
        else:
            signal = "high_volume_selloff"
            score = -0.6
    elif vol_ratio > 1.5:
        if price_up:
            signal = "above_avg_buying"
            score = 0.3
        else:
            signal = "above_avg_selling"
            score = -0.3
    elif vol_ratio < 0.5:
        signal = "low_volume"
        score = 0.0  # Low conviction either way
    else:
        signal = "normal"
        score = 0.1 if price_up else -0.1

    return {
        "current_volume": float(current_vol),
        "avg_10_period": round(float(avg_vol_10), 2),
        "volume_ratio": round(float(vol_ratio), 3),
        "price_direction": "up" if price_up else "down",
        "signal": signal,
        "score": round(score, 3),
    }


def run_technical_analysis(price_data: dict) -> dict[str, Any]:
    """Main entry point — runs all technical analysis on price data."""
    logger.info("📈 Running technical analysis...")

    # Use 4h candles for primary analysis
    candles_4h = price_data.get("candles_4h", [])
    candles_1d = price_data.get("candles_1d", [])

    df_4h = _candles_to_df(candles_4h)
    df_1d = _candles_to_df(candles_1d)

    if df_4h.empty:
        logger.warning("  ⚠️ No candle data available for technical analysis")
        return {"technical_score": 0, "signal": "neutral"}

    # Run all indicators on 4h data
    rsi = calculate_rsi(df_4h)
    macd = calculate_macd(df_4h)
    bollinger = calculate_bollinger_bands(df_4h)
    ema = calculate_ema_crossovers(df_4h)
    volume = calculate_volume_analysis(df_4h)

    # Also check daily RSI for longer-term context
    daily_rsi = calculate_rsi(df_1d) if not df_1d.empty else {"signal": "neutral", "score": 0}

    # Weighted combination of all technical signals
    scores = {
        "rsi": rsi.get("score", 0) * 0.25,
        "macd": macd.get("score", 0) * 0.25,
        "bollinger": bollinger.get("score", 0) * 0.15,
        "ema": ema.get("combined_score", 0) * 0.20,
        "volume": volume.get("score", 0) * 0.15,
    }

    technical_score = sum(scores.values())
    technical_score = max(-1.0, min(1.0, technical_score))  # Clamp to [-1, 1]

    if technical_score > 0.3:
        overall_signal = "bullish"
    elif technical_score < -0.3:
        overall_signal = "bearish"
    else:
        overall_signal = "neutral"

    result = {
        "technical_score": round(technical_score, 3),
        "signal": overall_signal,
        "rsi": rsi,
        "macd": macd,
        "bollinger": bollinger,
        "ema_crossovers": ema,
        "volume": volume,
        "daily_rsi": daily_rsi,
        "component_scores": {k: round(v, 3) for k, v in scores.items()},
    }

    logger.info(f"  ✅ Technical Score: {technical_score:.3f} ({overall_signal})")
    logger.info(f"     RSI: {rsi.get('value', 'N/A')} ({rsi.get('signal')})")
    logger.info(f"     MACD: {macd.get('signal')} | BB: {bollinger.get('signal')}")
    logger.info(f"     Volume: {volume.get('signal')} ({volume.get('volume_ratio', 'N/A')}x avg)")

    return result
