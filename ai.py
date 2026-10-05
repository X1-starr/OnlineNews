import json
import re
import time

import requests

import config
from utils import get_logger

log = get_logger()

SYSTEM = """You are the news editor of a Persian-language Telegram channel. The channel focuses on Iran but also publishes major world political news and important football news. Posts must feel lively, friendly and human, like a skilled and relaxed Persian news channel admin, but strictly truthful.
Return ONE JSON object and nothing else, with these keys:
"category": one of "iran", "world", "football".
- "iran": Iran (its government, officials, military, nuclear program, economy, sanctions, diplomacy, or major events inside Iran) is a central subject.
- "world": significant international political, diplomatic or military news, for example Palestine, Gaza, Israel, Lebanon, Iraq, Syria, Yemen, the Gulf states, Russia and Ukraine, or major decisions of world powers that matter to Iranians.
- "football": important football news, for example the Iran national team, Persepolis, Esteghlal, Iranian players abroad, or major international tournaments.
"relevant": true if the item fits one of the three categories. False for celebrity, crime, accidents, weather, business gossip, other sports, entertainment and minor local stories.
"importance": integer 1-5 (1 trivial, 3 notable, 5 major breaking news). Be strict for "world" and "football": use 4 or 5 only for truly significant news.
"duplicate": true if it reports the same event as one of RECENT_HEADLINES.
"emojis": 2 to 4 emojis placed before the headline, chosen to fit THIS story; the first one sets the mood. Use only emojis from this palette: 🚨 breaking, 💥 explosion or attack, 🔥 escalation, 🚀 missiles, ✈️ air strikes or flights, 🪖 military, ⚠️ warning, 🔴 serious alert, 💀 deaths, ☢️ nuclear, 🛢 oil and energy, 💰 economy, 📉 📈 markets, ⛔ sanctions, 🤝 talks and agreements, 🕊 ceasefire and peace, 🏛 government and politics, 🗳 elections, 🎙 statements, 👀 developing story, ⚽ football, 🏆 trophies, 🏟 stadium, 🥅 goals. You may add 1 or 2 country flag emojis for the countries central to the story. Use the dangerous-mood emojis (🚨 💥 🔴 💀) only when the story really involves attacks, casualties or serious threats; use calmer emojis for normal news. This field must contain emojis only.
"headline": short, punchy, natural Persian, max 70 characters, no emoji, no clickbait, no exaggeration; it may end with ! or ? when it fits.
"body": casual, conversational everyday Persian (خودمونی), like a friendly channel admin talking to followers; colloquial forms are welcome (می‌گن، شده، رسید), 2-5 short sentences, max 450 characters, no filler. The casual voice must never change the facts, and on stories about deaths or tragedies it stays respectful and human, with no jokes.
"details": array of 0 to 3 short Persian lines, each starting with one fitting emoji, for concrete facts found in the text such as date and time, opponent or parties, place, numbers or casualty counts. Copy dates and times exactly as given in the text and never convert time zones. Use [] if there is nothing concrete.
"ps": a short P.S. (پ.ن.) in the same friendly Persian, 1-2 sentences, max 220 characters, or "" when it does not fit. It is YOUR light take or a small analysis of what the story may mean, clearly an opinion and not a fact. Write it ONLY for important stories (importance 4 or 5); for all others use an empty string. Humor is allowed ONLY for football stories and for political or diplomatic stories (statements, decisions, negotiations, elections, rivalries), and there it must stay gentle and never insulting. For military, security, economic, humanitarian and all other stories use a calm, serious, informative tone with no jokes at all. Also never joke about deaths, injuries, victims, disasters or suffering (for those stories write one short serious remark or leave it empty); never mock real people or groups; never present a prediction as a fact; never give dates or times for future attacks or events. For risky stories (possible strikes, escalation, threats) describe in hedged terms what the signs in the text suggest and how uncertain that is (for example «به نظر می‌رسه ... ولی معلوم نیست»). Use only the given text and basic, widely known context; never invent details. Do not repeat the body.
Rules: use ONLY facts present in the given text. Never add, guess or infer anything. Keep names, numbers and dates exact. If something is unclear, leave it out. Attribute claims to the source or named speaker (for example «به گزارش ...»), especially claims by governments or state media; never present them as established fact. If relevant is false, headline, body, emojis and details may be empty."""

DEFAULT_BASE = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "vertex": "https://aiplatform.googleapis.com/v1",
    "openai": "https://api.openai.com/v1",
}


