"""
╔══════════════════════════════════════════════════════╗
║   TELEGRAM AUTOMATION BOT  —  Aiogram v3  (Premium UI) ║
║   • Reply Keyboard Menu + SubMenus (Admin)             ║
║   • Force-join gate with real invite links             ║
║   • Broadcast, Content, Channels, Admin management      ║
║   • Auto-Accept Join Requests (toggle)                 ║
║   • Bot API 9.4 styled buttons + tg-emoji cards         ║
╚══════════════════════════════════════════════════════╝

Setup:
    pip install "aiogram>=3.7" aiosqlite
    (Needs a recent aiogram build that passes through Bot API 9.4
     fields — `style` / `icon_custom_emoji_id` — on button objects.)
    Set BOT_TOKEN and OWNER_ID below, then:
    python bot-v2.py

Admin Menu Tree:
    /start (Admin)
    ├── 📊 Statistics
    ├── 📢 Broadcast
    ├── 🗂 Content  ──► SubMenu: 🎬 Set Video | 📁 Set APK | 🎧 Set Voice
    ├── 📺 Channels ──► SubMenu: ➕ Add | 📋 List | 🗑 Remove
    ├── 👑 Admins   ──► SubMenu: ➕ Add | 📋 List | 🗑 Remove
    ├── 🤖 Auto-Accept ──► Toggle ON/OFF
    └── 👀 Preview
"""

import asyncio
import json
import logging
from typing import Optional

import aiosqlite
from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    ChatJoinRequest,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    MessageEntity,
)
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

try:
    from aiogram.client.default import DefaultBotProperties
except ImportError:
    class DefaultBotProperties:  # type: ignore
        def __init__(self, parse_mode=None):
            self.parse_mode = parse_mode

# ──────────────────────────────────────────────────────
#  ⚙️  CONFIG  ← Edit before running
# ──────────────────────────────────────────────────────
BOT_TOKEN: str = "8904332997:AAGwm_qnSPLpGLvZz18BHKHiks64-qAf-QU"  # Replace with your token
OWNER_ID:  int = 6676107937  # Replace with your ID
DB_PATH:   str = "bot.db"

# ──────────────────────────────────────────────────────
#  🎨  PREMIUM CUSTOM ANIMATED EMOJI IDS
# ──────────────────────────────────────────────────────
EMOJI_IDS = {
    "stats":     "6068619258298900164",   # 📊
    "broadcast": "6159205195222881182",   # 📢
    "content":   "5298853345241358103",   # 🗂
    "channels":  "5373330964372004748",   # 📺
    "admins":    "6266995104687330978",   # 👑
    "preview":   "5424885441100782420",   # 👀
    "back":      "5253997076169115797",   # 🔙
    "video":     "5375464961822695044",   # 🎬
    "apk":       "5409150592188690356",   # 📁
    "voice":     "5278779535683252020",   # 🎧
    "add":       "5397916757333654639",   # ➕
    "list":      "5197269100878907942",   # 📋
    "remove":    "5445267414562389170",   # 🗑
    "link":      "6185784123592807748",   # 🔗
    "forward":   "5253742260054409879",   # 📨
    "chat_id":   "5014902839575577394",   # 🆔
    "owner":     "5260647807257173709",   # 🔱
    "success":   "6267008582294705964",   # ✅
    "cancel":    "6188201202337977430",   # ❌
    "warning":   "6267039884016358504",   # ⚠️
    "blocked":   "5260293700088511294",   # ⛔
    "info":      "5289943353981410616",   # ℹ️
    "welcome":   "5461151367559141950",   # 🎉
    "wave":      "5413694143601842851",   # 👋
    "user":      "5258011929993026890",   # 👤
    "pointer":   "6147439566107186310",   # 👇
    "soon":      "5242715846349957653",   # 🚧
    "robot":     "5355051922862653659",   # 🤖
    "sent":      "5445355530111437729",   # 📤
    "delivered": "6190380687787300058",   # ✔️
    "auto_accept": "6188201202337977430", # 🤖
}

# Button style variants (Bot API 9.4): primary / success / danger
STYLE_PRIMARY = "primary"
STYLE_SUCCESS = "success"
STYLE_DANGER  = "danger"

# Max number of link buttons that can be attached to a single content item
MAX_CONTENT_BUTTONS = 3

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

# ──────────────────────────────────────────────────────
#  📋  LOGGING
# ──────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("Bot")


# ──────────────────────────────────────────────────────
#  🔄  FSM STATES
# ──────────────────────────────────────────────────────
class S(StatesGroup):
    broadcast    = State()
    set_video    = State()
    set_apk      = State()
    set_voice    = State()
    add_channel  = State()
    add_admin    = State()
    rm_admin     = State()
    button_text  = State()
    button_url   = State()
    button_style = State()


