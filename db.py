import os
import sqlite3
import time
from datetime import datetime

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS news(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url TEXT UNIQUE, title TEXT, source TEXT, published TEXT, hash TEXT,
  processed_at INTEGER, status TEXT, attempts INTEGER DEFAULT 0, headline_fa TEXT
);
CREATE INDEX IF NOT EXISTS idx_news_hash ON news(hash);
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS daily(
  day TEXT PRIMARY KEY,
  published INTEGER DEFAULT 0, skipped INTEGER DEFAULT 0, errors INTEGER DEFAULT 0,
  ai_calls INTEGER DEFAULT 0, tokens INTEGER DEFAULT 0, limited INTEGER DEFAULT 0,
  cycles INTEGER DEFAULT 0
);
"""
DAILY_COLS = ("published", "skipped", "errors", "ai_calls", "tokens", "limited", "cycles")


def today():
    return datetime.now().strftime("%Y-%m-%d")


class DB:
    def __init__(self, path=config.DB_PATH):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        self.c = sqlite3.connect(path, timeout=30)
        self.c.execute("PRAGMA journal_mode=WAL")
        self.c.executescript(SCHEMA)
        self.c.commit()

    # ---- اخبار
    def seen(self, url, h):
        rows = self.c.execute(
            "SELECT status, attempts FROM news WHERE url=? OR hash=?", (url, h)).fetchall()
        return any(s != "error" or a >= config.MAX_ATTEMPTS for s, a in rows)

    def save(self, item, h, status, headline=None):
        row = self.c.execute("SELECT attempts FROM news WHERE url=?", (item.url,)).fetchone()
        attempts = row[0] if row else 0
        if status == "error":
            attempts += 1
        self.c.execute(
            """INSERT INTO news(url,title,source,published,hash,processed_at,status,attempts,headline_fa)
               VALUES(?,?,?,?,?,?,?,?,?)
               ON CONFLICT(url) DO UPDATE SET status=excluded.status,
                 processed_at=excluded.processed_at, attempts=excluded.attempts,
                 headline_fa=COALESCE(excluded.headline_fa, headline_fa)""",
            (item.url, item.title, item.source_id,
             item.published.isoformat() if item.published else None,
             h, int(time.time()), status, attempts, headline))
        self.c.commit()
        if status == "published":
            self.add_daily(published=1)
        elif status.startswith("skipped"):
            self.add_daily(skipped=1)
        elif status == "error":
            self.add_daily(errors=1)

    def last_published(self):
        r = self.c.execute("SELECT MAX(processed_at) FROM news WHERE status='published'").fetchone()
        return r[0] if r and r[0] else None

    def recent(self, hours=24, limit=40):
        since = int(time.time()) - hours * 3600
        rows = self.c.execute(
            """SELECT title, headline_fa FROM news
               WHERE status='published' AND processed_at>?
               ORDER BY processed_at DESC LIMIT ?""", (since, limit)).fetchall()
        return [r[0] for r in rows], [r[1] for r in rows if r[1]]

    def recent_published(self, n=6):
        return self.c.execute(
            """SELECT headline_fa, source, processed_at FROM news
               WHERE status='published' ORDER BY id DESC LIMIT ?""", (n,)).fetchall()

    def status_counts(self):
        return dict(self.c.execute("SELECT status, COUNT(*) FROM news GROUP BY status").fetchall())

    def news_count(self):
        return self.c.execute("SELECT COUNT(*) FROM news").fetchone()[0]

    def size_kb(self):
        try:
            return os.path.getsize(self.path) // 1024
        except OSError:
            return 0

    # ---- تنظیمات داخلی
    def meta_get(self, k, default=None):
        r = self.c.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return r[0] if r else default

    def meta_set(self, k, v):
        self.c.execute("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))
        self.c.commit()

    # ---- آمار روزانه
    def add_daily(self, **kw):
        cols = [k for k in kw if k in DAILY_COLS]
        if not cols:
            return
        d = today()
        self.c.execute("INSERT OR IGNORE INTO daily(day) VALUES(?)", (d,))
        sets = ", ".join("%s=%s+?" % (k, k) for k in cols)
        self.c.execute("UPDATE daily SET " + sets + " WHERE day=?", [kw[k] for k in cols] + [d])
        self.c.commit()

    def daily_row(self, day=None):
        r = self.c.execute(
            "SELECT " + ",".join(DAILY_COLS) + " FROM daily WHERE day=?", (day or today(),)).fetchone()
        return dict(zip(DAILY_COLS, r)) if r else dict.fromkeys(DAILY_COLS, 0)

    def daily_last(self, n=7):
        rows = self.c.execute(
            "SELECT day," + ",".join(DAILY_COLS) + " FROM daily ORDER BY day DESC LIMIT ?", (n,)).fetchall()
        return [dict(zip(("day",) + DAILY_COLS, r)) for r in rows]

    def total_published(self):
        return self.c.execute("SELECT COALESCE(SUM(published),0) FROM daily").fetchone()[0]

    # ---- پاک‌سازی کامل اخبار (آمار روزانه می‌ماند)
    def wipe(self):
        self.c.execute("DELETE FROM news")
        self.c.execute("DELETE FROM daily WHERE day < date('now','-365 day')")
        self.c.commit()
        self.c.execute("VACUUM")
        self.meta_set("last_wipe", str(int(time.time())))
