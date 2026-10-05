import argparse
import fcntl
import json
import os
import random
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

import admin
import ai
import config
import state
from ai import analyze, analyze_batch
from db import DB
from filters import iran_keyword_match, is_iran, is_similar
from images import get_image
from publisher import alert, publish
from sources import SOURCES, Item, fetch_source
from utils import get_logger, title_hash

log = get_logger()
hstate = {"bad": 0, "alerted": False, "quiet": False}


def _root(res, i):
    t = res[i]["merge_into"]
    seen = {i}
    while t is not None and t in res and t not in seen:
        seen.add(t)
        nxt = res[t]["merge_into"]
        if nxt is None or nxt not in res or nxt in seen:
            return t
        t = nxt
    return None


def _handle_batch(db, chunk, res, titles, heads, health, room):
    roots, extra = {}, {}
    for i in res:
        rt = _root(res, i)
        if rt is not None:
            roots[i] = rt
            extra.setdefault(rt, []).append(chunk[i][0].source_name)

    published = 0
    for i, (it, h) in enumerate(chunk):
        r = res.get(i)
        if r is None:
            db.save(it, h, "error")
            continue
        if i in roots:
            db.save(it, h, "skipped_duplicate")
            continue
        if not r["relevant"]:
            db.save(it, h, "skipped_irrelevant")
            continue
        if r["duplicate"]:
            db.save(it, h, "skipped_duplicate")
            continue
        need = config.MIN_IMPORTANCE if r["category"] == "iran" else config.MIN_IMPORTANCE + 1
        if r["importance"] < need:
            db.save(it, h, "skipped_low")
            continue
        if not (r["headline"] and r["body"]):
            db.save(it, h, "error")
            continue
        if published >= room:
            continue
        names = [it.source_name]
        for n in extra.get(i, []):
            if n not in names:
                names.append(n)
        ps = r["ps"] if r["importance"] >= config.PS_MIN_IMPORTANCE else ""
        ok = publish(r["headline"], r["body"], names, get_image(it),
                     r["category"], r["emojis"], r["details"], ps)
        if ok:
            db.save(it, h, "published", r["headline"])
            titles.append(it.title)
            heads.append(r["headline"])
            published += 1
            log.info("published: %s", r["headline"])
            time.sleep(3)
        else:
            health["pub_fail"] += 1
            db.save(it, h, "error")
    return published


def run_cycle(db, baseline=False):
    health = {"ai_abort": False, "pub_fail": 0, "posted": 0}
    cutoff = datetime.now(timezone.utc) - timedelta(hours=config.MAX_AGE_HOURS)
    cands = []
    for src in SOURCES:
        if not src.enabled:
            continue
        try:
            items = fetch_source(src)
        except Exception as e:
            log.warning("[%s] fetch failed: %s", src.id, e)
            state.S["source_health"][src.id] = {"ok": False, "t": time.time(), "n": 0, "err": str(e)[:120]}
            state.S["last_error"] = "[%s] %s" % (src.id, str(e)[:100])
            continue
        new = 0
        for it in items:
            if it.published and it.published < cutoff:
                continue
            h = title_hash(it.title)
            if db.seen(it.url, h):
                continue
            cands.append((it, h))
            new += 1
        state.S["source_health"][src.id] = {"ok": True, "t": time.time(), "n": new, "err": ""}
        log.info("[%s] %d new", src.id, new)
        time.sleep(2)

    if baseline:
        for it, h in cands:
            db.save(it, h, "baseline")
        log.info("baseline: %d items marked as seen", len(cands))
        return health

    if config.AI_DAILY_TOKEN_BUDGET > 0:
        used = db.daily_row()["tokens"] + ai.USAGE["tokens"]
        if used >= config.AI_DAILY_TOKEN_BUDGET:
            log.info("daily token budget reached; skipping AI this cycle")
            return health

    now = datetime.now(timezone.utc)
    cands.sort(key=lambda x: (is_iran(x[0]), x[0].published or now), reverse=True)
    titles, heads = db.recent()

    seen_h, todo = set(), []
    limit = config.MAX_AI_CALLS * config.BATCH_SIZE
    for it, h in cands:
        if len(todo) >= limit:
            break
        if h in seen_h:
            db.save(it, h, "skipped_duplicate")
            continue
        seen_h.add(h)
        if not iran_keyword_match(it):
            db.save(it, h, "skipped_irrelevant")
            continue
        if is_similar(it.title, titles):
            db.save(it, h, "skipped_duplicate")
            continue
        todo.append((it, h))

    posted, ai_fail = 0, 0
    for start in range(0, len(todo), config.BATCH_SIZE):
        if posted >= config.MAX_POSTS_PER_CYCLE:
            break
        chunk = todo[start:start + config.BATCH_SIZE]
        res = analyze_batch([c[0] for c in chunk], heads)
        time.sleep(config.AI_DELAY_SEC)
        if not res:
            for it, h in chunk:
                db.save(it, h, "error")
            ai_fail += 1
            if ai_fail >= 2:
                log.warning("AI failing repeatedly; stopping this cycle")
                state.S["last_error"] = "AI failing repeatedly"
                health["ai_abort"] = True
                break
            continue
        ai_fail = 0
        posted += _handle_batch(db, chunk, res, titles, heads, health,
                                config.MAX_POSTS_PER_CYCLE - posted)
    health["posted"] = posted
    log.info("cycle done: %d candidates, %d sent to AI, %d published",
             len(cands), len(todo), posted)
    return health