# ══════════════════════════════════════════════════════
#  🗄️  DATABASE
# ══════════════════════════════════════════════════════
async def db_init() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS channels (
                channel_id  TEXT PRIMARY KEY,
                title       TEXT,
                invite_link TEXT
            );
            CREATE TABLE IF NOT EXISTS content (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS config (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        await db.commit()
    log.info("DB initialised.")


# ── Users ────────────────────────────────────────────
async def add_user(uid: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO users VALUES (?)", (uid,))
        await db.commit()

async def get_users() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur  = await db.execute("SELECT user_id FROM users")
        rows = await cur.fetchall()
    return [r[0] for r in rows]

async def count_users() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM users")
        row = await cur.fetchone()
    return row[0] if row else 0


# ── Config ────────────────────────────────────────────
async def set_config(key: str, value: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            (key, value)
        )
        await db.commit()

async def get_config(key: str, default: str = "off") -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT value FROM config WHERE key=?", (key,))
        row = await cur.fetchone()
    return row[0] if row else default

async def is_auto_accept_enabled() -> bool:
    return await get_config("auto_accept", "off") == "on"


# ── Channels ─────────────────────────────────────────
async def add_channel(channel_id: str, title: str, invite_link: Optional[str]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO channels (channel_id, title, invite_link) VALUES (?,?,?)",
            (channel_id, title, invite_link),
        )
        await db.commit()

async def remove_channel(channel_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM channels WHERE channel_id=?", (channel_id,))
        await db.commit()

async def get_channels() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur  = await db.execute("SELECT channel_id, title, invite_link FROM channels")
        rows = await cur.fetchall()
    return [{"channel_id": r[0], "title": r[1] or r[0], "invite_link": r[2]} for r in rows]


# ── Content ──────────────────────────────────────────
async def save_content(
    key: str,
    file_id: str,
    caption: Optional[str],
    entities: Optional[list[MessageEntity]] = None,
) -> None:
    """Stores the file + caption. `entities` preserves rich formatting —
    including custom_emoji entities (premium animated emojis) — exactly
    as Telegram sent them, so they survive the round trip untouched."""
    entities_data = [e.model_dump(mode="json") for e in entities] if entities else []
    payload = json.dumps({"file_id": file_id, "caption": caption, "entities": entities_data})
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO content (key, value) VALUES (?,?)", (key, payload)
        )
        await db.commit()

async def get_content(key: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT value FROM content WHERE key=?", (key,))
        row = await cur.fetchone()
    if not row:
        return None
    data = json.loads(row[0])
    raw_entities = data.get("entities") or []
    data["entities"] = [MessageEntity(**e) for e in raw_entities] if raw_entities else None
    # "buttons" is a list of up to MAX_CONTENT_BUTTONS {"text":..., "url":..., "style":...} dicts.
    # Older rows may only have a single "button" dict — migrate it transparently.
    buttons = data.get("buttons")
    if buttons is None:
        legacy = data.get("button")
        buttons = [legacy] if legacy else []
    data["buttons"] = buttons
    data["button"] = buttons[0] if buttons else None  # kept for backward compatibility
    return data

async def add_content_button(key: str, button: dict) -> None:
    """Append one URL button (max MAX_CONTENT_BUTTONS) to an already-saved content item."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT value FROM content WHERE key=?", (key,))
        row = await cur.fetchone()
        if not row:
            return
        data = json.loads(row[0])
        buttons = data.get("buttons")
        if buttons is None:
            legacy = data.get("button")
            buttons = [legacy] if legacy else []
        buttons.append(button)
        data["buttons"] = buttons[:MAX_CONTENT_BUTTONS]
        data.pop("button", None)
        await db.execute("UPDATE content SET value=? WHERE key=?", (json.dumps(data), key))
        await db.commit()


async def clear_content_buttons(key: str) -> None:
    """Remove all buttons from an already-saved content item."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT value FROM content WHERE key=?", (key,))
        row = await cur.fetchone()
        if not row:
            return
        data = json.loads(row[0])
        data["buttons"] = []
        data.pop("button", None)
        await db.execute("UPDATE content SET value=? WHERE key=?", (json.dumps(data), key))
        await db.commit()


# ── Admins ───────────────────────────────────────────
async def get_admins() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur  = await db.execute("SELECT user_id FROM admins")
        rows = await cur.fetchall()
    ids = [r[0] for r in rows]
    if OWNER_ID not in ids:
        ids.insert(0, OWNER_ID)
    return ids

async def add_admin(uid: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO admins VALUES (?)", (uid,))
        await db.commit()

async def remove_admin(uid: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM admins WHERE user_id=?", (uid,))
        await db.commit()

async def is_admin(uid: int) -> bool:
    if uid == OWNER_ID:
        return True
    admins = await get_admins()
    return uid in admins


async def is_owner(uid: int) -> bool:
    return uid == OWNER_ID


# ── Membership ───────────────────────────────────────
async def get_unjoined(bot: Bot, user_id: int) -> list[dict]:
    """Returns channel dicts the user has NOT joined."""
    channels = await get_channels()
    unjoined = []
    for ch in channels:
        try:
            m = await bot.get_chat_member(ch["channel_id"], user_id)
            if m.status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
                unjoined.append(ch)
        except Exception:
            unjoined.append(ch)
    return unjoined


# ══════════════════════════════════════════════════════
#  🎨  TEXT / EMOJI HELPERS
# ══════════════════════════════════════════════════════
def _h(text) -> str:
    """Escape special characters for HTML parse mode."""
    if text is None:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def tg_emoji(key: str, fallback: str = "") -> str:
    """Wrap a fallback emoji in a <tg-emoji> tag for HTML messages/captions."""
    eid = EMOJI_IDS.get(key)
    return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>' if eid else fallback


def _content_button_markup(buttons: Optional[list]) -> Optional[InlineKeyboardMarkup]:
    """Builds the optional stack of URL buttons (up to MAX_CONTENT_BUTTONS) attached
    to a content item, if any. One button per row, in the order they were added."""
    if not buttons:
        return None
    rows = [
        [ibtn(b.get("text") or "Open Link", url=b["url"],
              style=b.get("style"), icon=EMOJI_IDS["link"])]
        for b in buttons if b and b.get("url")
    ]
    if not rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ══════════════════════════════════════════════════════
#  📤  CONTENT DELIVERY  (Video → APK → Voice)
# ══════════════════════════════════════════════════════
async def send_content(bot: Bot, user_id: int, first_name: str) -> None:
    video = await get_content("video")
    doc   = await get_content("document")
    voice = await get_content("voice")
    sent  = False

    try:
        if video:
            await bot.send_video(
                user_id, video["file_id"],
                caption=video["caption"], caption_entities=video["entities"],
                parse_mode=None,  # entities + parse_mode can't be combined
                reply_markup=_content_button_markup(video.get("buttons")),
            )
            sent = True
            await asyncio.sleep(1.5)

        if doc:
            await bot.send_document(
                user_id, doc["file_id"],
                caption=doc["caption"], caption_entities=doc["entities"],
                parse_mode=None,
                reply_markup=_content_button_markup(doc.get("buttons")),
            )
            sent = True
            await asyncio.sleep(1.5)

        if voice:
            await bot.send_voice(
                user_id, voice["file_id"],
                caption=voice["caption"], caption_entities=voice["entities"],
                parse_mode=None,
                reply_markup=_content_button_markup(voice.get("buttons")),
            )
            sent = True

        if not sent:
            await bot.send_message(
                user_id,
                f"{tg_emoji('soon', '🚧')} <b>Content coming soon, {_h(first_name)}! Please stay tuned!</b>",
                parse_mode=ParseMode.HTML,
            )

    except TelegramForbiddenError:
        log.warning("User %s blocked the bot.", user_id)
    except Exception as e:
        log.error("send_content error (uid=%s): %s", user_id, e)


# ══════════════════════════════════════════════════════
#  🧩  BUTTON BUILDERS  (Bot API 9.4 style + icon)
# ══════════════════════════════════════════════════════
def ibtn(
    text: str,
    *,
    callback_data: Optional[str] = None,
    url: Optional[str] = None,
    style: Optional[str] = None,
    icon: Optional[str] = None,
) -> InlineKeyboardButton:
    """InlineKeyboardButton with optional Bot API 9.4 style / custom-emoji icon."""
    kwargs: dict = {"text": text}
    if callback_data is not None:
        kwargs["callback_data"] = callback_data
    if url is not None:
        kwargs["url"] = url
    if style is not None:
        kwargs["style"] = style
    if icon is not None:
        kwargs["icon_custom_emoji_id"] = icon
    return InlineKeyboardButton(**kwargs)


def rbtn(text: str, *, style: Optional[str] = None, icon: Optional[str] = None, **extra) -> KeyboardButton:
    """ReplyKeyboard KeyboardButton with optional Bot API 9.4 style / custom-emoji icon."""
    kwargs: dict = {"text": text, **extra}
    if style is not None:
        kwargs["style"] = style
    if icon is not None:
        kwargs["icon_custom_emoji_id"] = icon
    return KeyboardButton(**kwargs)


# ══════════════════════════════════════════════════════
#  🎨  KEYBOARDS
# ══════════════════════════════════════════════════════

# Cache for auto-accept status to avoid database calls on every keyboard build
_AUTO_ACCEPT_CACHE = None
_AUTO_ACCEPT_CACHE_TIME = 0

def get_auto_accept_status() -> bool:
    """Get cached auto-accept status or fetch from DB."""
    # This is a synchronous function, so we can't use async here
    # We'll handle this differently in the keyboard creation
    return False  # Default fallback


def kb_main_menu_owner(auto_accept: bool = False) -> ReplyKeyboardMarkup:
    """Owner panel — includes admin management."""
    status_text = "✅ ON" if auto_accept else "❌ OFF"
    return ReplyKeyboardMarkup(
        keyboard=[
            [rbtn("Statistics", style=STYLE_PRIMARY, icon=EMOJI_IDS["stats"]),
             rbtn("Broadcast", style=STYLE_SUCCESS, icon=EMOJI_IDS["broadcast"])],
            [rbtn("Content", style=STYLE_PRIMARY, icon=EMOJI_IDS["content"]),
             rbtn("Channels", style=STYLE_SUCCESS, icon=EMOJI_IDS["channels"])],
            [rbtn("Admins", style=STYLE_DANGER, icon=EMOJI_IDS["admins"]),
             rbtn(f"Auto-Accept {status_text}", style=STYLE_PRIMARY, icon=EMOJI_IDS["auto_accept"])],
            [rbtn("Preview", style=STYLE_PRIMARY, icon=EMOJI_IDS["preview"])],
        ],
        resize_keyboard=True,
    )


def kb_main_menu_admin() -> ReplyKeyboardMarkup:
    """Admin panel without admin-management controls."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [rbtn("Statistics", style=STYLE_PRIMARY, icon=EMOJI_IDS["stats"]),
             rbtn("Broadcast", style=STYLE_SUCCESS, icon=EMOJI_IDS["broadcast"])],
            [rbtn("Content", style=STYLE_PRIMARY, icon=EMOJI_IDS["content"]),
             rbtn("Channels", style=STYLE_SUCCESS, icon=EMOJI_IDS["channels"])],
            [rbtn("Preview", style=STYLE_PRIMARY, icon=EMOJI_IDS["preview"])],
        ],
        resize_keyboard=True,
    )


def _submenu_back_row(back_data: str = "nav:main") -> list[list[InlineKeyboardButton]]:
    return [[ibtn("Main Menu", callback_data=back_data, style=STYLE_PRIMARY, icon=EMOJI_IDS["back"])]]


def kb_content_menu() -> InlineKeyboardMarkup:
    """Content sub-menu."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [ibtn("Set Video", callback_data="content:set_video", style=STYLE_PRIMARY, icon=EMOJI_IDS["video"]),
             ibtn("Set APK", callback_data="content:set_apk", style=STYLE_SUCCESS, icon=EMOJI_IDS["apk"])],
            [ibtn("Set Voice", callback_data="content:set_voice", style=STYLE_PRIMARY, icon=EMOJI_IDS["voice"])],
            *_submenu_back_row("content:back"),
        ],
    )


def kb_channels_menu() -> InlineKeyboardMarkup:
    """Channels sub-menu."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [ibtn("Add Channel", callback_data="channels:add", style=STYLE_SUCCESS, icon=EMOJI_IDS["add"]),
             ibtn("List Channels", callback_data="channels:list", style=STYLE_PRIMARY, icon=EMOJI_IDS["list"])],
            [ibtn("Remove Channel", callback_data="channels:remove", style=STYLE_DANGER, icon=EMOJI_IDS["remove"])],
            *_submenu_back_row("channels:back"),
        ],
    )


def kb_admins_menu() -> InlineKeyboardMarkup:
    """Admins sub-menu."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [ibtn("Add Admin", callback_data="admins:add", style=STYLE_SUCCESS, icon=EMOJI_IDS["add"]),
             ibtn("List Admins", callback_data="admins:list", style=STYLE_PRIMARY, icon=EMOJI_IDS["list"])],
            [ibtn("Remove Admin", callback_data="admins:remove", style=STYLE_DANGER, icon=EMOJI_IDS["remove"])],
            *_submenu_back_row("admins:back"),
        ],
    )


