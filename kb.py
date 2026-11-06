from aiogram.types import (InlineKeyboardButton, InlineKeyboardMarkup,
                           KeyboardButton, ReplyKeyboardMarkup)

import db

# red→danger · blue→primary · green→success  (Telegram button style)
STYLE = {"red": "danger", "blue": "primary", "green": "success"}
EMOJI = {"red": "🔴", "blue": "🔵", "green": "🟢", "none": "⚪"}
NAMES = {"red": "ក្រហម", "blue": "ខៀវ", "green": "បៃតង", "none": "ធម្មតា"}

# id: (label, default_color)
BUTTONS = {
    "download": ("📥 ទាញយកវីដេអូ", "green"),
    "redeem": ("🔑 ដាក់ Key", "blue"),
    "account": ("👤 គណនីខ្ញុំ", "none"),
    "buy": ("🛒 ទិញ Key", "green"),
    "history": ("📜 ប្រវត្តិ", "none"),
    "help": ("ℹ️ ជំនួយ", "none"),
    "admin": ("🛠 Admin Panel", "red"),
    "a_create": ("➕ បង្កើត Key", "green"),
    "a_keys": ("📋 បញ្ជី Key", "blue"),
    "a_del": ("🗑 លុប Key", "red"),
    "a_users": ("👥 ព័ត៌មាន User", "none"),
    "a_stats": ("📊 ស្ថិតិ", "blue"),
    "a_cast": ("📢 Broadcast", "blue"),
    "a_ban": ("🚫 Ban", "red"),
    "a_unban": ("✅ Unban", "green"),
    "a_credit": ("💎 ថែមចំនួនទាញយក", "green"),
    "a_colors": ("🎨 ពណ៌ប៊ូតុង", "blue"),
    "a_settings": ("⚙️ ការកំណត់", "none"),
    "a_admins": ("👮 គ្រប់គ្រង Admin", "red"),
    "a_userbot": ("🤖 ភ្ជាប់ Userbot", "blue"),
    "back": ("⬅️ ត្រឡប់", "none"),
    "video": ("🎬 វីដេអូ", "green"),
    "audio": ("🎵 អូឌីយ៉ូ MP3", "blue"),
    "cancel": ("❌ បោះបង់", "red"),
    "dst_me": ("👤 ផ្ទាល់ខ្លួន (Private)", "green"),
    "dst_new": ("➕ បន្ថែម Channel/Group ថ្មី", "blue"),
    "p_post": ("📤 ផុសចូល Channel/Group", "green"),
    "p_edit": ("✏️ កែអត្ថបទ", "blue"),
    "p_cancel": ("❌ បោះបង់ការផុស", "red"),
    "a_ulist": ("📃 បញ្ជី User ទាំងអស់", "blue"),
}

COLORS = {}


async def load_colors():
    for bid, (_, d) in BUTTONS.items():
        COLORS[bid] = await db.get_setting(f"color:{bid}", d)


async def set_color(bid, c):
    await db.set_setting(f"color:{bid}", c)
    COLORS[bid] = c


async def reset_colors():
    for bid, (_, d) in BUTTONS.items():
        await set_color(bid, d)


def _extra(color):
    return {"style": STYLE[color]} if color in STYLE else {}


def rb(bid):
    return KeyboardButton(text=BUTTONS[bid][0], **_extra(COLORS.get(bid, "none")))


def ib(text, data, color="none"):
    return InlineKeyboardButton(text=text, callback_data=data, **_extra(color))


def ibid(bid, data):
    return ib(BUTTONS[bid][0], data, COLORS.get(bid, "none"))


