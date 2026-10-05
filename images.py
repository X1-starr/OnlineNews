import html
import re
from urllib.parse import urljoin

import requests

from utils import SESSION, get_logger

log = get_logger()
MAX_BYTES = 8 * 1024 * 1024
_OG = [
    re.compile(r'<meta[^>]+(?:property|name)=["\']og:image(?::url)?["\'][^>]*content=["\']([^"\']+)["\']', re.I),
    re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\']og:image["\']', re.I),
]
_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def og_image(page_url):
    try:
        r = SESSION.get(page_url, timeout=15)
        if not r.ok:
            return None
        head = r.text[:150000]
    except requests.RequestException:
        return None
    for rx in _OG:
        m = rx.search(head)
        if m:
            return urljoin(page_url, html.unescape(m.group(1)))
    return None


def download_image(url):
    try:
        r = SESSION.get(url, timeout=20, stream=True)
        ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
        if not r.ok or ctype not in _EXT:
            return None
        buf = b""
        for chunk in r.iter_content(65536):
            buf += chunk
            if len(buf) > MAX_BYTES:
                return None
        if len(buf) < 5000:      # آیکون/لوگوی کوچک
            return None
        return buf, "photo." + _EXT[ctype]
    except requests.RequestException:
        return None


def get_image(item):
    """تصویر اصلی خبر؛ اگر نشد None (پست بدون عکس)."""
    try:
        url = item.image or (og_image(item.url) if item.fetch_og else None)
        return download_image(url) if url else None
    except Exception as e:
        log.warning("image failed: %s", type(e).__name__)
        return None
