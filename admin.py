import html
import os
import time

import requests

import ai
import config
import state
from db import DB
from utils import get_logger

log = get_logger()
API = "https://api.telegram.org/bot{}/{}"

TUNABLE = {
    "MIN_IMPORTANCE": ("MIN_IMPORTANCE", 1, 5),
    "PS_MIN_IMPORTANCE": ("PS_MIN_IMPORTANCE", 1, 6),
    "MAX_POSTS_PER_CYCLE": ("MAX_POSTS_PER_CYCLE", 1, 30),
    "MAX_AI_CALLS_PER_CYCLE": ("MAX_AI_CALLS", 1, 30),
    "BATCH_SIZE": ("BATCH_SIZE", 1, 20),
    "CHECK_INTERVAL_MIN": ("CHECK_INTERVAL_MIN", 5, 720),
    "WIPE_DAYS": ("WIPE_DAYS", 1, 90),
    "AI_DAILY_TOKEN_BUDGET": ("AI_DAILY_TOKEN_BUDGET", 0, 100000000),
}

HELP = """🛠 <b>پنل مدیریت OnlineNews</b>

از دکمه‌ها استفاده کنید یا دستور بنویسید:
/status علائم حیاتی
/stats آمار
/pause و /resume خاموش و روشن
/runnow بررسی فوری
/recent آخرین پست‌ها
/sources وضعیت منابع
/errors آخرین خطاها
/settings تنظیمات
/set نام مقدار ← تغییر تنظیم
/post متن ← اطلاعیه برای کانال
/wipe پاک‌سازی دیتابیس
/cancel لغو"""

CMD_ACTIONS = {
    "/status": "st", "/stats": "stats", "/pause": "pause", "/resume": "resume",
    "/runnow": "run", "/recent": "recent", "/sources": "src", "/errors": "err",
    "/settings": "cfg", "/wipe": "wipe",
}


def tg(method, payload=None, timeout=60):
    try:
        r = requests.post(API.format(config.TELEGRAM_BOT_TOKEN, method),
                          json=payload or {}, timeout=timeout)
        return r.json()
    except (requests.RequestException, ValueError) as e:
        log.warning("admin %s failed: %s", method, type(e).__name__)
        return None


def send(text, kb=None):
    p = {"chat_id": config.ADMIN_CHAT_ID, "text": text[:3900], "parse_mode": "HTML",
         "disable_web_page_preview": True}
    if kb:
        p["reply_markup"] = kb
    return tg("sendMessage", p, timeout=30)


def menu(db):
    paused = db.meta_get("paused") == "1"
    return {"inline_keyboard": [
        [{"text": "📊 وضعیت", "callback_data": "st"}, {"text": "📈 آمار", "callback_data": "stats"}],
        [{"text": "▶️ روشن کردن" if paused else "⏸ خاموش کردن", "callback_data": "toggle"},
         {"text": "🔄 بررسی الان", "callback_data": "run"}],
        [{"text": "📰 آخرین پست‌ها", "callback_data": "recent"}, {"text": "🌐 منابع", "callback_data": "src"}],
        [{"text": "⚙️ تنظیمات", "callback_data": "cfg"}, {"text": "🧾 خطاها", "callback_data": "err"}],
        [{"text": "📢 اطلاعیه", "callback_data": "ann"}, {"text": "🧹 پاک‌سازی", "callback_data": "wipe"}],
    ]}