def main_kb(admin=False):
    rows = [[rb("download")], [rb("redeem"), rb("account")], [rb("buy"), rb("history")], [rb("help")]]
    if admin:
        rows.append([rb("admin")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, input_field_placeholder="ផ្ញើតំណវីដេអូ...")


def admin_kb():
    rows = [
        [rb("a_create"), rb("a_keys")],
        [rb("a_del"), rb("a_credit")],
        [rb("a_users"), rb("a_stats")],
        [rb("a_ban"), rb("a_unban")],
        [rb("a_cast"), rb("a_colors")],
        [rb("a_settings"), rb("a_admins")],
        [rb("a_userbot")],
        [rb("a_ulist")],
        [rb("back")],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def kind_kb(tok):
    return InlineKeyboardMarkup(inline_keyboard=[
        [ibid("video", f"dl:video:{tok}"), ibid("audio", f"dl:audio:{tok}")],
        [ibid("cancel", f"dl:cancel:{tok}")],
    ])


def colors_kb():
    rows, row = [], []
    for bid, (label, _) in BUTTONS.items():
        row.append(ib(f"{EMOJI[COLORS.get(bid, 'none')]} {label}", f"col:{bid}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([ib("↩️ កំណត់ពណ៌ដើមវិញ", "colreset", "red")])
    rows.insert(0, [ib("🌈 ប្តូរពណ៌ទាំងអស់", "colall", "green")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pick_color_kb(bid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [ib("🔴 ក្រហម", f"setcol:{bid}:red", "red"), ib("🔵 ខៀវ", f"setcol:{bid}:blue", "blue")],
        [ib("🟢 បៃតង", f"setcol:{bid}:green", "green"), ib("⚪ ធម្មតា", f"setcol:{bid}:none")],
        [ib("⬅️ ត្រឡប់", "colback")],
    ])


def settings_kb(maint, delg):
    return InlineKeyboardMarkup(inline_keyboard=[
        [ib("🔑 NUB API Token", "set:nubtoken", "blue")],
        [ib("👥 Group ID (ឯកសារធំ)", "set:group", "blue")],
        [ib("🎁 Free/ថ្ងៃ", "set:free"), ib("💬 សារស្វាគមន៍", "set:welcome")],
        [ib("🛒 អត្ថបទទិញ Key", "set:buy")],
        [ib(f"🔧 Maintenance: {'ON' if maint else 'OFF'}", "tog:maint", "red" if maint else "green")],
        [ib(f"🧹 លុបពី Group បន្ទាប់ពីផ្ញើ: {'ON' if delg else 'OFF'}", "tog:delg", "green" if delg else "none")],
    ])


def ub_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [ib("🔗 ភ្ជាប់គណនី Userbot", "ub:connect", "green")],
        [ib("🔐 ប្តូរ API_ID / API_HASH", "ub:api", "blue")],
        [ib("🧪 ពិនិត្យ Group", "ub:test", "blue"), ib("🔌 ផ្តាច់", "ub:off", "red")],
    ])


def pick_all_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [ib("🔴 ក្រហមទាំងអស់", "setall:red", "red"), ib("🔵 ខៀវទាំងអស់", "setall:blue", "blue")],
        [ib("🟢 បៃតងទាំងអស់", "setall:green", "green"), ib("⚪ ធម្មតាទាំងអស់", "setall:none")],
        [ib("⬅️ ត្រឡប់", "colback")],
    ])


def dest_kb(tok, channels):
    """ជ្រើសទីតាំងទទួល: ផ្ទាល់ខ្លួន / Channel-Group ដែលបានរក្សាទុក / បន្ថែមថ្មី"""
    rows = [[ibid("dst_me", f"dst:me:{tok}")]]
    for c in channels:
        rows.append([ib(f"📢 {c['title']}"[:40], f"dst:c:{tok}:{c['chat_id']}"),
                     ib("🗑", f"dst:x:{tok}:{c['chat_id']}", "red")])
    rows.append([ibid("dst_new", f"dst:new:{tok}")])
    rows.append([ibid("cancel", f"dl:cancel:{tok}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def preview_kb(ptok, dest_title):
    return InlineKeyboardMarkup(inline_keyboard=[
        [ib(f"📤 ផុសចូល {dest_title}"[:60], f"pv:post:{ptok}", COLORS.get("p_post", "green"))],
        [ibid("p_edit", f"pv:edit:{ptok}"), ibid("p_cancel", f"pv:cancel:{ptok}")],
    ])


def users_kb(page, pages):
    nav = []
    if page > 1:
        nav.append(ib("⬅️ មុន", f"ul:{page - 1}"))
    nav.append(ib(f"📄 {page}/{pages}", "ul:noop"))
    if page < pages:
        nav.append(ib("បន្ទាប់ ➡️", f"ul:{page + 1}"))
    return InlineKeyboardMarkup(inline_keyboard=[nav, [ib("📥 Export CSV (ទាំងអស់)", "ul:csv", "blue")]])
