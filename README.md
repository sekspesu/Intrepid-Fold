# 🌡️ Solana Community Mood Tracker

A hobby project that tracks community sentiment around Solana (SOL) by aggregating publicly available data from social media, news, and on-chain metrics.

## What It Does

- Collects public discussions from Reddit, news RSS feeds, and YouTube
- Runs basic sentiment analysis on community conversations
- Tracks the Crypto Fear & Greed Index
- Monitors on-chain activity (DEX volume, TVL) via public APIs
- Summarizes the overall "mood" of the Solana community

## Why?

I wanted to learn about NLP, sentiment analysis, and crypto data pipelines. This is a personal/educational project to explore how public community sentiment correlates with market movements over time.

## Data Sources

| Source | What We Collect |
|:---|:---|
| Reddit (PRAW) | Public posts & comments from crypto subreddits |
| RSS Feeds | Headlines from CoinDesk, The Block, Decrypt |
| YouTube | Video titles from crypto education channels |
| CoinGecko / Binance | Public price data |
| Alternative.me | Fear & Greed Index |
| DexScreener / DefiLlama | Public on-chain metrics |

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
# Fill in your API keys

# Run
python -m src.main --force --dry-run
```

## Notes

- This is a personal learning project, not financial advice
- All data comes from publicly available APIs
- Reddit data is read-only (no posting, voting, or messaging)
- Respects all API rate limits

## License

MIT
