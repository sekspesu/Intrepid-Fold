from __future__ import annotations
"""
AI Sentiment Analyzer — OpenAI GPT.
Processes raw data from all scrapers and produces structured sentiment signals.
"""

import asyncio
import logging
from typing import Any

from openai import AsyncOpenAI

from src.config import (
    GPT_MAX_CONCURRENT,
    GPT_TEMPERATURE,
    OPENAI_API_KEY,
    OPENAI_MODEL,
)

logger = logging.getLogger(__name__)

_client = None
_semaphore = asyncio.Semaphore(GPT_MAX_CONCURRENT)


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _client


async def _gpt_analyze(prompt: str, system_prompt: str = "") -> str:
    """Send a prompt to GPT and return the response text."""
    async with _semaphore:
        try:
            client = _get_client()
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = await client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                temperature=GPT_TEMPERATURE,
                max_tokens=600,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"GPT analysis failed: {e}")
            return ""


SYSTEM_PROMPT = """You are a professional cryptocurrency trading analyst specializing in Solana (SOL).
Your task is to analyze data and provide a clear sentiment assessment.
Always respond in the exact JSON format requested. Be objective, data-driven, and concise.
Never give financial advice — only analysis."""


async def analyze_news_sentiment(articles: list[dict]) -> dict[str, Any]:
    """Analyze news articles for sentiment impact on SOL price."""
    if not articles:
        return {"sentiment_score": 0, "analysis": "No news data available", "key_stories": []}

    # Build news summary for GPT
    headlines = []
    for a in articles[:20]:
        sol_tag = "🎯" if a.get("sol_specific") else "🌐"
        headlines.append(f"{sol_tag} [{a.get('outlet', '?')}] {a.get('title', '')}")

    prompt = f"""Analyze these recent crypto/Solana news headlines for their impact on SOL price.

Headlines:
{chr(10).join(headlines)}

Respond in this exact JSON format:
{{
    "sentiment_score": <float from -1.0 (very bearish) to +1.0 (very bullish)>,
    "confidence": <float 0.0 to 1.0>,
    "analysis": "<1-2 sentence summary of overall news sentiment>",
    "key_stories": [
        {{"headline": "<most impactful headline>", "impact": "bullish/bearish/neutral", "reason": "<why>"}}
    ],
    "catalysts": ["<list of upcoming catalysts if any mentioned>"]
}}"""

    response = await _gpt_analyze(prompt, SYSTEM_PROMPT)

    try:
        import json
        return json.loads(response)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to parse GPT news analysis, using fallback")
        return {"sentiment_score": 0, "analysis": response or "Analysis failed", "key_stories": []}


async def analyze_reddit_sentiment(reddit_data: dict) -> dict[str, Any]:
    """Analyze Reddit community sentiment using GPT."""
    posts = reddit_data.get("posts", [])
    summary = reddit_data.get("summary", {})

    if not posts:
        return {"sentiment_score": 0, "analysis": "No Reddit data available"}

    # Build Reddit content summary
    post_summaries = []
    for p in posts[:15]:
        post_summaries.append(
            f"r/{p.get('subreddit')} | ⬆️{p.get('score', 0)} | {p.get('title', '')}"
            f"\n  Keywords: bull={p.get('bullish_keywords', 0)} bear={p.get('bearish_keywords', 0)}"
        )

    keyword_summary = (
        f"Aggregate stats: {summary.get('total_posts', 0)} posts, "
        f"{summary.get('bullish_posts', 0)} bullish, "
        f"{summary.get('bearish_posts', 0)} bearish, "
        f"{summary.get('neutral_posts', 0)} neutral, "
        f"avg sentiment: {summary.get('avg_sentiment_score', 0):.3f}"
    )

    prompt = f"""Analyze Reddit community sentiment about Solana based on these top posts.

{keyword_summary}

Top Posts:
{chr(10).join(post_summaries)}

Respond in this exact JSON format:
{{
    "sentiment_score": <float from -1.0 (very bearish) to +1.0 (very bullish)>,
    "confidence": <float 0.0 to 1.0>,
    "analysis": "<1-2 sentence summary of community mood>",
    "dominant_topics": ["<top 3 discussion topics>"],
    "fomo_level": "<none/low/moderate/high/extreme>"
}}"""

    response = await _gpt_analyze(prompt, SYSTEM_PROMPT)

    try:
        import json
        return json.loads(response)
    except (json.JSONDecodeError, TypeError):
        # Fallback to keyword-based score
        return {
            "sentiment_score": summary.get("avg_sentiment_score", 0),
            "analysis": response or "Analysis failed",
        }