def ago(ts):
    if not ts:
        return "—"
    s = int(time.time() - float(ts))
    if s < 60:
        return "%d ثانیه پیش" % s
    if s < 3600:
        return "%d دقیقه پیش" % (s // 60)
    if s < 86400:
        return "%d ساعت پیش" % (s // 3600)
    return "%d روز پیش" % (s // 86400)


def dur(s):
    s = max(int(s), 0)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    parts = []
    if d:
        parts.append("%d روز" % d)
    if h:
        parts.append("%d ساعت" % h)
    parts.append("%d دقیقه" % (s // 60))
    return " و ".join(parts)


def status_text(db):
    S = state.S
    paused = db.meta_get("paused") == "1"
    d = db.daily_row()
    u = ai.USAGE
    tokens = d["tokens"] + u["tokens"]
    budget = config.AI_DAILY_TOKEN_BUDGET
    if budget > 0:
        budget_line = "بودجه روزانه: {:,} | باقی‌مانده: {:,}".format(budget, max(budget - tokens, 0))
    else:
        budget_line = "بودجه روزانه: تنظیم نشده"
    nxt = "—"
    if S["next_cycle"] and not paused:
        left = S["next_cycle"] - time.time()
        nxt = dur(left) + " دیگر" if left > 0 else "به‌زودی"
    last_wipe = db.meta_get("last_wipe")
    wipe_next = "—"
    if last_wipe:
        days_left = (float(last_wipe) + config.WIPE_DAYS * 86400 - time.time()) / 86400
        wipe_next = "%d روز دیگر" % max(int(days_left), 0)
    secs = " (%d ثانیه)" % S["last_cycle_secs"] if S["last_cycle_secs"] else ""
    lines = [
        "🩺 <b>علائم حیاتی ربات</b>", "",
        "وضعیت: " + ("⏸ خاموش (موقت)" if paused else "🟢 روشن"),
        "مدت اجرا: " + dur(time.time() - S["started"]),
        "آخرین بررسی: " + ago(S["last_cycle"]) + secs,
        "بررسی بعدی: " + nxt,
        "الان در حال بررسی: " + ("بله" if S["cycle_running"] else "خیر"),
        "", "📊 <b>امروز</b>",
        "منتشرشده: %d | ردشده: %d | خطا: %d" % (d["published"], d["skipped"], d["errors"]),
        "تعداد بررسی: %d" % d["cycles"],
        "", "🤖 <b>هوش مصنوعی</b>",
        "مدل: " + html.escape(config.AI_MODEL),
        "درخواست امروز: {} | توکن مصرفی: {:,} | خطای 429: {}".format(
            d["ai_calls"] + u["calls"], tokens, d["limited"] + u["limited"]),
        budget_line,
        "<i>سهمیه واقعی گوگل از API قابل خواندن نیست؛ اعداد بالا مصرف ثبت‌شده توسط خود ربات است.</i>",
        "", "🗄 <b>دیتابیس</b>",
        "حجم: {:,} KB | اخبار ذخیره‌شده: {:,}".format(db.size_kb(), db.news_count()),
        "آخرین پاک‌سازی: %s | بعدی: %s" % (ago(last_wipe), wipe_next),
    ]
    if S["last_error"]:
        lines += ["", "آخرین خطا: " + html.escape(S["last_error"][:150])]
    return "\n".join(lines)


def stats_text(db):
    lines = ["📈 <b>آمار ۷ روز اخیر</b>", "", "<pre>روز      منتشر  رد  خطا  توکن"]
    for r in db.daily_last(7):
        lines.append("%-8s %5d %4d %4d %7d" % (r["day"][5:], r["published"], r["skipped"], r["errors"], r["tokens"]))
    lines.append("</pre>")
    lines.append("کل پست‌های منتشرشده (تا یک سال اخیر): %d" % db.total_published())
    sc = db.status_counts()
    if sc:
        lines += ["", "وضعیت اخبار موجود در دیتابیس:"]
        lines += ["• %s: %d" % (html.escape(k), v) for k, v in sorted(sc.items())]
    return "\n".join(lines)


def recent_text(db):
    rows = db.recent_published(6)
    if not rows:
        return "هنوز پستی در دیتابیس نیست."
    out = ["📰 <b>آخرین پست‌ها</b>", ""]
    for head, src, ts in rows:
        out.append("• %s (%s، %s)" % (html.escape(head or "—"), html.escape(src or ""), ago(ts)))
    return "\n".join(out)


def src_text():
    h = state.S["source_health"]
    if not h:
        return "هنوز دوری اجرا نشده."
    out = ["🌐 <b>وضعیت منابع</b>", ""]
    for sid in sorted(h):
        x = h[sid]
        if x["ok"]:
            out.append("✅ %s — %d خبر جدید، %s" % (html.escape(sid), x["n"], ago(x["t"])))
        else:
            out.append("❌ %s — %s" % (html.escape(sid), html.escape(x["err"][:80])))
    return "\n".join(out)


def err_text():
    path = os.path.join(config.BASE, "logs", "bot.log")
    try:
        lines = open(path, encoding="utf-8").read().splitlines()[-400:]
    except OSError:
        return "فایل لاگ پیدا نشد."
    bad = [l for l in lines if " WARNING " in l or " ERROR " in l][-12:]
    if not bad:
        return "✅ خطای اخیری در لاگ نیست."
    return "🧾 <b>آخرین هشدارها و خطاها</b>\n\n" + "\n".join(html.escape(l[:170]) for l in bad)


def cfg_text():
    out = ["⚙️ <b>تنظیمات قابل تغییر</b>", "", "با دستور <code>/set نام مقدار</code> عوضشان کنید:", ""]
    for k, (attr, lo, hi) in TUNABLE.items():
        out.append("<code>%s</code> = %s (بین %s تا %s)" % (k, getattr(config, attr, "—"), lo, hi))
    out.append("")
    out.append("مثال: <code>/set MIN_IMPORTANCE 3</code>")
    return "\n".join(out)


def apply_overrides(db):
    for k, (attr, lo, hi) in TUNABLE.items():
        v = db.meta_get("set:" + k)
        if v is not None and v.lstrip("-").isdigit():
            setattr(config, attr, int(v))


def do_set(arg, db):
    parts = arg.split()
    if len(parts) != 2 or parts[0].upper() not in TUNABLE or not parts[1].lstrip("-").isdigit():
        send(cfg_text(), menu(db))
        return
    key = parts[0].upper()
    attr, lo, hi = TUNABLE[key]
    val = int(parts[1])
    if not lo <= val <= hi:
        send("مقدار باید بین %s و %s باشد." % (lo, hi), menu(db))
        return
    setattr(config, attr, val)
    db.meta_set("set:" + key, str(val))
    send("✅ %s = %d" % (key, val), menu(db))


def send_announcement(text):
    link = '<a href="%s">@online_newsIR</a>' % config.CHANNEL_URL
    body = "📢 <b>اطلاعیه</b>\n\n" + html.escape(text) + "\n\n💢 " + link + " | 🤖 Bot News"
    kb = {"inline_keyboard": [[{"text": config.CHANNEL_BUTTON, "url": config.CHANNEL_URL}]]}
    res = tg("sendMessage", {"chat_id": config.TELEGRAM_CHAT_ID, "text": body, "parse_mode": "HTML",
                             "reply_markup": kb, "disable_web_page_preview": True}, timeout=30)
    return bool(res and res.get("ok"))


def draft(text, db, pending):
    pending["ann_text"] = text[:3500]
    pending["wait"] = None
    kb = {"inline_keyboard": [[{"text": "✅ ارسال به کانال", "callback_data": "ann_ok"},
                               {"text": "❌ لغو", "callback_data": "ann_no"}]]}
    send("👀 <b>پیش‌نمایش اطلاعیه</b>\n\n" + html.escape(pending["ann_text"]), kb)


def act(a, db, pending):
    if a == "st":
        send(status_text(db), menu(db))
    elif a == "stats":
        send(stats_text(db), menu(db))
    elif a in ("toggle", "pause", "resume"):
        paused = db.meta_get("paused") == "1"
        want = (not paused) if a == "toggle" else (a == "pause")
        db.meta_set("paused", "1" if want else "0")
        if want:
            send("⏸ ربات خاموش شد و خبری نمی‌گیرد و منتشر نمی‌کند. اگر یک دور در حال اجراست، تمام می‌شود.", menu(db))
        else:
            state.RUN_NOW.set()
            send("▶️ ربات روشن شد و بررسی بعدی همین حالا شروع می‌شود.", menu(db))
    elif a == "run":
        if db.meta_get("paused") == "1":
            send("ربات خاموش است. اول روشنش کنید.", menu(db))
        elif state.S["cycle_running"]:
            send("یک دور بررسی همین الان در حال اجراست.", menu(db))
        else:
            state.RUN_NOW.set()
            send("🔄 بررسی دستی شروع شد. نتیجه را در «وضعیت» ببینید.", menu(db))
    elif a == "recent":
        send(recent_text(db), menu(db))
    elif a == "src":
        send(src_text(), menu(db))
    elif a == "err":
        send(err_text(), menu(db))
    elif a == "cfg":
        send(cfg_text(), menu(db))
    elif a == "ann":
        pending.clear()
        pending["wait"] = "ann"
        send("📢 متن اطلاعیه را همین‌جا بفرستید (یا /cancel).")
    elif a == "ann_ok":
        text = pending.pop("ann_text", None)
        if not text:
            send("اطلاعیه‌ای در انتظار نیست.", menu(db))
        else:
            send("✅ در کانال منتشر شد." if send_announcement(text) else "❌ ارسال به کانال ناموفق بود.", menu(db))
    elif a == "ann_no":
        pending.clear()
        send("لغو شد.", menu(db))
    elif a == "wipe":
        pending["wipe"] = True
        kb = {"inline_keyboard": [[{"text": "🧹 بله، پاک کن", "callback_data": "wipe_ok"},
                                   {"text": "❌ لغو", "callback_data": "ann_no"}]]}
        send("🧹 همه اخبار ذخیره‌شده پاک می‌شوند و یک دور بی‌صدا خبرهای فعلی را «دیده‌شده» ثبت می‌کند تا چیز قدیمی دوباره منتشر نشود. آمار روزانه می‌ماند. مطمئنید؟", kb)
    elif a == "wipe_ok":
        if pending.pop("wipe", None):
            state.S["wipe_request"] = True
            state.RUN_NOW.set()
            send("🧹 درخواست ثبت شد و در شروع دور بعدی انجام می‌شود (اگر ربات خاموش است، بعد از روشن شدن).", menu(db))
        else:
            send("درخواستی در انتظار نیست.", menu(db))


def handle(u, db, pending):
    cb = u.get("callback_query")
    if cb:
        tg("answerCallbackQuery", {"callback_query_id": cb["id"]}, timeout=15)
        if str(cb.get("from", {}).get("id")) == config.ADMIN_CHAT_ID:
            act(cb.get("data", ""), db, pending)
        return
    msg = u.get("message")
    if (not msg or str(msg.get("from", {}).get("id")) != config.ADMIN_CHAT_ID
            or msg.get("chat", {}).get("type") != "private"):
        return
    text = (msg.get("text") or "").strip()
    if not text:
        return
    if text.startswith("/"):
        cmd, _, arg = text.partition(" ")
        cmd = cmd.split("@")[0].lower()
        arg = arg.strip()
        if cmd in ("/start", "/panel", "/menu", "/help"):
            pending.clear()
            send(HELP, menu(db))
        elif cmd == "/cancel":
            pending.clear()
            send("لغو شد.", menu(db))
        elif cmd == "/post":
            if arg:
                draft(arg, db, pending)
            else:
                act("ann", db, pending)
        elif cmd == "/set":
            do_set(arg, db)
        elif cmd in CMD_ACTIONS:
            act(CMD_ACTIONS[cmd], db, pending)
        else:
            send("دستور ناشناخته. /panel", menu(db))
    elif pending.get("wait") == "ann":
        draft(text, db, pending)
    else:
        send("برای دیدن پنل /panel را بزنید.", menu(db))


def loop():
    db = DB()
    apply_overrides(db)
    offset = int(db.meta_get("tg_offset", "0") or 0)
    pending = {}
    log.info("admin panel started")
    while True:
        res = tg("getUpdates", {"offset": offset, "timeout": 50,
                                "allowed_updates": ["message", "callback_query"]}, timeout=70)
        if not res or not res.get("ok"):
            time.sleep(10)
            continue
        for u in res.get("result", []):
            offset = u["update_id"] + 1
            try:
                handle(u, db, pending)
            except Exception:
                log.exception("admin handler crashed")
        db.meta_set("tg_offset", str(offset))
