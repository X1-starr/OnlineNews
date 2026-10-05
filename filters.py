import difflib

from utils import normalize

_RAW = [
    "iran", "iranian", "tehran", "khamenei", "pezeshkian", "araghchi", "irgc",
    "revolutionary guard", "natanz", "fordow", "isfahan", "hormuz",
    "ایران", "تهران", "ایرانی", "خامنه ای", "پزشکیان", "عراقچی", "سپاه", "نطنز", "فردو", "هرمز",
    "إيران", "ايران", "طهران", "الإيرانية", "خامنئي", "بزشكيان", "عراقجي", "الحرس الثوري",
    "иран", "тегеран", "хаменеи", "пезешкиан", "аракчи", "ксир",
]

_EXTRA = [
    "palestin", "gaza", "israel", "hamas", "hezbollah", "iraq", "syria", "lebanon", "yemen",
    "houthi", "saudi", "ukrain", "russia", "putin", "trump", "netanyahu", "nato", "sanction",
    "football", "soccer", "world cup", "premier league", "champions league",
    "فوتبال", "پرسپولیس", "استقلال", "تیم ملی", "جام جهانی", "فلسطین", "غزه", "اسرائیل",
    "حماس", "حزب الله", "عراق", "سوریه", "لبنان", "یمن", "عربستان", "اوکراین", "روسیه",
    "پوتین", "ترامپ", "نتانیاهو",
    "فلسطين", "غزة", "إسرائيل", "العراق", "سوريا", "اليمن", "كرة القدم", "كأس العالم",
    "палестин", "газа", "израил", "хамас", "ирак", "сири", "ливан", "йемен", "украин",
    "путин", "трамп", "футбол",
]
_IRAN = [normalize(k) for k in _RAW]
KEYWORDS = [normalize(k) for k in _RAW + _EXTRA]


def is_iran(item):
    text = " " + normalize(item.title + " " + item.summary)
    return any(" " + k in text for k in _IRAN)


def iran_keyword_match(item):
    if item.iran_native:
        return True
    text = " " + normalize(item.title + " " + item.summary)
    return any(" " + k in text for k in KEYWORDS)


def is_similar(title, others, threshold=0.82):
    n = normalize(title)
    return any(difflib.SequenceMatcher(None, n, normalize(o)).ratio() >= threshold for o in others)
