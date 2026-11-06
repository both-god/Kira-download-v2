import asyncio
import csv
import html
import io
import logging
import os
import re
import secrets
import shutil
import time
from datetime import datetime

from aiohttp import web
from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import config
import db
import downloader as dl
import kb
import userbot

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("bot")
router = Router()
esc = html.escape

URLS, ACTIVE, TASKS = {}, {}, set()
PREVIEWS, JOBMETA = {}, {}
SEM = asyncio.Semaphore(config.MAX_PARALLEL)

DEFAULT_WELCOME = (
    "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
    "┃  ⚡ <b>MEDIA DOWNLOADER BOT</b>\n"
    "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
    "👋 <b>សួស្តី! ស្វាគមន៍មកកាន់សេវាកម្មទាញយក</b>\n\n"
    "┌ 📥 <b>គាំទ្រ៖</b> YouTube, TikTok, FB, IG, Spotify...\n"
    "├ ⚡ <b>ល្បឿនលឿន៖</b> គាំទ្រឯកសារធំដល់ 2GB\n"
    "└ 🔑 <b>កូតា៖</b> ប្រើប្រាស់ Key ដើម្បីបន្ថែមចំនួនដង\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "💡 <i>ផ្ញើតំណភ្ជាប់ (Link) មកកាន់ទីនេះដើម្បីចាប់ផ្តើម!</i>"
)
DEFAULT_BUY = (
    "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
    "┃  💎 <b>តារាងតម្លៃ & ទិញ KEY</b>\n"
    "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
    "┌ 🔹 <b>គម្រោង Standard:</b> ទាក់ទង Admin\n"
    "├ 🔹 <b>គម្រោង VIP:</b> ទាក់ទង Admin\n"
    "└ 📞 <b>ទំនាក់ទំនងម្ចាស់ Bot៖</b> ផ្ញើសារទៅកាន់ Admin\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "✨ <i>ទូទាត់រហ័សតាម KHQR និងដំណើរការ Key ភ្លាមៗ!</i>"
)

REPLY_IDS = [
    "download", "redeem", "account", "buy", "history", "help", "admin", "a_create",
    "a_keys", "a_del", "a_users", "a_stats", "a_cast", "a_ban", "a_unban",
    "a_credit", "a_colors", "a_settings", "a_admins", "a_userbot", "a_ulist", "back"
]
LABELS = {kb.BUTTONS[i][0]: i for i in REPLY_IDS if i in kb.BUTTONS}

PROMPTS = {
    "redeem": "╭─ 🔑 <b>បញ្ចូល KEY</b>\n╰─ ផ្ញើ Key របស់អ្នកមក\n\nឧទាហរណ៍៖ <code>KIRA ABCD EFGH JKLM</code>",
    "create": "╭─ ➕ <b>បង្កើត KEY ថ្មី</b>\n╰─ ផ្ញើ៖ <code>ចំនួនដង ចំនួនថ្ងៃ ចំនួនKey</code>\n\nឧទាហរណ៍៖ <code>50 30 5</code> (5 Key, 1 Key = 50 ដង, 30 ថ្ងៃ)",
    "delkey": "╭─ 🗑 <b>លុប KEY</b>\n╰─ ផ្ញើ Key ដែលចង់លុបចេញពីប្រព័ន្ធ",
    "cast": "╭─ 📢 <b>ផ្សាយដំណឹង (BROADCAST)</b>\n╰─ ផ្ញើសារ (អត្ថបទ/រូបភាព/វីដេអូ) ដែលចង់ផ្ញើទៅកាន់ User ទាំងអស់",
    "ban": "╭─ 🚫 <b>BAN USER</b>\n╰─ ផ្ញើ User ID ដែលចង់ផ្អាកដំណើរការ",
    "unban": "╭─ ✅ <b>UNBAN USER</b>\n╰─ ផ្ញើ User ID ដែលចង់ដោះ Ban",
    "credit": "╭─ 💎 <b>បញ្ចូល CREDIT ផ្ទាល់</b>\n╰─ ផ្ញើ៖ <code>user_id ចំនួនដង [ថ្ងៃ]</code>\n\nឧទាហរណ៍៖ <code>123456789 20 30</code>",
    "user": "╭─ 👥 <b>ពិនិត្យ USER</b>\n╰─ ផ្ញើ User ID ដែលចង់ស្វែងរកព័ត៌មាន",
    "admin": "╭─ 👮 <b>គ្រប់គ្រង ADMIN</b>\n╰─ ផ្ញើ៖ <code>add 123456</code> ឬ <code>del 123456</code> ឬ <code>list</code>",
    "group": "╭─ 👥 <b>កំណត់ GROUP ID ផ្ទុកឯកសារធំ</b>\n╰─ ផ្ញើ Group ID (ឧ. <code>-1001234567890</code>)",
    "nubtoken": "╭─ 🔑 <b>NUB API TOKEN</b>\n╰─ ផ្ញើ Token មក (Bot នឹងលុបសារចេញភ្លាមៗដើម្បីសុវត្ថិភាព)",
    "cookies": "╭─ 🍪 <b>បញ្ចូល COOKIES</b>\n╰─ សូមផ្ញើឯកសារ <b>cookies.txt</b> ជា File",
    "newchan": (
        "╭─ 📢 <b>បន្ថែម CHANNEL / GROUP សម្រាប់ POST</b>\n"
        "├ ផ្ញើ <b>@username</b> ឬ <b>ID</b> (ឧ. <code>-1001234567890</code>)\n"
        "└ ⚠️ <i>Bot និងអ្នកត្រូវតែជា Admin ដែលមានសិទ្ធិ Post Messages</i>"
    ),
    "free": "╭─ 🎁 <b>កំណត់ FREE QUOTA</b>\n╰─ ផ្ញើចំនួន Free ក្នុងមួយថ្ងៃ (0 = បិទការឱ្យ Free)",
    "welcome": "╭─ 💬 <b>សារស្វាគមន៍ថ្មី</b>\n╰─ ផ្ញើ Text ថ្មី (គាំទ្រទម្រង់ HTML)",
    "buy": "╭─ 🛒 <b>ព័ត៌មានទិញ KEY</b>\n╰─ ផ្ញើព័ត៌មានទិញ Key ថ្មី",
    "ub_api": "╭─ 🔐 <b>USERBOT API CONFIG</b>\n╰─ ផ្ញើ <code>API_ID API_HASH</code> (ពី my.telegram.org)",
    "ub_phone": "╭─ 📱 <b>USERBOT PHONE NUMBER</b>\n╰─ ផ្ញើលេខទូរស័ព្ទគណនី (ឧ. <code>+85512345678</code>)",
    "ub_code": "╭─ 💬 <b>TELEGRAM LOGIN CODE</b>\n╰─ ផ្ញើដោយដកឃ្លា ឬដាក់ដក ឧ. <code>1 2 3 4 5</code>",
    "ub_pass": "╭─ 🔑 <b>TWO-STEP VERIFICATION</b>\n╰─ ផ្ញើពាក្យសម្ងាត់ 2FA នៃគណនី Telegram",
}


class Ask(StatesGroup):
    input = State()


