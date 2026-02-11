"""
Central configuration for the Solana Community Mood Tracker.
All data source endpoints, API settings, and scraper parameters.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ============================================
# API Keys & Credentials
# ============================================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = "gpt-4o-mini"  # cost-effective for high-frequency analysis

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_IDS = [
    cid.strip() for cid in os.getenv("TELEGRAM_CHAT_IDS", "").split(",") if cid.strip()
]

REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "SolanaBot/1.0")

LUNARCRUSH_API_KEY = os.getenv("LUNARCRUSH_API_KEY", "")
CRYPTOPANIC_API_KEY = os.getenv("CRYPTOPANIC_API_KEY", "")
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")

WEBSHARE_USERNAME = os.getenv("WEBSHARE_USERNAME", "")
WEBSHARE_PASSWORD = os.getenv("WEBSHARE_PASSWORD", "")

# ============================================
# Bot Settings
# ============================================

RUN_INTERVAL_HOURS = int(os.getenv("RUN_INTERVAL_HOURS", "4"))
TIMEZONE = os.getenv("TIMEZONE", "Europe/Tallinn")
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

# ============================================
# Data Sources Configuration
# ============================================

# --- Reddit ---
SUBREDDITS = [
    "solana",
    "cryptocurrency",
    "CryptoMarkets",
    "SolanaTrading",
    "defi",
    "SolanaMemeCoins",
    "altcoin",
    "CryptoMoonShots",
]
REDDIT_POST_LIMIT = 5          # top posts per subreddit
REDDIT_TIME_FILTER = "day"     # last 24h
REDDIT_COMMENT_LIMIT = 10     # top comments to analyze per post

# Keywords for bullish/bearish detection in Reddit
BULLISH_KEYWORDS = [
    "bullish", "moon", "pump", "breakout", "buy", "accumulate",
    "undervalued", "gem", "rally", "green", "long", "hodl",
    "ath", "all time high", "adoption", "partnership", "upgrade",
]
BEARISH_KEYWORDS = [
    "bearish", "dump", "crash", "sell", "short", "overvalued",
    "scam", "rug", "red", "dead", "bleeding", "collapse",
    "hack", "exploit", "lawsuit", "sec", "regulation",
]

# --- YouTube ---
YOUTUBE_CHANNELS = [
    "Coin Bureau",
    "Benjamin Cowen",
    "CryptoBanter",
    "Altcoin Daily",
    "InvestAnswers",
    "DataDash",
    "Crypto Banter",
    "The Moon",
    "Lark Davis",
    "Alex Becker",
]
YOUTUBE_VIDEO_LIMIT = 3      # recent videos per channel
YOUTUBE_MAX_AGE_HOURS = 48   # only consider videos from last 48h

# --- News RSS Feeds ---
NEWS_RSS_FEEDS = [
    {
        "name": "CoinDesk",
        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    },
    {
        "name": "The Block",
        "url": "https://www.theblock.co/rss.xml",
    },
    {
        "name": "Decrypt",
        "url": "https://decrypt.co/feed",
    },
    {
        "name": "CoinTelegraph",
        "url": "https://cointelegraph.com/rss",
    },
    {
        "name": "Solana News",
        "url": "https://solana.com/news/rss.xml",
    },
]
NEWS_MAX_AGE_HOURS = 24

# --- CryptoPanic ---
CRYPTOPANIC_BASE_URL = "https://cryptopanic.com/api/v1/posts/"
CRYPTOPANIC_CURRENCIES = "SOL"  # filter for Solana news

# --- CoinGecko ---
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
COINGECKO_COIN_ID = "solana"

# --- Binance ---
BINANCE_BASE_URL = "https://api.binance.com/api/v3"
BINANCE_SYMBOL = "SOLUSDT"

# --- Fear & Greed ---
FEAR_GREED_URL = "https://api.alternative.me/fng/"

# --- LunarCrush ---
LUNARCRUSH_BASE_URL = "https://lunarcrush.com/api4/public"

# --- DexScreener ---
DEXSCREENER_BASE_URL = "https://api.dexscreener.com/latest"
DEXSCREENER_CHAIN = "solana"

# --- DefiLlama ---
DEFILLAMA_BASE_URL = "https://api.llama.fi"
DEFILLAMA_CHAIN = "Solana"

# ============================================
# Analysis Configuration
# ============================================

# Technical Analysis periods
TA_RSI_PERIOD = 14
TA_MACD_FAST = 12
TA_MACD_SLOW = 26
TA_MACD_SIGNAL = 9
TA_BB_PERIOD = 20
TA_BB_STD = 2
TA_EMA_SHORT = 9
TA_EMA_MEDIUM = 21
TA_EMA_LONG = 50
TA_EMA_VERY_LONG = 200

# Signal weights for prediction engine
SIGNAL_WEIGHTS = {
    "technical":    0.30,   # Price action is most objective
    "onchain":      0.20,   # Smart money movements lead price
    "news":         0.18,   # Major news catalysts drive volatility
    "social":       0.15,   # Crowd sentiment (confirming/contrarian)
    "fear_greed":   0.10,   # Macro market mood
    "youtube":      0.07,   # Expert opinion supplement
}

# Confidence thresholds
CONFIDENCE_HIGH = 75     # >= 75% = strong signal
CONFIDENCE_MEDIUM = 50   # >= 50% = moderate signal
CONFIDENCE_LOW = 30      # < 30% = weak / neutral

# GPT Analysis Settings
GPT_MAX_CONCURRENT = 10
GPT_TEMPERATURE = 0.3    # lower = more deterministic analysis

# ============================================
# Data Storage
# ============================================

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
PREDICTIONS_FILE = os.path.join(DATA_DIR, "predictions.json")
