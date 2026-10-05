import hashlib
import html
import logging
import os
import re
from logging.handlers import RotatingFileHandler

import requests

import config

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (Linux; Android 13) OnlineNewsBot/1.0"})

_TOKEN_RE = re.compile(r"bot\d+:[A-Za-z0-9_-]+")


def redact(text):
    for s in config.SECRETS:
        text = text.replace(s, "***")
    return _TOKEN_RE.sub("bot***", text)


class _SafeFormatter(logging.Formatter):
    def format(self, record):
        return redact(super().format(record))


def get_logger():
    log = logging.getLogger("onlinenews")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    fmt = _SafeFormatter("%(asctime)s %(levelname)s %(message)s")
    os.makedirs(os.path.join(config.BASE, "logs"), exist_ok=True)
    handlers = [
        logging.StreamHandler(),
        RotatingFileHandler(os.path.join(config.BASE, "logs", "bot.log"),
                            maxBytes=500_000, backupCount=2, encoding="utf-8"),
    ]
    for h in handlers:
        h.setFormatter(fmt)
        log.addHandler(h)
    return log


def normalize(text):
    text = (text or "").lower()
    for a, b in (("ي", "ی"), ("ك", "ک"), ("إ", "ا"), ("أ", "ا"), ("آ", "ا"), ("\u200c", " ")):
        text = text.replace(a, b)
    text = re.sub(r"[\u064b-\u065f\u0640]", "", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def strip_html(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def title_hash(title):
    return hashlib.sha256(normalize(title).encode("utf-8")).hexdigest()