def fmt_ts(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "-"


# ---------------- Mini Web Server សម្រាប់ Render Port 8080 ----------------
async def web_health(request):
    return web.Response(text="Bot is running smoothly!", status=200)


async def start_web_server():
    app = web.Application()
    app.router.add_get("/", web_health)
    app.router.add_get("/health", web_health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info(f"🚀 Render HTTP Health Check server running on port {port}")


# ---------------- Middleware ----------------
class Guard(BaseMiddleware):
    async def __call__(self, handler, event, data):
        msg = event if isinstance(event, Message) else getattr(event, "message", None)
        if not msg or msg.chat.type != "private" or not event.from_user:
            return await handler(event, data)
        u = event.from_user
        await db.upsert_user(u)
        if await db.is_admin(u.id):
            return await handler(event, data)
        row = await db.get_user(u.id)
        if row and row.get("banned"):
            if isinstance(event, Message):
                await event.answer("🚫 <b>គណនីរបស់អ្នកត្រូវបានផ្អាកមិនឱ្យប្រើប្រាស់ Bot នេះ។</b>")
            return
        if await db.get_setting("maint", "0") == "1":
            if isinstance(event, Message):
                await event.answer("🔧 <b>Bot កំពុងស្ថិតក្រោមការថែទាំបណ្តោះអាសន្ន។ សូមត្រឡប់មកវិញពេលក្រោយ!</b>")
            return
        return await handler(event, data)


router.message.outer_middleware(Guard())
router.callback_query.outer_middleware(Guard())


# ---------------- UI Formatters & Helpers ----------------
async def ask(m: Message, state: FSMContext, act: str):
    await state.set_state(Ask.input)
    await state.update_data(act=act)
    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ បោះបង់", callback_data="cancel_action")]]
    )
    await m.answer(PROMPTS[act] + "\n\n<i>ចុចប៊ូតុងខាងក្រោម ឬវាយ /cancel ដើម្បីបោះបង់</i>", reply_markup=cancel_kb)


async def account_text(uid):
    q = await db.quota(uid)
    exp = "គ្មានកំណត់" if q["expiry"] == 0 else fmt_ts(q["expiry"])
    if q["expired"]:
        exp += " ⚠️ (ផុតកំណត់)"
    
    return (
        "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
        "┃  👤 <b>ព័ត៌មានគណនីរបស់អ្នក</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"┌ 🆔 <b>ID របស់អ្នក៖</b> <code>{uid}</code>\n"
        f"├ 💎 <b>ចំនួនទាញយកនៅសល់៖</b> <code>{q['credits']}</code> ដង\n"
        f"├ ⏳ <b>សុពលភាព Key៖</b> {exp}\n"
        f"├ 🎁 <b>កូតា Free ថ្ងៃនេះ៖</b> {q['free_left']}/{q['free_total']}\n"
        f"└ 📥 <b>បានទាញយកសរុប៖</b> {q['total']} ដង\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━"
    )


def account_inline_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Refresh", callback_data="refresh_account"),
                InlineKeyboardButton(text="🔑 បញ្ចូល Key", callback_data="act:redeem"),
            ],
            [InlineKeyboardButton(text="🛒 ទិញ Key បន្ថែម", callback_data="act:buy")]
        ]
    )


async def no_credit_text():
    return (
        "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
        "┃  ⛔ <b>អស់ចំនួនទាញយក</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "អ្នកបានប្រើប្រាស់កូតាអស់ ឬ Key បានផុតកំណត់ហើយ។\n\n"
        + await db.get_setting("buy_text", DEFAULT_BUY)
    )


