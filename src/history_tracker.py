"""
History Tracker — Prediction Logging & Accuracy.
Stores every prediction and later checks actual price movement
to calculate rolling accuracy metrics.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import aiohttp

from src.config import BINANCE_BASE_URL, BINANCE_SYMBOL, DATA_DIR, PREDICTIONS_FILE

logger = logging.getLogger(__name__)


def _ensure_data_dir():
    """Ensure data directory exists."""
    os.makedirs(DATA_DIR, exist_ok=True)


def _load_predictions() -> list[dict]:
    """Load existing predictions from JSON file."""
    if not os.path.exists(PREDICTIONS_FILE):
        return []
    try:
        with open(PREDICTIONS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_predictions(predictions: list[dict]):
    """Save predictions to JSON file."""
    _ensure_data_dir()
    with open(PREDICTIONS_FILE, "w") as f:
        json.dump(predictions, f, indent=2, default=str)


def log_prediction(prediction: dict):
    """Log a new prediction to the history file."""
    logger.info("📝 Logging prediction to history...")

    predictions = _load_predictions()

    record = {
        "id": len(predictions) + 1,
        "timestamp": prediction.get("timestamp", datetime.utcnow().isoformat()),
        "direction": prediction.get("direction"),
        "confidence": prediction.get("confidence"),
        "strength": prediction.get("strength"),
        "weighted_score": prediction.get("weighted_score"),
        "price_at_prediction": prediction.get("current_price_usd"),
        "timeframe": prediction.get("timeframe", "24h"),
        "signal_scores": prediction.get("signal_scores"),
        # To be filled later
        "price_after": None,
        "actual_change_pct": None,
        "was_correct": None,
        "checked_at": None,
    }

    predictions.append(record)
    _save_predictions(predictions)
    logger.info(f"  ✅ Prediction #{record['id']} logged (${record['price_at_prediction']})")


async def check_prediction_results():
    """Check unchecked predictions and record actual price movements."""
    logger.info("📊 Checking prediction results...")

    predictions = _load_predictions()
    updated = False

    # Get current price
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{BINANCE_BASE_URL}/ticker/price"
            params = {"symbol": BINANCE_SYMBOL}
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    current_price = float(data.get("price", 0))
                else:
                    logger.warning("Could not fetch current price for result checking")
                    return
    except Exception as e:
        logger.error(f"Error fetching price for results: {e}")
        return

    now = datetime.now(timezone.utc)

    for pred in predictions:
        if pred.get("was_correct") is not None:
            continue  # Already checked

        # Check if enough time has passed based on timeframe
        try:
            ts_str = pred["timestamp"]
            if "+" not in ts_str and "Z" not in ts_str:
                ts_str += "+00:00"
            pred_time = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if pred_time.tzinfo is None:
                pred_time = pred_time.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue

        timeframe = pred.get("timeframe", "24h")
        hours = int(timeframe.replace("h", "").replace("d", "")) if "h" in timeframe else int(timeframe.replace("d", "")) * 24

        if now - pred_time < timedelta(hours=hours):
            continue  # Not enough time passed

        # Calculate result
        price_at = pred.get("price_at_prediction")
        if not price_at or price_at == 0:
            continue

        actual_change = ((current_price - price_at) / price_at) * 100
        direction = pred.get("direction")

        if direction == "LONG":
            was_correct = actual_change > 0
        elif direction == "SHORT":
            was_correct = actual_change < 0
        else:  # NEUTRAL
            was_correct = abs(actual_change) < 2  # Within 2% = neutral was correct

        pred["price_after"] = current_price
        pred["actual_change_pct"] = round(actual_change, 2)
        pred["was_correct"] = was_correct
        pred["checked_at"] = now.isoformat()
        updated = True

        emoji = "✅" if was_correct else "❌"
        logger.info(f"  {emoji} Prediction #{pred['id']}: {direction} → "
                     f"Price moved {actual_change:+.2f}% ({'correct' if was_correct else 'incorrect'})")

    if updated:
        _save_predictions(predictions)


def get_accuracy_stats() -> dict[str, Any]:
    """Calculate rolling accuracy statistics."""
    predictions = _load_predictions()
    checked = [p for p in predictions if p.get("was_correct") is not None]

    if not checked:
        return {"total_predictions": len(predictions), "checked": 0, "message": "No results checked yet"}

    total = len(checked)
    correct = sum(1 for p in checked if p["was_correct"])
    accuracy = (correct / total) * 100 if total > 0 else 0

    # Per-direction accuracy
    direction_stats = {}
    for direction in ["LONG", "SHORT", "NEUTRAL"]:
        dir_preds = [p for p in checked if p.get("direction") == direction]
        if dir_preds:
            dir_correct = sum(1 for p in dir_preds if p["was_correct"])
            direction_stats[direction] = {
                "total": len(dir_preds),
                "correct": dir_correct,
                "accuracy": round((dir_correct / len(dir_preds)) * 100, 1),
            }

    # Rolling accuracy (last 7d, 30d)
    now = datetime.now(timezone.utc)
    last_7d = [p for p in checked if _parse_time(p["timestamp"]) and now - _parse_time(p["timestamp"]) < timedelta(days=7)]
    last_30d = [p for p in checked if _parse_time(p["timestamp"]) and now - _parse_time(p["timestamp"]) < timedelta(days=30)]

    def _calc_acc(preds):
        if not preds:
            return None
        c = sum(1 for p in preds if p["was_correct"])
        return round((c / len(preds)) * 100, 1)

    # Find best performing signal source
    signal_accuracy = {}
    for pred in checked:
        scores = pred.get("signal_scores", {})
        direction = pred.get("direction")
        was_correct = pred.get("was_correct")

        for signal, score in scores.items():
            if signal not in signal_accuracy:
                signal_accuracy[signal] = {"correct": 0, "total": 0}

            signal_agreed = (
                (score > 0 and direction == "LONG") or
                (score < 0 and direction == "SHORT")
            )
            if signal_agreed:
                signal_accuracy[signal]["total"] += 1
                if was_correct:
                    signal_accuracy[signal]["correct"] += 1

    best_signals = {
        k: round((v["correct"] / max(v["total"], 1)) * 100, 1)
        for k, v in signal_accuracy.items()
        if v["total"] >= 3  # Min sample size
    }

    return {
        "total_predictions": len(predictions),
        "checked": total,
        "correct": correct,
        "overall_accuracy": round(accuracy, 1),
        "accuracy_7d": _calc_acc(last_7d),
        "accuracy_30d": _calc_acc(last_30d),
        "direction_stats": direction_stats,
        "signal_accuracy": best_signals,
    }


def _parse_time(ts: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError, AttributeError):
        return None


if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)

    stats = get_accuracy_stats()
    print(json.dumps(stats, indent=2, default=str))

    # Also check any pending results
    asyncio.run(check_prediction_results())
    print("\nUpdated stats:")
    stats = get_accuracy_stats()
    print(json.dumps(stats, indent=2, default=str))
