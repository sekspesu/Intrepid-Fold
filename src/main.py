"""
Solana Community Mood Tracker — Main Orchestrator.
Runs the full pipeline: collect data → analyze → assess mood → report.
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime

import pytz

from src.config import DRY_RUN, RUN_INTERVAL_HOURS, TIMEZONE

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def should_run_now() -> bool:
    """Check if it's time to run based on configured interval.
    
    For GitHub Actions running hourly, we only execute at interval hours.
    E.g., if interval=4, run at 00:00, 04:00, 08:00, 12:00, 16:00, 20:00.
    """
    try:
        tz = pytz.timezone(TIMEZONE)
        now = datetime.now(tz)
        current_hour = now.hour

        if RUN_INTERVAL_HOURS <= 0:
            return True

        should = current_hour % RUN_INTERVAL_HOURS == 0
        logger.info(f"⏰ Current time: {now.strftime('%Y-%m-%d %H:%M %Z')} | "
                     f"Interval: every {RUN_INTERVAL_HOURS}h | "
                     f"Should run: {should}")
        return should

    except Exception as e:
        logger.warning(f"Timezone check failed ({e}), proceeding anyway")
        return True


async def run_pipeline(dry_run: bool = False):
    """Execute the full data → analysis → prediction pipeline."""
    logger.info("=" * 60)
    logger.info("🚀 SOLANA COMMUNITY MOOD TRACKER — Starting Pipeline")
    logger.info("=" * 60)

    # Override dry run from CLI
    if dry_run:
        import src.config as cfg
        cfg.DRY_RUN = True

    # ============================================
    # PHASE 1: Data Collection
    # ============================================
    logger.info("\n📡 PHASE 1: Data Collection")
    logger.info("-" * 40)

    from src.scrapers.price_scraper import scrape_price_data
    from src.scrapers.fear_greed_scraper import scrape_fear_greed
    from src.scrapers.reddit_scraper import scrape_reddit
    from src.scrapers.social_scraper import scrape_social
    from src.scrapers.youtube_scraper import scrape_youtube
    from src.scrapers.news_scraper import scrape_news
    from src.scrapers.onchain_scraper import scrape_onchain

    # Run all scrapers in parallel
    (
        price_data,
        fear_greed_data,
        reddit_data,
        social_data,
        youtube_data,
        news_data,
        onchain_data,
    ) = await asyncio.gather(
        scrape_price_data(),
        scrape_fear_greed(),
        scrape_reddit(),
        scrape_social(),
        scrape_youtube(),
        scrape_news(),
        scrape_onchain(),
    )

    scraped_data = {
        "price": price_data,
        "fear_greed": fear_greed_data,
        "reddit": reddit_data,
        "social": social_data,
        "youtube": youtube_data,
        "news": news_data,
        "onchain": onchain_data,
    }

    logger.info("\n✅ Data collection complete!")

    # ============================================
    # PHASE 2: Technical Analysis
    # ============================================
    logger.info("\n📈 PHASE 2: Technical Analysis")
    logger.info("-" * 40)

    from src.analysis.technical_analysis import run_technical_analysis

    technical_result = run_technical_analysis(price_data)

    # ============================================
    # PHASE 3: AI Sentiment Analysis
    # ============================================
    logger.info("\n🧠 PHASE 3: AI Sentiment Analysis")
    logger.info("-" * 40)

    from src.analysis.analyzer import run_full_analysis

    ai_analysis = await run_full_analysis(scraped_data)

    # ============================================
    # PHASE 4: Prediction Generation
    # ============================================
    logger.info("\n🎯 PHASE 4: Prediction Generation")
    logger.info("-" * 40)

    from src.analysis.prediction_engine import generate_prediction

    prediction = generate_prediction(
        technical_result=technical_result,
        ai_analysis=ai_analysis,
        fear_greed_data=fear_greed_data,
        onchain_data=onchain_data,
        price_data=price_data,
    )

    # ============================================
    # PHASE 5: Delivery
    # ============================================
    logger.info("\n📤 PHASE 5: Delivery & Logging")
    logger.info("-" * 40)

    from src.telegram_sender import send_prediction
    from src.history_tracker import log_prediction, check_prediction_results

    # Send to Telegram
    await send_prediction(prediction)

    # Log prediction for accuracy tracking
    log_prediction(prediction)

    # Check any past predictions that are due for result verification
    await check_prediction_results()

    # ============================================
    # DONE
    # ============================================
    logger.info("\n" + "=" * 60)
    logger.info(f"✅ Pipeline complete! Signal: {prediction['direction']} "
                f"({prediction['confidence']}% confidence)")
    logger.info("=" * 60)

    return prediction


def main():
    """Entry point with CLI argument handling."""
    parser = argparse.ArgumentParser(description="Solana Community Mood Tracker")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Run full pipeline but don't send Telegram messages"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Skip time check and run immediately"
    )
    parser.add_argument(
        "--check-results", action="store_true",
        help="Only check past prediction results, don't generate new prediction"
    )
    args = parser.parse_args()

    if args.check_results:
        from src.history_tracker import check_prediction_results, get_accuracy_stats
        asyncio.run(check_prediction_results())
        stats = get_accuracy_stats()
        import json
        print(json.dumps(stats, indent=2, default=str))
        return

    # Check if it's time to run
    if not args.force and not should_run_now():
        logger.info("⏸ Not scheduled to run at this hour. Use --force to override.")
        sys.exit(0)

    # Run the pipeline
    try:
        prediction = asyncio.run(run_pipeline(dry_run=args.dry_run or DRY_RUN))
        sys.exit(0)
    except KeyboardInterrupt:
        logger.info("⛔ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Pipeline failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