def kb_cancel_reply() -> InlineKeyboardMarkup:
    """Shown during any FSM input — inline cancel button."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[ibtn("Cancel", callback_data="ui:cancel", style=STYLE_DANGER, icon=EMOJI_IDS["cancel"])]],
    )


def kb_auto_accept() -> InlineKeyboardMarkup:
    """Auto-accept toggle menu."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [ibtn("✅ Turn ON", callback_data="auto:on", style=STYLE_SUCCESS, icon=EMOJI_IDS["success"])],
            [ibtn("❌ Turn OFF", callback_data="auto:off", style=STYLE_DANGER, icon=EMOJI_IDS["cancel"])],
            *_submenu_back_row("auto:back"),
        ],
    )


# ── Content Link-Button Flow ──────────────────────────
def kb_ask_button(more: bool = False) -> InlineKeyboardMarkup:
    """Asked right after saving content (or after attaching a button) — attach
    another URL button, or skip/finish. `more=True` swaps to "1 more button" wording."""
    add_label = "Add 1 More Button" if more else "Add Button"
    skip_label = "Done" if more else "Skip"
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            ibtn(add_label, callback_data="btn:add", style=STYLE_SUCCESS, icon=EMOJI_IDS["add"]),
            ibtn(skip_label, callback_data="btn:skip", style=STYLE_DANGER, icon=EMOJI_IDS["cancel"]),
        ]],
    )


