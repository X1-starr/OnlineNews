from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote
import re

import feedparser

import config
from utils import SESSION, strip_html


@dataclass
class Source:
    id: str
    name: str                   # نام نمایشی در پست
    lang: str                   # fa / en / ar / ru
    url: str
    iran_native: bool = False   # منبع ایرانی: فیلتر کلیدواژه اعمال نمی‌شود (AI تصمیم می‌گیرد)
    fetch_og: bool = True       # اگر RSS عکس نداشت، عکس از صفحه خبر گرفته شود
    enabled: bool = True


@dataclass
class Item:
    url: str
    title: str
    summary: str
    source_id: str
    source_name: str
    lang: str
    published: Optional[datetime]
    image: Optional[str]
    iran_native: bool
    fetch_og: bool


def gnews(query, lang="en", gl="US"):
    """RSS گوگل‌نیوز؛ برای رسانه‌هایی که RSS رسمی ندارند (Reuters, AP)."""
    return (f"https://news.google.com/rss/search?q={quote(query)}"
            f"&hl={lang}-{gl}&gl={gl}&ceid={gl}:{lang}")


# ====== برای افزودن/حذف منبع فقط همین لیست را ویرایش کنید ======
SOURCES = [
    Source("gn_iran_fa", "گوگل نیوز", "fa", gnews("ایران when:12h", "fa", "IR"), iran_native=True, fetch_og=False),
    Source("gn_iran_en", "گوگل نیوز", "en", gnews("Iran when:12h"), iran_native=True, fetch_og=False),
    Source("gn_levant_en", "گوگل نیوز", "en", gnews("Israel OR Gaza OR Palestine OR Lebanon when:12h"), iran_native=True, fetch_og=False),
    Source("gn_arab_en", "گوگل نیوز", "en", gnews("Iraq OR Syria OR Yemen OR Saudi when:12h"), iran_native=True, fetch_og=False),
    Source("gn_world_en", "گوگل نیوز", "en", gnews("Russia Ukraine OR NATO OR Trump when:12h"), iran_native=True, fetch_og=False),
    Source("gn_foot_fa", "گوگل نیوز", "fa", gnews("فوتبال when:12h", "fa", "IR"), iran_native=True, fetch_og=False),
    Source("gn_foot_en", "گوگل نیوز", "en", gnews("Iran national team OR Persepolis OR Esteghlal OR Messi OR World Cup OR Champions League when:12h"), iran_native=True, fetch_og=False),
    Source("bbc_world", "BBC", "en", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    Source("bbc_football", "BBC Sport", "en", "https://feeds.bbci.co.uk/sport/football/rss.xml"),
    Source("tasnim_gn", "تسنیم", "fa", gnews("site:tasnimnews.com when:1d", "fa", "IR"), iran_native=True, fetch_og=False),
    Source("fars_gn", "فارس", "fa", gnews("site:farsnews.ir when:1d", "fa", "IR"), iran_native=True, fetch_og=False),
    Source("irna_gn", "ایرنا", "fa", gnews("site:irna.ir when:1d", "fa", "IR"), iran_native=True, fetch_og=False),
    Source("alarabiya_gn", "العربیه", "ar", gnews("إيران site:alarabiya.net when:1d", "ar", "SA"), fetch_og=False),
    # فارسی
    Source("tasnim", "تسنیم", "fa",
           "https://www.tasnimnews.com/fa/rss/feed/0/7/0/%D8%A2%D8%AE%D8%B1%DB%8C%D9%86-%D8%AE%D8%A8%D8%B1%D9%87%D8%A7",
           iran_native=True),
    Source("fars", "فارس", "fa", "https://www.farsnews.ir/rss", iran_native=True),
    Source("irna", "ایرنا", "fa", "https://www.irna.ir/rss", iran_native=True),
    Source("isna", "ایسنا", "fa", "https://www.isna.ir/rss", iran_native=True),
    Source("mehr", "مهر", "fa", "https://www.mehrnews.com/rss", iran_native=True),
    Source("bbc_fa", "بی‌بی‌سی فارسی", "fa", "https://feeds.bbci.co.uk/persian/rss.xml", iran_native=True),
    # انگلیسی
    Source("bbc_me", "BBC", "en", "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml"),
    Source("fox", "Fox News", "en", "https://moxie.foxnews.com/google-publisher/world.xml"),
    Source("reuters", "Reuters", "en", gnews("Iran site:reuters.com when:1d"), fetch_og=False),
    Source("ap", "AP", "en", gnews("Iran site:apnews.com when:1d"), fetch_og=False),
    # عربی
    Source("aljazeera_en", "Al Jazeera", "en", "https://www.aljazeera.com/xml/rss/all.xml"),
    Source("aljazeera_ar", "الجزیره", "ar",
           "https://www.aljazeera.net/aljazeerarss/a7c186be-1baa-4bd4-9d80-a84db769f779/73d0e1b4-532f-45ef-b135-bfdb1f9b5a0b"),
    Source("alarabiya", "العربیه", "ar", "https://www.alarabiya.net/feed/rss2/ar.xml"),
    # روسی
    Source("tass_ru", "TASS", "ru", "https://tass.ru/rss/v2.xml"),
    Source("ria", "RIA", "ru", "https://ria.ru/export/rss2/archive/index.xml"),
]


def _feed_image(e):
    for key in ("media_content", "media_thumbnail"):
        for m in e.get(key, []) or []:
            if m.get("url"):
                return m["url"]
    for l in e.get("links", []) or []:
        if l.get("rel") == "enclosure" and str(l.get("type", "")).startswith("image"):
            return l.get("href")
    m = re.search(r'<img[^>]+src=["\']([^"\']+)', e.get("summary", "") or "")
    return m.group(1) if m else None


def _name(src, e):
    if "news.google.com" in src.url:
        t = (e.get("source") or {}).get("title")
        if t:
            return strip_html(t)
    return src.name


def fetch_source(src):
    r = SESSION.get(src.url, timeout=20)
    r.raise_for_status()
    feed = feedparser.parse(r.content)
    if not feed.entries:
        raise ValueError("feed empty or invalid")
    items = []
    for e in feed.entries[:config.MAX_ITEMS_PER_SOURCE]:
        url, title = e.get("link"), strip_html(e.get("title", ""))
        if not url or not title:
            continue
        summary = strip_html(e.get("summary", "") or e.get("description", ""))[:1500]
        t = e.get("published_parsed") or e.get("updated_parsed")
        pub = datetime(*t[:6], tzinfo=timezone.utc) if t else None
        items.append(Item(url, title, summary, src.id, _name(src, e), src.lang, pub,
                          _feed_image(e), src.iran_native, src.fetch_og))
    return items


for _s in SOURCES:
    if _s.id in ("tasnim", "fars", "irna", "alarabiya"):
        _s.enabled = False
