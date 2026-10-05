import os
from dotenv import load_dotenv

BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE, ".env"))


def _int(key, default):
    try:
        return int(os.getenv(key, default))
    except ValueError:
        return default


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").strip().lower()
AI_MODEL = os.getenv("AI_MODEL", "gemini-2.5-flash").strip()
AI_BASE_URL = os.getenv("AI_BASE_URL", "").strip().rstrip("/")

CHECK_INTERVAL_MIN = _int("CHECK_INTERVAL_MIN", 60)
MAX_AGE_HOURS = _int("MAX_AGE_HOURS", 6)
MAX_POSTS_PER_CYCLE = _int("MAX_POSTS_PER_CYCLE", 5)
MAX_AI_CALLS = _int("MAX_AI_CALLS_PER_CYCLE", 30)
MIN_IMPORTANCE = _int("MIN_IMPORTANCE", 3)
MAX_ITEMS_PER_SOURCE = _int("MAX_ITEMS_PER_SOURCE", 10)
MAX_ATTEMPTS = 4

CHANNEL_URL = "https://t.me/online_newsIR"
CHANNEL_BUTTON = "OnlineNews"
DB_PATH = os.path.join(BASE, "database", "news.db")

SECRETS = [v for v in (TELEGRAM_BOT_TOKEN, AI_API_KEY) if v]


def missing_settings():
    bad = []
    for name in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "AI_API_KEY"):
        v = globals()[name]
        if not v or v.startswith("PUT_"):
            bad.append(name)
    return bad


ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "").strip()
BATCH_SIZE = _int("BATCH_SIZE", 8)
AI_DELAY_SEC = _int("AI_DELAY_SEC", 8)
NO_POST_ALERT_HOURS = _int("NO_POST_ALERT_HOURS", 12)


PS_MIN_IMPORTANCE = _int("PS_MIN_IMPORTANCE", 4)


WIPE_DAYS = _int("WIPE_DAYS", 20)
AI_DAILY_TOKEN_BUDGET = _int("AI_DAILY_TOKEN_BUDGET", 0)
