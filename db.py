import os
import re
import secrets
import time
from datetime import date

import aiosqlite

import config

_db = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, name TEXT, username TEXT,
  credits INTEGER DEFAULT 0, expiry INTEGER DEFAULT 0,
  banned INTEGER DEFAULT 0, joined INTEGER DEFAULT 0,
  free_day TEXT DEFAULT '', free_used INTEGER DEFAULT 0, total INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS keys(
  key TEXT PRIMARY KEY, credits INTEGER, days INTEGER,
  created_by INTEGER, created_at INTEGER, used_by INTEGER, used_at INTEGER);
CREATE TABLE IF NOT EXISTS admins(id INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS history(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, url TEXT,
  title TEXT, kind TEXT, status TEXT, ts INTEGER);
CREATE TABLE IF NOT EXISTS pending(
  req_id TEXT PRIMARY KEY, user_id INTEGER, hist_id INTEGER, src TEXT, ts INTEGER);
CREATE TABLE IF NOT EXISTS channels(
  user_id INTEGER, chat_id INTEGER, title TEXT, username TEXT, ts INTEGER,
  PRIMARY KEY(user_id, chat_id));
"""


def today():
    return date.today().isoformat()


async def init():
    global _db
    os.makedirs(os.path.dirname(config.DB_PATH) or '.', exist_ok=True)
    _db = await aiosqlite.connect(config.DB_PATH)
    _db.row_factory = aiosqlite.Row
    await _db.executescript(SCHEMA)
    await _db.commit()


async def ex(sql, args=()):
    cur = await _db.execute(sql, args)
    await _db.commit()
    return cur


async def one(sql, args=()):
    cur = await _db.execute(sql, args)
    return await cur.fetchone()


async def many(sql, args=()):
    cur = await _db.execute(sql, args)
    return await cur.fetchall()


# ---------- settings ----------
async def get_setting(k, d=""):
    r = await one("SELECT v FROM settings WHERE k=?", (k,))
    return r["v"] if r else d


async def set_setting(k, v):
    await ex("INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))


# ---------- users ----------
async def upsert_user(u):
    await ex(
        "INSERT INTO users(id,name,username,joined) VALUES(?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET name=excluded.name, username=excluded.username",
        (u.id, u.full_name, u.username or "", int(time.time())),
    )


async def get_user(uid):
    return await one("SELECT * FROM users WHERE id=?", (uid,))


async def all_user_ids():
    return [r["id"] for r in await many("SELECT id FROM users WHERE banned=0")]


async def set_ban(uid, v):
    cur = await ex("UPDATE users SET banned=? WHERE id=?", (1 if v else 0, uid))
    return cur.rowcount > 0


async def add_credits(uid, n, days=0):
    u = await get_user(uid)
    if not u:
        return False
    now = int(time.time())
    exp = u["expiry"]
    cr = u["credits"] if (not exp or exp > now) else 0
    if days > 0:
        exp = (exp if exp > now else now) + days * 86400
    await ex("UPDATE users SET credits=?,expiry=? WHERE id=?", (cr + n, exp, uid))
    return True


async def count_users():
    return (await one("SELECT COUNT(*) FROM users"))[0]


async def users_page(offset, limit):
    return await many("SELECT id,name,username,credits,expiry,banned,total,joined FROM users "
                      "ORDER BY joined DESC, id DESC LIMIT ? OFFSET ?", (limit, offset))


async def all_users():
    return await many("SELECT id,name,username,credits,expiry,banned,total,joined FROM users "
                      "ORDER BY joined DESC, id DESC")


# ---------- admins ----------
async def is_admin(uid):
    if uid == config.OWNER_ID:
        return True
    return bool(await one("SELECT 1 FROM admins WHERE id=?", (uid,)))


async def list_admins():
    return [r["id"] for r in await many("SELECT id FROM admins")]


async def add_admin(uid):
    await ex("INSERT OR IGNORE INTO admins(id) VALUES(?)", (uid,))


async def del_admin(uid):
    await ex("DELETE FROM admins WHERE id=?", (uid,))


# ---------- keys ----------
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def norm_key(raw):
    """KIRA XXXX XXXX XXXX (16 ខ្ទង់) · ទទួលយកទាំងមានដកឃ្លា/ដក/គ្មាន"""
    s = re.sub(r"[^A-Za-z0-9]", "", raw or "").upper()
    if len(s) != 16 or not s.startswith(config.KEY_PREFIX):
        return None
    return " ".join(s[i:i + 4] for i in range(0, 16, 4))


async def create_keys(credits, days, qty, by):
    out = []
    now = int(time.time())
    while len(out) < qty:
        body = "".join(secrets.choice(ALPHABET) for _ in range(16 - len(config.KEY_PREFIX)))
        k = norm_key(config.KEY_PREFIX + body)
        cur = await ex("INSERT OR IGNORE INTO keys(key,credits,days,created_by,created_at) VALUES(?,?,?,?,?)",
                       (k, credits, days, by, now))
        if cur.rowcount:
            out.append(k)
    return out


async def list_keys(unused=True, limit=300):
    cond = "used_by IS NULL" if unused else "used_by IS NOT NULL"
    return await many(f"SELECT * FROM keys WHERE {cond} ORDER BY created_at DESC LIMIT ?", (limit,))


async def delete_key(key):
    k = norm_key(key)
    if not k:
        return False
    cur = await ex("DELETE FROM keys WHERE key=?", (k,))
    return cur.rowcount > 0


async def redeem(uid, key):
    key = norm_key(key)
    r = await one("SELECT * FROM keys WHERE key=?", (key,)) if key else None
    if not r:
        return False, "❌ Key មិនត្រឹមត្រូវ (ទម្រង់: KIRA XXXX XXXX XXXX)"
    if r["used_by"]:
        return False, "❌ Key នេះត្រូវបានប្រើរួចហើយ"
    now = int(time.time())
    u = await get_user(uid)
    exp = u["expiry"]
    cr = u["credits"] if (not exp or exp > now) else 0
    if r["days"] > 0:
        exp = (exp if exp > now else now) + r["days"] * 86400
    elif exp and exp <= now:
        exp = 0
    cur = await ex("UPDATE keys SET used_by=?,used_at=? WHERE key=? AND used_by IS NULL", (uid, now, key))
    if cur.rowcount == 0:
        return False, "❌ Key នេះត្រូវបានប្រើរួចហើយ"
    await ex("UPDATE users SET credits=?,expiry=? WHERE id=?", (cr + r["credits"], exp, uid))
    days = f"{r['days']} ថ្ងៃ" if r["days"] else "គ្មានកំណត់ថ្ងៃ"
    return True, f"✅ ដាក់ Key ជោគជ័យ!\n➕ បានបន្ថែម <b>{r['credits']}</b> ដង · សុពលភាព {days}"


# ---------- quota ----------
async def quota(uid):
    u = await get_user(uid)
    now = int(time.time())
    valid = u["credits"] > 0 and (u["expiry"] == 0 or u["expiry"] > now)
    free = int(await get_setting("free_daily", "1"))
    used = u["free_used"] if u["free_day"] == today() else 0
    return {
        "credits": u["credits"] if valid else 0,
        "expiry": u["expiry"],
        "valid": valid,
        "free_left": max(0, free - used),
        "free_total": free,
        "total": u["total"],
        "expired": bool(u["expiry"] and u["expiry"] <= now),
    }


async def consume(uid):
    q = await quota(uid)
    if q["valid"]:
        await ex("UPDATE users SET credits=credits-1,total=total+1 WHERE id=?", (uid,))
        return "key"
    if q["free_left"] > 0:
        used = q["free_total"] - q["free_left"] + 1
        await ex("UPDATE users SET free_day=?,free_used=?,total=total+1 WHERE id=?", (today(), used, uid))
        return "free"
    return None


async def refund(uid, src):
    if src == "key":
        await ex("UPDATE users SET credits=credits+1,total=MAX(total-1,0) WHERE id=?", (uid,))
    elif src == "free":
        await ex("UPDATE users SET free_used=MAX(free_used-1,0),total=MAX(total-1,0) WHERE id=?", (uid,))


# ---------- history / pending ----------
async def add_history(uid, url, kind):
    cur = await ex("INSERT INTO history(user_id,url,title,kind,status,ts) VALUES(?,?,?,?,?,?)",
                   (uid, url, "", kind, "pending", int(time.time())))
    return cur.lastrowid


async def finish_history(hid, status, title=None):
    if title is not None:
        await ex("UPDATE history SET status=?,title=? WHERE id=?", (status, title[:200], hid))
    else:
        await ex("UPDATE history SET status=? WHERE id=?", (status, hid))


async def last_history(uid, n=10):
    return await many("SELECT * FROM history WHERE user_id=? ORDER BY id DESC LIMIT ?", (uid, n))


async def add_pending(req, uid, hid, src):
    await ex("INSERT INTO pending(req_id,user_id,hist_id,src,ts) VALUES(?,?,?,?,?)",
             (req, uid, hid, src, int(time.time())))


async def pop_pending(req):
    r = await one("SELECT * FROM pending WHERE req_id=?", (req,))
    if not r:
        return None
    cur = await ex("DELETE FROM pending WHERE req_id=?", (req,))
    return r if cur.rowcount else None


# ---------- saved channels / groups ----------
async def add_channel(uid, chat_id, title, username=""):
    await ex("INSERT INTO channels(user_id,chat_id,title,username,ts) VALUES(?,?,?,?,?) "
             "ON CONFLICT(user_id,chat_id) DO UPDATE SET title=excluded.title, username=excluded.username",
             (uid, chat_id, (title or str(chat_id))[:100], username or "", int(time.time())))


async def list_channels(uid):
    return await many("SELECT * FROM channels WHERE user_id=? ORDER BY ts DESC LIMIT 30", (uid,))


async def has_channel(uid, chat_id):
    return bool(await one("SELECT 1 FROM channels WHERE user_id=? AND chat_id=?", (uid, chat_id)))


async def del_channel(uid, chat_id):
    await ex("DELETE FROM channels WHERE user_id=? AND chat_id=?", (uid, chat_id))


# ---------- stats ----------
async def stats():
    now = int(time.time())
    day = now - 86400
    g = lambda r: r[0]
    return {
        "users": g(await one("SELECT COUNT(*) FROM users")),
        "banned": g(await one("SELECT COUNT(*) FROM users WHERE banned=1")),
        "active": g(await one("SELECT COUNT(*) FROM users WHERE credits>0 AND (expiry=0 OR expiry>?)", (now,))),
        "keys_free": g(await one("SELECT COUNT(*) FROM keys WHERE used_by IS NULL")),
        "keys_used": g(await one("SELECT COUNT(*) FROM keys WHERE used_by IS NOT NULL")),
        "dl_all": g(await one("SELECT COUNT(*) FROM history WHERE status='ok'")),
        "dl_day": g(await one("SELECT COUNT(*) FROM history WHERE status='ok' AND ts>?", (day,))),
        "fail": g(await one("SELECT COUNT(*) FROM history WHERE status='fail'")),
    }