def maybe_wipe(db):
    now = time.time()
    last = db.meta_get("last_wipe")
    if last is None:
        db.meta_set("last_wipe", str(int(now)))
        return False
    due = now - float(last) > config.WIPE_DAYS * 86400
    if due or state.S["wipe_request"]:
        state.S["wipe_request"] = False
        db.wipe()
        log.info("database wiped; running silent baseline cycle")
        alert("🧹 دیتابیس اخبار پاک شد. این دور فقط خبرهای فعلی را «دیده‌شده» ثبت می‌کند و پستی نمی‌گذارد.")
        return True
    return False


def flush_usage(db):
    u = ai.USAGE
    db.add_daily(cycles=1, ai_calls=u["calls"], tokens=u["tokens"], limited=u["limited"])
    u["calls"] = u["tokens"] = u["limited"] = 0


def health_check(db, h):
    bad = h["ai_abort"] or h["pub_fail"] >= 2
    if bad:
        hstate["bad"] += 1
        if hstate["bad"] >= 2 and not hstate["alerted"]:
            why = "خطای هوش مصنوعی" if h["ai_abort"] else "خطا در ارسال به تلگرام"
            alert("⚠️ ربات OnlineNews دو دور پشت‌سرهم مشکل داشت: " + why + ". لاگ را چک کنید.")
            hstate["alerted"] = True
    else:
        if hstate["alerted"]:
            alert("✅ ربات OnlineNews دوباره سالم شد.")
        hstate["bad"], hstate["alerted"] = 0, False

    last = db.last_published()
    if last and time.time() - last > config.NO_POST_ALERT_HOURS * 3600:
        if not hstate["quiet"]:
            alert("ℹ️ ربات بیش از %d ساعت است پستی منتشر نکرده. اگر انتظار خبر داشتید، لاگ را چک کنید."
                  % config.NO_POST_ALERT_HOURS)
            hstate["quiet"] = True
    else:
        hstate["quiet"] = False


def check_sources():
    for s in SOURCES:
        try:
            items = fetch_source(s)
            img = sum(1 for i in items if i.image)
            print(f"✅ {s.id}: {len(items)} items, {img} with image")
        except Exception as e:
            print(f"❌ {s.id}: {type(e).__name__}: {e}")
        time.sleep(1)


def test_ai():
    it = Item("http://x", "Iran rejects new nuclear talks, foreign ministry says",
              "Iran's foreign ministry spokesman said on Monday that Tehran would not "
              "return to nuclear negotiations under current conditions.",
              "test", "Reuters", "en", None, None, False, False)
    print(json.dumps(analyze(it, []), ensure_ascii=False, indent=2))


def test_telegram():
    ok = publish("تست ربات OnlineNews", "این یک پیام آزمایشی است و می‌توانید آن را حذف کنید.", ["تست"])
    print("✅ sent" if ok else "❌ failed (see logs/bot.log)")


def test_alert():
    if not config.ADMIN_CHAT_ID:
        print("ADMIN_CHAT_ID is not set in .env")
        return
    alert("✅ تست هشدار ربات OnlineNews")
    print("sent (if you pressed Start in the bot's private chat, you got it)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-sources", action="store_true")
    ap.add_argument("--test-ai", action="store_true")
    ap.add_argument("--test-telegram", action="store_true")
    ap.add_argument("--test-alert", action="store_true")
    ap.add_argument("--once", action="store_true", help="run one cycle and exit")
    a = ap.parse_args()

    if a.check_sources:
        return check_sources()
    bad = config.missing_settings()
    if bad:
        sys.exit("Missing in .env: " + ", ".join(bad))
    if a.test_ai:
        return test_ai()
    if a.test_telegram:
        return test_telegram()
    if a.test_alert:
        return test_alert()

    lock = open(os.path.join(config.BASE, "bot.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit("Bot is already running.")

    db = DB()
    admin.apply_overrides(db)
    if db.meta_get("last_wipe") is None:
        db.meta_set("last_wipe", str(int(time.time())))
    if config.ADMIN_CHAT_ID and not a.once:
        threading.Thread(target=admin.loop, daemon=True).start()
    log.info("OnlineNews bot started (every %d min)", config.CHECK_INTERVAL_MIN)

    try:
        while True:
            wait = 30
            paused = db.meta_get("paused") == "1"
            try:
                if not paused:
                    baseline = maybe_wipe(db)
                    state.S["cycle_running"] = True
                    t0 = time.time()
                    try:
                        health = run_cycle(db, baseline)
                    finally:
                        state.S["cycle_running"] = False
                    state.S["last_cycle"] = time.time()
                    state.S["last_cycle_secs"] = time.time() - t0
                    flush_usage(db)
                    if not baseline:
                        health_check(db, health)
                    wait = config.CHECK_INTERVAL_MIN * 60 + random.randint(0, 120)
            except Exception:
                log.exception("cycle crashed")  # لاگ، بدون افشای کلیدها
                state.S["last_error"] = "cycle crashed (see logs)"
                wait = 300
            if a.once:
                break
            state.S["next_cycle"] = None if paused else time.time() + wait
            state.RUN_NOW.wait(timeout=wait)
            state.RUN_NOW.clear()
    except KeyboardInterrupt:
        log.info("stopped by user")


if __name__ == "__main__":
    main()
