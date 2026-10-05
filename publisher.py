import html
import json
import re
import time

import requests

import config
from utils import get_logger

log = get_logger()
API = "https://api.telegram.org/bot{}/{}"
PREFIX = {"iran": "🇮🇷👀", "world": "🌍👀", "football": "⚽👀"}


def _call(method, data, files=None):
    for attempt in range(3):
        try:
            r = requests.post(API.format(config.TELEGRAM_BOT_TOKEN, method),
                              data=data, files=files, timeout=60)
            if r.status_code == 429:
                wait = r.json().get("parameters", {}).get("retry_after", 5)
                time.sleep(min(int(wait) + 1, 60))
                continue
            if r.ok:
                return True
            log.error("Telegram %s failed: %s %s", method, r.status_code, r.text[:300])
            return False
        except requests.RequestException as e:
            log.warning("Telegram network error: %s (try %d)", type(e).__name__, attempt + 1)
            time.sleep(5)
    return False


def build_text(headline, body, sources, limit, category="iran", emojis="", details=None, ps=""):
    emo = emojis if emojis and not re.search(r"[A-Za-z0-9\u0600-\u06FF]", emojis) else PREFIX.get(category, PREFIX["iran"])
    head = html.escape(emo) + " <b>" + html.escape(headline) + "</b>\n\n"
    det = ("\n\n" + "\n".join(html.escape(d) for d in details)) if details else ""
    link = '<a href="' + config.CHANNEL_URL + '">@online_newsIR</a>'
    tail = "\n\n📰 منبع: " + html.escape("، ".join(sources)) + "\n\n💢 " + link + " | 🤖 Bot News"
    psb = ("\n\n<blockquote>🤖 پ.ن.: " + html.escape(ps) + "</blockquote>") if ps else ""
    room = limit - len(head) - len(det) - len(psb) - len(tail) - 10
    if psb and room < 200:
        psb = ""
        room = limit - len(head) - len(det) - len(tail) - 10
    b, trimmed = body, False
    while len(html.escape(b)) > room and len(b) > 20:
        b, trimmed = b[: int(len(b) * 0.9)].rstrip(), True
    return head + html.escape(b + ("…" if trimmed else "")) + det + psb + tail


def publish(headline, body, sources, image=None, category="iran", emojis="", details=None, ps=""):
    markup = json.dumps({"inline_keyboard": [[
        {"text": config.CHANNEL_BUTTON, "url": config.CHANNEL_URL}]]})
    base = {"chat_id": config.TELEGRAM_CHAT_ID, "parse_mode": "HTML", "reply_markup": markup}
    if image:
        data, name = image
        d = dict(base, caption=build_text(headline, body, sources, 1024, category, emojis, details, ps))
        if _call("sendPhoto", d, files={"photo": (name, data)}):
            return True
        log.warning("photo send failed; falling back to text only")
    d = dict(base, text=build_text(headline, body, sources, 4096, category, emojis, details, ps),
             disable_web_page_preview="true")
    return _call("sendMessage", d)


def alert(text):
    if not config.ADMIN_CHAT_ID:
        return
    try:
        requests.post(API.format(config.TELEGRAM_BOT_TOKEN, "sendMessage"),
                      data={"chat_id": config.ADMIN_CHAT_ID, "text": text}, timeout=30)
    except requests.RequestException as e:
        log.warning("alert failed: %s", type(e).__name__)
