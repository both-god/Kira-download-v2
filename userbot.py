import logging
import os

import config
import db

log = logging.getLogger("userbot")
client = None
_login = None


def ready():
    return client is not None


async def creds():
    api_id = int(await db.get_setting("ub_api_id", str(config.API_ID)) or 0)
    api_hash = await db.get_setting("ub_api_hash", config.API_HASH)
    return api_id, api_hash


async def start():
    global client
    sess = await db.get_setting("ub_session", config.SESSION_STRING)
    api_id, api_hash = await creds()
    if not (sess and api_id and api_hash):
        log.warning("Userbot មិនទាន់ភ្ជាប់ — ភ្ជាប់តាម Admin Panel → 🤖 ភ្ជាប់ Userbot")
        return False
    await stop()
    try:
        from pyrogram import Client
        c = Client("userbot", api_id=api_id, api_hash=api_hash, session_string=sess, in_memory=True)
        await c.start()
        client = c
        try:
            async for _ in c.get_dialogs(limit=200):
                pass
        except Exception as e:
            log.warning("get_dialogs: %s", e)
        log.info("Userbot ready")
        return True
    except Exception as e:
        log.error("Userbot start failed: %s", e)
        client = None
        return False


async def stop():
    global client
    if client:
        try:
            await client.stop()
        except Exception:
            pass
    client = None


async def info():
    if not client:
        return None
    me = await client.get_me()
    return f"{me.first_name or ''} (@{me.username or '-'})" + (" ⭐Premium" if getattr(me, "is_premium", False) else "")


async def check_group(gid):
    try:
        ch = await client.get_chat(gid)
        return True, ch.title
    except Exception as e:
        return False, str(e)


# ---------- login ក្នុង Bot ----------
async def login_cancel():
    global _login
    if _login:
        try:
            await _login["c"].disconnect()
        except Exception:
            pass
    _login = None


async def login_begin(api_id, api_hash, phone):
    global _login
    await login_cancel()
    from pyrogram import Client
    c = Client("login", api_id=api_id, api_hash=api_hash, in_memory=True)
    await c.connect()
    try:
        sent = await c.send_code(phone)
    except Exception:
        await c.disconnect()
        raise
    _login = {"c": c, "phone": phone, "hash": sent.phone_code_hash, "api_id": api_id, "api_hash": api_hash}


async def login_code(code):
    from pyrogram.errors import SessionPasswordNeeded
    try:
        await _login["c"].sign_in(_login["phone"], _login["hash"], code)
    except SessionPasswordNeeded:
        return "password"
    await _finish()
    return "ok"


async def login_password(pw):
    await _login["c"].check_password(pw)
    await _finish()


async def _finish():
    s = await _login["c"].export_session_string()
    await db.set_setting("ub_session", s)
    await db.set_setting("ub_api_id", str(_login["api_id"]))
    await db.set_setting("ub_api_hash", _login["api_hash"])
    await login_cancel()
    await start()


async def logout():
    await stop()
    await db.set_setting("ub_session", "")


async def upload(chat_id, path, caption, kind, meta):
    th = meta.get("thumb")
    if th and not os.path.exists(th):
        th = None
    if kind == "audio":
        return await client.send_audio(chat_id, path, caption=caption, title=meta.get("title"),
                                       duration=int(meta.get("duration") or 0), thumb=th)
    try:
        return await client.send_video(chat_id, path, caption=caption, supports_streaming=True,
                                       duration=int(meta.get("duration") or 0),
                                       width=int(meta.get("width") or 0), height=int(meta.get("height") or 0),
                                       thumb=th)
    except Exception as e:
        log.warning("send_video failed (%s) → send_document", e)
        return await client.send_document(chat_id, path, caption=caption)
