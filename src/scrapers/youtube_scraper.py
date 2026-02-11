"""
YouTube crypto analyst scraper.
Finds recent videos from key channels, downloads transcripts for AI analysis.
Uses scrapetube + youtube_transcript_api (same approach as Autom-AI-News).
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from src.config import (
    WEBSHARE_PASSWORD,
    WEBSHARE_USERNAME,
    YOUTUBE_CHANNELS,
    YOUTUBE_MAX_AGE_HOURS,
    YOUTUBE_VIDEO_LIMIT,
)

logger = logging.getLogger(__name__)


def _get_proxy() -> Optional[dict]:
    """Configure proxy for YouTube scraping if credentials exist."""
    if WEBSHARE_USERNAME and WEBSHARE_PASSWORD:
        proxy = f"http://{WEBSHARE_USERNAME}:{WEBSHARE_PASSWORD}@p.webshare.io:80"
        return {"http": proxy, "https": proxy}
    return None


def _find_channel_videos(channel_name: str, limit: int = 3) -> list[dict]:
    """Find recent videos from a YouTube channel using scrapetube."""
    try:
        import scrapetube

        # Random delay to avoid rate limiting
        time.sleep(random.uniform(1.0, 3.0))

        videos = scrapetube.get_search(
            query=f"{channel_name} solana crypto",
            limit=limit,
            sort_by="upload_date",
        )

        results = []
        for v in videos:
            video_id = v.get("videoId", "")
            title = v.get("title", {})
            if isinstance(title, dict):
                title = title.get("runs", [{}])[0].get("text", "")

            # Check if title mentions Solana or crypto-related topics
            title_lower = title.lower() if title else ""
            sol_related = any(kw in title_lower for kw in [
                "solana", "sol", "crypto", "bitcoin", "market", "altcoin",
                "defi", "trading", "price", "bull", "bear",
            ])

            if video_id and sol_related:
                results.append({
                    "video_id": video_id,
                    "title": title,
                    "channel": channel_name,
                    "url": f"https://youtube.com/watch?v={video_id}",
                })

            if len(results) >= limit:
                break

        return results

    except Exception as e:
        logger.error(f"Error searching videos for {channel_name}: {e}")
        return []


def _get_transcript(video_id: str) -> Optional[str]:
    """Fetch transcript for a YouTube video."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        proxies = _get_proxy()
        transcript_list = YouTubeTranscriptApi.get_transcript(
            video_id,
            languages=["en", "en-US", "en-GB"],
            proxies=proxies if proxies else None,
        )

        full_text = " ".join(entry["text"] for entry in transcript_list)
        return full_text[:5000]  # Cap at 5000 chars for GPT context

    except Exception as e:
        logger.debug(f"No transcript for {video_id}: {e}")
        return None


async def scrape_youtube() -> dict[str, Any]:
    """Main entry point — finds recent videos and fetches transcripts."""
    logger.info(f"🎥 Scraping YouTube ({len(YOUTUBE_CHANNELS)} channels)...")

    loop = asyncio.get_event_loop()
    all_videos = []

    for channel in YOUTUBE_CHANNELS:
        videos = await loop.run_in_executor(
            None, _find_channel_videos, channel, YOUTUBE_VIDEO_LIMIT
        )

        for video in videos:
            transcript = await loop.run_in_executor(
                None, _get_transcript, video["video_id"]
            )
            video["transcript"] = transcript
            video["has_transcript"] = transcript is not None

        all_videos.extend(videos)
        logger.info(f"  ✅ {channel}: {len(videos)} videos "
                     f"({sum(1 for v in videos if v.get('has_transcript'))} with transcripts)")

    # Filter to only videos with transcripts (more useful for analysis)
    videos_with_transcripts = [v for v in all_videos if v.get("has_transcript")]

    result = {
        "source": "youtube",
        "timestamp": datetime.utcnow().isoformat(),
        "total_videos": len(all_videos),
        "videos_with_transcripts": len(videos_with_transcripts),
        "videos": all_videos,
    }

    logger.info(f"  📊 YouTube Total: {len(all_videos)} videos, "
                f"{len(videos_with_transcripts)} with transcripts")

    return result


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    data = asyncio.run(scrape_youtube())
    summary = {k: v for k, v in data.items() if k != "videos"}
    summary["video_titles"] = [v["title"] for v in data.get("videos", [])]
    print(json.dumps(summary, indent=2, default=str))