async def analyze_youtube_content(videos: list[dict]) -> dict[str, Any]:
    """Analyze YouTube crypto analyst opinions on SOL."""
    videos_with_transcripts = [v for v in videos if v.get("transcript")]

    if not videos_with_transcripts:
        return {"sentiment_score": 0, "analysis": "No YouTube transcripts available"}

    # Analyze each video's transcript
    tasks = []
    for video in videos_with_transcripts[:5]:  # Max 5 to manage costs
        transcript_excerpt = video["transcript"][:2000]
        prompt = f"""Analyze this crypto YouTube video transcript for Solana sentiment and price predictions.

Channel: {video.get('channel', 'Unknown')}
Title: {video.get('title', 'Unknown')}
Transcript excerpt:
{transcript_excerpt}

Respond in JSON:
{{
    "sentiment_score": <float -1.0 to +1.0>,
    "sol_mentioned": <true/false>,
    "key_points": ["<main takeaways about SOL or market>"],
    "price_prediction": "<any specific SOL price prediction mentioned, or 'none'>",
    "summary": "<1-2 sentence summary>"
}}"""
        tasks.append(_gpt_analyze(prompt, SYSTEM_PROMPT))

    results = await asyncio.gather(*tasks)

    # Aggregate video analyses
    import json
    video_analyses = []
    total_score = 0
    count = 0

    for i, response in enumerate(results):
        try:
            parsed = json.loads(response)
            parsed["channel"] = videos_with_transcripts[i].get("channel", "Unknown")
            parsed["title"] = videos_with_transcripts[i].get("title", "Unknown")
            video_analyses.append(parsed)
            total_score += parsed.get("sentiment_score", 0)
            count += 1
        except (json.JSONDecodeError, TypeError):
            continue

    avg_score = total_score / max(count, 1)

    return {
        "sentiment_score": round(avg_score, 3),
        "videos_analyzed": count,
        "analysis": f"Analyzed {count} YouTube videos from crypto analysts",
        "video_details": video_analyses,
    }


async def analyze_social_metrics(social_data: dict) -> dict[str, Any]:
    """Interpret LunarCrush social metrics for trading signal."""
    metrics = social_data.get("metrics", {})

    if not metrics:
        return {"sentiment_score": 0, "analysis": "No social data available"}

    prompt = f"""Analyze these LunarCrush social metrics for Solana and determine the social sentiment signal.

Galaxy Score: {metrics.get('galaxy_score', 'N/A')}
AltRank: {metrics.get('alt_rank', 'N/A')}
Social Volume: {metrics.get('social_volume', 'N/A')}
Social Volume 24h Change: {metrics.get('social_volume_change_24h', 'N/A')}%
Social Dominance: {metrics.get('social_dominance', 'N/A')}%
Bullish Sentiment: {metrics.get('bullish_sentiment_pct', 'N/A')}%
Bearish Sentiment: {metrics.get('bearish_sentiment_pct', 'N/A')}%
Social Contributors: {metrics.get('social_contributors', 'N/A')}
Tweet Sentiment: {metrics.get('tweet_sentiment', 'N/A')}

Respond in JSON:
{{
    "sentiment_score": <float -1.0 to +1.0>,
    "confidence": <float 0.0 to 1.0>,
    "analysis": "<1-2 sentence interpretation>",
    "social_momentum": "<declining/stable/rising/surging>",
    "contrarian_signal": "<is high social activity a warning sign? yes/no and why>"
}}"""

    response = await _gpt_analyze(prompt, SYSTEM_PROMPT)

    try:
        import json
        return json.loads(response)
    except (json.JSONDecodeError, TypeError):
        # Fallback to simple score from bullish %
        bullish = metrics.get("bullish_sentiment_pct", 50) or 50
        score = (bullish - 50) / 50  # Normalize to -1 to +1
        return {"sentiment_score": round(score, 3), "analysis": response or "Analysis failed"}


async def run_full_analysis(scraped_data: dict) -> dict[str, Any]:
    """Run all AI analyses in parallel and return combined results."""
    logger.info("🧠 Running AI sentiment analysis on all collected data...")

    if not OPENAI_API_KEY:
        logger.warning("  ⚠️ OpenAI API key not configured, skipping AI analysis")
        return {}

    news_task = analyze_news_sentiment(
        scraped_data.get("news", {}).get("articles", [])
    )
    reddit_task = analyze_reddit_sentiment(
        scraped_data.get("reddit", {})
    )
    youtube_task = analyze_youtube_content(
        scraped_data.get("youtube", {}).get("videos", [])
    )
    social_task = analyze_social_metrics(
        scraped_data.get("social", {})
    )

    news_result, reddit_result, youtube_result, social_result = await asyncio.gather(
        news_task, reddit_task, youtube_task, social_task
    )

    result = {
        "news_sentiment": news_result,
        "reddit_sentiment": reddit_result,
        "youtube_sentiment": youtube_result,
        "social_sentiment": social_result,
    }

    logger.info(f"  ✅ News: {news_result.get('sentiment_score', 'N/A')}")
    logger.info(f"  ✅ Reddit: {reddit_result.get('sentiment_score', 'N/A')}")
    logger.info(f"  ✅ YouTube: {youtube_result.get('sentiment_score', 'N/A')}")
    logger.info(f"  ✅ Social: {social_result.get('sentiment_score', 'N/A')}")

    return result