def kb_button_style(label: str) -> InlineKeyboardMarkup:
    """Live-preview style picker — each row shows the real label in that colour."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [ibtn(label, callback_data="btnstyle:primary", style=STYLE_PRIMARY, icon=EMOJI_IDS["link"])],
            [ibtn(label, callback_data="btnstyle:success", style=STYLE_SUCCESS, icon=EMOJI_IDS["link"])],
            [ibtn(label, callback_data="btnstyle:danger", style=STYLE_DANGER, icon=EMOJI_IDS["link"])],
        ],
    )


# ── User / Force-Join Inline Keyboards ───────────────
def kb_force_join(channels: list[dict]) -> InlineKeyboardMarkup:
    """Force-join gate keyboard — one row per channel + a check button."""
    rows: list[list[InlineKeyboardButton]] = []
    for ch in channels:
        if ch.get("invite_link"):
            rows.append([ibtn(ch["title"], url=ch["invite_link"], style=STYLE_SUCCESS, icon=EMOJI_IDS["channels"])])
        else:
            rows.append([ibtn(ch["title"], callback_data="noop", style=STYLE_SUCCESS, icon=EMOJI_IDS["channels"])])
    rows.append([ibtn("I've Joined All", callback_data="user:check", style=STYLE_SUCCESS, icon=EMOJI_IDS["success"])])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ══════════════════════════════════════════════════════
#  🛣️  ROUTER
# ══════════════════════════════════════════════════════
router = Router()

MAIN_MENU_TEXT = (
    "╔══════════════════════╗\n"
    f"║   {tg_emoji('robot', '🤖')}  <b>Admin Panel</b>   ║\n"
    "╚══════════════════════╝\n\n"
    "Choose an action from the menu below:"
)


# ──────────────────────────────────────────────────────
#  🔔  JOIN REQUEST HANDLER
# ──────────────────────────────────────────────────────
@router.chat_join_request()
async def on_join_request(req: ChatJoinRequest, bot: Bot) -> None:
    uid   = req.from_user.id
    fname = req.from_user.first_name or "Friend"
    
    # Record the user
    await add_user(uid)
    
    # Check if auto-accept is enabled
    auto_accept = await is_auto_accept_enabled()
    
    if auto_accept:
        # Auto-accept: approve the request
        try:
            await req.approve()
            log.info(f"Auto-approved join request from {uid} ({fname})")
        except Exception as e:
            log.error(f"Failed to approve join request from {uid}: {e}")
    else:
        # Don't auto-accept - just log
        log.info(f"Join request from {uid} ({fname}) - auto-accept is OFF")
        # Note: We're not approving the request, so they remain in the pending list
    
    # Send content to the user
    try:
        await bot.send_message(
            uid,
            f"{tg_emoji('welcome', '🎉')} <b>Welcome {_h(fname)}!</b> Your content is ready 👇",
            parse_mode=ParseMode.HTML,
        )
        await asyncio.sleep(1)
        await send_content(bot, uid, fname)
        
        # If auto-accept is off, send a note about pending approval
        if not auto_accept:
            await bot.send_message(
                uid,
                f"{tg_emoji('info', 'ℹ️')} <b>Note:</b> Your request to join the channel is <b>pending approval</b>.\n"
                f"An admin will review and approve it soon.",
                parse_mode=ParseMode.HTML,
            )
    except TelegramForbiddenError:
        log.warning("User %s hasn't started bot — can't DM.", uid)


# ──────────────────────────────────────────────────────
#  /START
# ──────────────────────────────────────────────────────
@router.message(Command("start"))
async def cmd_start(msg: Message, bot: Bot, state: FSMContext) -> None:
    uid   = msg.from_user.id
    fname = msg.from_user.first_name or "Friend"

    await add_user(uid)
    await state.clear()

    # ── Admin → Reply Keyboard Panel ─────────────────
    if await is_admin(uid):
        auto_status = await is_auto_accept_enabled() if await is_owner(uid) else False
        menu = kb_main_menu_owner(auto_status) if await is_owner(uid) else kb_main_menu_admin()
        await msg.answer(
            MAIN_MENU_TEXT,
            parse_mode=ParseMode.HTML,
            reply_markup=menu,
        )
        return

    # ── Regular user → force-join gate ───────────────
    unjoined = await get_unjoined(bot, uid)
    if unjoined:
        n = len(unjoined)
        ch_icon = tg_emoji("channels", "📢")
        if n == 1:
            body = f"You must join this channel to unlock your content:\n\n{ch_icon} <b>{_h(unjoined[0]['title'])}</b>"
        else:
            ch_list = "\n".join(f"  {ch_icon}  <b>{_h(c['title'])}</b>" for c in unjoined)
            body    = f"You must join <b>all {n} channels</b> to unlock your content:\n\n{ch_list}"

        await msg.answer(
            f"{tg_emoji('wave', '👋')} <b>Hey {_h(fname)}!</b>\n\n"
            f"{tg_emoji('warning', '⚠️')} <b>Access Restricted</b>\n\n"
            f"{body}\n\n"
            f"{tg_emoji('pointer', '👇')} Join and tap <b>I've Joined All</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_force_join(unjoined),
        )
        return

    # All joined → deliver content
    await msg.answer(
        f"{tg_emoji('welcome', '🎉')} <b>Welcome {_h(fname)}!</b> Here's your content 👇",
        parse_mode=ParseMode.HTML,
    )
    await send_content(bot, uid, fname)


# ──────────────────────────────────────────────────────
#  ✅  USER CALLBACKS  (force-join gate)
# ──────────────────────────────────────────────────────
@router.callback_query(F.data == "user:check")
async def cb_user_check(call: CallbackQuery, bot: Bot) -> None:
    uid   = call.from_user.id
    fname = call.from_user.first_name or "Friend"

    unjoined = await get_unjoined(bot, uid)
    if unjoined:
        # Alert popups are plain text only — no HTML / tg-emoji here.
        titles = ", ".join(c["title"] for c in unjoined)
        await call.answer(f"❌ Still not joined: {titles}", show_alert=True)
        try:
            await call.message.edit_reply_markup(reply_markup=kb_force_join(unjoined))
        except Exception:
            pass
        return

    await call.answer("✅ Verified! Sending your content…")
    try:
        await call.message.delete()
    except Exception:
        pass

    await bot.send_message(
        uid,
        f"{tg_emoji('welcome', '🎉')} <b>Welcome {_h(fname)}!</b> Here's your content 👇",
        parse_mode=ParseMode.HTML,
    )
    await send_content(bot, uid, fname)


@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery) -> None:
    await call.answer("Contact the admin for the invite link.", show_alert=True)


# ══════════════════════════════════════════════════════
#  🔙  CANCEL / BACK  — works from ANY state
#  NOTE: Registered FIRST so it wins over FSM handlers
# ══════════════════════════════════════════════════════

async def _go_main_menu(msg: Message, state: FSMContext) -> None:
    """Helper: clear FSM state and show the correct main menu."""
    await state.clear()
    if await is_owner(msg.chat.id):
        auto_status = await is_auto_accept_enabled()
        menu = kb_main_menu_owner(auto_status)
    else:
        menu = kb_main_menu_admin()
    await msg.answer(
        MAIN_MENU_TEXT,
        parse_mode=ParseMode.HTML,
        reply_markup=menu,
    )


@router.callback_query(F.data.in_({"nav:main", "ui:cancel", "content:back", "channels:back", "admins:back", "auto:back"}))
async def cb_go_main_menu(call: CallbackQuery, state: FSMContext) -> None:
    if not await is_admin(call.from_user.id):
        await call.answer("⛔ Not authorized.", show_alert=True)
        return

    await call.answer()
    if call.message:
        await _go_main_menu(call.message, state)
        try:
            await call.message.delete()
        except Exception:
            pass


@router.callback_query(F.data == "content:set_video")
async def cb_content_set_video(call: CallbackQuery, state: FSMContext) -> None:
    if not await is_admin(call.from_user.id):
        await call.answer("⛔ Not authorized.", show_alert=True)
        return
    await call.answer()
    if call.message:
        await handle_set_video_start(call.message, state)


@router.callback_query(F.data == "content:set_apk")
async def cb_content_set_apk(call: CallbackQuery, state: FSMContext) -> None:
    if not await is_admin(call.from_user.id):
        await call.answer("⛔ Not authorized.", show_alert=True)
        return
    await call.answer()
    if call.message:
        await handle_set_apk_start(call.message, state)


@router.callback_query(F.data == "content:set_voice")
async def cb_content_set_voice(call: CallbackQuery, state: FSMContext) -> None:
    if not await is_admin(call.from_user.id):
        await call.answer("⛔ Not authorized.", show_alert=True)
        return
    await call.answer()
    if call.message:
        await handle_set_voice_start(call.message, state)


@router.callback_query(F.data == "channels:add")
async def cb_channels_add(call: CallbackQuery, state: FSMContext) -> None:
    if not await is_admin(call.from_user.id):
        await call.answer("⛔ Not authorized.", show_alert=True)
        return
    await call.answer()
    if call.message:
        await handle_add_channel_start(call.message, state)


@router.callback_query(F.data == "channels:list")
async def cb_channels_list(call: CallbackQuery) -> None:
    if not await is_admin(call.from_user.id):
        await call.answer("⛔ Not authorized.", show_alert=True)
        return
    await call.answer()
    if call.message:
        await handle_list_channels(call.message)


@router.callback_query(F.data == "channels:remove")
async def cb_channels_remove(call: CallbackQuery) -> None:
    if not await is_admin(call.from_user.id):
        await call.answer("⛔ Not authorized.", show_alert=True)
        return
    await call.answer()
    if call.message:
        await handle_remove_channel(call.message)


@router.callback_query(F.data == "admins:add")
async def cb_admins_add(call: CallbackQuery, state: FSMContext) -> None:
    if not await is_owner(call.from_user.id):
        await call.answer("⛔ Not authorized.", show_alert=True)
        return
    await call.answer()
    if call.message:
        await handle_add_admin_start(call.message, state)


@router.callback_query(F.data == "admins:list")
async def cb_admins_list(call: CallbackQuery) -> None:
    if not await is_owner(call.from_user.id):
        await call.answer("⛔ Not authorized.", show_alert=True)
        return
    await call.answer()
    if call.message:
        await handle_list_admins(call.message)


@router.callback_query(F.data == "admins:remove")
async def cb_admins_remove(call: CallbackQuery, state: FSMContext) -> None:
    if not await is_owner(call.from_user.id):
        await call.answer("⛔ Not authorized.", show_alert=True)
        return
    await call.answer()
    if call.message:
        await handle_remove_admin_start(call.message, state)


@router.message(Command("cancel"))
async def cmd_cancel(msg: Message, state: FSMContext) -> None:
    if not await is_admin(msg.from_user.id):
        return
    if not await state.get_state():
        return
    await _go_main_menu(msg, state)


# ══════════════════════════════════════════════════════
#  📊  STATISTICS
# ══════════════════════════════════════════════════════
@router.message(F.text == "Statistics")
async def handle_stats(msg: Message) -> None:
    if not await is_admin(msg.from_user.id):
        return

    total    = await count_users()
    channels = await get_channels()
    admins   = await get_admins()
    video    = await get_content("video")
    doc      = await get_content("document")
    voice    = await get_content("voice")
    auto     = await is_auto_accept_enabled()

    ok  = tg_emoji("success", "✅") + " Ready"
    no  = tg_emoji("cancel", "❌") + " Not set"
    auto_status = tg_emoji("success", "✅") + " ON" if auto else tg_emoji("cancel", "❌") + " OFF"

    await msg.answer(
        f"{tg_emoji('stats', '📊')} <b>Bot Statistics</b>\n"
        "──────────────────────\n"
        f"{tg_emoji('user', '👤')} Total Users  : <b>{total}</b>\n"
        f"{tg_emoji('channels', '📺')} Channels     : <b>{len(channels)}</b>\n"
        f"{tg_emoji('admins', '👑')} Admins       : <b>{len(admins)}</b>\n"
        f"{tg_emoji('auto_accept', '🤖')} Auto-Accept : <b>{auto_status}</b>\n\n"
        f"{tg_emoji('content', '🗂')} <b>Content Status:</b>\n"
        f"  {tg_emoji('video', '🎬')} Video  : {ok if video else no}\n"
        f"  {tg_emoji('apk', '📁')} APK    : {ok if doc else no}\n"
        f"  {tg_emoji('voice', '🎧')} Voice  : {ok if voice else no}",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_main_menu_owner(await is_auto_accept_enabled()) if await is_owner(msg.from_user.id) else kb_main_menu_admin(),
    )


# ══════════════════════════════════════════════════════
#  📢  BROADCAST
# ══════════════════════════════════════════════════════
@router.message(F.text == "Broadcast")
async def handle_broadcast_start(msg: Message, state: FSMContext) -> None:
    if not await is_admin(msg.from_user.id):
        return
    await state.set_state(S.broadcast)
    await msg.answer(
        f"{tg_emoji('broadcast', '📢')} <b>Broadcast Mode</b>\n"
        "──────────────────────\n"
        "Send the message you want to broadcast to <b>all users</b>.\n\n"
        "Supports: text, photo, video, document, sticker…\n\n"
        f"Tap {tg_emoji('cancel', '❌')} <b>Cancel</b> or send /cancel to abort.",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_cancel_reply(),
    )


@router.message(S.broadcast)
async def handle_broadcast(msg: Message, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(msg.from_user.id):
        return

    users = await get_users()
    ok = fail = 0
    note = await msg.answer(
        f"{tg_emoji('sent', '📤')} Sending to <b>{len(users)}</b> users…",
        parse_mode=ParseMode.HTML,
    )

    for uid in users:
        try:
            await msg.copy_to(uid)
            ok += 1
        except (TelegramForbiddenError, TelegramBadRequest):
            fail += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)

    await state.clear()
    try:
        await note.edit_text(
            f"{tg_emoji('success', '✅')} <b>Broadcast Complete</b>\n"
            "──────────────────────\n"
            f"{tg_emoji('delivered', '✔️')} Delivered : <b>{ok}</b>\n"
            f"{tg_emoji('cancel', '❌')} Failed    : <b>{fail}</b>",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass

    if await is_owner(msg.from_user.id):
        menu = kb_main_menu_owner(await is_auto_accept_enabled())
    else:
        menu = kb_main_menu_admin()
    await msg.answer(
        MAIN_MENU_TEXT,
        parse_mode=ParseMode.HTML,
        reply_markup=menu,
    )


# ══════════════════════════════════════════════════════
#  🤖  AUTO-ACCEPT TOGGLE
# ══════════════════════════════════════════════════════
@router.message(F.text.startswith("Auto-Accept"))
async def handle_auto_accept_menu(msg: Message, state: FSMContext) -> None:
    if not await is_owner(msg.from_user.id):
        return
    await state.clear()
    
    auto_status = await is_auto_accept_enabled()
    status_text = "✅ <b>ON</b>" if auto_status else "❌ <b>OFF</b>"
    
    await msg.answer(
        f"{tg_emoji('auto_accept', '🤖')} <b>Auto-Accept Join Requests</b>\n"
        "──────────────────────\n"
        f"Current status: {status_text}\n\n"
        f"{tg_emoji('info', 'ℹ️')} <b>How it works:</b>\n"
        "• <b>ON</b>  → Auto-approves all join requests\n"
        "• <b>OFF</b> → Admin must manually approve requests\n"
        "\n<b>Note:</b> Users receive content regardless of approval status.",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_auto_accept(),
    )


@router.callback_query(F.data.startswith("auto:"))
async def cb_auto_accept_toggle(call: CallbackQuery, state: FSMContext) -> None:
    if not await is_owner(call.from_user.id):
        await call.answer("⛔ Not authorized.", show_alert=True)
        return
    
    action = call.data.split(":")[1]
    
    if action == "on":
        await set_config("auto_accept", "on")
        await call.answer("✅ Auto-accept turned ON!")
        status_text = "✅ <b>ON</b>"
    elif action == "off":
        await set_config("auto_accept", "off")
        await call.answer("❌ Auto-accept turned OFF!")
        status_text = "❌ <b>OFF</b>"
    else:
        await call.answer()
        return
    
    # Update the message with new status
    try:
        await call.message.edit_text(
            f"{tg_emoji('auto_accept', '🤖')} <b>Auto-Accept Join Requests</b>\n"
            "──────────────────────\n"
            f"Current status: {status_text}\n\n"
            f"{tg_emoji('info', 'ℹ️')} <b>How it works:</b>\n"
            "• <b>ON</b>  → Auto-approves all join requests\n"
            "• <b>OFF</b> → Admin must manually approve requests\n"
            "\n<b>Note:</b> Users receive content regardless of approval status.",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_auto_accept(),
        )
    except Exception:
        pass
    
    # Send confirmation and update main menu
    await call.message.answer(
        f"{tg_emoji('success', '✅')} Auto-accept set to <b>{'ON' if action == 'on' else 'OFF'}</b>",
        parse_mode=ParseMode.HTML,
    )


# ══════════════════════════════════════════════════════
#  🗂  CONTENT SUB-MENU
# ══════════════════════════════════════════════════════
@router.message(F.text == "Content")
async def handle_content_menu(msg: Message, state: FSMContext) -> None:
    if not await is_admin(msg.from_user.id):
        return
    await state.clear()

    video = await get_content("video")
    doc   = await get_content("document")
    voice = await get_content("voice")

    ok = tg_emoji("success", "✅") + " Ready"
    no = tg_emoji("cancel", "❌") + " Not set"

    await msg.answer(
        f"{tg_emoji('content', '🗂')} <b>Content Management</b>\n"
        "──────────────────────\n"
        f"{tg_emoji('video', '🎬')} Video  : {ok if video else no}\n"
        f"{tg_emoji('apk', '📁')} APK    : {ok if doc else no}\n"
        f"{tg_emoji('voice', '🎧')} Voice  : {ok if voice else no}\n\n"
        "Choose what to update:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_content_menu(),
    )


def _normalize_url(raw: str) -> Optional[str]:
    """Accepts a full URL, a t.me/... link, or an @username and returns a valid button URL."""
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith(("http://", "https://", "tg://")):
        return raw
    if raw.startswith("t.me/"):
        return f"https://{raw}"
    if raw.startswith("@") and len(raw) > 1:
        return f"https://t.me/{raw[1:]}"
    return None


async def _finish_content_save(msg: Message, state: FSMContext, key: str, label: str) -> None:
    """After a content file is saved, ask whether to attach a link button (or skip).
    Also clears any old buttons on this key, since it was just replaced/re-saved."""
    await clear_content_buttons(key)
    await state.clear()
    await state.update_data(button_target=key, buttons_added=0)
    await msg.answer(
        f"{tg_emoji('success', '✅')} <b>{label} saved!</b>\n\n"
        f"{tg_emoji('link', '🔗')} Want to attach a link button below this content? "
        f"(up to {MAX_CONTENT_BUTTONS})",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_ask_button(),
    )


# ── Set Video ─────────────────────────────────────────
@router.message(F.text == "Set Video")
async def handle_set_video_start(msg: Message, state: FSMContext) -> None:
    if not await is_admin(msg.chat.id):
        return
    await state.set_state(S.set_video)
    await msg.answer(
        f"{tg_emoji('video', '🎬')} <b>Set Video</b>\n"
        "──────────────────────\n"
        "Send the video file now.\n"
        "Caption (if sent with video) will be stored and shown to users.\n\n"
        f"{tg_emoji('warning', '⚠️')} Replaces any previously set video.\n\n"
        f"Tap {tg_emoji('cancel', '❌')} <b>Cancel</b> or send /cancel to abort.",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_cancel_reply(),
    )


@router.message(S.set_video)
async def handle_video(msg: Message, state: FSMContext) -> None:
    if not await is_admin(msg.from_user.id):
        return
    if not msg.video:
        await msg.answer(
            f"{tg_emoji('warning', '⚠️')} Please send a <b>video</b> file.",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_cancel_reply(),
        )
        return
    await save_content("video", msg.video.file_id, msg.caption or None, msg.caption_entities)
    await _finish_content_save(msg, state, "video", "Video")


# ── Set APK / Document ────────────────────────────────
@router.message(F.text == "Set APK")
async def handle_set_apk_start(msg: Message, state: FSMContext) -> None:
    if not await is_admin(msg.chat.id):
        return
    await state.set_state(S.set_apk)
    await msg.answer(
        f"{tg_emoji('apk', '📁')} <b>Set APK / Document</b>\n"
        "──────────────────────\n"
        "Send the file now (APK, ZIP, PDF — any document).\n"
        "Optionally include a caption.\n\n"
        f"{tg_emoji('warning', '⚠️')} Replaces any previously set document.\n\n"
        f"Tap {tg_emoji('cancel', '❌')} <b>Cancel</b> or send /cancel to abort.",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_cancel_reply(),
    )


@router.message(S.set_apk)
async def handle_apk(msg: Message, state: FSMContext) -> None:
    if not await is_admin(msg.from_user.id):
        return
    if not msg.document:
        await msg.answer(
            f"{tg_emoji('warning', '⚠️')} Please send a <b>document</b> file.",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_cancel_reply(),
        )
        return
    await save_content("document", msg.document.file_id, msg.caption or None, msg.caption_entities)
    await _finish_content_save(msg, state, "document", "Document")


# ── Set Voice ─────────────────────────────────────────
@router.message(F.text == "Set Voice")
async def handle_set_voice_start(msg: Message, state: FSMContext) -> None:
    if not await is_admin(msg.chat.id):
        return
    await state.set_state(S.set_voice)
    await msg.answer(
        f"{tg_emoji('voice', '🎧')} <b>Set Voice Message</b>\n"
        "──────────────────────\n"
        "Send a voice message now.\n"
        "Optionally include a caption.\n\n"
        f"{tg_emoji('warning', '⚠️')} Replaces any previously set voice.\n\n"
        f"Tap {tg_emoji('cancel', '❌')} <b>Cancel</b> or send /cancel to abort.",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_cancel_reply(),
    )


@router.message(S.set_voice)
async def handle_voice(msg: Message, state: FSMContext) -> None:
    if not await is_admin(msg.from_user.id):
        return
    if not msg.voice:
        await msg.answer(
            f"{tg_emoji('warning', '⚠️')} Please send a <b>voice</b> message.",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_cancel_reply(),
        )
        return
    await save_content("voice", msg.voice.file_id, msg.caption or None, msg.caption_entities)
    await _finish_content_save(msg, state, "voice", "Voice")


# ══════════════════════════════════════════════════════
#  👀  PREVIEW
# ══════════════════════════════════════════════════════
@router.message(F.text == "Preview")
async def handle_preview(msg: Message, bot: Bot) -> None:
    if not await is_admin(msg.from_user.id):
        return
    fname = msg.from_user.first_name or "Admin"
    await msg.answer(
        f"{tg_emoji('preview', '👀')} <b>Preview — exactly what users receive:</b>",
        parse_mode=ParseMode.HTML,
    )
    await send_content(bot, msg.from_user.id, fname)


# ══════════════════════════════════════════════════════
#  🔗  OPTIONAL LINK BUTTON  (attached after saving content)
# ══════════════════════════════════════════════════════
@router.callback_query(F.data == "btn:skip")
async def cb_btn_skip(call: CallbackQuery, state: FSMContext) -> None:
    if not await is_admin(call.from_user.id):
        await call.answer("⛔ Not authorized.", show_alert=True)
        return
    data = await state.get_data()
    added = data.get("buttons_added", 0)
    await call.answer()
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    if added:
        await call.message.answer(
            f"{tg_emoji('success', '✅')} <b>{added} button{'s' if added != 1 else ''} attached to this content.</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_content_menu(),
        )
    else:
        await call.message.answer(
            f"{tg_emoji('info', 'ℹ️')} No button attached.",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_content_menu(),
        )


@router.callback_query(F.data == "btn:add")
async def cb_btn_add(call: CallbackQuery, state: FSMContext) -> None:
    if not await is_admin(call.from_user.id):
        await call.answer("⛔ Not authorized.", show_alert=True)
        return
    data = await state.get_data()
    if "button_target" not in data:
        await call.answer("Session expired — please set the content again.", show_alert=True)
        return

    added = data.get("buttons_added", 0)
    if added >= MAX_CONTENT_BUTTONS:
        await call.answer(f"Maximum of {MAX_CONTENT_BUTTONS} buttons reached.", show_alert=True)
        return

    await call.answer()
    # Clear any stale label/url from a previous round, keep button_target + buttons_added
    await state.update_data(button_label=None, button_url=None)
    await state.set_state(S.button_text)
    try:
        await call.message.delete()
    except Exception:
        pass

    n = added + 1
    await call.message.answer(
        f"{tg_emoji('link', '🔗')} <b>Button {n} of {MAX_CONTENT_BUTTONS} — Label</b>\n"
        "──────────────────────\n"
        "Send the text to show on the button (e.g. <code>Join Channel</code>).\n\n"
        f"Tap {tg_emoji('cancel', '❌')} <b>Cancel</b> or send /cancel to abort.",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_cancel_reply(),
    )


@router.message(S.button_text)
async def handle_button_text(msg: Message, state: FSMContext) -> None:
    if not await is_admin(msg.from_user.id):
        return
    if not msg.text or not msg.text.strip():
        await msg.answer(
            f"{tg_emoji('warning', '⚠️')} Please send valid text for the button label.",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_cancel_reply(),
        )
        return
    label = msg.text.strip()[:64]
    data  = await state.get_data()
    n     = data.get("buttons_added", 0) + 1
    await state.update_data(button_label=label)
    await state.set_state(S.button_url)
    await msg.answer(
        f"{tg_emoji('link', '🔗')} <b>Button {n} of {MAX_CONTENT_BUTTONS} — URL</b>\n"
        "──────────────────────\n"
        "Send the link this button should open.\n\n"
        "Examples: <code>https://example.com</code>, <code>t.me/mychannel</code>, <code>@myusername</code>\n\n"
        f"Tap {tg_emoji('cancel', '❌')} <b>Cancel</b> or send /cancel to abort.",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_cancel_reply(),
    )


@router.message(S.button_url)
async def handle_button_url(msg: Message, state: FSMContext) -> None:
    if not await is_admin(msg.from_user.id):
        return
    url = _normalize_url(msg.text.strip() if msg.text else "")
    if not url:
        await msg.answer(
            f"{tg_emoji('warning', '⚠️')} That doesn't look like a valid link. Send a full URL "
            "(starting with <code>http://</code> / <code>https://</code>), a <code>t.me/...</code> link, "
            "or an <code>@username</code>.",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_cancel_reply(),
        )
        return
    await state.update_data(button_url=url)
    await state.set_state(S.button_style)
    data  = await state.get_data()
    label = data.get("button_label", "Open Link")
    n     = data.get("buttons_added", 0) + 1
    await msg.answer(
        f"{tg_emoji('link', '🔗')} <b>Button {n} of {MAX_CONTENT_BUTTONS} — Style</b>\n"
        "──────────────────────\n"
        "Tap the colour you want for this button:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_button_style(label),
    )


@router.callback_query(F.data.startswith("btnstyle:"))
async def cb_btn_style(call: CallbackQuery, state: FSMContext) -> None:
    if not await is_admin(call.from_user.id):
        await call.answer("⛔ Not authorized.", show_alert=True)
        return

    style = call.data.split(":", 1)[1]
    if style not in (STYLE_PRIMARY, STYLE_SUCCESS, STYLE_DANGER):
        await call.answer("Invalid style.", show_alert=True)
        return

    data   = await state.get_data()
    target = data.get("button_target")
    label  = data.get("button_label")
    url    = data.get("button_url")
    if not (target and label and url):
        await call.answer("Session expired — please set the content again.", show_alert=True)
        await state.clear()
        return

    await add_content_button(target, {"text": label, "url": url, "style": style})
    added = data.get("buttons_added", 0) + 1
    await call.answer("✅ Button attached!")

    try:
        await call.message.delete()
    except Exception:
        pass

    # Show every button attached to this content so far
    saved = await get_content(target)
    preview_rows = [
        [ibtn(b.get("text") or "Open Link", url=b["url"], style=b.get("style"), icon=EMOJI_IDS["link"])]
        for b in (saved.get("buttons") or []) if b and b.get("url")
    ]
    await call.message.answer(
        f"{tg_emoji('success', '✅')} <b>Button {added} of {MAX_CONTENT_BUTTONS} attached!</b>\n\nPreview so far:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=preview_rows) if preview_rows else None,
    )

    if added >= MAX_CONTENT_BUTTONS:
        # Reached the cap — finish up automatically
        await state.clear()
        await call.message.answer(
            f"{tg_emoji('content', '🗂')} All {MAX_CONTENT_BUTTONS} buttons attached. Back to content menu:",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_content_menu(),
        )
        return

    # Otherwise, ask whether to add another one
    await state.update_data(buttons_added=added, button_label=None, button_url=None)
    await state.set_state(None)
    await call.message.answer(
        f"{tg_emoji('link', '🔗')} Want to add 1 more button to this same content? "
        f"({added}/{MAX_CONTENT_BUTTONS} used)",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_ask_button(more=True),
    )


# ══════════════════════════════════════════════════════
#  📺  CHANNELS SUB-MENU
# ══════════════════════════════════════════════════════
@router.message(F.text == "Channels")
async def handle_channels_menu(msg: Message, state: FSMContext) -> None:
    if not await is_admin(msg.from_user.id):
        return
    await state.clear()
    channels = await get_channels()
    n      = len(channels)
    status = f"<b>{n} channel{'s' if n != 1 else ''}</b> active." if n else "No channels saved yet."
    await msg.answer(
        f"{tg_emoji('channels', '📺')} <b>Channel Management</b>\n"
        "──────────────────────\n"
        f"{tg_emoji('info', 'ℹ️')} {status}\n\n"
        "Choose an action:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_channels_menu(),
    )


# ── Add Channel ───────────────────────────────────────
@router.message(F.text == "Add Channel")
async def handle_add_channel_start(msg: Message, state: FSMContext) -> None:
    if not await is_admin(msg.chat.id):
        return
    await state.set_state(S.add_channel)
    await msg.answer(
        f"{tg_emoji('add', '➕')} <b>Add Channel</b>\n"
        "──────────────────────\n"
        "Send the channel in <b>any</b> of these ways:\n\n"
        f"{tg_emoji('link', '🔗')}  <b>Username</b>  →  <code>@mychannel</code>\n"
        f"{tg_emoji('chat_id', '🆔')}  <b>Chat ID</b>   →  <code>-1001234567890</code>\n"
        f"{tg_emoji('forward', '📨')}  <b>Forward</b>   →  Forward any message from the channel\n\n"
        f"{tg_emoji('warning', '⚠️')} Make sure the bot is <b>admin</b> in the channel first!\n\n"
        f"Tap {tg_emoji('cancel', '❌')} <b>Cancel</b> or send /cancel to abort.",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_cancel_reply(),
    )


@router.message(S.add_channel)
async def handle_add_channel(msg: Message, bot: Bot, state: FSMContext) -> None:
    if not await is_admin(msg.from_user.id):
        return

    channel_raw: Optional[str] = None

    # Method 1: Forwarded message from a channel
    if msg.forward_from_chat and msg.forward_from_chat.type == "channel":
        fc = msg.forward_from_chat
        channel_raw = f"@{fc.username}" if fc.username else str(fc.id)

    # Method 2: Text (@username or numeric ID)
    elif msg.text:
        raw = msg.text.strip()
        if raw.lstrip("-").isdigit():
            channel_raw = raw
        else:
            channel_raw = raw if raw.startswith("@") else f"@{raw}"

    else:
        await msg.answer(
            f"{tg_emoji('warning', '⚠️')} <b>Cannot detect channel.</b>\n\n"
            "Send a <code>@username</code>, a numeric ID, or <b>forward a message</b> from the channel.",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_cancel_reply(),
        )
        return

    # Validate with Telegram
    try:
        chat  = await bot.get_chat(channel_raw)
        ch_id = f"@{chat.username}" if chat.username else str(chat.id)
        title = chat.title or ch_id
    except Exception:
        await msg.answer(
            f"{tg_emoji('cancel', '❌')} <b>Could not access</b> <code>{_h(channel_raw)}</code>\n\n"
            "Check that:\n"
            "› The channel exists\n"
            "› The bot is <b>admin</b> in the channel\n"
            "› The username / ID is correct",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_cancel_reply(),
        )
        return

    # Generate invite link
    invite_link: Optional[str] = None
    try:
        invite_link = await bot.export_chat_invite_link(ch_id)
    except Exception:
        if str(ch_id).startswith("@"):
            invite_link = f"https://t.me/{ch_id.lstrip('@')}"

    # Duplicate check
    existing = await get_channels()
    if any(c["channel_id"] == ch_id for c in existing):
        await msg.answer(
            f"{tg_emoji('info', 'ℹ️')} <b>{_h(title)}</b> is already in the list.",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_channels_menu(),
        )
        await state.clear()
        return

    await add_channel(ch_id, title, invite_link)
    await state.clear()
    await msg.answer(
        f"{tg_emoji('success', '✅')} <b>Channel Added!</b>\n"
        "──────────────────────\n"
        f"{tg_emoji('channels', '📢')} <b>{_h(title)}</b>\n"
        f"{tg_emoji('chat_id', '🆔')} <code>{_h(ch_id)}</code>\n"
        f"{tg_emoji('link', '🔗')} Invite link: {'saved ' + tg_emoji('success', '✅') if invite_link else 'not available ' + tg_emoji('warning', '⚠️')}\n\n"
        f"{tg_emoji('list', '📋')} Total channels: <b>{len(existing) + 1}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_channels_menu(),
    )


# ── List Channels ─────────────────────────────────────
@router.message(F.text == "List Channels")
async def handle_list_channels(msg: Message) -> None:
    if not await is_admin(msg.chat.id):
        return
    channels = await get_channels()
    if not channels:
        await msg.answer(
            f"{tg_emoji('list', '📋')} <b>No channels saved yet.</b>\n\nUse <b>Add Channel</b> to add one.",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_channels_menu(),
        )
        return

    lines = [f"{tg_emoji('list', '📋')} <b>Required Channels:</b>\n"]
    for i, ch in enumerate(channels, 1):
        link_part = f' — <a href="{_h(ch["invite_link"])}">Join</a>' if ch.get("invite_link") else ""
        lines.append(f"  {i}. <b>{_h(ch['title'])}</b>{link_part}")

    await msg.answer(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=kb_channels_menu(),
        disable_web_page_preview=True,
    )


# ── Remove Channel — tap to delete (inline list) ─────
@router.message(F.text == "Remove Channel")
async def handle_remove_channel(msg: Message) -> None:
    if not await is_admin(msg.chat.id):
        return
    channels = await get_channels()
    if not channels:
        await msg.answer(
            f"{tg_emoji('info', 'ℹ️')} No channels to remove.",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_channels_menu(),
        )
        return

    rows = [
        [ibtn(ch["title"], callback_data=f"ch:del:{ch['channel_id']}", style=STYLE_DANGER, icon=EMOJI_IDS["remove"])]
        for ch in channels
    ]
    await msg.answer(
        f"{tg_emoji('remove', '🗑')} <b>Remove Channel</b>\n"
        "──────────────────────\n"
        "Tap the channel you want to remove:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("ch:del:"))
async def cb_ch_do_delete(call: CallbackQuery) -> None:
    if not await is_admin(call.from_user.id):
        await call.answer("⛔ Not authorized.", show_alert=True)
        return

    ch_id    = call.data[len("ch:del:"):]
    channels = await get_channels()
    entry    = next((c for c in channels if c["channel_id"] == ch_id), None)

    if not entry:
        await call.answer("Channel not found.", show_alert=True)
        return

    await remove_channel(ch_id)
    await call.answer(f"✅ {entry['title']} removed!")

    # Refresh the inline list
    channels = await get_channels()
    if not channels:
        await call.message.edit_text(
            f"{tg_emoji('success', '✅')} <b>Channel removed.</b>\n\nNo channels remaining.",
            parse_mode=ParseMode.HTML,
        )
        return

    rows = [
        [ibtn(ch["title"], callback_data=f"ch:del:{ch['channel_id']}", style=STYLE_DANGER, icon=EMOJI_IDS["remove"])]
        for ch in channels
    ]
    await call.message.edit_reply_markup(
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )


# ══════════════════════════════════════════════════════
#  👑  ADMINS SUB-MENU
# ══════════════════════════════════════════════════════
@router.message(F.text == "Admins")
async def handle_admins_menu(msg: Message, state: FSMContext) -> None:
    if not await is_owner(msg.from_user.id):
        return
    await state.clear()
    admins = await get_admins()
    await msg.answer(
        f"{tg_emoji('admins', '👑')} <b>Admin Management</b>\n"
        "──────────────────────\n"
        f"Currently <b>{len(admins)}</b> admin(s).\n\n"
        "Choose an action:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_admins_menu(),
    )


# ── List Admins ───────────────────────────────────────
@router.message(F.text == "List Admins")
async def handle_list_admins(msg: Message) -> None:
    if not await is_owner(msg.chat.id):
        return
    admins = await get_admins()
    lines  = [f"{tg_emoji('admins', '👑')} <b>Admin List:</b>\n"]
    for i, uid in enumerate(admins, 1):
        tag = f" {tg_emoji('owner', '🔱')} <i>(Owner)</i>" if uid == OWNER_ID else ""
        lines.append(f"  {i}. <code>{uid}</code>{tag}")
    await msg.answer(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=kb_admins_menu(),
    )


# ── Add Admin ─────────────────────────────────────────
@router.message(F.text == "Add Admin")
async def handle_add_admin_start(msg: Message, state: FSMContext) -> None:
    if not await is_owner(msg.chat.id):
        return
    await state.set_state(S.add_admin)
    await msg.answer(
        f"{tg_emoji('add', '➕')} <b>Add Admin</b>\n"
        "──────────────────────\n"
        "Send the <b>numeric Telegram user ID</b> of the new admin.\n\n"
        f"Tap {tg_emoji('cancel', '❌')} <b>Cancel</b> or send /cancel to abort.",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_cancel_reply(),
    )


@router.message(S.add_admin)
async def handle_add_admin(msg: Message, state: FSMContext) -> None:
    if not await is_owner(msg.from_user.id):
        return
    try:
        new_id = int(msg.text.strip())
    except (ValueError, AttributeError):
        await msg.answer(
            f"{tg_emoji('warning', '⚠️')} Invalid user ID. Please send a numeric Telegram ID.",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_cancel_reply(),
        )
        return
    if new_id == OWNER_ID:
        await msg.answer(
            f"{tg_emoji('info', 'ℹ️')} Owner is already the primary admin.",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_admins_menu(),
        )
        return
    await add_admin(new_id)
    await state.clear()
    await msg.answer(
        f"{tg_emoji('success', '✅')} <b>Admin added:</b> <code>{new_id}</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_admins_menu(),
    )


# ── Remove Admin ──────────────────────────────────────
@router.message(F.text == "Remove Admin")
async def handle_remove_admin_start(msg: Message, state: FSMContext) -> None:
    if not await is_owner(msg.chat.id):
        return
    await state.set_state(S.rm_admin)
    await msg.answer(
        f"{tg_emoji('remove', '🗑')} <b>Remove Admin</b>\n"
        "──────────────────────\n"
        "Send the <b>user ID</b> to remove.\n\n"
        f"{tg_emoji('warning', '⚠️')} The owner cannot be removed.\n\n"
        f"Tap {tg_emoji('cancel', '❌')} <b>Cancel</b> or send /cancel to abort.",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_cancel_reply(),
    )


@router.message(S.rm_admin)
async def handle_rm_admin(msg: Message, state: FSMContext) -> None:
    if not await is_owner(msg.from_user.id):
        return
    try:
        target = int(msg.text.strip())
    except (ValueError, AttributeError):
        await msg.answer(
            f"{tg_emoji('warning', '⚠️')} Invalid user ID.",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_cancel_reply(),
        )
        return
    if target == OWNER_ID:
        await msg.answer(
            f"{tg_emoji('blocked', '⛔')} The owner cannot be removed.",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_admins_menu(),
        )
        await state.clear()
        return
    await remove_admin(target)
    await state.clear()
    await msg.answer(
        f"{tg_emoji('success', '✅')} <b>Admin removed:</b> <code>{target}</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_admins_menu(),
    )


# ══════════════════════════════════════════════════════
#  🚀  STARTUP
# ══════════════════════════════════════════════════════
async def main() -> None:
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        log.error("Please set BOT_TOKEN in the config section!")
        return

    await db_init()
    await add_admin(OWNER_ID)  # Owner is always admin
    # Set default auto-accept to OFF
    await set_config("auto_accept", "off")

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    log.info("Bot starting…")
    await dp.start_polling(
        bot,
        allowed_updates=["message", "callback_query", "chat_join_request"],
    )


if __name__ == "__main__":
    asyncio.run(main())