def _parse(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    return json.loads(text)


def _call(user_text, system=None):
    prov = config.AI_PROVIDER
    base = config.AI_BASE_URL or DEFAULT_BASE.get(prov, "")
    for attempt in range(3):
        try:
            if prov in ("gemini", "vertex"):
                path = "models" if prov == "gemini" else "publishers/google/models"
                url = f"{base}/{path}/{config.AI_MODEL}:generateContent"
                headers = {"x-goog-api-key": config.AI_API_KEY, "Content-Type": "application/json"}
                body = {
                    "systemInstruction": {"parts": [{"text": system or SYSTEM}]},
                    "contents": [{"role": "user", "parts": [{"text": user_text}]}],
                    "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
                }
            else:
                url = f"{base}/chat/completions"
                headers = {"Authorization": f"Bearer {config.AI_API_KEY}"}
                body = {
                    "model": config.AI_MODEL, "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "system", "content": system or SYSTEM},
                                 {"role": "user", "content": user_text}],
                }
            r = requests.post(url, headers=headers, json=body, timeout=120)
            if r.status_code in (429, 500, 502, 503, 504):
                USAGE["limited"] += int(r.status_code == 429)
                log.warning("AI temporary error %s (try %d)", r.status_code, attempt + 1)
                time.sleep(5 * 2 ** attempt)
                continue
            if not r.ok:
                log.error("AI error %s: %s", r.status_code, r.text[:300])
                return None
            data = r.json()
            _track(data, prov)
            if prov in ("gemini", "vertex"):
                parts = data["candidates"][0]["content"]["parts"]
                text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
            else:
                text = data["choices"][0]["message"]["content"]
            return _parse(text)
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as e:
            log.warning("AI call failed: %s (try %d)", type(e).__name__, attempt + 1)
            time.sleep(3)
    return None


def analyze(item, recent_headlines):
    payload = {
        "source": item.source_name, "language": item.lang,
        "title": item.title, "text": item.summary,
        "RECENT_HEADLINES": recent_headlines[-30:],
    }
    d = _call(json.dumps(payload, ensure_ascii=False))
    if not isinstance(d, dict):
        return None
    try:
        return {
            "relevant": bool(d.get("relevant")),
            "importance": int(d.get("importance", 0)),
            "duplicate": bool(d.get("duplicate")),
            "category": str(d.get("category", "iran")).strip().lower(),
            "emojis": str(d.get("emojis", "")).strip()[:30], "ps": str(d.get("ps", "")).strip()[:300],
            "details": ([str(x).strip() for x in d["details"] if str(x).strip()][:3] if isinstance(d.get("details"), list) else []),
            "headline": str(d.get("headline", "")).strip(),
            "body": str(d.get("body", "")).strip(),
        }
    except (TypeError, ValueError):
        return None



BATCH_NOTE = """

BATCH MODE: you receive a JSON object {"items": [...], "RECENT_HEADLINES": [...]}. Each item has an "id". Judge every item independently using all the rules above. Return ONE JSON object {"results": [...]} with exactly one object per item. Each result object has the key "id" (copied exactly) plus every key described above, and one more key: "merge_into": the id of ANOTHER item in this same batch that reports the same event and is the better version (more complete or more authoritative), otherwise null. The better version itself must have merge_into null."""


def _norm(d):
    det = d.get("details")
    m = d.get("merge_into")
    try:
        m = int(m) if m is not None else None
    except (TypeError, ValueError):
        m = None
    return {
        "relevant": bool(d.get("relevant")),
        "importance": int(d.get("importance", 0)),
        "duplicate": bool(d.get("duplicate")),
        "category": str(d.get("category", "iran")).strip().lower(),
        "emojis": str(d.get("emojis", "")).strip()[:30], "ps": str(d.get("ps", "")).strip()[:300],
        "details": [str(x).strip() for x in det if str(x).strip()][:3] if isinstance(det, list) else [],
        "headline": str(d.get("headline", "")).strip(),
        "body": str(d.get("body", "")).strip(),
        "merge_into": m,
    }


def analyze_batch(items, recent_headlines):
    payload = {
        "items": [{"id": i, "source": it.source_name, "language": it.lang,
                   "title": it.title, "text": it.summary[:600]} for i, it in enumerate(items)],
        "RECENT_HEADLINES": recent_headlines[-30:],
    }
    d = _call(json.dumps(payload, ensure_ascii=False), SYSTEM + BATCH_NOTE)
    if isinstance(d, list):
        d = {"results": d}
    if not isinstance(d, dict) or not isinstance(d.get("results"), list):
        return None
    out = {}
    for r in d["results"]:
        try:
            i = int(r.get("id"))
            if 0 <= i < len(items):
                out[i] = _norm(r)
        except (TypeError, ValueError, AttributeError):
            continue
    return out



USAGE = {"calls": 0, "tokens": 0, "limited": 0}


def _track(data, prov):
    try:
        if prov in ("gemini", "vertex"):
            t = (data.get("usageMetadata") or {}).get("totalTokenCount", 0)
        else:
            t = (data.get("usage") or {}).get("total_tokens", 0)
        USAGE["tokens"] += int(t or 0)
    except (TypeError, ValueError, AttributeError):
        pass
    USAGE["calls"] += 1
