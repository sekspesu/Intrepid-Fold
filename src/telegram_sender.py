from __future__ import annotations
"""
Telegram Signal Sender.
Formats trading predictions into rich Telegram messages and delivers them.
"""

import asyncio
import logging
from typing import Any

from telegram import Bot
from telegram.constants import ParseMode

from src.config import DRY_RUN, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS

logger = logging.getLogger(__name__)

TELEGRAM_MSG_LIMIT = 4096


def format_prediction_message(prediction: dict) -> str:
    """Format prediction data into a rich Telegram message."""
    direction = prediction.get("direction", "NEUTRAL")
    confidence = prediction.get("confidence", 0)
    strength = prediction.get("strength", "WEAK")
    price = prediction.get("current_price_usd")
    price_change = prediction.get("price_change_24h_pct")
    weighted_score = prediction.get("weighted_score", 0)
    timeframe = prediction.get("timeframe", "24h")

    # Direction emoji
    if direction == "LONG":
        dir_emoji = "🟢"
        dir_word = "LONG (Buy)"
    elif direction == "SHORT":
        dir_emoji = "🔴"
        dir_word = "SHORT (Sell)"
    else:
        dir_emoji = "🟡"
        dir_word = "NEUTRAL (Hold)"

    # Strength bar
    filled = int(confidence / 10)
    strength_bar = "█" * filled + "░" * (10 - filled)

    # Price formatting
    price_str = f"${price:,.2f}" if price else "N/A"
    change_str = f"{price_change:+.2f}%" if price_change is not None else "N/A"
    change_emoji = "📈" if (price_change or 0) > 0 else "📉"

    # Build signal breakdown
    scores = prediction.get("signal_scores", {})
    signal_lines = []
    signal_emojis = {
        "technical": "📊",
        "onchain": "🔗",
        "whales": "🐋",
        "news": "📰",
        "social": "📱",
        "fear_greed": "😱",
        "youtube": "🎥",
    }

    for key, score in sorted(scores.items(), key=lambda x: abs(x[1]), reverse=True):
        emoji = signal_emojis.get(key, "•")
        label = key.replace("_", " ").title()
        direction_arrow = "↑" if score > 0 else "↓" if score < 0 else "→"
        bar_pos = int((score + 1) * 5)  # Map [-1,1] to [0,10]
        mini_bar = "▪" * bar_pos + "▫" * (10 - bar_pos)
        signal_lines.append(f"{emoji} {label}: {score:+.2f} {direction_arrow} [{mini_bar}]")

    # Top factors
    top_factors = prediction.get("top_factors", [])
    factor_lines = []
    for i, f in enumerate(top_factors[:3], 1):
        factor_lines.append(f"  {i}. {f.get('description', 'N/A')}")

    # Agreement info
    bulls = prediction.get("signals_bullish", 0)
    bears = prediction.get("signals_bearish", 0)
    agreement = prediction.get("signal_agreement", 0)

    message = f"""{dir_emoji} *SOL SIGNAL: {dir_word}*
━━━━━━━━━━━━━━━━━━━━

💰 *Price:* {price_str} ({change_emoji} {change_str})
🎯 *Confidence:* {confidence}% ({strength})
[{strength_bar}]
⏱ *Timeframe:* {timeframe}
📐 *Score:* {weighted_score:+.3f}

━━━ *SIGNAL BREAKDOWN* ━━━

{chr(10).join(signal_lines)}

━━━ *KEY FACTORS* ━━━

{chr(10).join(factor_lines)}

📊 *Agreement:* {bulls} bullish / {bears} bearish ({agreement:.0%} agree)

⚠️ _Not financial advice. Always DYOR._
🤖 _Solana Community Mood Tracker v1.0_"""

    return message


def _split_message(text: str) -> list[str]:
    """Split a long message at natural line breaks."""
    if len(text) <= TELEGRAM_MSG_LIMIT:
        return [text]

    messages = []
    current = ""

    for line in text.split("\n"):
        if len(current) + len(line) + 1 > TELEGRAM_MSG_LIMIT:
            messages.append(current)
            current = line
        else:
            current += "\n" + line if current else line

    if current:
        messages.append(current)

    return messages


async def send_prediction(prediction: dict) -> bool:
    """Format and send prediction to all configured Telegram chats."""
    logger.info("📤 Sending prediction to Telegram...")

    message = format_prediction_message(prediction)

    if DRY_RUN:
        logger.info("  🏃 DRY RUN — Message not sent. Preview:")
        print("\n" + "=" * 50)
        print(message)
        print("=" * 50 + "\n")
        return True

    if not TELEGRAM_BOT_TOKEN:
        logger.warning("  ⚠️ Telegram bot token not configured")
        return False

    if not TELEGRAM_CHAT_IDS:
        logger.warning("  ⚠️ No Telegram chat IDs configured")
        return False

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    messages = _split_message(message)
    success = True

    for chat_id in TELEGRAM_CHAT_IDS:
        for msg_part in messages:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=msg_part,
                    parse_mode=ParseMode.MARKDOWN,
                )
                logger.info(f"  ✅ Sent to {chat_id}")
            except Exception as e:
                logger.warning(f"  ⚠️ Markdown failed for {chat_id}, trying plain text: {e}")
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=msg_part,
                    )
                    logger.info(f"  ✅ Sent (plain text) to {chat_id}")
                except Exception as e2:
                    logger.error(f"  ❌ Failed to send to {chat_id}: {e2}")
                    success = False

    return success
