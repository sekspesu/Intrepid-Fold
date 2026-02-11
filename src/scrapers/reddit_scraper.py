from __future__ import annotations
"""
Reddit sentiment scraper — PRAW.
Scrapes Solana-related subreddits for posts and comments,
extracts sentiment keywords and engagement metrics.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from src.config import (
    BEARISH_KEYWORDS,
    BULLISH_KEYWORDS,
    REDDIT_CLIENT_ID,
    REDDIT_CLIENT_SECRET,
    REDDIT_COMMENT_LIMIT,
    REDDIT_POST_LIMIT,
    REDDIT_TIME_FILTER,
    REDDIT_USER_AGENT,
    SUBREDDITS,
)

logger = logging.getLogger(__name__)


def _count_keywords(text: str, keywords: list[str]) -> int:
    """Count how many keyword matches exist in text."""
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw in text_lower)


def _analyze_post_sentiment(title: str, body: str, comments: list[str]) -> dict:
    """Analyze sentiment of a single post based on keyword matching."""
    all_text = f"{title} {body} {' '.join(comments)}"
    bullish = _count_keywords(all_text, BULLISH_KEYWORDS)
    bearish = _count_keywords(all_text, BEARISH_KEYWORDS)
    total = bullish + bearish

    if total == 0:
        sentiment_score = 0.0
        sentiment_label = "neutral"
    else:
        sentiment_score = (bullish - bearish) / total  # -1 to +1
        if sentiment_score > 0.2:
            sentiment_label = "bullish"
        elif sentiment_score < -0.2:
            sentiment_label = "bearish"
        else:
            sentiment_label = "neutral"

    return {
        "bullish_keywords": bullish,
        "bearish_keywords": bearish,
        "sentiment_score": round(sentiment_score, 3),
        "sentiment_label": sentiment_label,
    }


def _scrape_subreddit_sync(subreddit_name: str) -> list[dict[str, Any]]:
    """Synchronous subreddit scraping (PRAW is not async)."""
    try:
        import praw

        reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT,
        )

        subreddit = reddit.subreddit(subreddit_name)
        posts = []

        for post in subreddit.top(time_filter=REDDIT_TIME_FILTER, limit=REDDIT_POST_LIMIT):
            if post.stickied:
                continue

            # Get top comments
            post.comment_sort = "top"
            post.comments.replace_more(limit=0)
            top_comments = [
                comment.body for comment in post.comments[:REDDIT_COMMENT_LIMIT]
                if hasattr(comment, "body") and len(comment.body) > 10
            ]

            body = post.selftext or ""
            sentiment = _analyze_post_sentiment(post.title, body, top_comments)

            posts.append({
                "subreddit": subreddit_name,
                "title": post.title,
                "body_preview": body[:500] if body else "",
                "url": f"https://reddit.com{post.permalink}",
                "score": post.score,
                "upvote_ratio": post.upvote_ratio,
                "num_comments": post.num_comments,
                "created_utc": datetime.fromtimestamp(post.created_utc, tz=timezone.utc).isoformat(),
                "top_comments": top_comments[:5],
                **sentiment,
            })

        return posts

    except Exception as e:
        logger.error(f"Error scraping r/{subreddit_name}: {e}")
        return []


async def scrape_reddit() -> dict[str, Any]:
    """Main entry point — scrapes all configured subreddits."""
    logger.info(f"📱 Scraping Reddit ({len(SUBREDDITS)} subreddits)...")

    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        logger.warning("  ⚠️ Reddit credentials not configured, skipping")
        return {"posts": [], "summary": {}}

    # Run PRAW in executor (it's synchronous)
    loop = asyncio.get_event_loop()
    all_posts = []

    for sub in SUBREDDITS:
        posts = await loop.run_in_executor(None, _scrape_subreddit_sync, sub)
        all_posts.extend(posts)
        logger.info(f"  ✅ r/{sub}: {len(posts)} posts")

    # Aggregate sentiment
    if all_posts:
        avg_score = sum(p["sentiment_score"] for p in all_posts) / len(all_posts)
        bullish_count = sum(1 for p in all_posts if p["sentiment_label"] == "bullish")
        bearish_count = sum(1 for p in all_posts if p["sentiment_label"] == "bearish")
        neutral_count = sum(1 for p in all_posts if p["sentiment_label"] == "neutral")
        total_engagement = sum(p["score"] + p["num_comments"] for p in all_posts)
    else:
        avg_score = 0.0
        bullish_count = bearish_count = neutral_count = 0
        total_engagement = 0

    summary = {
        "total_posts": len(all_posts),
        "avg_sentiment_score": round(avg_score, 3),
        "bullish_posts": bullish_count,
        "bearish_posts": bearish_count,
        "neutral_posts": neutral_count,
        "total_engagement": total_engagement,
        "overall_sentiment": (
            "bullish" if avg_score > 0.1
            else "bearish" if avg_score < -0.1
            else "neutral"
        ),
    }

    logger.info(f"  📊 Reddit Summary: {summary['overall_sentiment']} "
                f"(score: {avg_score:.3f}, {len(all_posts)} posts)")

    return {
        "source": "reddit",
        "timestamp": datetime.utcnow().isoformat(),
        "posts": all_posts,
        "summary": summary,
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    data = asyncio.run(scrape_reddit())
    summary = {k: v for k, v in data.items() if k != "posts"}
    summary["post_count"] = len(data.get("posts", []))
    print(json.dumps(summary, indent=2, default=str))