async def settings_view():
    g = await db.get_setting("group_id", str(config.BIG_GROUP_ID))
    free = await db.get_setting("free_daily", "1")
    maint = await db.get_setting("maint", "0") == "1"
    delg = await db.get_setting("del_group", "0") == "1"
    tok = await db.get_setting("nub_token", config.NUB_API_TOKEN)
    txt = (
        "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
        "┃  ⚙️ <b>ការកំណត់ប្រព័ន្ធ (SETTINGS)</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"┌ 🔑 <b>NUB Token:</b> {'✅ រួចរាល់' if tok else '❌ មិនទាន់ដាក់'}\n"
        f"├ 👥 <b>Storage Group ID:</b> <code>{g or 'មិនទាន់កំណត់'}</code>\n"
        f"├ 🎁 <b>Free ប្រចាំថ្ងៃ:</b> <code>{free}</code> ដង\n"
        f"├ 🔧 <b>Maintenance Mode:</b> {'បើក ⚠️' if maint else 'បិទ'}\n"
        f"└ 🤖 <b>Userbot Status:</b> {'✅ ដំណើរការ' if userbot.ready() else '❌ មិនទាន់ភ្ជាប់'}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    return txt, kb.settings_kb(maint, delg)


async def send_keys(m: Message, keys, head):
    body = "\n".join(f"<code>{k}</code>" for k in keys)
    if len(keys) <= 15:
        await m.answer(f"{head}\n\n{body}")
    else:
        await m.answer(head)
        await m.answer_document(BufferedInputFile("\n".join(keys).encode(), "keys.txt"))


async def do_create(m: Message, text: str):
    p = text.split()
    if len(p) != 3 or not all(x.isdigit() for x in p):
        return await m.answer("❌ <b>ទម្រង់ខុស៖</b> សូមផ្ញើជា <code>ចំនួនដង ចំនួនថ្ងៃ ចំនួនKey</code>\nឧទាហរណ៍៖ <code>50 30 5</code>")
    n, d, q = map(int, p)
    if not (n >= 1 and 0 <= d <= 3650 and 1 <= q <= 500):
        return await m.answer("❌ <b>តម្លៃមិនត្រឹមត្រូវ៖</b> Key ត្រូវតែចន្លោះពី 1 ដល់ 500")
    keys = await db.create_keys(n, d, q, m.from_user.id)
    await send_keys(m, keys, f"✅ <b>បង្កើតបានជោគជ័យ!</b>\n┌ ចំនួន៖ <b>{q}</b> Key\n├ កូតា៖ <b>{n}</b> ដង\n└ សុពលភាព៖ <b>{d or 'គ្មានកំណត់'}</b> ថ្ងៃ")


async def ub_status():
    inf = await userbot.info()
    g = await db.get_setting("group_id", str(config.BIG_GROUP_ID))
    return (
        "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
        "┃  🤖 <b>ស្ថានភាព USERBOT</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"┌ 📡 <b>ការតភ្ជាប់៖</b> {('✅ ' + esc(inf)) if inf else '❌ មិនទាន់ភ្ជាប់'}\n"
        f"└ 👥 <b>Storage Group៖</b> <code>{g or 'មិនទាន់កំណត់'}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━"
    )


async def ub_done(m: Message):
    inf = await userbot.info()
    if not inf:
        return await m.answer("❌ មិនអាចភ្ជាប់បានឡើយ សូមព្យាយាមម្តងទៀត។")
    g = int(await db.get_setting("group_id", str(config.BIG_GROUP_ID)) or 0)
    extra = "⚠️ មិនទាន់កំណត់ Group ID នៅឡើយ"
    if g:
        ok, t = await userbot.check_group(g)
        extra = f"👥 Group: {esc(str(t))[:80]}" if ok else f"⚠️ រក Group មិនឃើញ: {esc(str(t))[:120]}"
    await m.answer(
        "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
        "┃  ✅ <b>ភ្ជាប់ USERBOT ជោគជ័យ</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"┌ 👤 <b>គណនី៖</b> {esc(inf)}\n"
        f"└ 📌 <b>ស្ថានភាព៖</b> {extra}"
    )


async def ub_step(m: Message, state: FSMContext, act: str, text: str):
    try:
        await m.delete()
    except Exception:
        pass
    if act == "ub_api":
        p = text.replace(",", " ").split()
        if len(p) != 2 or not p[0].isdigit() or not re.fullmatch(r"[0-9a-fA-F]{32}", p[1]):
            await m.answer("❌ <b>ទម្រង់ខុស៖</b> API_ID ជាលេខ និង API_HASH ត្រូវមាន 32 ខ្ទង់។")
            return await ask(m, state, "ub_api")
        await db.set_setting("ub_api_id", p[0])
        await db.set_setting("ub_api_hash", p[1])
        return await ask(m, state, "ub_phone")
    if act == "ub_phone":
        api_id, api_hash = await userbot.creds()
        try:
            await userbot.login_begin(api_id, api_hash, text.replace(" ", ""))
        except Exception as e:
            if "API_ID_INVALID" in str(e) or type(e).__name__ == "ApiIdInvalid":
                await db.set_setting("ub_api_id", "0")
                await db.set_setting("ub_api_hash", "")
                await m.answer("❌ API_ID/API_HASH មិនត្រឹមត្រូវ សូមបញ្ចូលម្តងទៀត។")
                return await ask(m, state, "ub_api")
            await m.answer(f"❌ {esc(str(e))[:250]}\nសូមផ្ញើលេខទូរស័ព្ទម្តងទៀត")
            return await ask(m, state, "ub_phone")
        return await ask(m, state, "ub_code")
    if act == "ub_code":
        try:
            r = await userbot.login_code(re.sub(r"\D", "", text))
        except Exception as e:
            n = type(e).__name__
            if n == "PhoneCodeInvalid":
                await m.answer("❌ កូដផ្ទៀងផ្ទាត់មិនត្រឹមត្រូវ")
                return await ask(m, state, "ub_code")
            await userbot.login_cancel()
            return await m.answer(f"❌ {n}: កូដផុតកំណត់ សូមចុចភ្ជាប់ជាថ្មីម្តងទៀត។")
        if r == "password":
            return await ask(m, state, "ub_pass")
        return await ub_done(m)
    if act == "ub_pass":
        try:
            await userbot.login_password(text)
        except Exception:
            await m.answer("❌ ពាក្យសម្ងាត់ 2FA មិនត្រឹមត្រូវ")
            return await ask(m, state, "ub_pass")
        await ub_done(m)


# ---------------- Commands ----------------
@router.message(CommandStart(), F.chat.type == "private")
async def start(m: Message, state: FSMContext):
    await state.clear()
    adm = await db.is_admin(m.from_user.id)
    await m.answer(await db.get_setting("welcome", DEFAULT_WELCOME), reply_markup=kb.main_kb(adm))


@router.message(Command("cancel"))
async def cancel(m: Message, state: FSMContext):
    await state.clear()
    await userbot.login_cancel()
    await m.answer("❎ <b>ប្រតិបត្តិការត្រូវបានបោះបង់។</b>")


@router.callback_query(F.data == "cancel_action")
async def cancel_callback(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await userbot.login_cancel()
    await cb.answer("បានបោះបង់")
    try:
        await cb.message.edit_text("❎ <b>ប្រតិបត្តិការត្រូវបានបោះបង់។</b>")
    except Exception:
        pass


@router.callback_query(F.data == "refresh_account")
async def refresh_acc_cb(cb: CallbackQuery):
    await cb.answer("🔄 បានធ្វើបច្ចុប្បន្នភាព")
    txt = await account_text(cb.from_user.id)
    try:
        await cb.message.edit_text(txt, reply_markup=account_inline_kb())
    except Exception:
        pass


@router.callback_query(F.data.startswith("act:"))
async def quick_act_cb(cb: CallbackQuery, state: FSMContext):
    act = cb.data.split(":")[1]
    await cb.answer()
    if act == "redeem":
        await ask(cb.message, state, "redeem")
    elif act == "buy":
        await cb.message.answer(await db.get_setting("buy_text", DEFAULT_BUY))


@router.message(Command("myid"))
async def myid(m: Message):
    await m.answer(
        "╭─ 🆔 <b>លេខសម្គាល់ (ID)</b>\n"
        f"├ 👤 User ID: <code>{m.from_user.id}</code>\n"
        f"╰ 💬 Chat ID: <code>{m.chat.id}</code>"
    )


@router.message(Command("redeem"), F.chat.type == "private")
async def redeem_cmd(m: Message):
    parts = (m.text or "").split(maxsplit=1)
    if len(parts) < 2:
        return await m.answer("របៀបប្រើ៖ <code>/redeem KEY</code>")
    ok, msg = await db.redeem(m.from_user.id, parts[1])
    await m.answer(msg)


@router.message(Command("genkey"), F.chat.type == "private")
async def genkey_cmd(m: Message):
    if not await db.is_admin(m.from_user.id):
        return
    await do_create(m, (m.text or "").replace("/genkey", "", 1).strip())


@router.message(Command("testapi"), F.chat.type == "private")
async def testapi_cmd(m: Message):
    if not await db.is_admin(m.from_user.id):
        return
    parts = (m.text or "").split(maxsplit=1)
    url = parts[1] if len(parts) > 1 else "https://youtu.be/EHtxN9sORzI"
    await m.answer("⏳ <b>កំពុងធ្វើតេស្ត API...</b>")
    await m.answer(f"<pre>{esc(await dl.diagnose(url))[:3500]}</pre>")


@router.message(Command("apiquota"), F.chat.type == "private")
async def apiquota_cmd(m: Message):
    if not await db.is_admin(m.from_user.id):
        return
    try:
        await m.answer(f"<pre>{esc(await dl.api_quota())}</pre>")
    except Exception as e:
        await m.answer(f"❌ {esc(str(e))[:300]}")


@router.message(Command("cookies"), F.chat.type == "private")
async def cookies_cmd(m: Message, state: FSMContext):
    if m.from_user.id != config.OWNER_ID:
        return
    await ask(m, state, "cookies")


# ---------------- Reply-Keyboard Menu ----------------
@router.message(F.chat.type == "private", F.text.in_(LABELS))
async def menu(m: Message, state: FSMContext):
    await state.clear()
    bid, uid = LABELS[m.text], m.from_user.id
    adm = await db.is_admin(uid)
    if (bid.startswith("a_") or bid == "admin") and not adm:
        return
    if bid == "download":
        await m.answer(
            "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
            "┃  📥 <b>របៀបទាញយកមេឌៀ</b>\n"
            "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
            "គ្រាន់តែផ្ញើតំណភ្ជាប់ (Link) មកទីនេះ៖\n"
            "┌ 🎬 <b>វីដេអូ៖</b> YouTube, TikTok, Facebook, IG...\n"
            "└ 🎵 <b>ចម្រៀង៖</b> Spotify, SoundCloud, YouTube Music...\n\n"
            "⚡ <i>Bot នឹងដំណើរការទាញយកភ្លាមៗ!</i>"
        )
    elif bid == "redeem":
        await ask(m, state, "redeem")
    elif bid == "account":
        await m.answer(await account_text(uid), reply_markup=account_inline_kb())
    elif bid == "buy":
        await m.answer(await db.get_setting("buy_text", DEFAULT_BUY))
    elif bid == "history":
        rows = await db.last_history(uid)
        if not rows:
            return await m.answer("📜 <b>មិនទាន់មានប្រវត្តិទាញយកនៅឡើយទេ។</b>")
        ic = {"ok": "✅", "fail": "❌", "pending": "⏳"}
        lines = [f"├ {ic.get(r['status'], '•')} <b>{esc(r['title'] or r['url'])[:35]}</b>\n│  └ <i>{r['kind']} · {fmt_ts(r['ts'])}</i>" for r in rows]
        await m.answer(
            "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
            "┃  📜 <b>ប្រវត្តិទាញយក ១០ ចុងក្រោយ</b>\n"
            "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
            + "\n".join(lines)
            + "\n━━━━━━━━━━━━━━━━━━━━━━━━"
        )
    elif bid == "help":
        await m.answer(
            "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
            "┃  ℹ️ <b>ការណែនាំអំពីការប្រើប្រាស់</b>\n"
            "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
            "1️⃣ ផ្ញើតំណភ្ជាប់វីដេអូ ឬចម្រៀង\n"
            "2️⃣ ជ្រើសរើសប្រភេទ (🎬 Video ឬ 🎵 Audio)\n"
            "3️⃣ ជ្រើសរើសទីតាំងទទួល (ផ្ញើក្នុង Chat នេះ ឬ Post ចូល Channel)\n"
            "4️⃣ រង់ចាំទទួលឯកសារជាការស្រេច!\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 <i>គាំទ្រឯកសារទំហំធំរហូតដល់ 2000MB (2GB)!</i>"
        )
    elif bid == "admin":
        await m.answer("🛠 <b>ផ្ទាំងគ្រប់គ្រង Admin (Admin Dashboard)</b>", reply_markup=kb.admin_kb())
    elif bid == "back":
        await m.answer("🏠 <b>ត្រឡប់មកមឺនុយមេ</b>", reply_markup=kb.main_kb(adm))
    elif bid == "a_create":
        await ask(m, state, "create")
    elif bid == "a_keys":
        rows = await db.list_keys(True)
        if not rows:
            return await m.answer("📋 <b>មិនមាន Key ទំនេរក្នុងប្រព័ន្ធទេ។</b>")
        lines = [f"{r['key']} | {r['credits']} ដង | {r['days'] or '∞'} ថ្ងៃ" for r in rows]
        if len(lines) <= 15:
            await m.answer(f"📋 <b>Key ទំនេរក្នុងស្តុក:</b> <code>{len(lines)}</code>\n\n" + "\n".join(f"<code>{l}</code>" for l in lines))
        else:
            await m.answer_document(BufferedInputFile("\n".join(lines).encode(), "keys_unused.txt"),
                                    caption=f"📋 Key ទំនេរក្នុងស្តុក: {len(lines)}")
    elif bid == "a_del":
        await ask(m, state, "delkey")
    elif bid == "a_users":
        await ask(m, state, "user")
    elif bid == "a_ulist":
        t, k = await users_view(1)
        await m.answer(t, reply_markup=k)
    elif bid == "a_stats":
        s = await db.stats()
        await m.answer(
            "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
            "┃  📊 <b>ស្ថិតិប្រព័ន្ធសរុប (STATS)</b>\n"
            "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
            f"┌ 👥 <b>អ្នកប្រើប្រាស់សរុប៖</b> <code>{s['users']}</code> នាក់\n"
            f"├ 🚫 <b>គណនី Banned៖</b> <code>{s['banned']}</code> នាក់\n"
            f"├ 💎 <b>សកម្មភាព (Active)៖</b> <code>{s['active']}</code> នាក់\n"
            f"├ 🔑 <b>Key ទំនេរ / ប្រើរួច៖</b> <code>{s['keys_free']}</code> / <code>{s['keys_used']}</code>\n"
            f"├ 📥 <b>ទាញយកសរុប៖</b> <code>{s['dl_all']}</code> ដង\n"
            f"├ ⚡ <b>ទាញយកក្នុង 24h៖</b> <code>{s['dl_day']}</code> ដង\n"
            f"└ ❌ <b>ទាញយកបរាជ័យ៖</b> <code>{s['fail']}</code> ដង\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━"
        )
    elif bid == "a_cast":
        await ask(m, state, "cast")
    elif bid in ("a_ban", "a_unban"):
        await ask(m, state, "ban" if bid == "a_ban" else "unban")
    elif bid == "a_credit":
        await ask(m, state, "credit")
    elif bid == "a_colors":
        await m.answer("🎨 <b>កំណត់ពណ៌ប៊ូតុង</b>\nជ្រើសរើសពណ៌សម្រាប់ប៊ូតុងនីមួយៗតាមចំណង់ចំណូលចិត្ត។", reply_markup=kb.colors_kb())
    elif bid == "a_settings":
        t, k = await settings_view()
        await m.answer(t, reply_markup=k)
    elif bid == "a_admins":
        if uid != config.OWNER_ID:
            return await m.answer("⛔ <b>សម្រាប់ម្ចាស់ Bot ប៉ុណ្ណោះ!</b>")
        await ask(m, state, "admin")
    elif bid == "a_userbot":
        if uid != config.OWNER_ID:
            return await m.answer("⛔ <b>សម្រាប់ម្ចាស់ Bot ប៉ុណ្ណោះ!</b>")
        await m.answer(await ub_status(), reply_markup=kb.ub_kb())


# ---------------- Admin Users Pagination ----------------
USERS_PER_PAGE = 15


async def users_view(page):
    total = await db.count_users()
    pages = max(1, (total + USERS_PER_PAGE - 1) // USERS_PER_PAGE)
    page = min(max(page, 1), pages)
    rows = await db.users_page((page - 1) * USERS_PER_PAGE, USERS_PER_PAGE)
    lines = []
    for i, r in enumerate(rows, (page - 1) * USERS_PER_PAGE + 1):
        un = f"@{esc(r['username'])}" if r["username"] else "គ្មាន"
        lines.append(f"├ {i}. {'🚫 ' if r['banned'] else ''}<b>{esc(r['name'] or '-')}</b> ({un})\n│  └ ID: <code>{r['id']}</code> · Credits: <b>{r['credits']}</b>")
    
    text = (
        "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
        f"┃  📃 <b>បញ្ជី User (ទំព័រ {page}/{pages})</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        + ("\n".join(lines) if lines else "មិនទាន់មាន User ទេ")
        + "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>សរុបទាំងអស់៖</b> <code>{total}</code> នាក់"
    )
    return text, kb.users_kb(page, pages)


def _csv_safe(v):
    v = "" if v is None else str(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@") else v


def users_csv(rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "name", "username", "credits", "banned", "total_downloads", "joined"])
    for r in rows:
        w.writerow([r["id"], _csv_safe(r["name"]), r["username"] or "",
                    r["credits"], r["banned"], r["total"], fmt_ts(r["joined"])])
    return buf.getvalue().encode("utf-8-sig")


@router.callback_query(F.data.startswith("ul:"))
async def ul_cb(cb: CallbackQuery):
    if not await db.is_admin(cb.from_user.id):
        return await cb.answer()
    arg = cb.data.split(":")[1]
    if arg == "noop":
        return await cb.answer()
    if arg == "csv":
        rows = await db.all_users()
        await cb.answer()
        return await cb.message.answer_document(
            BufferedInputFile(users_csv(rows), f"users_{datetime.now():%Y%m%d_%H%M}.csv"),
            caption=f"👥 បញ្ជី User ទាំងអស់: {len(rows)} នាក់")
    t, k = await users_view(int(arg))
    await cb.answer()
    try:
        await cb.message.edit_text(t, reply_markup=k)
    except TelegramBadRequest:
        pass


# ---------------- FSM Process ----------------
@router.message(Ask.input, F.chat.type == "private")
async def ask_input(m: Message, state: FSMContext):
    data = await state.get_data()
    act = data.get("act")
    text = (m.text or m.caption or "").strip()
    uid = m.from_user.id
    await state.clear()
    adm = await db.is_admin(uid)

    if act == "newchan":
        return await newchan_step(m, state, uid, text, data.get("tok"))
    if act == "caption":
        return await caption_step(m, state, uid, data.get("ptok"))
    if act and act.startswith("ub_"):
        if uid != config.OWNER_ID:
            return
        return await ub_step(m, state, act, text)
    if act != "redeem" and not adm:
        return

    if act == "redeem":
        ok, msg = await db.redeem(uid, text)
        await m.answer(msg)
    elif act == "create":
        await do_create(m, text)
    elif act == "delkey":
        await m.answer("✅ <b>បានលុប Key រួចរាល់!</b>" if await db.delete_key(text) else "❌ រកមិនឃើញ Key នេះទេ")
    elif act == "cast":
        ids = await db.all_user_ids()
        st = await m.answer(f"📢 <b>កំពុងផ្សាយដំណឹង...</b> 0/{len(ids)}")
        ok = fail = 0
        for i, u in enumerate(ids, 1):
            for _ in range(2):
                try:
                    await m.copy_to(u)
                    ok += 1
                    break
                except TelegramRetryAfter as e:
                    await asyncio.sleep(e.retry_after)
                except Exception:
                    fail += 1
                    break
            if i % 25 == 0:
                try:
                    await st.edit_text(f"📢 <b>កំពុងផ្សាយដំណឹង...</b> {i}/{len(ids)}")
                except Exception:
                    pass
            await asyncio.sleep(0.05)
        await st.edit_text(f"📢 <b>ការផ្សាយបានបញ្ចប់!</b>\n\n┌ ✅ ជោគជ័យ៖ <b>{ok}</b>\n└ ❌ បរាជ័យ៖ <b>{fail}</b>")
    elif act in ("ban", "unban"):
        if not text.lstrip("-").isdigit():
            return await m.answer("❌ User ID មិនត្រឹមត្រូវ")
        if act == "ban" and int(text) == config.OWNER_ID:
            return await m.answer("❌ មិនអាច Ban ម្ចាស់ Bot បានទេ")
        ok = await db.set_ban(int(text), act == "ban")
        await m.answer(("🚫 បាន Ban រួចរាល់" if act == "ban" else "✅ បាន Unban រួចរាល់") if ok else "❌ រកមិនឃើញ User")
    elif act == "credit":
        p = text.split()
        if len(p) not in (2, 3) or not all(x.isdigit() for x in p):
            return await m.answer("❌ ទម្រង់ខុស៖ <code>user_id ចំនួន [ថ្ងៃ]</code>")
        ok = await db.add_credits(int(p[0]), int(p[1]), int(p[2]) if len(p) == 3 else 0)
        await m.answer("✅ <b>បានបញ្ចូល Credit ជោគជ័យ!</b>" if ok else "❌ រកមិនឃើញ User នេះឡើយ")
        if ok:
            try:
                await m.bot.send_message(int(p[0]), f"🎁 <b>អ្នកទទួលបានកូតាបន្ថែម {p[1]} ដងដោយជោគជ័យ!</b>")
            except Exception:
                pass
    elif act == "user":
        u = await db.get_user(int(text)) if text.isdigit() else None
        if not u:
            return await m.answer("❌ រកមិនឃើញព័ត៌មាន User នេះឡើយ")
        q = await db.quota(u["id"])
        await m.answer(
            "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
            "┃  👤 <b>ព័ត៌មាន USER</b>\n"
            "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
            f"┌ ឈ្មោះ៖ <b>{esc(u['name'] or '')}</b> (@{esc(u['username'] or 'គ្មាន')})\n"
            f"├ ID: <code>{u['id']}</code>\n"
            f"├ Credits: <b>{q['credits']}</b> ដង\n"
            f"├ សុពលភាព: {fmt_ts(u['expiry']) if u['expiry'] else 'គ្មានកំណត់'}\n"
            f"├ ទាញយកសរុប: <b>{u['total']}</b> ដង\n"
            f"├ ស្ថានភាព: {'🚫 Banned' if u['banned'] else '✅ ធម្មតា'}\n"
            f"└ ថ្ងៃចូលរួម: {fmt_ts(u['joined'])}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━"
        )
    elif act == "admin":
        p = text.split()
        if uid != config.OWNER_ID:
            return
        if p and p[0] == "list":
            ids = await db.list_admins()
            return await m.answer("👮 <b>បញ្ជី Admin ទាំងអស់៖</b>\n" + ("\n".join(f"• <code>{i}</code>" for i in ids) or "គ្មាន"))
        if len(p) == 2 and p[0] in ("add", "del") and p[1].isdigit():
            await (db.add_admin if p[0] == "add" else db.del_admin)(int(p[1]))
            return await m.answer("✅ <b>បានកែប្រែសិទ្ធិ Admin រួចរាល់!</b>")
        await m.answer("❌ ទម្រង់ខុស៖ <code>add/del UserID</code>")
    elif act == "nubtoken":
        try:
            await m.delete()
        except Exception:
            pass
        if uid != config.OWNER_ID or len(text) < 6:
            return await m.answer("❌ Token មិនត្រឹមត្រូវ")
        await db.set_setting("nub_token", text)
        await m.answer("✅ <b>បានរក្សាទុក NUB API Token ដោយជោគជ័យ!</b>")
    elif act == "cookies":
        if uid != config.OWNER_ID or not m.document:
            return await m.answer("❌ សូមផ្ញើជាឯកសារ .txt")
        await m.bot.download(m.document, destination=dl.cookies_path())
        try:
            await m.delete()
        except Exception:
            pass
        await m.answer("✅ <b>បានរក្សាទុកឯកសារ Cookies រួចរាល់!</b>")
    elif act == "group":
        if not text.lstrip("-").isdigit():
            return await m.answer("❌ Group ID មិនត្រឹមត្រូវ")
        await db.set_setting("group_id", text)
        await m.answer(f"✅ <b>Storage Group ID:</b> <code>{text}</code>")
    elif act == "free":
        if not text.isdigit():
            return await m.answer("❌ សូមបញ្ចូលជាលេខ")
        await db.set_setting("free_daily", text)
        await m.answer(f"✅ <b>កំណត់ Free Quota ថ្មី៖</b> {text} ដង/ថ្ងៃ")
    elif act in ("welcome", "buy"):
        await db.set_setting("welcome" if act == "welcome" else "buy_text", m.html_text or text)
        await m.answer("✅ <b>បានរក្សាទុកខ្លឹមសារថ្មីដោយជោគជ័យ!</b>")


# ---------------- Settings & Color Callbacks ----------------
@router.callback_query(F.data.startswith(("set:", "tog:", "col", "setcol:", "setall:", "ub:")))
async def admin_cb(cb: CallbackQuery, state: FSMContext):
    if not await db.is_admin(cb.from_user.id):
        return await cb.answer("⛔ គ្មានសិទ្ធិ", show_alert=True)
    d = cb.data
    if d.startswith("ub:"):
        if cb.from_user.id != config.OWNER_ID:
            return await cb.answer("⛔ សម្រាប់ម្ចាស់ Bot ប៉ុណ្ណោះ", show_alert=True)
        act = d[3:]
        if act == "connect":
            api_id, api_hash = await userbot.creds()
            await cb.answer()
            return await ask(cb.message, state, "ub_phone" if (api_id and api_hash) else "ub_api")
        if act == "api":
            await cb.answer()
            return await ask(cb.message, state, "ub_api")
        if act == "off":
            await userbot.logout()
            await cb.message.edit_text(await ub_status(), reply_markup=kb.ub_kb())
            return await cb.answer("🔌 ផ្តាច់រួច")
        if act == "test":
            g = int(await db.get_setting("group_id", str(config.BIG_GROUP_ID)) or 0)
            if not userbot.ready() or not g:
                return await cb.answer("❌ Userbot ឬ Group ID មិនទាន់កំណត់", show_alert=True)
            ok, t = await userbot.check_group(g)
            return await cb.answer(("✅ " if ok else "❌ ") + str(t)[:150], show_alert=True)
    if d.startswith("set:"):
        act = d[4:]
        await state.set_state(Ask.input)
        await state.update_data(act=act)
        await cb.message.answer(PROMPTS[act] + "\n\n/cancel — បោះបង់")
        return await cb.answer()
    if d.startswith("tog:"):
        key = "maint" if d == "tog:maint" else "del_group"
        cur = await db.get_setting(key, "0")
        await db.set_setting(key, "0" if cur == "1" else "1")
        t, k = await settings_view()
        await cb.message.edit_text(t, reply_markup=k)
        return await cb.answer("✅")
    if d.startswith("col:"):
        bid = d[4:]
        cur = kb.COLORS.get(bid, "none")
        await cb.message.edit_text(f"🎨 {kb.BUTTONS[bid][0]}\nពណ៌បច្ចុប្បន្ន: {kb.EMOJI[cur]} {kb.NAMES[cur]}",
                                   reply_markup=kb.pick_color_kb(bid))
        return await cb.answer()
    if d == "colall":
        await cb.message.edit_text("🌈 <b>ជ្រើសពណ៌ សម្រាប់ប៊ូតុងទាំងអស់</b>", reply_markup=kb.pick_all_kb())
        return await cb.answer()
    if d.startswith("setall:"):
        c = d.split(":")[1]
        for bid in kb.BUTTONS:
            await kb.set_color(bid, c)
        await cb.message.edit_text("🎨 <b>កំណត់ពណ៌ប៊ូតុង</b>", reply_markup=kb.colors_kb())
        await cb.message.answer(f"✅ ប៊ូតុងទាំងអស់ → {kb.EMOJI[c]} {kb.NAMES[c]}", reply_markup=kb.admin_kb())
        return await cb.answer()
    if d == "colback":
        await cb.message.edit_text("🎨 <b>កំណត់ពណ៌ប៊ូតុង</b>", reply_markup=kb.colors_kb())
        return await cb.answer()
    if d == "colreset":
        await kb.reset_colors()
        await cb.message.edit_text("🎨 <b>កំណត់ពណ៌ប៊ូតុង</b>", reply_markup=kb.colors_kb())
        await cb.message.answer("✅ កំណត់ពណ៌ដើមវិញ", reply_markup=kb.admin_kb())
        return await cb.answer()
    if d.startswith("setcol:"):
        _, bid, c = d.split(":")
        await kb.set_color(bid, c)
        await cb.message.edit_text("🎨 <b>កំណត់ពណ៌ប៊ូតុង</b>", reply_markup=kb.colors_kb())
        await cb.message.answer(f"✅ {kb.BUTTONS[bid][0]} → {kb.EMOJI[c]} {kb.NAMES[c]}", reply_markup=kb.admin_kb())
        return await cb.answer()


# ---------------- Download Flow ----------------
@router.message(F.chat.type == "private", F.text.regexp(r"https?://\S+"))
async def got_url(m: Message):
    url = re.search(r"https?://\S+", m.text).group(0)
    if len(URLS) > 500:
        URLS.clear()
    tok = secrets.token_hex(4)
    URLS[tok] = (m.from_user.id, url)
    await m.reply(
        "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
        "┃  🎯 <b>ជ្រើសរើសទម្រង់មេឌៀ</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "សូមជ្រើសរើសប្រភេទដែលអ្នកចង់ទាញយក៖",
        reply_markup=kb.kind_kb(tok)
    )


@router.callback_query(F.data.startswith("dl:"))
async def dl_cb(cb: CallbackQuery):
    _, kind, tok = cb.data.split(":")
    item = URLS.get(tok)
    if not item or item[0] != cb.from_user.id:
        return await cb.answer("⌛ តំណភ្ជាប់ផុតកំណត់ សូមផ្ញើម្តងទៀត", show_alert=True)
    if kind == "cancel":
        URLS.pop(tok, None)
        try:
            await cb.message.delete()
        except Exception:
            pass
        return await cb.answer()
    URLS[tok] = (item[0], item[1], kind)
    chans = await db.list_channels(cb.from_user.id)
    await cb.answer()
    try:
        await cb.message.edit_text(
            "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
            "┃  📍 <b>ជ្រើសរើសទីតាំងទទួល</b>\n"
            "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
            "តើអ្នកចង់ទទួលឯកសារនៅទីណា?",
            reply_markup=kb.dest_kb(tok, chans)
        )
    except Exception:
        pass


def start_job(bot, chat_id, uid, url, kind, dest=None, dest_title=None):
    t = asyncio.create_task(process(bot, chat_id, uid, url, kind, dest, dest_title))
    TASKS.add(t)
    t.add_done_callback(TASKS.discard)


def parse_chat_ref(text):
    parts = (text or "").strip().split()
    if not parts:
        return None
    t = parts[0]
    if re.fullmatch(r"-\d{5,}", t):
        return int(t)
    m = re.search(r"t\.me/c/(\d+)", t)
    if m:
        return int("-100" + m.group(1))
    m = re.search(r"(?:https?://)?(?:t|telegram)\.me/([A-Za-z][A-Za-z0-9_]{3,})", t)
    if m and m.group(1).lower() != "joinchat":
        return "@" + m.group(1)
    if re.fullmatch(r"@?[A-Za-z][A-Za-z0-9_]{3,31}", t):
        return "@" + t.lstrip("@")
    return None


async def check_target(bot: Bot, ref, uid):
    try:
        chat = await bot.get_chat(ref)
    except Exception:
        return None, "❌ រក Channel/Group មិនឃើញ។ សូមប្រាកដថាអ្នកបាន Add Bot ចូល និងតម្លើងជា Admin។"
    if chat.type not in ("channel", "group", "supergroup"):
        return None, "❌ ត្រូវតែជា Channel ឬ Group ប៉ុណ្ណោះ"
    me = await bot.me()
    try:
        bm = await bot.get_chat_member(chat.id, me.id)
    except Exception:
        return None, "❌ Bot មិនទាន់ជា Admin ក្នុង Channel/Group នោះទេ"
    if bm.status not in ("administrator", "creator"):
        return None, "❌ Bot មិនទាន់ជា Admin ក្នុង Channel/Group នោះទេ"
    if chat.type == "channel" and getattr(bm, "can_post_messages", True) is False:
        return None, "❌ Bot គ្មានសិទ្ធិ Post Messages ក្នុង Channel នោះឡើយ"
    try:
        um = await bot.get_chat_member(chat.id, uid)
    except Exception:
        return None, "❌ មិនអាចផ្ទៀងផ្ទាត់សិទ្ធិ Admin របស់អ្នកបានទេ"
    if um.status not in ("administrator", "creator"):
        return None, "❌ អ្នកត្រូវតែជា Admin ក្នុង Channel/Group នោះដែរ"
    return chat, None


async def ask_newchan(m: Message, state: FSMContext, tok):
    await state.set_state(Ask.input)
    await state.update_data(act="newchan", tok=tok)
    await m.answer(PROMPTS["newchan"] + "\n\n/cancel — បោះបង់")


async def newchan_step(m: Message, state: FSMContext, uid, text, tok):
    ref = parse_chat_ref(text)
    if ref is None:
        await m.answer("❌ ទម្រង់មិនត្រឹមត្រូវ។ ផ្ញើ @username, ID (-100...) ឬ Link t.me/username")
        return await ask_newchan(m, state, tok)
    chat, err = await check_target(m.bot, ref, uid)
    if err:
        await m.answer(err)
        return await ask_newchan(m, state, tok)
    await db.add_channel(uid, chat.id, chat.title or str(chat.id), chat.username or "")
    item = URLS.pop(tok, None) if tok else None
    if not item or item[0] != uid or len(item) < 3:
        return await m.answer(f"✅ <b>បានរក្សាទុក៖</b> <b>{esc(chat.title or '')}</b>\nសូមផ្ញើតំណវីដេអូម្តងទៀត។")
    await m.answer(f"✅ <b>បានរក្សាទុក៖</b> <b>{esc(chat.title or '')}</b>")
    start_job(m.bot, m.chat.id, uid, item[1], item[2], chat.id, chat.title or str(chat.id))


@router.callback_query(F.data.startswith("dst:"))
async def dst_cb(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")
    act, tok = parts[1], parts[2]
    uid = cb.from_user.id
    item = URLS.get(tok)
    if not item or item[0] != uid or len(item) < 3:
        return await cb.answer("⌛ អស់សុពលភាព សូមផ្ញើតំណម្តងទៀត", show_alert=True)
    if act == "me":
        URLS.pop(tok, None)
        try:
            await cb.message.delete()
        except Exception:
            pass
        await cb.answer()
        return start_job(cb.bot, cb.message.chat.id, uid, item[1], item[2])
    if act == "new":
        await cb.answer()
        return await ask_newchan(cb.message, state, tok)
    chat_id = int(parts[3])
    if not await db.has_channel(uid, chat_id):
        return await cb.answer("❌ រកមិនឃើញក្នុងបញ្ជី", show_alert=True)
    if act == "x":
        await db.del_channel(uid, chat_id)
        await cb.answer("🗑 បានលុប")
        try:
            await cb.message.edit_reply_markup(reply_markup=kb.dest_kb(tok, await db.list_channels(uid)))
        except Exception:
            pass
        return
    if act == "c":
        chat, err = await check_target(cb.bot, chat_id, uid)
        if err:
            return await cb.answer(err[:190], show_alert=True)
        URLS.pop(tok, None)
        try:
            await cb.message.delete()
        except Exception:
            pass
        await cb.answer()
        start_job(cb.bot, cb.message.chat.id, uid, item[1], item[2], chat.id, chat.title or str(chat.id))


# ---------------- Preview & Edit Caption Flow ----------------
def add_preview(ptok, uid, msg_id, dest, dest_title, title, cap, kind):
    while len(PREVIEWS) > 300:
        PREVIEWS.pop(next(iter(PREVIEWS)))
    PREVIEWS[ptok] = {
        "uid": uid, "msg": msg_id, "dest": dest, "dest_title": dest_title,
        "title": title, "cap": cap, "kind": kind, "busy": False
    }


async def caption_step(m: Message, state: FSMContext, uid, ptok):
    pv = PREVIEWS.get(ptok)
    if not pv or pv["uid"] != uid:
        return await m.answer("⌛ អស់សុពលភាព សូមទាញយកម្តងទៀត")
    new = (m.html_text or "").strip().replace("{title}", esc(pv["title"]))
    plain = html.unescape(re.sub(r"<[^>]+>", "", new))
    if not plain or len(plain) > 1024:
        await m.answer("❌ Caption ត្រូវមានប្រវែងពី 1–1024 តួអក្សរ")
        await state.set_state(Ask.input)
        await state.update_data(act="caption", ptok=ptok)
        return
    try:
        await m.bot.edit_message_caption(
            chat_id=uid, message_id=pv["msg"], caption=new,
            parse_mode=ParseMode.HTML,
            reply_markup=kb.preview_kb(ptok, pv["dest_title"])
        )
    except TelegramBadRequest as e:
        if "not modified" not in str(e).lower():
            await m.answer(f"❌ កែមិនបាន: {esc(str(e))[:200]}\nសូមផ្ញើម្តងទៀត")
            await state.set_state(Ask.input)
            await state.update_data(act="caption", ptok=ptok)
            return
    pv["cap"] = new
    await m.answer("✅ <b>កែប្រែ Caption រួចរាល់!</b> សូមពិនិត្យមើលរូប/វីដេអូខាងលើ រួចចុច 📤 ផុសចូល")


@router.callback_query(F.data.startswith("pv:"))
async def pv_cb(cb: CallbackQuery, state: FSMContext):
    _, act, ptok = cb.data.split(":")
    uid = cb.from_user.id
    pv = PREVIEWS.get(ptok)
    if not pv or pv["uid"] != uid:
        return await cb.answer("⌛ អស់សុពលភាព", show_alert=True)
    if act == "cancel":
        PREVIEWS.pop(ptok, None)
        try:
            await cb.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return await cb.answer("❎ បានបោះបង់ការផុស")
    if act == "edit":
        await cb.answer()
        await state.set_state(Ask.input)
        await state.update_data(act="caption", ptok=ptok)
        return await cb.message.answer(
            "╭─ ✏️ <b>កែប្រែ CAPTION</b>\n"
            "├ ផ្ញើអត្ថបទថ្មីសម្រាប់ដាក់ជាមួយ File\n"
            "└ 💡 ប្រើពាក្យ <code>{title}</code> ដើម្បីជំនួសដោយចំណងជើងដើម\n\n"
            f"<b>Caption បច្ចុប្បន្ន៖</b>\n{pv['cap']}\n\n"
            "/cancel — បោះបង់"
        )
    if act == "post":
        if pv["busy"]:
            return await cb.answer("⏳ កំពុងដំណើរការ...")
        pv["busy"] = True
        try:
            chat, err = await check_target(cb.bot, pv["dest"], uid)
            if err:
                return await cb.answer(err[:190], show_alert=True)
            r = await cb.bot.copy_message(
                chat_id=chat.id, from_chat_id=uid, message_id=pv["msg"],
                caption=pv["cap"], parse_mode=ParseMode.HTML
            )
        except Exception as e:
            log.exception("post failed")
            return await cb.answer(f"❌ ផុសមិនបាន: {str(e)[:150]}", show_alert=True)
        finally:
            pv["busy"] = False
        PREVIEWS.pop(ptok, None)
        try:
            await cb.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        link = ""
        if chat.username:
            link = f"\n🔗 https://t.me/{chat.username}/{r.message_id}"
        elif str(chat.id).startswith("-100"):
            link = f"\n🔗 https://t.me/c/{str(chat.id)[4:]}/{r.message_id}"
        await cb.answer("✅ ផុសបានជោគជ័យ!")
        await cb.message.answer(f"✅ <b>បានផុសចូល {esc(chat.title or '')} រួចរាល់!</b>{link}")


# ---------------- Core Processing (Rate-Limited Progress Bar) ----------------
def create_progress_bar(pct):
    total_blocks = 10
    filled = int(round(pct / 100 * total_blocks))
    return "█" * filled + "▒" * (total_blocks - filled)


async def process(bot: Bot, chat_id, uid, url, kind, dest=None, dest_title=None):
    if ACTIVE.get(uid, 0) >= 2:
        return await bot.send_message(chat_id, "⏳ <b>សូមរង់ចាំដំណើរការចាស់បញ្ចប់សិន មុននឹងចាប់ផ្តើមទាញយកថ្មី!</b>")
    src = await db.consume(uid)
    if not src:
        return await bot.send_message(chat_id, await no_credit_text())
    
    ACTIVE[uid] = ACTIVE.get(uid, 0) + 1
    hid = await db.add_history(uid, url, kind)
    
    st = await bot.send_message(
        chat_id,
        "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
        "┃  ⚡ <b>ដំណើរការទាញយក</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "┌ 🔄 <b>ស្ថានភាព៖</b> កំពុងរៀបចំទាញយក...\n"
        "└ ⏱ <i>សូមរង់ចាំបន្តិច</i>"
    )
    jobdir = os.path.join(config.DOWNLOAD_DIR, secrets.token_hex(6))

    # Rate limiting progress bar (កែសម្រួលដើម្បីកុំឱ្យជាប់ Flood Limit)
    last_edit = 0
    last_text = ""

    async def progress(done, total):
        nonlocal last_edit, last_text
        now = time.time()
        # កំណត់ឱ្យ edit យ៉ាងហោចណាស់ 2.5 វិនាទីម្តង
        if now - last_edit < 2.5 and done < total:
            return
        last_edit = now

        if total:
            pct = int(done * 100 // total)
            bar = create_progress_bar(pct)
            txt = (
                "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
                "┃  ⬇️ <b>កំពុងទាញយកមេឌៀ...</b>\n"
                "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
                f"┌ 📊 <b>ភាគរយ៖</b> <code>{bar}</code> {pct}%\n"
                f"└ 💾 <b>ទំហំ៖</b> <code>{done >> 20}MB</code> / <code>{total >> 20}MB</code>"
            )
        else:
            txt = (
                "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
                "┃  ⬇️ <b>កំពុងទាញយកមេឌៀ...</b>\n"
                "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
                f"└ 💾 <b>ទំហំទាញយកបាន៖</b> <code>{done >> 20}MB</code>"
            )

        if txt != last_text:
            last_text = txt
            try:
                await st.edit_text(txt)
            except (TelegramRetryAfter, TelegramBadRequest, Exception):
                pass

    try:
        async with SEM:
            res = await dl.fetch(url, kind, jobdir, progress)
        
        title, path = res["title"], res["path"]
        size = os.path.getsize(path)
        
        if size <= config.BOT_UPLOAD_LIMIT:
            try:
                await st.edit_text(
                    "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
                    "┃  📤 <b>កំពុងបញ្ជូនឯកសារ...</b>\n"
                    "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
                    f"┌ 📦 <b>ឈ្មោះ៖</b> {esc(title)[:45]}\n"
                    f"└ 💾 <b>ទំហំ៖</b> <code>{size >> 20}MB</code>"
                )
            except Exception:
                pass
            
            cap = f"{'🎵' if kind == 'audio' else '🎬'} <b>{esc(title)}</b>"[:1000]
            f = FSInputFile(path)
            th = FSInputFile(res["thumb"]) if res.get("thumb") else None
            ptok, markup = None, None
            
            if dest:
                ptok = secrets.token_hex(4)
                markup = kb.preview_kb(ptok, dest_title)
            
            try:
                if kind == "audio":
                    sent = await bot.send_audio(
                        chat_id, f, caption=cap, title=title[:60],
                        duration=res.get("duration", 0), thumbnail=th, reply_markup=markup
                    )
                else:
                    sent = await bot.send_video(
                        chat_id, f, caption=cap, duration=res.get("duration", 0),
                        width=res.get("width"), height=res.get("height"),
                        supports_streaming=True, thumbnail=th, reply_markup=markup
                    )
            except Exception:
                sent = await bot.send_document(chat_id, FSInputFile(path), caption=cap, reply_markup=markup)
            
            await db.finish_history(hid, "ok", title)
            if dest:
                add_preview(ptok, uid, sent.message_id, dest, dest_title, title, cap, kind)
                await st.edit_text("👆 <b>ពិនិត្យមើលឯកសារខាងលើ៖</b> អ្នកអាចកែប្រែ Caption មុននឹងចុច Post ចូល Channel/Group")
            else:
                await st.delete()
        else:
            group = int(await db.get_setting("group_id", str(config.BIG_GROUP_ID)) or 0)
            if not group or not userbot.ready():
                raise RuntimeError("ឯកសារធំជាង 50MB ហើយមិនទាន់ភ្ជាប់ Userbot/Storage Group នៅឡើយ")
            
            req = secrets.token_hex(6)
            await db.add_pending(req, uid, hid, src)
            await db.finish_history(hid, "pending", title)
            
            await st.edit_text(
                "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
                "┃  📦 <b>ឯកសារទំហំធំ (>50MB)</b>\n"
                "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
                f"┌ 💾 <b>ទំហំ៖</b> <code>{size >> 20}MB</code>\n"
                "└ ⚡ <i>Userbot កំពុង Upload ចូលប្រព័ន្ធផ្ទុកឯកសារធំ...</i>"
            )
            
            if dest:
                JOBMETA[req] = {"dest": dest, "dest_title": dest_title, "kind": kind, "title": title}
            
            try:
                await userbot.upload(group, path, f"REQ:{req}\n{cap_title(title, kind)}", kind, res)
            except Exception:
                await db.pop_pending(req)
                JOBMETA.pop(req, None)
                raise
            
            t = asyncio.create_task(watchdog(bot, req, chat_id))
            TASKS.add(t)
            t.add_done_callback(TASKS.discard)
            
    except Exception as e:
        log.exception("download failed")
        await db.refund(uid, src)
        await db.finish_history(hid, "fail")
        try:
            await st.edit_text(
                "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
                "┃  ❌ <b>ការទាញយកបរាជ័យ</b>\n"
                "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
                f"┌ ⚠️ <b>មូលហេតុ៖</b> {esc(str(e))[:300]}\n"
                "└ 💎 <i>ចំនួនដងទាញយក (Credit) ត្រូវបានសងត្រឡប់ទៅវិញដោយស្វ័យប្រវត្តិ។</i>"
            )
        except Exception:
            pass
    finally:
        ACTIVE[uid] = max(0, ACTIVE.get(uid, 1) - 1)
        shutil.rmtree(jobdir, ignore_errors=True)


def cap_title(title, kind):
    return f"{'🎵' if kind == 'audio' else '🎬'} {esc(title)}"[:900]


async def watchdog(bot: Bot, req, chat_id):
    await asyncio.sleep(180)
    p = await db.pop_pending(req)
    JOBMETA.pop(req, None)
    if not p:
        return
    await db.refund(p["user_id"], p["src"])
    await db.finish_history(p["hist_id"], "fail")
    try:
        await bot.send_message(chat_id, "❌ <b>មិនអាចផ្ញើឯកសារធំបានទេ</b> (Credit ត្រូវបានសងវិញរួចរាល់)")
        await bot.send_message(config.OWNER_ID, "⚠️ <b>Warning:</b> Bot មិនបានទទួលឯកសារពី Group។ សូមពិនិត្យមើលសិទ្ធិ Admin របស់ Bot ក្នុង Storage Group។")
    except Exception:
        pass


# ---------------- Big-File Pickup from Group ----------------
@router.message(F.chat.type.in_({"group", "supergroup"}), F.caption.startswith("REQ:"))
async def group_pick(m: Message):
    gid = int(await db.get_setting("group_id", str(config.BIG_GROUP_ID)) or 0)
    if m.chat.id != gid:
        return
    mt = re.match(r"REQ:([0-9a-f]+)", m.caption)
    p = await db.pop_pending(mt.group(1)) if mt else None
    if not p:
        return
    cap = m.caption.split("\n", 1)[1] if "\n" in m.caption else ""
    meta = JOBMETA.pop(mt.group(1), None)
    try:
        ptok, markup = None, None
        if meta:
            ptok = secrets.token_hex(4)
            markup = kb.preview_kb(ptok, meta["dest_title"])
        r = await m.bot.copy_message(
            p["user_id"], m.chat.id, m.message_id, caption=cap,
            parse_mode=ParseMode.HTML, reply_markup=markup
        )
        if meta:
            add_preview(ptok, p["user_id"], r.message_id, meta["dest"], meta["dest_title"],
                        meta["title"], cap, meta["kind"])
            await m.bot.send_message(p["user_id"], "👆 <b>ពិនិត្យមើលឯកសារខាងលើ៖</b> អ្នកអាចកែប្រែ Caption មុននឹងចុច Post ចូល Channel/Group")
        await db.finish_history(p["hist_id"], "ok")
        if await db.get_setting("del_group", "0") == "1":
            await m.delete()
    except Exception as e:
        log.exception("copy failed")
        await db.refund(p["user_id"], p["src"])
        await db.finish_history(p["hist_id"], "fail")
        await m.bot.send_message(p["user_id"], f"❌ ផ្ញើមិនបាន: {esc(str(e))[:200]}")


# ---------------- Main Function ----------------
async def main():
    if not config.BOT_TOKEN:
        raise SystemExit("សូមដាក់ BOT_TOKEN ក្នុង .env")
    os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)
    await db.init()
    await kb.load_colors()
    
    # ចាប់ផ្តើម Web Server សម្រាប់ Render Health Check លើ Port 8080
    await start_web_server()
    
    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    
    await userbot.start()
    log.info("🤖 Bot and Services started successfully.")
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        await userbot.stop()


if __name__ == "__main__":
    asyncio.run(main())
