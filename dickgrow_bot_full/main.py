import os, sqlite3, random, time, re, logging, traceback, tempfile
import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaPhoto
from aiogram.types import BufferedInputFile, FSInputFile
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("man_market_bot")

TOKEN = os.getenv("BOT_TOKEN")
DB = os.getenv("DB_PATH", "database.db")
COOLDOWN=1*60*60
ADMIN_IDS = {5952134460, 5429762495}

db_dir = os.path.dirname(DB)
if db_dir:
    os.makedirs(db_dir, exist_ok=True)
db=sqlite3.connect(DB)
c=db.cursor()

# ===== Ù‡Ù…Ù‡â€ŒÛŒ Ø¬Ø¯ÙˆÙ„â€ŒÙ‡Ø§ÛŒ Ø§Ù‚ØªØµØ§Ø¯ÛŒ Ø­Ø§Ù„Ø§ Ø¨Ø§ chat_id Ø§Ø³Ú©ÙˆÙ¾ Ù…ÛŒØ´Ù† =====
# ÛŒØ¹Ù†ÛŒ Ù‡Ø± Ú¯Ø±ÙˆÙ‡ (ÛŒØ§ Ú†Øª Ø®ØµÙˆØµÛŒ) ÛŒÙ‡ Ø§Ù‚ØªØµØ§Ø¯ Ú©Ø§Ù…Ù„Ø§Ù‹ Ù…Ø³ØªÙ‚Ù„ Ø¯Ø§Ø±Ù‡Ø›
# Ø¢ÛŒØ¯ÛŒ Ø¹Ø¯Ø¯ÛŒ Ú©Ø§Ø±Ø¨Ø± ØªÙˆ Ú¯Ø±ÙˆÙ‡â€ŒÙ‡Ø§ÛŒ Ù…Ø®ØªÙ„Ù Ø¨Ù‡â€ŒØµÙˆØ±Øª Ø¬Ø¯Ø§ Ø´Ù…Ø±Ø¯Ù‡ Ù…ÛŒØ´Ù‡.
c.execute("""CREATE TABLE IF NOT EXISTS users(
    chat_id INTEGER,
    user_id INTEGER,
    name TEXT,
    size INTEGER DEFAULT 0,
    sperm INTEGER DEFAULT 0,
    debt INTEGER DEFAULT 0,
    last_grow INTEGER DEFAULT 0,
    PRIMARY KEY(chat_id, user_id)
)""")
c.execute("CREATE TABLE IF NOT EXISTS battles(id INTEGER PRIMARY KEY AUTOINCREMENT,creator INTEGER,bet INTEGER,active INTEGER DEFAULT 1)")
c.execute("""CREATE TABLE IF NOT EXISTS pvp_stats(
    chat_id INTEGER,
    user_id INTEGER,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    PRIMARY KEY(chat_id, user_id)
)""")
c.execute("""CREATE TABLE IF NOT EXISTS rank_stats(
    chat_id INTEGER,
    user_id INTEGER,
    rp INTEGER DEFAULT 0,
    duels_today INTEGER DEFAULT 0,
    last_active_day TEXT DEFAULT '',
    PRIMARY KEY(chat_id, user_id)
)""")
c.execute("""CREATE TABLE IF NOT EXISTS loans(
    chat_id INTEGER,
    lender_id INTEGER,
    borrower_id INTEGER,
    amount INTEGER,
    loan_time INTEGER DEFAULT 0
)""")
c.execute("""CREATE TABLE IF NOT EXISTS listings(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    seller_id INTEGER,
    celeb TEXT,
    price INTEGER,
    active INTEGER DEFAULT 1
)""")
c.execute("""CREATE TABLE IF NOT EXISTS game_loans(
    chat_id INTEGER,
    user_id INTEGER,
    amount INTEGER,
    due_time INTEGER,
    PRIMARY KEY(chat_id, user_id)
)""")
db.commit()

try:
    c.execute("ALTER TABLE users ADD COLUMN sperm INTEGER DEFAULT 0")
    db.commit()
except sqlite3.OperationalError:
    pass

try:
    c.execute("ALTER TABLE users ADD COLUMN farm_plots INTEGER DEFAULT 2")
    db.commit()
except sqlite3.OperationalError:
    pass

c.execute("""CREATE TABLE IF NOT EXISTS farm_tiles(
    chat_id INTEGER,
    user_id INTEGER,
    plot_num INTEGER,
    egg_type TEXT,
    planted_at INTEGER,
    PRIMARY KEY(chat_id, user_id, plot_num)
)""")
c.execute("""CREATE TABLE IF NOT EXISTS farm_inventory(
    chat_id INTEGER,
    user_id INTEGER,
    egg_type TEXT,
    count INTEGER DEFAULT 0,
    PRIMARY KEY(chat_id, user_id, egg_type)
)""")
c.execute("""CREATE TABLE IF NOT EXISTS farm_records(
    chat_id INTEGER,
    user_id INTEGER,
    eggs_bought INTEGER DEFAULT 0,
    eggs_planted INTEGER DEFAULT 0,
    eggs_harvested INTEGER DEFAULT 0,
    total_harvest_value INTEGER DEFAULT 0,
    plots_opened INTEGER DEFAULT 0,
    spent_cm INTEGER DEFAULT 0,
    PRIMARY KEY(chat_id, user_id)
)""")
c.execute("""CREATE TABLE IF NOT EXISTS auctions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    name TEXT,
    photo TEXT,
    status TEXT DEFAULT 'active',
    top_bid INTEGER DEFAULT 0,
    top_bidder INTEGER DEFAULT 0,
    top_bidder_name TEXT DEFAULT '',
    last_activity INTEGER,
    created_at INTEGER,
    msg_id INTEGER DEFAULT 0
)""")
db.commit()
try:
    c.execute("ALTER TABLE auctions ADD COLUMN msg_id INTEGER DEFAULT 0")
    db.commit()
except sqlite3.OperationalError:
    pass

SPERM_RATE = 2  # Û± Ø³Ø§Ù†Øª = Û² Ø§Ø³Ù¾Ø±Ù… (ÙˆØ§Ø­Ø¯ Ø¬Ø¯Ø§Ú¯Ø§Ù†Ù‡â€ŒÛŒ Ø¨Ø®Ø´ Ø¨ÙˆØ±Ø³)

def strip_command(text: str) -> str:
    """Ø­Ø°Ù /command ÛŒØ§ /command@botusername Ø§Ø² Ø§Ø¨ØªØ¯Ø§ÛŒ Ù…ØªÙ† Ùˆ Ø¨Ø±Ú¯Ø±Ø¯ÙˆÙ†Ø¯Ù† Ø¨Ù‚ÛŒÙ‡â€ŒÛŒ Ù…ØªÙ†.
    Ø§ÛŒÙ† Ú©Ø§Ø± Ù„Ø§Ø²Ù…Ù‡ Ú†ÙˆÙ† ØªÙˆ Ú¯Ø±ÙˆÙ‡â€ŒÙ‡Ø§ ØªÙ„Ú¯Ø±Ø§Ù… Ù…Ø¹Ù…ÙˆÙ„Ø§Ù‹ @ÛŒÙˆØ²Ø±Ù†ÛŒÙ… Ø¨Ø§Øª Ø±Ùˆ Ø¨Ù‡ Ø¯Ø³ØªÙˆØ± Ù…ÛŒâ€ŒÚ†Ø³Ø¨ÙˆÙ†Ù‡
    (Ù…Ø«Ù„Ø§Ù‹ /buy@YourBot Kylie Jenner) Ùˆ replace Ø³Ø§Ø¯Ù‡â€ŒÛŒ Ø±Ø´ØªÙ‡ Ø§ÛŒÙ† Ø­Ø§Ù„Øª Ø±Ùˆ Ø¯Ø±Ø³Øª Ù¾Ø§Ø±Ø³ Ù†Ù…ÛŒâ€ŒÚ©Ù†Ù‡."""
    return re.sub(r'^/\S+\s*', '', text or '', count=1).strip()

def user(chat_id,uid,name):
    c.execute("INSERT OR IGNORE INTO users(chat_id,user_id,name) VALUES(?,?,?)",(chat_id,uid,name))
    c.execute("UPDATE users SET name=? WHERE chat_id=? AND user_id=?",(name,chat_id,uid))
    db.commit()

def get_size(chat_id,uid):
    row=c.execute("SELECT size FROM users WHERE chat_id=? AND user_id=?",(chat_id,uid)).fetchone()
    return row[0] if row else 0

def get_sperm(chat_id,uid):
    row=c.execute("SELECT sperm FROM users WHERE chat_id=? AND user_id=?",(chat_id,uid)).fetchone()
    return row[0] if row else 0

def get_name(chat_id,uid):
    row=c.execute("SELECT name FROM users WHERE chat_id=? AND user_id=?",(chat_id,uid)).fetchone()
    return row[0] if row else "Ú©Ø§Ø±Ø¨Ø±"

dp=Dispatcher()

# ===== Ø±Ø§Ù‡Ù†Ù…Ø§ÛŒ Ø¨Ø§Ø²ÛŒ =====
HELP_SECTIONS = {
    "econ": (
        "ðŸ’° Ø§Ù‚ØªØµØ§Ø¯ Ù¾Ø§ÛŒÙ‡",
        "ðŸ† /grow â€” Ù‡Ø± Ú†Ù†Ø¯Ø³Ø§Ø¹Øª ÛŒÙ‡â€ŒØ¨Ø§Ø± Ø³Ø§ÛŒØ²Øª Ø±Ùˆ Ø±Ø´Ø¯ Ø¨Ø¯Ù‡\n"
        "ðŸ“Š /size â€” Ø¯ÛŒØ¯Ù† Ø§Ù†Ø¯Ø§Ø²Ù‡ØŒ Ø§Ø³Ù¾Ø±Ù… Ùˆ Ø¨Ø¯Ù‡ÛŒØª\n"
        "ðŸ† /top â€” Ù„ÛŒØ¯Ø±Ø¨Ø±Ø¯ Ø¨Ø²Ø±Ú¯â€ŒØªØ±ÛŒÙ†â€ŒÙ‡Ø§ÛŒ Ú¯Ø±ÙˆÙ‡\n"
        "ðŸ’³ /loan â€” Ú¯Ø±ÙØªÙ† ÙˆØ§Ù… (Ø¨Ø§ Ø¨Ù‡Ø±Ù‡)\n"
        "ðŸ’µ /repay [Ù…Ù‚Ø¯Ø§Ø±] â€” Ù¾Ø±Ø¯Ø§Ø®Øª ÙˆØ§Ù…\n"
        "ðŸ§¬ /tosperm [Ù…Ù‚Ø¯Ø§Ø± Ø³Ø§Ù†Øª] â€” ØªØ¨Ø¯ÛŒÙ„ Ø³Ø§Ù†Øª Ø¨Ù‡ Ø§Ø³Ù¾Ø±Ù… (Ù†Ø±Ø® Û± Ø¨Ù‡ Û²)\n"
        "ðŸ’° /tocent [Ù…Ù‚Ø¯Ø§Ø± Ø§Ø³Ù¾Ø±Ù…] â€” ØªØ¨Ø¯ÛŒÙ„ Ø§Ø³Ù¾Ø±Ù… Ø¨Ù‡ Ø³Ø§Ù†Øª"
    ),
    "pvp": (
        "âš”ï¸ Ø¯ÙˆØ¦Ù„ Ùˆ Ø±Ù†Ú©",
        "âš”ï¸ /pvp [Ù…Ø¨Ù„Øº Ø´Ø±Ø·] â€” Ú†Ø§Ù„Ø´ Ø¯Ø§Ø¯Ù† Ø¨Ù‡ ÛŒÙ‡ Ù†ÙØ± Ø¨Ø±Ø§ÛŒ Ø¯ÙˆØ¦Ù„ Û± Ø¨Ù‡ Û±\n"
        "ðŸ… /rank â€” Ø¯ÛŒØ¯Ù† Ø±Ù†Ú©ØŒ Ø§Ù…ØªÛŒØ§Ø² (RP) Ùˆ Ù¾ÛŒØ´Ø±ÙØª Ø±ÙˆØ²Ø§Ù†Ù‡â€ŒØª\n"
        "ðŸ† /ranktop â€” Ù„ÛŒØ¯Ø±Ø¨Ø±Ø¯ Ø±Ù†Ú© Ú¯Ø±ÙˆÙ‡\n"
        "\nÙ†Ú©ØªÙ‡: Ø´Ø§Ù†Ø³ Ø¨Ø±Ø¯Øª ØªÙˆ Ø¯ÙˆØ¦Ù„ Ø«Ø§Ø¨Øª Ù†ÛŒØ³Øª â€” Ø§Ú¯Ù‡ Ø²ÛŒØ§Ø¯ÛŒ Ø¨Ø±Ø¯Ù‡ Ø¨Ø§Ø´ÛŒ Ø´Ø§Ù†Ø³Øª Ú©Ù… Ù…ÛŒâ€ŒØ´Ù‡ØŒ Ø§Ú¯Ù‡ Ø²ÛŒØ§Ø¯ÛŒ Ø¨Ø§Ø®ØªÙ‡ Ø¨Ø§Ø´ÛŒ Ø´Ø§Ù†Ø³Øª Ø²ÛŒØ§Ø¯ Ù…ÛŒâ€ŒØ´Ù‡ ØªØ§ Ø¹Ø§Ø¯Ù„Ø§Ù†Ù‡ Ø¨Ù…ÙˆÙ†Ù‡."
    ),
    "mafia": (
        "ðŸ”« Ù…Ø§ÙÛŒØ§",
        "ðŸ”« /mafia [Ù…Ø¨Ù„Øº Ø´Ø±Ø·] â€” Ø³Ø§Ø®ØªÙ† ÛŒÙ‡ Ù†Ø¨Ø±Ø¯ Ù…Ø§ÙÛŒØ§ÛŒ ØªÛŒÙ…ÛŒ (Ø¨Ø¯ÙˆÙ† Ù…Ø­Ø¯ÙˆØ¯ÛŒØª Ù†ÙØ±Ø§Øª)\n"
        "ðŸ•µï¸ /mafia2 [Ù…Ø¨Ù„Øº Ø´Ø±Ø·] â€” Ù†Ø³Ø®Ù‡â€ŒÛŒ Ù…Ø®ÙÛŒØ§Ù†Ù‡â€ŒÛŒ Ù…Ø§ÙÛŒØ§ (ØªÛŒÙ…â€ŒÙ‡Ø§ Ù„Ùˆ Ù†Ù…ÛŒâ€ŒØ±Ù†)\n\n"
        "Ø¨Ù‚ÛŒÙ‡ Ø¨Ø§ Ø²Ø¯Ù† Ø¯Ú©Ù…Ù‡â€ŒÛŒ Ø¯Ø§Ø®Ù„ Ù¾ÛŒØ§Ù… Ø¨Ù‡ ÛŒÙ‡ ØªÛŒÙ… Ù…Ù„Ø­Ù‚ Ù…ÛŒâ€ŒØ´Ù†ØŒ Ø¨Ø¹Ø¯ Ø³Ø§Ø²Ù†Ø¯Ù‡ ÛŒØ§ Ø­Ø±ÛŒÙ Ø¨Ø§ Â«Ø´Ø±ÙˆØ¹ Ù†Ø¨Ø±Ø¯Â» Ø¨Ø§Ø²ÛŒ Ø±Ùˆ ØªÙ…ÙˆÙ… Ù…ÛŒâ€ŒÚ©Ù†Ù‡. ØªÛŒÙ… Ø¨Ø²Ø±Ú¯â€ŒØªØ± Ù…ÛŒâ€ŒØ¨Ø±Ù‡ Ùˆ Ø¬Ø§ÛŒØ²Ù‡ Ø¨ÛŒÙ† Ø¨Ø±Ù†Ø¯Ù‡â€ŒÙ‡Ø§ ØªÙ‚Ø³ÛŒÙ… Ù…ÛŒâ€ŒØ´Ù‡."
    ),
    "celeb": (
        "ðŸŒŸ Ø³Ù„Ø¨Ø±ÛŒØªÛŒâ€ŒÙ‡Ø§",
        "ðŸŽ° /spin [ØªÛŒØ±: S/A/B/PH] â€” Ø§Ø³Ù¾ÛŒÙ† Ú¯Ø±ÙØªÙ† ÛŒÙ‡ Ø³Ù„Ø¨Ø±ÛŒØªÛŒ Ø±Ù†Ø¯ÙˆÙ… Ø§Ø² ÛŒÙ‡ ØªÛŒØ±\n"
        "ðŸª /market â€” Ø¯ÛŒØ¯Ù† Ø³Ù„Ø¨Ø±ÛŒØªÛŒâ€ŒÙ‡Ø§ÛŒ Ù‚Ø§Ø¨Ù„â€ŒØ®Ø±ÛŒØ¯\n"
        "ðŸ›’ /buy [Ø§Ø³Ù…] â€” Ø®Ø±ÛŒØ¯ Ù…Ø³ØªÙ‚ÛŒÙ… ÛŒÙ‡ Ø³Ù„Ø¨Ø±ÛŒØªÛŒ Ø§Ø² Ù…Ø§Ø±Ú©Øª\n"
        "ðŸ“ /collection â€” Ø¯ÛŒØ¯Ù† Ú©Ù„Ú©Ø³ÛŒÙˆÙ† Ø®ÙˆØ¯Øª\n"
        "ðŸ“œ /list â€” Ù„ÛŒØ³Øª Ú©Ø±Ø¯Ù† ÛŒÙ‡ Ø³Ù„Ø¨Ø±ÛŒØªÛŒ Ø¨Ø±Ø§ÛŒ ÙØ±ÙˆØ´ Ø¨Ù‡ Ø¨Ù‚ÛŒÙ‡\n"
        "ðŸ’¸ /sell [Ø§Ø³Ù…] â€” ÙØ±ÙˆØ´ ÛŒÙ‡ Ø³Ù„Ø¨Ø±ÛŒØªÛŒ\n"
        "ðŸ”’ /lock [Ø§Ø³Ù…] â€” Ù‚ÙÙ„ Ú©Ø±Ø¯Ù† ÛŒÙ‡ Ø³Ù„Ø¨Ø±ÛŒØªÛŒ Ø¯Ø± Ø¨Ø±Ø§Ø¨Ø± ÙØ±ÙˆØ´ Ø®ÙˆØ¯Ú©Ø§Ø± (Ù‡Ø²ÛŒÙ†Ù‡ Ø¨Ø± Ø§Ø³Ø§Ø³ ØªÛŒØ±Ø´ ÙØ±Ù‚ Ø¯Ø§Ø±Ù‡)\n"
        "ðŸ… /collectors â€” Ú©ÛŒ Ø¨ÛŒØ´ØªØ±ÛŒÙ† Ø³Ù„Ø¨Ø±ÛŒØªÛŒ Ø±Ùˆ Ø¯Ø§Ø±Ù‡\n"
        "ðŸ’³ /gloan â€” ÙˆØ§Ù… Ù…Ø®ØµÙˆØµ Ø®Ø±ÛŒØ¯ Ø³Ù„Ø¨Ø±ÛŒØªÛŒ\n"
        "ðŸ’µ /gpay [Ù…Ù‚Ø¯Ø§Ø±] â€” Ù¾Ø±Ø¯Ø§Ø®Øª Ø§ÙˆÙ† ÙˆØ§Ù…"
    ),
    "bourse": (
        "ðŸ“ˆ Ø¨ÙˆØ±Ø³",
        "ðŸ“ˆ /copen â€” Ø¨Ø§Ø² Ú©Ø±Ø¯Ù† ÛŒÙ‡ Ø¨Ø§Ø²Ø§Ø± Ø¨ÙˆØ±Ø³ Ø¬Ø¯ÛŒØ¯ (Ø§Ø¯Ù…ÛŒÙ†ØŒ Ù…ÛŒâ€ŒØ´Ù‡ Ú†Ù†Ø¯ØªØ§ Ø±Ùˆ Ù‡Ù…Ø²Ù…Ø§Ù† Ø¨Ø§Ø² Ø¯Ø§Ø´Øª)\n"
        "ðŸ§¬ /invest â€” Ø³Ø±Ù…Ø§ÛŒÙ‡â€ŒÚ¯Ø°Ø§Ø±ÛŒ Ù…Ø®ÙÛŒØ§Ù†Ù‡ Ø±ÙˆÛŒ ÛŒÙ‡ Ø´Ø±Ú©Øª (Ø¨Ø§ Ø§Ø³Ù¾Ø±Ù…ØŒ Ø§Ø² Ø·Ø±ÛŒÙ‚ Ù¾ÛŒÙˆÛŒØ› Ø§Ú¯Ù‡ Ú†Ù†Ø¯ØªØ§ Ø¨Ø§Ø²Ø§Ø± Ù‡Ù…Ø²Ù…Ø§Ù† Ø¨Ø§Ø² Ø¨Ø§Ø´Ù‡ Ø§ÙˆÙ„ Ø§Ù†ØªØ®Ø§Ø¨ Ù…ÛŒâ€ŒÚ©Ù†ÛŒ Ú©Ø¯ÙˆÙ…)\n"
        "ðŸ“‰ /cclose [Ø´Ù…Ø§Ø±Ù‡ Ø¨Ø§Ø²Ø§Ø±] â€” Ø¨Ø³ØªÙ† ÛŒÙ‡ Ø¨Ø§Ø²Ø§Ø± Ø®Ø§Øµ Ùˆ Ø§Ø¹Ù„Ø§Ù… Ø¨Ø±Ù†Ø¯Ù‡â€ŒÙ‡Ø§ (Ø§Ø¯Ù…ÛŒÙ†Ø› Ø§Ú¯Ù‡ ÙÙ‚Ø· ÛŒÚ©ÛŒ Ø¨Ø§Ø² Ø¨Ø§Ø´Ù‡ Ù†ÛŒØ§Ø²ÛŒ Ø¨Ù‡ Ø´Ù…Ø§Ø±Ù‡ Ù†ÛŒØ³Øª)\n"
        "ðŸ¢ /mycompanies â€” Ø´Ø±Ú©Øªâ€ŒÙ‡Ø§ÛŒÛŒ Ú©Ù‡ Ø¨Ø±Ø¯ÛŒ\n"
        "ðŸ“Š /bourseleader â€” Ø¬Ø¯ÙˆÙ„ Ø±Ù†Ú© Ø¨ÙˆØ±Ø³ Ú¯Ø±ÙˆÙ‡ (Ø§Ø±Ø²Ø´ Ø®Ø§Ù„ØµØŒ ØªØ¹Ø¯Ø§Ø¯ Ø´Ø±Ú©ØªØŒ Ø¨Ø±Ø¯Ù‡Ø§ØŒ Ø³ÙˆØ¯ Ø±ÙˆØ²Ø§Ù†Ù‡)\n"
        "ðŸ•µï¸ /useyar â€” ÙØ±Ø³ØªØ§Ø¯Ù† ÛŒÙ‡ ÛŒØ§Ø± (Ú©Ø§Ø±Ú¯Ø±) Ø§Ø² Ø´Ø±Ú©ØªØª Ø¨Ù‡ ÛŒÙ‡ Ù†Ø¨Ø±Ø¯ Ù…Ø§ÙÛŒØ§ÛŒ ÙØ¹Ù„ÛŒØª\n"
        "ðŸ’° /cashout [Ø´Ù…Ø§Ø±Ù‡ Ø´Ø±Ú©Øª] â€” Ù†Ù‚Ø¯ Ú©Ø±Ø¯Ù† Ù†ØµÙ Ø§Ø±Ø²Ø´ ÛŒÙ‡ Ø´Ø±Ú©Øª Ø¨Ù‡ Ø§Ø³Ù¾Ø±Ù…\n\n"
        "Ø¨ÙˆØ±Ø³ Ø¨Ø§ Â«Ø§Ø³Ù¾Ø±Ù…Â» Ú©Ø§Ø± Ù…ÛŒâ€ŒÚ©Ù†Ù‡ØŒ Ù†Ù‡ Ø³Ø§Ù†Øª â€” Ø§ÙˆÙ„ Ø¨Ø§ /tosperm Ø³Ø§Ù†ØªØª Ø±Ùˆ ØªØ¨Ø¯ÛŒÙ„ Ú©Ù†."
    ),
    "farm": (
        "ðŸŒ¾ Ù…Ø²Ø±Ø¹Ù‡â€ŒÛŒ Ø§Ø³Ù¾Ø±Ù…",
        "ðŸŒ¾ /farm â€” Ø¨Ø§Ø² Ú©Ø±Ø¯Ù† Ù¾Ù†Ù„ Ù…Ø²Ø±Ø¹Ù‡ (ÛŒÙ‡ Ú¯Ø±ÛŒØ¯ Ø§Ø² Ø²Ù…ÛŒÙ†â€ŒÙ‡Ø§Øª Ø¨Ø§ Ø¯Ú©Ù…Ù‡)\n\n"
        "âž• Ø²Ù…ÛŒÙ† Ø®Ø§Ù„ÛŒ â†’ Ø¨Ø²Ù† Ø±ÙˆØ´ ØªØ§ ØªØ®Ù…ÛŒ Ú©Ù‡ ØªÙˆ Ø§Ù†Ø¨Ø§Ø±Øª Ø¯Ø§Ø±ÛŒ Ø±Ùˆ Ø¨Ú©Ø§Ø±ÛŒ\n"
        "â³ Ø¯Ø± Ø­Ø§Ù„ Ø±Ø´Ø¯ â†’ Ø¨Ø²Ù† Ø±ÙˆØ´ ØªØ§ Ø¨Ø¨ÛŒÙ†ÛŒ Ú†Ù‚Ø¯Ø± Ù…ÙˆÙ†Ø¯Ù‡\n"
        "âœ… Ø¢Ù…Ø§Ø¯Ù‡â€ŒÛŒ Ø¨Ø±Ø¯Ø§Ø´Øª â†’ Ø¨Ø²Ù† Ø±ÙˆØ´ ØªØ§ Ø§Ø³Ù¾Ø±Ù… Ø¨Ú¯ÛŒØ±ÛŒ\n"
        "ðŸ’€ ÙØ§Ø³Ø¯Ø´Ø¯Ù‡ â†’ Ø§Ú¯Ù‡ Ø¯ÛŒØ± Ø¨Ø¬Ù†Ø¨ÛŒ Ù†ØµÙ Ø§Ø±Ø²Ø´Ø´ Ø±Ùˆ Ù…ÛŒâ€ŒÚ¯ÛŒØ±ÛŒ\n\n"
        "Ø§Ø² Ù‡Ù…ÙˆÙ† Ù¾Ù†Ù„ Ù…ÛŒâ€ŒØªÙˆÙ†ÛŒ Ø²Ù…ÛŒÙ† Ø¬Ø¯ÛŒØ¯ Ø¨Ø§Ø² Ú©Ù†ÛŒØŒ ÛŒÙ‡ ØªØ®Ù… ØªÚ©ÛŒ Ø´Ø§Ù†Ø³ÛŒ Ø¨Ø®Ø±ÛŒ (Û· Ø³Ø§Ù†Øª)ØŒ ÛŒØ§ ÛŒÙ‡ Ù¾Ú© Û³ØªØ§ÛŒÛŒ Ø¨Ø®Ø±ÛŒ (Û´Û° Ø³Ø§Ù†Øª). Ø±Ù†Ú¯â€ŒÙ‡Ø§ÛŒ Ø§Ø±Ø²ÙˆÙ† (âšªðŸŸ¢) Ø´Ø§Ù†Ø³ Ø¯Ø§Ø±Ù† Ù…ÙˆÙ‚Ø¹ Ø¨Ø±Ø¯Ø§Ø´Øª ÛŒÙ‡ ØªØ®Ù… Ø¯ÛŒÚ¯Ù‡ Ø§Ø² Ø®ÙˆØ¯Ø´ÙˆÙ† Ø¨Ù†Ø¯Ø§Ø²Ù†Ø› Ø¨Ù‚ÛŒÙ‡ (ðŸ”·ðŸ”µðŸŸªðŸŸ£ðŸŸ¡) Ù‡ÛŒÚ†â€ŒÙˆÙ‚Øª ØªÚ©Ø±Ø§Ø± Ù†Ù…ÛŒâ€ŒØ´Ù† ÙˆÙ„ÛŒ Ø³ÙˆØ¯Ø´ÙˆÙ† Ø¨ÛŒØ´ØªØ±Ù‡ â€” Ù‡Ø±Ú†ÛŒ Ú©Ù…ÛŒØ§Ø¨â€ŒØªØ±ØŒ Ø¯ÛŒØ±ØªØ± Ù…ÛŒâ€ŒØ±Ø³Ù‡ ÙˆÙ„ÛŒ Ø³ÙˆØ¯Ø´ Ù†Ø§Ù…ØªÙ†Ø§Ø³Ø¨ Ø¨ÛŒØ´ØªØ±Ù‡.\n\n"
        "ðŸŒ¾ /farmrank â€” Ø±Ù†Ú© Ù…Ø²Ø±Ø¹Ù‡â€ŒÛŒ Ø®ÙˆØ¯ØªØŒ Ø¨Ø± Ø§Ø³Ø§Ø³ Ø¯Ù‚ÛŒÙ‚Ø§Ù‹ Ú†ÛŒØ²ÛŒ Ú©Ù‡ Ø§Ù„Ø§Ù† ØªÙˆ Ø²Ù…ÛŒÙ†â€ŒÙ‡Ø§ Ùˆ Ø§Ù†Ø¨Ø§Ø±ØªÙ‡\n"
        "ðŸ“Š /farmleader â€” Ø¬Ø¯ÙˆÙ„ Ø±Ù†Ú© Ù…Ø²Ø±Ø¹Ù‡â€ŒÛŒ Ú©Ù„ Ú¯Ø±ÙˆÙ‡"
    ),
    "auction": (
        "ðŸ”¨ Ù…Ø²Ø§ÛŒØ¯Ù‡",
        "ðŸ”¨ /bid [Ù…Ø¨Ù„Øº] â€” Ù¾ÛŒØ´Ù†Ù‡Ø§Ø¯ Ø¯Ø§Ø¯Ù† (Ø§Ú¯Ù‡ Ú†Ù†Ø¯ØªØ§ Ù…Ø²Ø§ÛŒØ¯Ù‡ Ù‡Ù…Ø²Ù…Ø§Ù† ÙØ¹Ø§Ù„Ù‡: /bid [Ø´Ù…Ø§Ø±Ù‡] [Ù…Ø¨Ù„Øº] ÛŒØ§ Ø±ÛŒÙ¾Ù„Ø§ÛŒ Ø±ÙˆÛŒ Ø¹Ú©Ø³ Ù‡Ù…ÙˆÙ† Ù…Ø²Ø§ÛŒØ¯Ù‡)\n"
        "ðŸ“‹ /auctionstatus â€” Ø¯ÛŒØ¯Ù† Ù‡Ù…Ù‡â€ŒÛŒ Ù…Ø²Ø§ÛŒØ¯Ù‡â€ŒÙ‡Ø§ÛŒ ÙØ¹Ø§Ù„ØŒ Ø¨Ø§Ù„Ø§ØªØ±ÛŒÙ† Ù¾ÛŒØ´Ù†Ù‡Ø§Ø¯Ù‡Ø§ Ùˆ Ø²Ù…Ø§Ù† Ø¨Ø§Ù‚ÛŒâ€ŒÙ…ÙˆÙ†Ø¯Ù‡\n"
        "ðŸ—‚ï¸ /myauctions â€” Ú©Ø§Ù„Ú©Ø´Ù† Ù…Ø²Ø§ÛŒØ¯Ù‡â€ŒÛŒ Ø®ÙˆØ¯Øª: Ù¾ÛŒØ´Ù†Ù‡Ø§Ø¯Ù‡Ø§ÛŒ Ø¨Ø§Ù„Ø§ÛŒ ÙØ¹Ù„ÛŒØŒ Ø³Ø§Ù†Øª Ø¨Ù„ÙˆÚ©Ù‡â€ŒØ´Ø¯Ù‡ Ùˆ Ø¨Ø§Ù‚ÛŒâ€ŒÙ…ÙˆÙ†Ø¯Ù‡ØŒ Ùˆ Ù‡Ù…Ù‡â€ŒÛŒ Ù…Ø²Ø§ÛŒØ¯Ù‡â€ŒÙ‡Ø§ÛŒÛŒ Ú©Ù‡ ØªØ§ Ø­Ø§Ù„Ø§ Ø¨Ø±Ø¯ÛŒ (Ø¨Ø±Ø§ÛŒ Ø¯ÛŒØ¯Ù† Ù…Ø§Ù„ ÛŒÚ©ÛŒ Ø¯ÛŒÚ¯Ù‡ Ø±ÙˆÛŒ Ù¾ÛŒØ§Ù…Ø´ Ø±ÛŒÙ¾Ù„Ø§ÛŒ Ú©Ù†)\n\n"
        "Ø³Ø§Ù†Øª Ù¾ÛŒØ´Ù†Ù‡Ø§Ø¯Øª Ù‡Ù…ÙˆÙ† Ù„Ø­Ø¸Ù‡ Ø¨Ù„ÙˆÚ©Ù‡ Ù…ÛŒâ€ŒØ´Ù‡ Ùˆ Ø§Ú¯Ù‡ Ú©Ø³ÛŒ Ø¨Ø§Ù„Ø§ØªØ± Ø¨Ø¯Ù‡ Ø¨Ø±Ù…ÛŒâ€ŒÚ¯Ø±Ø¯Ù‡. Ù‡Ø± Ù¾ÛŒØ´Ù†Ù‡Ø§Ø¯ Ø¬Ø¯ÛŒØ¯ ØªØ§ÛŒÙ…Ø± Û±Û² Ø³Ø§Ø¹ØªÙ‡â€ŒÛŒ Ù‡Ù…ÙˆÙ† Ù…Ø²Ø§ÛŒØ¯Ù‡ Ø±Ùˆ Ø§Ø² Ø§ÙˆÙ„ Ù…ÛŒâ€ŒÚ©Ù†Ù‡Ø› Ù‡Ø±Ú©Ø³ Û±Û² Ø³Ø§Ø¹Øª Ø¨Ø¯ÙˆÙ† Ù¾ÛŒØ´Ù†Ù‡Ø§Ø¯ Ø¨Ø§Ù„Ø§ØªØ± Ø¨Ù…ÙˆÙ†Ù‡ Ø¨Ø±Ù†Ø¯Ù‡â€ŒØ³Øª.\n\n"
        "Ø§Ø¯Ù…ÛŒÙ†:\n"
        "ðŸ”¨ /auction [file_id] [Ø§Ø³Ù…] â€” Ø´Ø±ÙˆØ¹ ÛŒÙ‡ Ù…Ø²Ø§ÛŒØ¯Ù‡â€ŒÛŒ Ø¬Ø¯ÛŒØ¯ (ÛŒØ§ Ø±ÛŒÙ¾Ù„Ø§ÛŒ Ø±Ùˆ ÛŒÙ‡ Ø¹Ú©Ø³: /auction [Ø§Ø³Ù…])Ø› Ù‡Ø±Ú†Ù†Ø¯ØªØ§ Ú©Ù‡ Ø¨Ø®ÙˆØ§ÛŒ Ù‡Ù…Ø²Ù…Ø§Ù†\n"
        "ðŸ /endauction [Ø´Ù…Ø§Ø±Ù‡] â€” Ù¾Ø§ÛŒØ§Ù† Ø²ÙˆØ¯ØªØ± ÛŒÙ‡ Ù…Ø²Ø§ÛŒØ¯Ù‡Ø› Ø¨Ø§ /endauction [Ø´Ù…Ø§Ø±Ù‡] cancel Ù„ØºÙˆ Ù…ÛŒâ€ŒØ´Ù‡ Ùˆ Ù¾ÙˆÙ„ Ø¨Ø±Ù…ÛŒâ€ŒÚ¯Ø±Ø¯Ù‡"
    ),
}

@dp.message(Command("help"))
async def help_cmd(m: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="ðŸ’° Ø§Ù‚ØªØµØ§Ø¯ Ù¾Ø§ÛŒÙ‡", callback_data="help:econ")],
        [InlineKeyboardButton(text="âš”ï¸ Ø¯ÙˆØ¦Ù„ Ùˆ Ø±Ù†Ú©", callback_data="help:pvp")],
        [InlineKeyboardButton(text="ðŸ”« Ù…Ø§ÙÛŒØ§", callback_data="help:mafia")],
        [InlineKeyboardButton(text="ðŸŒŸ Ø³Ù„Ø¨Ø±ÛŒØªÛŒâ€ŒÙ‡Ø§", callback_data="help:celeb")],
        [InlineKeyboardButton(text="ðŸ“ˆ Ø¨ÙˆØ±Ø³", callback_data="help:bourse")],
        [InlineKeyboardButton(text="ðŸŒ¾ Ù…Ø²Ø±Ø¹Ù‡", callback_data="help:farm")],
        [InlineKeyboardButton(text="ðŸ”¨ Ù…Ø²Ø§ÛŒØ¯Ù‡", callback_data="help:auction")],
    ])
    await m.reply(
        "ðŸ“– Ø±Ø§Ù‡Ù†Ù…Ø§ÛŒ Ø¨Ø§Ø²ÛŒ\n\n"
        "ÛŒÙ‡ Ø¨Ø®Ø´ Ø±Ùˆ Ø§Ù†ØªØ®Ø§Ø¨ Ú©Ù† ØªØ§ Ú©Ø§Ù…Ù†Ø¯Ù‡Ø§Ø´ Ø±Ùˆ Ø¨Ø¨ÛŒÙ†ÛŒ:",
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith("help:"))
async def help_section(q: CallbackQuery):
    key = q.data.split(":")[1]
    main_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="ðŸ’° Ø§Ù‚ØªØµØ§Ø¯ Ù¾Ø§ÛŒÙ‡", callback_data="help:econ")],
        [InlineKeyboardButton(text="âš”ï¸ Ø¯ÙˆØ¦Ù„ Ùˆ Ø±Ù†Ú©", callback_data="help:pvp")],
        [InlineKeyboardButton(text="ðŸ”« Ù…Ø§ÙÛŒØ§", callback_data="help:mafia")],
        [InlineKeyboardButton(text="ðŸŒŸ Ø³Ù„Ø¨Ø±ÛŒØªÛŒâ€ŒÙ‡Ø§", callback_data="help:celeb")],
        [InlineKeyboardButton(text="ðŸ“ˆ Ø¨ÙˆØ±Ø³", callback_data="help:bourse")],
        [InlineKeyboardButton(text="ðŸŒ¾ Ù…Ø²Ø±Ø¹Ù‡", callback_data="help:farm")],
        [InlineKeyboardButton(text="ðŸ”¨ Ù…Ø²Ø§ÛŒØ¯Ù‡", callback_data="help:auction")],
    ])
    if key == "back" or key not in HELP_SECTIONS:
        await q.message.edit_text("ðŸ“– Ø±Ø§Ù‡Ù†Ù…Ø§ÛŒ Ø¨Ø§Ø²ÛŒ\n\nÛŒÙ‡ Ø¨Ø®Ø´ Ø±Ùˆ Ø§Ù†ØªØ®Ø§Ø¨ Ú©Ù† ØªØ§ Ú©Ø§Ù…Ù†Ø¯Ù‡Ø§Ø´ Ø±Ùˆ Ø¨Ø¨ÛŒÙ†ÛŒ:", reply_markup=main_kb)
        return await q.answer()
    title, body = HELP_SECTIONS[key]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="â¬…ï¸ Ø¨Ø±Ú¯Ø´Øª Ø¨Ù‡ ÙÙ‡Ø±Ø³Øª", callback_data="help:back")]
    ])
    await q.message.edit_text(f"{title}\n\n{body}", reply_markup=kb)
    await q.answer()

# Ù†Ú¯Ù‡Ø¯Ø§Ø±ÛŒ Ù…ÙˆÙ‚Øª Ø³Ø±Ù…Ø§ÛŒÙ‡â€ŒÚ¯Ø°Ø§Ø±ÛŒâ€ŒÙ‡Ø§ÛŒÛŒ Ú©Ù‡ Ú©Ø§Ø±Ø¨Ø± ØªÙˆÛŒ Ú¯Ø±ÙˆÙ‡ Ø¯Ú©Ù…Ù‡â€ŒØ´ Ø±Ùˆ Ø²Ø¯Ù‡ ÙˆÙ„ÛŒ Ù‡Ù†ÙˆØ² Ù…Ø¨Ù„Øº Ø±Ùˆ ØªÙˆÛŒ Ù¾ÛŒÙˆÛŒ Ù†ÙØ±Ø³ØªØ§Ø¯Ù‡
pending_invest = {}  # user_id -> {"chat_id":..., "round_id":..., "slot":..., "ts":...}
PENDING_INVEST_TTL = 10 * 60  # Ø¨Ø¹Ø¯ Ø§Ø² Û±Û° Ø¯Ù‚ÛŒÙ‚Ù‡ Ù…Ù†Ù‚Ø¶ÛŒ Ù…ÛŒâ€ŒØ´Ù‡

@dp.message(Command("grow"))
async def grow(m:Message):
    user(m.chat.id,m.from_user.id,m.from_user.full_name)
    size,last=c.execute("SELECT size,last_grow FROM users WHERE chat_id=? AND user_id=?",(m.chat.id,m.from_user.id)).fetchone()
    now=int(time.time())
    if now-last<COOLDOWN:
        rem=(COOLDOWN-(now-last))//60
        return await m.reply(f"â³ Ù‡Ù†ÙˆØ² {rem} Ø¯Ù‚ÛŒÙ‚Ù‡ ØªØ§ Ø±Ø´Ø¯ Ø¨Ø¹Ø¯ÛŒ Ù…ÙˆÙ†Ø¯Ù‡!")
    delta=random.randint(5,20)
    size=max(0,size+delta)
    c.execute("UPDATE users SET size=?,last_grow=? WHERE chat_id=? AND user_id=?",(size,now,m.chat.id,m.from_user.id)); db.commit()
    await m.reply(
        f"ðŸŒ± Ù†ØªÛŒØ¬Ù‡ Ø±Ø´Ø¯\n\nðŸ† ØªØºÛŒÛŒØ±: {delta:+} Ø³Ø§Ù†Øª\nðŸ“ Ø§Ù†Ø¯Ø§Ø²Ù‡ ÙØ¹Ù„ÛŒ: {size} Ø³Ø§Ù†Øª\nðŸ˜Ž Ø§Ø¯Ø§Ù…Ù‡ Ø¨Ø¯Ù‡ Ù‚Ù‡Ø±Ù…Ø§Ù†!"
    )

@dp.message(Command("size"))
async def size(m:Message):
    user(m.chat.id,m.from_user.id,m.from_user.full_name)
    s,sp,d=c.execute("SELECT size,sperm,debt FROM users WHERE chat_id=? AND user_id=?",(m.chat.id,m.from_user.id)).fetchone()
    await m.reply(
        f"ðŸ“Š Ù¾Ø±ÙˆÙØ§ÛŒÙ„ Ø´Ù…Ø§\n\nðŸ† Ø§Ù†Ø¯Ø§Ø²Ù‡: {s} Ø³Ø§Ù†Øª\nðŸ§¬ Ø§Ø³Ù¾Ø±Ù… (Ø¨ÙˆØ±Ø³): {sp}\nðŸ’¸ Ø¨Ø¯Ù‡ÛŒ: {d} Ø³Ø§Ù†Øª"
    )

@dp.message(Command("tosperm"))
async def to_sperm(m:Message):
    try:
        amount=int(m.text.split()[1])
    except:
        return await m.reply(f"Ø§Ø³ØªÙØ§Ø¯Ù‡: /tosperm [Ù…Ù‚Ø¯Ø§Ø± Ø³Ø§Ù†Øª]\nÙ†Ø±Ø®: Ù‡Ø± Û± Ø³Ø§Ù†Øª = {SPERM_RATE} Ø§Ø³Ù¾Ø±Ù…")
    if amount<=0:
        return await m.reply("âŒ Ù…Ù‚Ø¯Ø§Ø± Ø¨Ø§ÛŒØ¯ Ù…Ø«Ø¨Øª Ø¨Ø§Ø´Ù‡.")
    user(m.chat.id,m.from_user.id,m.from_user.full_name)
    if get_size(m.chat.id,m.from_user.id)<amount:
        return await m.reply("âŒ Ø³Ø§Ù†Øª Ú©Ø§ÙÛŒ Ù†Ø¯Ø§Ø±ÛŒ.")
    gained=amount*SPERM_RATE
    c.execute("UPDATE users SET size=size-?,sperm=sperm+? WHERE chat_id=? AND user_id=?",(amount,gained,m.chat.id,m.from_user.id))
    db.commit()
    await m.reply(f"ðŸ§¬ {amount} Ø³Ø§Ù†Øª ØªØ¨Ø¯ÛŒÙ„ Ø´Ø¯ Ø¨Ù‡ {gained} Ø§Ø³Ù¾Ø±Ù…!")

@dp.message(Command("tocent"))
async def to_cent(m:Message):
    try:
        amount=int(m.text.split()[1])
    except:
        return await m.reply(f"Ø§Ø³ØªÙØ§Ø¯Ù‡: /tocent [Ù…Ù‚Ø¯Ø§Ø± Ø§Ø³Ù¾Ø±Ù…]\nÙ†Ø±Ø®: Ù‡Ø± {SPERM_RATE} Ø§Ø³Ù¾Ø±Ù… = Û± Ø³Ø§Ù†Øª")
    if amount<=0:
        return await m.reply("âŒ Ù…Ù‚Ø¯Ø§Ø± Ø¨Ø§ÛŒØ¯ Ù…Ø«Ø¨Øª Ø¨Ø§Ø´Ù‡.")
    user(m.chat.id,m.from_user.id,m.from_user.full_name)
    if get_sperm(m.chat.id,m.from_user.id)<amount:
        return await m.reply("âŒ Ø§Ø³Ù¾Ø±Ù… Ú©Ø§ÙÛŒ Ù†Ø¯Ø§Ø±ÛŒ.")
    gained=amount//SPERM_RATE
    if gained<=0:
        return await m.reply(f"âŒ Ø­Ø¯Ø§Ù‚Ù„ {SPERM_RATE} Ø§Ø³Ù¾Ø±Ù… Ù„Ø§Ø²Ù…Ù‡ ØªØ§ Û± Ø³Ø§Ù†Øª Ø¨Ú¯ÛŒØ±ÛŒ.")
    used=gained*SPERM_RATE
    c.execute("UPDATE users SET sperm=sperm-?,size=size+? WHERE chat_id=? AND user_id=?",(used,gained,m.chat.id,m.from_user.id))
    db.commit()
    await m.reply(f"ðŸ’° {used} Ø§Ø³Ù¾Ø±Ù… ØªØ¨Ø¯ÛŒÙ„ Ø´Ø¯ Ø¨Ù‡ {gained} Ø³Ø§Ù†Øª!")

# ===== Ù…Ø²Ø±Ø¹Ù‡â€ŒÛŒ Ø§Ø³Ù¾Ø±Ù… =====
EGGS = {
    "white":  {"emoji": "âšª", "name": "ØªØ®Ù… Ø´Ù„",         "chance": 45, "time": 30*60,   "min": 5,   "max": 10,  "replicate": 30},
    "green":  {"emoji": "ðŸŸ¢", "name": "ØªØ®Ù… Ø¢Ø¨Ø¯Ø§Ø±",      "chance": 20, "time": 2*3600,  "min": 20,  "max": 35,  "replicate": 15},
    "cyan":   {"emoji": "ðŸ”·", "name": "ØªØ®Ù… ÙÛŒØ±ÙˆØ²Ù‡â€ŒØ§ÛŒ",   "chance": 15, "time": 4*3600,  "min": 40,  "max": 60,  "replicate": 0},
    "blue":   {"emoji": "ðŸ”µ", "name": "ØªØ®Ù… Ù¾Ø±Ù‚Ø¯Ø±Øª",     "chance": 10, "time": 6*3600,  "min": 60,  "max": 100, "replicate": 0},
    "indigo": {"emoji": "ðŸŸª", "name": "ØªØ®Ù… Ø³Ø±Ù…Ù‡â€ŒØ§ÛŒ",     "chance": 6,  "time": 9*3600,  "min": 100, "max": 150, "replicate": 0},
    "purple": {"emoji": "ðŸŸ£", "name": "ØªØ®Ù… Ø±Ø¹Ø¯Ø¢Ø³Ø§",     "chance": 3,  "time": 12*3600, "min": 150, "max": 250, "replicate": 0},
    "gold":   {"emoji": "ðŸŸ¡", "name": "ØªØ®Ù… Ø§ÛŒÙ„Ø§Ù† Ù…Ø§Ø³Ú©", "chance": 1,  "time": 24*3600, "min": 500, "max": 800, "replicate": 0},
}
EGG_SURPRISE_CHANCE = 0.02   # Ø´Ø§Ù†Ø³ Ø§ÛŒÙ†Ú©Ù‡ ÛŒÙ‡ ØªØ®Ù… Ø§Ø±Ø²ÙˆÙ† Ø¯Ø± ÙˆØ§Ù‚Ø¹ Ø·Ù„Ø§ÛŒÛŒ Ù…Ø®ÙÛŒ Ø¯Ø±Ø¨ÛŒØ§Ø¯
FARM_SPOIL_MULTIPLIER = 2    # Ø¨Ø¹Ø¯ Ø§ÛŒÙ†â€ŒÙ‚Ø¯Ø± Ø¨Ø±Ø§Ø¨Ø± Ø²Ù…Ø§Ù† Ø§ØµÙ„ÛŒØŒ ØªØ®Ù… ÙØ§Ø³Ø¯ Ù…ÛŒØ´Ù‡ Ùˆ Ù†ØµÙ Ø§Ø±Ø²Ø´ Ù…ÛŒØ¯Ù‡
FARM_PAGE_SIZE = 9           # Ù‡Ø± ØµÙØ­Ù‡ Ø§Ø² Ù¾Ù†Ù„ Ú†Ù†Ø¯ØªØ§ Ø®ÙˆÙ†Ù‡ Ù†Ø´ÙˆÙ† Ø¨Ø¯Ù‡ (Û³ Ø¯Ø± Û³)
EGG_SINGLE_COST = 7          # Ù‡Ø²ÛŒÙ†Ù‡â€ŒÛŒ ÛŒÙ‡ ØªØ®Ù… ØªÚ©ÛŒ Ø´Ø§Ù†Ø³ÛŒ
EGG_PACK_COST = 40           # Ù‡Ø²ÛŒÙ†Ù‡â€ŒÛŒ Ù‡Ø± Ù¾Ú© (Û³ ØªØ®Ù… Ø´Ø§Ù†Ø³ÛŒ)
EGG_PACK_SIZE = 3
PLOT_BASE_COST = 20          # Ù‡Ø²ÛŒÙ†Ù‡â€ŒÛŒ Ø¨Ø§Ø² Ú©Ø±Ø¯Ù† Ø§ÙˆÙ„ÛŒÙ† Ø²Ù…ÛŒÙ†â€ŒÙ‡Ø§ÛŒ Ø§Ø¶Ø§ÙÙ‡Ø› Ù‡Ø±Ú†ÛŒ Ø¨ÛŒØ´ØªØ± Ø¯Ø§Ø´ØªÙ‡ Ø¨Ø§Ø´ÛŒ Ú¯Ø±ÙˆÙ†â€ŒØªØ± Ù…ÛŒØ´Ù‡

def roll_egg():
    names = list(EGGS.keys())
    weights = [EGGS[n]["chance"] for n in names]
    egg = random.choices(names, weights=weights, k=1)[0]
    if egg in ("white", "green") and random.random() < EGG_SURPRISE_CHANCE:
        return "gold", True
    return egg, False

def add_egg_to_inventory(chat_id, uid, egg_type, qty=1):
    c.execute(
        "INSERT INTO farm_inventory(chat_id,user_id,egg_type,count) VALUES(?,?,?,?) "
        "ON CONFLICT(chat_id,user_id,egg_type) DO UPDATE SET count=count+excluded.count",
        (chat_id, uid, egg_type, qty)
    )

def get_inventory(chat_id, uid):
    rows = c.execute("SELECT egg_type,count FROM farm_inventory WHERE chat_id=? AND user_id=? AND count>0", (chat_id, uid)).fetchall()
    return {t: n for t, n in rows}

def bump_farm_record(chat_id, uid, **deltas):
    cols = ("eggs_bought", "eggs_planted", "eggs_harvested", "total_harvest_value", "plots_opened", "spent_cm")
    c.execute(
        f"INSERT INTO farm_records(chat_id,user_id,{','.join(cols)}) VALUES(?,?,{','.join(['0']*len(cols))}) "
        "ON CONFLICT(chat_id,user_id) DO NOTHING",
        (chat_id, uid)
    )
    for col, val in deltas.items():
        if val:
            c.execute(f"UPDATE farm_records SET {col}={col}+? WHERE chat_id=? AND user_id=?", (val, chat_id, uid))

def get_farm_record(chat_id, uid):
    row = c.execute(
        "SELECT eggs_bought,eggs_planted,eggs_harvested,total_harvest_value,plots_opened,spent_cm "
        "FROM farm_records WHERE chat_id=? AND user_id=?", (chat_id, uid)
    ).fetchone()
    if not row:
        return {"eggs_bought": 0, "eggs_planted": 0, "eggs_harvested": 0, "total_harvest_value": 0, "plots_opened": 0, "spent_cm": 0}
    keys = ("eggs_bought", "eggs_planted", "eggs_harvested", "total_harvest_value", "plots_opened", "spent_cm")
    return dict(zip(keys, row))

def plot_unlock_cost(owned):
    return PLOT_BASE_COST + 15 * max(0, owned - 2)

def tile_state(egg_type, planted_at):
    """Ø¨Ø±Ù…ÛŒâ€ŒÚ¯Ø±Ø¯ÙˆÙ†Ù‡: ('growing'|'ready'|'spoiled', Ø«Ø§Ù†ÛŒÙ‡â€ŒÛŒ Ø¨Ø§Ù‚ÛŒâ€ŒÙ…ÙˆÙ†Ø¯Ù‡ ÛŒØ§ Ú¯Ø°Ø´ØªÙ‡)"""
    info = EGGS[egg_type]
    elapsed = int(time.time()) - planted_at
    if elapsed < info["time"]:
        return "growing", info["time"] - elapsed
    if elapsed < info["time"] * FARM_SPOIL_MULTIPLIER:
        return "ready", elapsed - info["time"]
    return "spoiled", elapsed - info["time"] * FARM_SPOIL_MULTIPLIER

def fmt_time(seconds):
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    mnt, _ = divmod(rem, 60)
    if h:
        return f"{h}:{mnt:02d}h"
    return f"{mnt}m"

def build_farm_keyboard(chat_id, uid, page):
    owned = c.execute("SELECT farm_plots FROM users WHERE chat_id=? AND user_id=?", (chat_id, uid)).fetchone()
    owned = owned[0] if owned else 2
    tiles = {n: (e, p) for n, e, p in c.execute(
        "SELECT plot_num,egg_type,planted_at FROM farm_tiles WHERE chat_id=? AND user_id=?", (chat_id, uid)
    ).fetchall()}
    total_pages = max(1, (owned + FARM_PAGE_SIZE - 1) // FARM_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * FARM_PAGE_SIZE
    rows = []
    row = []
    for i in range(start, start + FARM_PAGE_SIZE):
        if i >= owned:
            row.append(InlineKeyboardButton(text="ðŸ”’", callback_data="farm:noop"))
        elif i in tiles:
            egg_type, planted_at = tiles[i]
            state, _ = tile_state(egg_type, planted_at)
            emoji = EGGS[egg_type]["emoji"]
            label = {"growing": f"{emoji}â³", "ready": f"âœ…{emoji}", "spoiled": f"ðŸ’€{emoji}"}[state]
            row.append(InlineKeyboardButton(text=label, callback_data=f"farm:tile:{page}:{i}"))
        else:
            row.append(InlineKeyboardButton(text="âž•", callback_data=f"farm:tile:{page}:{i}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="â—€ï¸", callback_data=f"farm:page:{page-1}"))
    nav.append(InlineKeyboardButton(text=f"ðŸ“„ {page+1}/{total_pages}", callback_data="farm:noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="â–¶ï¸", callback_data=f"farm:page:{page+1}"))
    rows.append(nav)
    rows.append([InlineKeyboardButton(text=f"âž• Ø¨Ø§Ø² Ú©Ø±Ø¯Ù† Ø²Ù…ÛŒÙ† Ø¬Ø¯ÛŒØ¯ ({plot_unlock_cost(owned)} Ø³Ø§Ù†Øª)", callback_data=f"farm:unlock:{page}")])
    rows.append([InlineKeyboardButton(text=f"ðŸ¥š ÛŒÙ‡ ØªØ®Ù… ØªÚ©ÛŒ ({EGG_SINGLE_COST} Ø³Ø§Ù†Øª)", callback_data=f"farm:buyegg:{page}")])
    rows.append([InlineKeyboardButton(text=f"ðŸ“¦ Ù¾Ú© Û³ØªØ§ÛŒÛŒ ({EGG_PACK_COST} Ø³Ø§Ù†Øª)", callback_data=f"farm:buypack:{page}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def build_farm_text(chat_id, uid):
    inv = get_inventory(chat_id, uid)
    inv_txt = "ØŒ ".join(f"{EGGS[t]['emoji']}Ã—{n}" for t, n in inv.items()) if inv else "Ø®Ø§Ù„ÛŒÙ‡"
    return f"ðŸŒ¾ Ù…Ø²Ø±Ø¹Ù‡â€ŒÛŒ Ø§Ø³Ù¾Ø±Ù…\n\nðŸ“¦ Ø§Ù†Ø¨Ø§Ø± ØªØ®Ù…: {inv_txt}\n\nâž• Ø²Ù…ÛŒÙ† Ø®Ø§Ù„ÛŒ | â³ Ø¯Ø± Ø­Ø§Ù„ Ø±Ø´Ø¯ | âœ… Ø¢Ù…Ø§Ø¯Ù‡â€ŒÛŒ Ø¨Ø±Ø¯Ø§Ø´Øª | ðŸ’€ ÙØ§Ø³Ø¯Ø´Ø¯Ù‡ (Ù†ØµÙ Ø§Ø±Ø²Ø´)"

@dp.message(Command("farm"))
async def farm_cmd(m: Message):
    user(m.chat.id, m.from_user.id, m.from_user.full_name)
    await m.reply(build_farm_text(m.chat.id, m.from_user.id), reply_markup=build_farm_keyboard(m.chat.id, m.from_user.id, 0))

@dp.callback_query(F.data == "farm:noop")
async def farm_noop(q: CallbackQuery):
    await q.answer()

@dp.callback_query(F.data.startswith("farm:page:"))
async def farm_page(q: CallbackQuery):
    page = int(q.data.split(":")[2])
    await q.message.edit_text(build_farm_text(q.message.chat.id, q.from_user.id), reply_markup=build_farm_keyboard(q.message.chat.id, q.from_user.id, page))
    await q.answer()

@dp.callback_query(F.data.startswith("farm:unlock:"))
async def farm_unlock(q: CallbackQuery):
    page = int(q.data.split(":")[2])
    chat_id, uid = q.message.chat.id, q.from_user.id
    user(chat_id, uid, q.from_user.full_name)
    owned = c.execute("SELECT farm_plots FROM users WHERE chat_id=? AND user_id=?", (chat_id, uid)).fetchone()[0]
    cost = plot_unlock_cost(owned)
    if get_size(chat_id, uid) < cost:
        return await q.answer(f"âŒ {cost} Ø³Ø§Ù†Øª Ù„Ø§Ø²Ù… Ø¯Ø§Ø±ÛŒ!", show_alert=True)
    c.execute("UPDATE users SET size=size-?, farm_plots=farm_plots+1 WHERE chat_id=? AND user_id=?", (cost, chat_id, uid))
    bump_farm_record(chat_id, uid, plots_opened=1, spent_cm=cost)
    db.commit()
    await q.answer("âœ… ÛŒÙ‡ Ø²Ù…ÛŒÙ† Ø¬Ø¯ÛŒØ¯ Ø¨Ø§Ø² Ø´Ø¯!")
    await q.message.edit_text(build_farm_text(chat_id, uid), reply_markup=build_farm_keyboard(chat_id, uid, page))

@dp.callback_query(F.data.startswith("farm:buyegg:"))
async def farm_buyegg(q: CallbackQuery):
    page = int(q.data.split(":")[2])
    chat_id, uid = q.message.chat.id, q.from_user.id
    user(chat_id, uid, q.from_user.full_name)
    if get_size(chat_id, uid) < EGG_SINGLE_COST:
        return await q.answer(f"âŒ {EGG_SINGLE_COST} Ø³Ø§Ù†Øª Ù„Ø§Ø²Ù… Ø¯Ø§Ø±ÛŒ!", show_alert=True)
    c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?", (EGG_SINGLE_COST, chat_id, uid))
    egg, surprise = roll_egg()
    add_egg_to_inventory(chat_id, uid, egg, 1)
    bump_farm_record(chat_id, uid, eggs_bought=1, spent_cm=EGG_SINGLE_COST)
    db.commit()
    alert = f"ðŸ¥š Ú¯Ø±ÙØªÛŒ: {EGGS[egg]['emoji']} {EGGS[egg]['name']}!"
    if surprise:
        alert = "ðŸŽ‰ðŸŽ‰ Ú†ÛŒØŸ! Ø§ÛŒÙ† ÛŒÚ©ÛŒ Ø§ØµÙ„Ø§Ù‹ Ù…Ø¹Ù…ÙˆÙ„ÛŒ Ù†Ø¨ÙˆØ¯!\n\n" + alert
    await q.answer(alert, show_alert=True)
    await q.message.edit_text(build_farm_text(chat_id, uid), reply_markup=build_farm_keyboard(chat_id, uid, page))

@dp.callback_query(F.data.startswith("farm:buypack:"))
async def farm_buypack(q: CallbackQuery):
    page = int(q.data.split(":")[2])
    chat_id, uid = q.message.chat.id, q.from_user.id
    user(chat_id, uid, q.from_user.full_name)
    if get_size(chat_id, uid) < EGG_PACK_COST:
        return await q.answer(f"âŒ {EGG_PACK_COST} Ø³Ø§Ù†Øª Ù„Ø§Ø²Ù… Ø¯Ø§Ø±ÛŒ!", show_alert=True)
    c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?", (EGG_PACK_COST, chat_id, uid))
    results = []
    surprise = False
    for _ in range(EGG_PACK_SIZE):
        egg, was_surprise = roll_egg()
        add_egg_to_inventory(chat_id, uid, egg, 1)
        results.append(egg)
        surprise = surprise or was_surprise
    bump_farm_record(chat_id, uid, eggs_bought=EGG_PACK_SIZE, spent_cm=EGG_PACK_COST)
    db.commit()
    lines = "\n".join(f"{EGGS[e]['emoji']} {EGGS[e]['name']}" for e in results)
    alert = "ðŸŽ‰ Ù¾Ú© Ø¨Ø§Ø² Ø´Ø¯:\n" + lines
    if surprise:
        alert = "ðŸŽ‰ðŸŽ‰ Ú†ÛŒØŸ! ÛŒÚ©ÛŒØ´ÙˆÙ† Ø§ØµÙ„Ø§Ù‹ Ù…Ø¹Ù…ÙˆÙ„ÛŒ Ù†Ø¨ÙˆØ¯!\n\n" + alert
    await q.answer(alert, show_alert=True)
    await q.message.edit_text(build_farm_text(chat_id, uid), reply_markup=build_farm_keyboard(chat_id, uid, page))

@dp.callback_query(F.data.startswith("farm:tile:"))
async def farm_tile(q: CallbackQuery):
    _, _, page, num = q.data.split(":")
    page, num = int(page), int(num)
    chat_id, uid = q.message.chat.id, q.from_user.id
    user(chat_id, uid, q.from_user.full_name)
    tile = c.execute("SELECT egg_type,planted_at FROM farm_tiles WHERE chat_id=? AND user_id=? AND plot_num=?", (chat_id, uid, num)).fetchone()
    if tile:
        egg_type, planted_at = tile
        state, delta = tile_state(egg_type, planted_at)
        info = EGGS[egg_type]
        if state == "growing":
            return await q.answer(f"{info['emoji']} {info['name']} â€” {fmt_time(delta)} Ù…ÙˆÙ†Ø¯Ù‡", show_alert=True)
        gained = random.randint(info["min"], info["max"])
        if state == "spoiled":
            gained //= 2
        c.execute("UPDATE users SET sperm=sperm+? WHERE chat_id=? AND user_id=?", (gained, chat_id, uid))
        c.execute("DELETE FROM farm_tiles WHERE chat_id=? AND user_id=? AND plot_num=?", (chat_id, uid, num))
        bump_farm_record(chat_id, uid, eggs_harvested=1, total_harvest_value=gained)
        msg = f"{'ðŸ’€ ÙØ§Ø³Ø¯ Ø´Ø¯Ù‡ Ø¨ÙˆØ¯ ÙˆÙ„ÛŒ Ø¨Ø§Ø²Ù… Ú†ÛŒØ²ÛŒ Ú¯ÛŒØ±Øª Ø§ÙˆÙ…Ø¯!' if state=='spoiled' else 'âœ… Ø¨Ø±Ø¯Ø§Ø´Øª Ø´Ø¯!'}\n{info['emoji']} {info['name']}: +{gained} Ø§Ø³Ù¾Ø±Ù…"
        if info["replicate"] and random.randint(1, 100) <= info["replicate"]:
            add_egg_to_inventory(chat_id, uid, egg_type, 1)
            msg += f"\nðŸ€ ÛŒÙ‡ {info['emoji']} {info['name']} Ø¯ÛŒÚ¯Ù‡ Ù‡Ù… Ø§ÙØªØ§Ø¯ ØªÙˆ Ø§Ù†Ø¨Ø§Ø±Øª!"
        db.commit()
        await q.answer(msg, show_alert=True)
        return await q.message.edit_text(build_farm_text(chat_id, uid), reply_markup=build_farm_keyboard(chat_id, uid, page))
    # Ø²Ù…ÛŒÙ† Ø®Ø§Ù„ÛŒÙ‡ â€” Ù†Ø´ÙˆÙ† Ø¨Ø¯Ù‡ Ú†ÛŒ ØªÙˆ Ø§Ù†Ø¨Ø§Ø± Ø¯Ø§Ø±Ù‡ Ú©Ù‡ Ø¨Ú©Ø§Ø±Ù‡
    inv = get_inventory(chat_id, uid)
    if not inv:
        return await q.answer("ðŸ“­ Ø§Ù†Ø¨Ø§Ø±Øª Ø®Ø§Ù„ÛŒÙ‡! Ø§ÙˆÙ„ ÛŒÙ‡ Ù¾Ú© ØªØ®Ù… Ø¨Ø®Ø±.", show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{EGGS[t]['emoji']} {EGGS[t]['name']} ({n} ØªØ§)", callback_data=f"farm:plant:{page}:{num}:{t}")]
        for t, n in inv.items()
    ] + [[InlineKeyboardButton(text="â¬…ï¸ Ø¨Ø±Ú¯Ø´Øª", callback_data=f"farm:page:{page}")]])
    await q.message.edit_text(f"ðŸŒ± Ú©Ø¯ÙˆÙ… ØªØ®Ù… Ø±Ùˆ ØªÙˆ Ø§ÛŒÙ† Ø²Ù…ÛŒÙ† Ø¨Ú©Ø§Ø±ÛŒØŸ", reply_markup=kb)
    await q.answer()

@dp.callback_query(F.data.startswith("farm:plant:"))
async def farm_plant(q: CallbackQuery):
    _, _, page, num, egg_type = q.data.split(":")
    page, num = int(page), int(num)
    chat_id, uid = q.message.chat.id, q.from_user.id
    row = c.execute("SELECT count FROM farm_inventory WHERE chat_id=? AND user_id=? AND egg_type=?", (chat_id, uid, egg_type)).fetchone()
    if not row or row[0] <= 0:
        return await q.answer("âŒ Ø¯ÛŒÚ¯Ù‡ Ø§Ø² Ø§ÛŒÙ† Ù†Ø¯Ø§Ø±ÛŒ!", show_alert=True)
    c.execute("UPDATE farm_inventory SET count=count-1 WHERE chat_id=? AND user_id=? AND egg_type=?", (chat_id, uid, egg_type))
    c.execute("INSERT INTO farm_tiles(chat_id,user_id,plot_num,egg_type,planted_at) VALUES(?,?,?,?,?)", (chat_id, uid, num, egg_type, int(time.time())))
    bump_farm_record(chat_id, uid, eggs_planted=1)
    db.commit()
    await q.answer(f"ðŸŒ± {EGGS[egg_type]['name']} Ú©Ø§Ø´ØªÙ‡ Ø´Ø¯!")
    await q.message.edit_text(build_farm_text(chat_id, uid), reply_markup=build_farm_keyboard(chat_id, uid, page))

# ===== Ø±Ù†Ú© Ù…Ø²Ø±Ø¹Ù‡ Ø¨Ø± Ø§Ø³Ø§Ø³ ÙˆØ¶Ø¹ÛŒØª ÙØ¹Ù„ÛŒ Ù¾Ù†Ù„ =====
FARM_RANK_TIERS = [
    (0,    "ðŸŒ± Ù†ÙˆØ²Ù…ÛŒÙ†â€ŒØ¯Ø§Ø±"),
    (100,  "ðŸŒ¾ Ú©Ø´Ø§ÙˆØ±Ø²"),
    (300,  "ðŸšœ ØªØ±Ø§Ú©ØªÙˆØ±Ø¯Ø§Ø±"),
    (700,  "ðŸ­ ØµÙ†Ø¹ØªÛŒ"),
    (1500, "ðŸ‘‘ Ù¾Ø§Ø¯Ø´Ø§Ù‡ Ù…Ø²Ø±Ø¹Ù‡"),
]

def egg_avg_value(egg_type):
    info = EGGS[egg_type]
    return (info["min"] + info["max"]) / 2

def get_farm_tier(worth):
    tier = FARM_RANK_TIERS[0][1]
    for threshold, name in FARM_RANK_TIERS:
        if worth >= threshold:
            tier = name
    return tier

def compute_farm_stats(chat_id, uid):
    """Ù…Ø­Ø§Ø³Ø¨Ù‡â€ŒÛŒ Ø²Ù†Ø¯Ù‡â€ŒÛŒ ÙˆØ¶Ø¹ÛŒØª ÙØ¹Ù„ÛŒ Ù…Ø²Ø±Ø¹Ù‡: Ù‡Ø±Ú†ÛŒ Ø§Ù„Ø§Ù† ØªÙˆ Ø²Ù…ÛŒÙ†â€ŒÙ‡Ø§ Ùˆ Ø§Ù†Ø¨Ø§Ø± Ø¯Ø§Ø±Ù‡."""
    row = c.execute("SELECT farm_plots FROM users WHERE chat_id=? AND user_id=?", (chat_id, uid)).fetchone()
    plots_owned = row[0] if row else 2
    tiles = c.execute("SELECT egg_type,planted_at FROM farm_tiles WHERE chat_id=? AND user_id=?", (chat_id, uid)).fetchall()
    growing = ready = spoiled = 0
    tile_worth = 0.0
    for egg_type, planted_at in tiles:
        state, _ = tile_state(egg_type, planted_at)
        val = egg_avg_value(egg_type)
        if state == "growing":
            growing += 1
            tile_worth += val
        elif state == "ready":
            ready += 1
            tile_worth += val
        else:
            spoiled += 1
            tile_worth += val / 2
    inv = get_inventory(chat_id, uid)
    inv_count = sum(inv.values())
    inv_worth = sum(egg_avg_value(t) * n for t, n in inv.items())
    net_worth = round(tile_worth + inv_worth)
    return {
        "plots_owned": plots_owned, "growing": growing, "ready": ready, "spoiled": spoiled,
        "planted": len(tiles), "inv_count": inv_count, "net_worth": net_worth,
    }

@dp.message(Command("farmrank"))
async def farm_rank_cmd(m: Message):
    user(m.chat.id, m.from_user.id, m.from_user.full_name)
    st = compute_farm_stats(m.chat.id, m.from_user.id)
    rec = get_farm_record(m.chat.id, m.from_user.id)
    tier = get_farm_tier(st["net_worth"])
    await m.reply(
        f"ðŸŒ¾ Ø±Ù†Ú© Ù…Ø²Ø±Ø¹Ù‡â€ŒÛŒ Ø´Ù…Ø§\n\n"
        f"{tier}\n"
        f"ðŸ’° Ø§Ø±Ø²Ø´ Ø®Ø§Ù„Øµ ÙØ¹Ù„ÛŒ: {st['net_worth']} Ø§Ø³Ù¾Ø±Ù… (ØªØ®Ù…ÛŒÙ†ÛŒ)\n"
        f"ðŸŸ« Ø²Ù…ÛŒÙ†â€ŒÙ‡Ø§ÛŒ Ø¨Ø§Ø²: {st['plots_owned']}\n"
        f"ðŸŒ± Ú©Ø§Ø´ØªÙ‡â€ŒØ´Ø¯Ù‡ Ø§Ù„Ø§Ù†: {st['planted']} (â³{st['growing']} Ø¯Ø± Ø­Ø§Ù„ Ø±Ø´Ø¯ | âœ…{st['ready']} Ø¢Ù…Ø§Ø¯Ù‡ | ðŸ’€{st['spoiled']} ÙØ§Ø³Ø¯)\n"
        f"ðŸ“¦ ØªØ®Ù… ØªÙˆ Ø§Ù†Ø¨Ø§Ø±: {st['inv_count']}\n\n"
        f"ðŸ“œ Ø±Ú©ÙˆØ±Ø¯ Ú©Ù„ÛŒ (Ø§Ø² Ø§ÙˆÙ„ ØªØ§ Ø§Ù„Ø§Ù†):\n"
        f"ðŸ¥š ØªØ®Ù… Ø®Ø±ÛŒØ¯Ù‡: {rec['eggs_bought']}\n"
        f"ðŸŒ± ØªØ®Ù… Ú©Ø§Ø´ØªÙ‡: {rec['eggs_planted']}\n"
        f"ðŸŒ¾ ØªØ®Ù… Ø¨Ø±Ø¯Ø§Ø´Øªâ€ŒÚ©Ø±Ø¯Ù‡: {rec['eggs_harvested']}\n"
        f"ðŸ’° Ú©Ù„ Ø§Ø³Ù¾Ø±Ù… Ø¨Ù‡â€ŒØ¯Ø³Øªâ€ŒØ§ÙˆÙ…Ø¯Ù‡ Ø§Ø² Ø¨Ø±Ø¯Ø§Ø´Øª: {rec['total_harvest_value']}\n"
        f"ðŸŸ« Ú©Ù„ Ø²Ù…ÛŒÙ†â€ŒÙ‡Ø§ÛŒ Ø¨Ø§Ø²â€ŒØ´Ø¯Ù‡: {rec['plots_opened']}\n"
        f"ðŸ’¸ Ú©Ù„ Ø³Ø§Ù†Øª Ø®Ø±Ø¬â€ŒØ´Ø¯Ù‡ ØªÙˆ Ù…Ø²Ø±Ø¹Ù‡: {rec['spent_cm']}"
    )

@dp.message(Command("farmleader"))
async def farm_leaderboard(m: Message):
    chat_id = m.chat.id
    candidates = c.execute(
        "SELECT DISTINCT user_id FROM ("
        "  SELECT user_id FROM farm_tiles WHERE chat_id=?"
        "  UNION SELECT user_id FROM farm_inventory WHERE chat_id=? AND count>0"
        "  UNION SELECT user_id FROM users WHERE chat_id=? AND farm_plots>2"
        ")", (chat_id, chat_id, chat_id)
    ).fetchall()
    if not candidates:
        return await m.reply("ðŸ“­ Ù‡Ù†ÙˆØ² Ú©Ø³ÛŒ ØªÙˆ Ø§ÛŒÙ† Ú¯Ø±ÙˆÙ‡ Ù…Ø²Ø±Ø¹Ù‡ Ø±Ø§Ù‡ Ù†Ù†Ø¯Ø§Ø®ØªÙ‡!")
    board = []
    for (uid,) in candidates:
        st = compute_farm_stats(chat_id, uid)
        board.append((uid, st))
    board.sort(key=lambda x: x[1]["net_worth"], reverse=True)
    txt = "ðŸ“Š Ø¬Ø¯ÙˆÙ„ Ø±Ù†Ú© Ù…Ø²Ø±Ø¹Ù‡â€ŒÛŒ Ø§ÛŒÙ† Ú¯Ø±ÙˆÙ‡\n\n"
    for i, (uid, st) in enumerate(board[:10], 1):
        name = get_name(chat_id, uid)
        rec = get_farm_record(chat_id, uid)
        tier = get_farm_tier(st["net_worth"])
        txt += (
            f"{i}. {name}\n"
            f"   {tier}\n"
            f"   ðŸ’° Ø§Ø±Ø²Ø´ Ø§Ù„Ø§Ù†: {st['net_worth']} Ø§Ø³Ù¾Ø±Ù… | ðŸŸ« Ø²Ù…ÛŒÙ†: {st['plots_owned']} | "
            f"ðŸŒ± Ú©Ø§Ø´ØªÙ‡: {st['planted']} (âœ…{st['ready']}/â³{st['growing']}/ðŸ’€{st['spoiled']}) | ðŸ“¦ Ø§Ù†Ø¨Ø§Ø±: {st['inv_count']}\n"
            f"   ðŸ“œ Ø±Ú©ÙˆØ±Ø¯: {rec['eggs_harvested']} Ø¨Ø±Ø¯Ø§Ø´Øª | {rec['total_harvest_value']} Ø§Ø³Ù¾Ø±Ù… Ú©Ù„ | {rec['plots_opened']} Ø²Ù…ÛŒÙ† Ø¨Ø§Ø²â€ŒØ´Ø¯Ù‡\n\n"
        )
    await m.reply(txt)

@dp.message(Command("loan"))
async def loan(m:Message):
    try:
        amt=int(m.text.split()[1])
    except:
        return await m.reply("Reply to a user and use /loan 5")

    if not m.reply_to_message:
        return await m.reply("Reply to a user and use /loan 5")

    lender=m.from_user.id
    borrower=m.reply_to_message.from_user.id

    if lender==borrower:
        return await m.reply("You can't loan yourself.")

    user(m.chat.id,lender,m.from_user.full_name)
    user(m.chat.id,borrower,m.reply_to_message.from_user.full_name)

    s=get_size(m.chat.id,lender)

    if s<amt:
        return await m.reply("Not enough cm.")

    day_ago = int(time.time()) - 24*60*60
    borrowed_today = c.execute(
        "SELECT COALESCE(SUM(amount),0) FROM loans WHERE chat_id=? AND borrower_id=? AND loan_time>?",
        (m.chat.id, borrower, day_ago)
    ).fetchone()[0]

    if borrowed_today + amt > 50:
        remaining = max(0, 50 - borrowed_today)
        return await m.reply(
            f"âŒ Ø§ÛŒÙ† Ú©Ø§Ø±Ø¨Ø± Ø§Ù…Ø±ÙˆØ² {borrowed_today} Ø³Ø§Ù†Øª ÙˆØ§Ù… Ú¯Ø±ÙØªÙ‡!\n"
            f"Ø­Ø¯Ø§Ú©Ø«Ø± Ø±ÙˆØ²Ø§Ù†Ù‡ ÛµÛ° Ø³Ø§Ù†ØªÙ‡.\n"
            f"{'Ø¯ÛŒÚ¯Ù‡ Ù†Ù…ÛŒØªÙˆÙ†Ù‡ ÙˆØ§Ù… Ø¨Ú¯ÛŒØ±Ù‡!' if remaining == 0 else f'ÙÙ‚Ø· {remaining} Ø³Ø§Ù†Øª Ø¯ÛŒÚ¯Ù‡ Ù…ÛŒØªÙˆÙ†Ù‡ Ø¨Ú¯ÛŒØ±Ù‡.'}"
        )

    c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?",(amt,m.chat.id,lender))
    c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?",(amt,m.chat.id,borrower))
    c.execute("INSERT INTO loans(chat_id,lender_id,borrower_id,amount,loan_time) VALUES(?,?,?,?,?)",(m.chat.id,lender,borrower,amt,int(time.time())))
    db.commit()

    await m.reply(f"ðŸ’¸ ÙˆØ§Ù… Ø§Ù†Ø¬Ø§Ù… Ø´Ø¯!\n\nÙ…Ù‚Ø¯Ø§Ø±: {amt} Ø³Ø§Ù†Øª\nðŸ“Š Ø§ÛŒÙ† Ú©Ø§Ø±Ø¨Ø± Ø§Ù…Ø±ÙˆØ² {borrowed_today+amt}/50 Ø³Ø§Ù†Øª ÙˆØ§Ù… Ú¯Ø±ÙØªÙ‡")

@dp.message(Command("repay"))
async def repay(m:Message):
    try: amt=int(m.text.split()[1])
    except: return await m.reply("Usage: /repay 5")
    user(m.chat.id,m.from_user.id,m.from_user.full_name)
    s,d=c.execute("SELECT size,debt FROM users WHERE chat_id=? AND user_id=?",(m.chat.id,m.from_user.id)).fetchone()
    amt=min(amt,s,d)
    c.execute("UPDATE users SET size=?,debt=? WHERE chat_id=? AND user_id=?",(s-amt,d-amt,m.chat.id,m.from_user.id)); db.commit()
    await m.reply(f"âœ… Repaid {amt} cm")

@dp.message(Command("top"))
async def top(m:Message):
    rows=c.execute("SELECT name,size FROM users WHERE chat_id=? ORDER BY size DESC LIMIT 10",(m.chat.id,)).fetchall()
    txt="ðŸ† Ø¬Ø¯ÙˆÙ„ Ø¨Ø²Ø±Ú¯Ø§Ù†\n\n"
    for i,(n,s) in enumerate(rows,1): txt+=f"{i}. {n} â€” {s} Ø³Ø§Ù†Øª\n"
    await m.reply(txt)

PVP_MIN_GAMES = 3          # Ù‚Ø¨Ù„ Ø§Ø² Ø§ÛŒÙ† ØªØ¹Ø¯Ø§Ø¯ Ø¯ÙˆØ¦Ù„ØŒ Ø§ØµÙ„Ø§Ù‹ ØªØµØ­ÛŒØ­ Ø§Ù†Ø¬Ø§Ù… Ù†Ù…ÛŒâ€ŒØ´Ù‡ (Ø´Ø§Ù†Ø³ Ø®Ø§Ù… 50-50 Ù…ÛŒâ€ŒÙ…ÙˆÙ†Ù‡)
PVP_BALANCE_STRENGTH = 0.6 # Ù‡Ø±Ú†Ù‚Ø¯Ø± Ø¨ÛŒØ´ØªØ±ØŒ Ù…ÛŒÙ„ Ø¨Ù‡ 50Ùª Ù‚ÙˆÛŒâ€ŒØªØ±Ù‡ (0 = Ø¨ÛŒâ€ŒØ§Ø«Ø±ØŒ 1 = Ø®ÛŒÙ„ÛŒ Ù‚ÙˆÛŒ)
PVP_PROB_MIN = 0.25        # Ú©Ù Ø§Ø­ØªÙ…Ø§Ù„ Ø¨Ø±Ø¯ (Ù‡ÛŒÚ†â€ŒÙˆÙ‚Øª Ø´Ø§Ù†Ø³ Ú©Ø³ÛŒ Ø§Ø² Ø§ÛŒÙ† Ú©Ù…ØªØ± Ù†Ù…ÛŒâ€ŒØ´Ù‡)
PVP_PROB_MAX = 0.75        # Ø³Ù‚Ù Ø§Ø­ØªÙ…Ø§Ù„ Ø¨Ø±Ø¯ (Ù‡ÛŒÚ†â€ŒÙˆÙ‚Øª Ø´Ø§Ù†Ø³ Ú©Ø³ÛŒ Ø§Ø² Ø§ÛŒÙ† Ø¨ÛŒØ´ØªØ± Ù†Ù…ÛŒâ€ŒØ´Ù‡)

def get_pvp_winrate(chat_id, uid):
    row = c.execute("SELECT wins,losses FROM pvp_stats WHERE chat_id=? AND user_id=?", (chat_id, uid)).fetchone()
    if not row:
        return 0.5, 0
    wins, losses = row
    games = wins + losses
    if games < PVP_MIN_GAMES:
        return 0.5, games
    return wins / games, games

def bump_pvp_stats(chat_id, winner, loser):
    for uid, w, l in ((winner, 1, 0), (loser, 0, 1)):
        c.execute(
            "INSERT INTO pvp_stats(chat_id,user_id,wins,losses) VALUES(?,?,?,?) "
            "ON CONFLICT(chat_id,user_id) DO UPDATE SET wins=wins+excluded.wins, losses=losses+excluded.losses",
            (chat_id, uid, w, l)
        )

# ===== Ø³ÛŒØ³ØªÙ… Ø±Ù†Ú© =====
RANK_DAILY_QUOTA = 6          # Ø­Ø¯Ø§Ù‚Ù„ Ø¯ÙˆØ¦Ù„ Ù„Ø§Ø²Ù… Ø¯Ø± Ø±ÙˆØ² ØªØ§ Ø±Ù†Ú© Ù†Ø±ÛŒØ²Ù‡
RANK_WIN_RP = 20              # Ø§Ù…ØªÛŒØ§Ø² Ø±Ù†Ú© Ø¨Ø±Ø§ÛŒ Ø¨Ø±Ø¯
RANK_LOSS_RP = 10             # Ø§Ù…ØªÛŒØ§Ø² Ø±Ù†Ú© Ú©Ù…â€ŒØ´Ø¯Ù‡ Ø¨Ø±Ø§ÛŒ Ø¨Ø§Ø®Øª
RANK_DECAY_PER_MISSED_DAY = 15  # Ø±ÛŒØ²Ø´ Ø±Ù†Ú© Ø¨Ù‡â€ŒØ§Ø²Ø§ÛŒ Ù‡Ø± Ø±ÙˆØ²ÛŒ Ú©Ù‡ Ø­Ø¯Ù†ØµØ§Ø¨ Ø±Ø¹Ø§ÛŒØª Ù†Ø´Ø¯Ù‡
RANK_TIERS = [
    (0,    "ðŸ¥’ Ù†ÙˆÙ¾Ø§"),
    (100,  "ðŸŒ­ Ø¢Ù…Ø§ØªÙˆØ±"),
    (250,  "ðŸ† Ø­Ø±ÙÙ‡â€ŒØ§ÛŒ"),
    (500,  "ðŸš€ Ø§Ø³ØªØ§Ø¯"),
    (900,  "ðŸ‘‘ Ø§ÙØ³Ø§Ù†Ù‡â€ŒØ§ÛŒ"),
]

def today_str():
    return time.strftime("%Y-%m-%d", time.gmtime())

def get_rank_tier(rp):
    tier = RANK_TIERS[0][1]
    for threshold, name in RANK_TIERS:
        if rp >= threshold:
            tier = name
    return tier

def ensure_rank_row(chat_id, uid):
    row = c.execute("SELECT rp,duels_today,last_active_day FROM rank_stats WHERE chat_id=? AND user_id=?", (chat_id, uid)).fetchone()
    if not row:
        c.execute("INSERT INTO rank_stats(chat_id,user_id,rp,duels_today,last_active_day) VALUES(?,?,0,0,?)", (chat_id, uid, today_str()))
        db.commit()
        return 0, 0, today_str()
    return row

def apply_daily_decay(chat_id, uid):
    """Ø§Ú¯Ù‡ Ø§Ø² Ø¢Ø®Ø±ÛŒÙ† Ø¨Ø§Ø±ÛŒ Ú©Ù‡ Ø¯ÙˆØ¦Ù„ Ø²Ø¯Ù‡ Ø±ÙˆØ²(Ù‡Ø§) Ú¯Ø°Ø´ØªÙ‡ Ø¨Ø§Ø´Ù‡ Ùˆ Ø§ÙˆÙ† Ø±ÙˆØ²Ù‡Ø§ Ø­Ø¯Ù†ØµØ§Ø¨ Ø±Ø¹Ø§ÛŒØª Ù†Ø´Ø¯Ù‡ØŒ Ø±Ù†Ú© Ù…ÛŒâ€ŒØ±ÛŒØ²Ù‡."""
    rp, duels_today, last_day = ensure_rank_row(chat_id, uid)
    today = today_str()
    if last_day == today:
        return rp, duels_today
    try:
        gap = (
            time.mktime(time.strptime(today, "%Y-%m-%d")) -
            time.mktime(time.strptime(last_day, "%Y-%m-%d"))
        ) / 86400
        gap = int(round(gap))
    except Exception:
        gap = 1
    if gap < 1:
        gap = 1
    missed_days = gap if duels_today < RANK_DAILY_QUOTA else gap - 1
    if missed_days > 0:
        rp = max(0, rp - missed_days * RANK_DECAY_PER_MISSED_DAY)
    c.execute("UPDATE rank_stats SET rp=?,duels_today=0,last_active_day=? WHERE chat_id=? AND user_id=?", (rp, today, chat_id, uid))
    db.commit()
    return rp, 0

def record_rank_duel(chat_id, winner, loser):
    for uid, delta in ((winner, RANK_WIN_RP), (loser, -RANK_LOSS_RP)):
        rp, duels_today = apply_daily_decay(chat_id, uid)
        rp = max(0, rp + delta)
        duels_today += 1
        c.execute("UPDATE rank_stats SET rp=?,duels_today=? WHERE chat_id=? AND user_id=?", (rp, duels_today, chat_id, uid))
    db.commit()

@dp.message(Command("rank"))
async def rank_cmd(m: Message):
    user(m.chat.id, m.from_user.id, m.from_user.full_name)
    rp, duels_today = apply_daily_decay(m.chat.id, m.from_user.id)
    tier = get_rank_tier(rp)
    left = max(0, RANK_DAILY_QUOTA - duels_today)
    quota_txt = "âœ… Ø­Ø¯Ù†ØµØ§Ø¨ Ø§Ù…Ø±ÙˆØ² Ø±Ø¹Ø§ÛŒØª Ø´Ø¯Ù‡!" if left == 0 else f"âš ï¸ {left} Ø¯ÙˆØ¦Ù„ Ø¯ÛŒÚ¯Ù‡ Ù…ÙˆÙ†Ø¯Ù‡ ØªØ§ Ø±Ù†Ú©Øª ÙØ±Ø¯Ø§ Ù†Ø±ÛŒØ²Ù‡!"
    await m.reply(
        f"ðŸ… Ø±Ù†Ú© Ø´Ù…Ø§\n\n"
        f"{tier}\n"
        f"ðŸ“Š Ø§Ù…ØªÛŒØ§Ø²: {rp} RP\n"
        f"âš”ï¸ Ø¯ÙˆØ¦Ù„ Ø§Ù…Ø±ÙˆØ²: {duels_today}/{RANK_DAILY_QUOTA}\n\n"
        f"{quota_txt}"
    )

@dp.message(Command("ranktop"))
async def rank_top(m: Message):
    rows = c.execute(
        "SELECT user_id,rp FROM rank_stats WHERE chat_id=? ORDER BY rp DESC LIMIT 10", (m.chat.id,)
    ).fetchall()
    if not rows:
        return await m.reply("ðŸ“­ Ù‡Ù†ÙˆØ² Ú©Ø³ÛŒ ØªÙˆ Ø§ÛŒÙ† Ú¯Ø±ÙˆÙ‡ Ø¯ÙˆØ¦Ù„ Ù†Ø²Ø¯Ù‡!")
    txt = "ðŸ† Ø¨Ø±ØªØ±ÛŒÙ†â€ŒÙ‡Ø§ÛŒ Ø±Ù†Ú© Ø§ÛŒÙ† Ú¯Ø±ÙˆÙ‡\n\n"
    for i, (uid, rp) in enumerate(rows, 1):
        name = get_name(m.chat.id, uid)
        txt += f"{i}. {name} â€” {rp} RP ({get_rank_tier(rp)})\n"
    await m.reply(txt)

@dp.message(Command("pvp"))
async def pvp(m:Message):
    try: bet=int(m.text.split()[1])
    except: return await m.reply("Usage: /pvp 30")
    if bet<=0: return await m.reply("âŒ Ù…Ù‚Ø¯Ø§Ø± Ø´Ø±Ø· Ø¨Ø§ÛŒØ¯ Ø¹Ø¯Ø¯ Ù…Ø«Ø¨Øª Ø¨Ø§Ø´Ù‡!")
    user(m.chat.id,m.from_user.id,m.from_user.full_name)
    s=get_size(m.chat.id,m.from_user.id)
    if s<bet: return await m.reply("Not enough cm.")
    cur = c.execute(
        "INSERT INTO battles(creator,bet) VALUES(?,?)",
        (m.from_user.id, bet)
    )
    db.commit()
    bid=cur.lastrowid
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="âš”ï¸ Ù‚Ø¨ÙˆÙ„ Ø¯ÙˆØ¦Ù„",callback_data=f"pvp:{bid}")]])
    await m.reply(f"âš”ï¸ Ø¯ÙˆØ¦Ù„ Ù…Ø±Ú¯Ø¨Ø§Ø±!\n\nðŸ’° Ø´Ø±Ø·: {bet} Ø³Ø§Ù†Øª\n\nØ¨Ø±Ù†Ø¯Ù‡ Ù‡Ù…Ù‡ Ø±Ùˆ Ù…ÛŒâ€ŒØ¨Ø±Ù‡!",reply_markup=kb)

@dp.callback_query(F.data.startswith("pvp:"))
async def accept(q:CallbackQuery):
    bid=int(q.data.split(":")[1])
    row=c.execute("SELECT creator,bet,active FROM battles WHERE id=?",(bid,)).fetchone()
    if not row or row[2]==0: return await q.answer("Expired")
    creator,bet,_=row
    if q.from_user.id==creator: return await q.answer("Not yourself")
    chat_id=q.message.chat.id
    user(chat_id,q.from_user.id,q.from_user.full_name)
    s1=get_size(chat_id,creator)
    s2=get_size(chat_id,q.from_user.id)
    if s1<bet or s2<bet: return await q.answer("Not enough cm")
    opponent = q.from_user.id
    wr_creator, _ = get_pvp_winrate(chat_id, creator)
    wr_opponent, _ = get_pvp_winrate(chat_id, opponent)
    # Ù‡Ø±Ú©ÛŒ Ù†Ø±Ø® Ø¨Ø±Ø¯Ø´ Ø¨Ø§Ù„Ø§ØªØ± Ø§Ø² 50Ùª Ø¨Ø§Ø´Ù‡ Ø´Ø§Ù†Ø³Ø´ Ú©Ù… Ù…ÛŒâ€ŒØ´Ù‡ØŒ Ù‡Ø±Ú©ÛŒ Ù¾Ø§ÛŒÛŒÙ†â€ŒØªØ±Ù‡ Ø´Ø§Ù†Ø³Ø´ Ø²ÛŒØ§Ø¯ Ù…ÛŒâ€ŒØ´Ù‡
    p_creator = 0.5 + PVP_BALANCE_STRENGTH * (wr_opponent - wr_creator)
    p_creator = max(PVP_PROB_MIN, min(PVP_PROB_MAX, p_creator))
    winner = creator if random.random() < p_creator else opponent
    loser = opponent if winner == creator else creator
    bump_pvp_stats(chat_id, winner, loser)
    record_rank_duel(chat_id, winner, loser)
    c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?",(bet,chat_id,winner))
    c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?",(bet,chat_id,loser))
    c.execute("UPDATE battles SET active=0 WHERE id=?",(bid,))
    db.commit()
    winner_name=get_name(chat_id,winner)
    await q.message.edit_text(f"ðŸ† Ù¾Ø§ÛŒØ§Ù† Ø¯ÙˆØ¦Ù„!\n\nðŸ‘‘ Ø¨Ø±Ù†Ø¯Ù‡: {winner_name}\nðŸ’° Ø¬Ø§ÛŒØ²Ù‡: {bet} Ø³Ø§Ù†Øª\nðŸ… +{RANK_WIN_RP} RP Ø¨Ø±Ù†Ø¯Ù‡ | -{RANK_LOSS_RP} RP Ø¨Ø§Ø²Ù†Ø¯Ù‡\n\nðŸ˜‚ Ø¨Ø§Ø²Ù†Ø¯Ù‡ Ø¨Ø§ÛŒØ¯ Ø¨ÛŒØ´ØªØ± ØªÙ…Ø±ÛŒÙ† Ú©Ù†Ù‡!")


# ===== Mafia Team PvP System =====
c.execute("CREATE TABLE IF NOT EXISTS mafia_battles(id INTEGER PRIMARY KEY AUTOINCREMENT,creator INTEGER,opponent INTEGER,bet INTEGER,active INTEGER DEFAULT 1,chat_id INTEGER)")
c.execute("CREATE TABLE IF NOT EXISTS mafia_members(battle_id INTEGER,user_id INTEGER,name TEXT,team INTEGER)")
db.commit()

def mafia_counts(bid):
    t1=c.execute("SELECT COUNT(*) FROM mafia_members WHERE battle_id=? AND team=1",(bid,)).fetchone()[0]
    t2=c.execute("SELECT COUNT(*) FROM mafia_members WHERE battle_id=? AND team=2",(bid,)).fetchone()[0]
    return t1,t2

def mafia_board(bid,creator_name,opp_name,bet,status="ðŸ”« Ø¬Ù†Ú¯ Ù…Ø§ÙÛŒØ§ Ø´Ø±ÙˆØ¹ Ø´Ø¯!"):
    t1,t2=mafia_counts(bid)
    return (
        f"{status}\n\n"
        f"ðŸ”´ ØªÛŒÙ… {creator_name}  Ø¯Ø± Ù…Ù‚Ø§Ø¨Ù„  ðŸ”µ ØªÛŒÙ… {opp_name}\n"
        f"ðŸ’° ÙˆØ±ÙˆØ¯ÛŒ Ù‡Ø± Ù†ÙØ±: {bet} Ø³Ø§Ù†Øª\n\n"
        f"Ù‡Ø± Ú©ÛŒ Ù…ÛŒØ®ÙˆØ§Ø¯ ÙˆØ§Ø±Ø¯ Ø¨Ø´Ù‡ Ø¯Ú©Ù…Ù‡ ØªÛŒÙ…Ø´ Ø±Ùˆ Ø¨Ø²Ù†Ù‡ (Ù…Ø®ÙÛŒØ§Ù†Ù‡ Ø«Ø¨Øª Ù…ÛŒØ´Ù‡ØŒ ØªÛŒÙ…â€ŒØ¨Ù†Ø¯ÛŒ Ù…Ø¹Ù„ÙˆÙ… Ù†ÛŒØ³Øª)!\n"
        f"ðŸ‘¥ ØªØ¹Ø¯Ø§Ø¯ Ø´Ø±Ú©Øªâ€ŒÚ©Ù†Ù†Ø¯Ù‡â€ŒÙ‡Ø§: {t1+t2}\n\n"
        f"ÙˆÙ‚ØªÛŒ Ø¢Ù…Ø§Ø¯Ù‡ Ø¨ÙˆØ¯ÛŒØ¯ØŒ Ø³Ø§Ø²Ù†Ø¯Ù‡ ÛŒØ§ Ø­Ø±ÛŒÙ Ø¯Ú©Ù…Ù‡ Â«Ø´Ø±ÙˆØ¹ Ù†Ø¨Ø±Ø¯Â» Ø±Ùˆ Ø¨Ø²Ù†Ù‡."
    )

@dp.message(Command("mafia"))
async def mafia_start(m:Message):
    if not m.reply_to_message:
        return await m.reply("âš ï¸ Ø±ÙˆÛŒ Ù¾ÛŒØ§Ù… Ø­Ø±ÛŒÙ Ø±ÛŒÙ¾Ù„Ø§ÛŒ Ú©Ù† Ùˆ Ø¨Ù†ÙˆÛŒØ³ /mafia [Ù…Ø¨Ù„Øº]\nÙ…Ø«Ø§Ù„: /mafia 5")
    try:
        bet=int(m.text.split()[1])
    except:
        return await m.reply("âš ï¸ Ø§Ø³ØªÙØ§Ø¯Ù‡: /mafia [Ù…Ø¨Ù„Øº]\nÙ…Ø«Ø§Ù„: /mafia 5")
    if bet<=0:
        return await m.reply("âŒ Ù…Ø¨Ù„Øº Ø¨Ø§ÛŒØ¯ Ù…Ø«Ø¨Øª Ø¨Ø§Ø´Ù‡!")
    creator=m.from_user.id
    opponent=m.reply_to_message.from_user.id
    if creator==opponent:
        return await m.reply("âŒ Ù†Ù…ÛŒØªÙˆÙ†ÛŒ Ø¨Ø§ Ø®ÙˆØ¯Øª Ù…Ø§ÙÛŒØ§ Ø¨Ø§Ø²ÛŒ Ú©Ù†ÛŒ!")
    if m.reply_to_message.from_user.is_bot:
        return await m.reply("âŒ Ù†Ù…ÛŒØªÙˆÙ†ÛŒ Ø¨Ø§ Ø¨Ø§Øª Ù…Ø§ÙÛŒØ§ Ø¨Ø§Ø²ÛŒ Ú©Ù†ÛŒ!")
    user(m.chat.id,creator,m.from_user.full_name)
    user(m.chat.id,opponent,m.reply_to_message.from_user.full_name)
    s=get_size(m.chat.id,creator)
    if s<bet:
        return await m.reply("âŒ Ø³Ø§Ù†Øª Ú©Ø§ÙÛŒ Ù†Ø¯Ø§Ø±ÛŒ!")
    c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?",(bet,m.chat.id,creator))
    cur=c.execute("INSERT INTO mafia_battles(creator,opponent,bet,chat_id) VALUES(?,?,?,?)",(creator,opponent,bet,m.chat.id))
    db.commit()
    bid=cur.lastrowid
    c.execute("INSERT INTO mafia_members(battle_id,user_id,name,team) VALUES(?,?,?,1)",(bid,creator,m.from_user.full_name))
    db.commit()
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"ðŸ”´ ØªÛŒÙ… {m.from_user.full_name}",callback_data=f"mjoin:{bid}:1"),
         InlineKeyboardButton(text=f"ðŸ”µ ØªÛŒÙ… {m.reply_to_message.from_user.full_name}",callback_data=f"mjoin:{bid}:2")],
        [InlineKeyboardButton(text="ðŸ Ø´Ø±ÙˆØ¹ Ù†Ø¨Ø±Ø¯ Ùˆ Ø´Ù…Ø§Ø±Ø´",callback_data=f"mstart:{bid}")]
    ])
    await m.reply(
        mafia_board(bid,m.from_user.full_name,m.reply_to_message.from_user.full_name,bet),
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith("mjoin:"))
async def mafia_join(q:CallbackQuery):
    try:
        _,bid,team=q.data.split(":")
        bid=int(bid); team=int(team)
        row=c.execute("SELECT creator,opponent,bet,active,chat_id FROM mafia_battles WHERE id=?",(bid,)).fetchone()
        if not row or row[3]==0:
            return await q.answer("âš ï¸ Ø§ÛŒÙ† Ù†Ø¨Ø±Ø¯ ØªÙ…ÙˆÙ… Ø´Ø¯Ù‡!",show_alert=True)
        creator,opponent,bet,_,chat_id=row
        uid=q.from_user.id
        already=c.execute("SELECT team FROM mafia_members WHERE battle_id=? AND user_id=?",(bid,uid)).fetchone()
        if already:
            return await q.answer("âš ï¸ Ù‚Ø¨Ù„Ø§Ù‹ Ù…Ø®ÙÛŒØ§Ù†Ù‡ ÙˆØ§Ø±Ø¯ ÛŒÙ‡ ØªÛŒÙ… Ø´Ø¯ÛŒ!",show_alert=True)
        user(chat_id,uid,q.from_user.full_name)
        s=get_size(chat_id,uid)
        if s<bet:
            return await q.answer("âŒ Ø³Ø§Ù†Øª Ú©Ø§ÙÛŒ Ù†Ø¯Ø§Ø±ÛŒ!",show_alert=True)
        c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?",(bet,chat_id,uid))
        c.execute("INSERT INTO mafia_members(battle_id,user_id,name,team) VALUES(?,?,?,?)",(bid,uid,q.from_user.full_name,team))
        db.commit()
        creator_name=get_name(chat_id,creator)
        opp_name=get_name(chat_id,opponent)
        await q.answer("âœ… Ù…Ø®ÙÛŒØ§Ù†Ù‡ ÙˆØ§Ø±Ø¯ ØªÛŒÙ… Ø´Ø¯ÛŒ!")
        try:
            await q.message.edit_text(
                mafia_board(bid,creator_name,opp_name,bet),
                reply_markup=q.message.reply_markup
            )
        except Exception:
            pass
    except Exception:
        logger.exception("mafia_join crashed for data=%s", q.data)
        try:
            await q.answer("âš ï¸ ÛŒÙ‡ Ø®Ø·Ø§ Ù¾ÛŒØ´ Ø§ÙˆÙ…Ø¯ØŒ Ø¯ÙˆØ¨Ø§Ø±Ù‡ Ø§Ù…ØªØ­Ø§Ù† Ú©Ù†.", show_alert=True)
        except Exception:
            pass

@dp.callback_query(F.data.startswith("mstart:"))
async def mafia_resolve(q:CallbackQuery):
    try:
        bid=int(q.data.split(":")[1])
        row=c.execute("SELECT creator,opponent,bet,active,chat_id FROM mafia_battles WHERE id=?",(bid,)).fetchone()
        if not row or row[3]==0:
            return await q.answer("âš ï¸ Ø§ÛŒÙ† Ù†Ø¨Ø±Ø¯ ØªÙ…ÙˆÙ… Ø´Ø¯Ù‡!",show_alert=True)
        creator,opponent,bet,_,chat_id=row
        if q.from_user.id not in (creator,opponent):
            return await q.answer("âš ï¸ ÙÙ‚Ø· Ø³Ø§Ø²Ù†Ø¯Ù‡ ÛŒØ§ Ø­Ø±ÛŒÙ Ù…ÛŒØªÙˆÙ†Ù‡ Ù†Ø¨Ø±Ø¯ Ø±Ùˆ Ø´Ø±ÙˆØ¹ Ú©Ù†Ù‡!",show_alert=True)
        members=c.execute("SELECT user_id,name,team FROM mafia_members WHERE battle_id=?",(bid,)).fetchall()
        team1=[(u,n) for u,n,t in members if t==1]
        team2=[(u,n) for u,n,t in members if t==2]
        tie=len(team1)==len(team2)
        if len(team1)>len(team2):
            winners,losers,wteam=team1,team2,1
        elif len(team2)>len(team1):
            winners,losers,wteam=team2,team1,2
        else:
            wteam=random.choice([1,2])
            winners,losers=(team1,team2) if wteam==1 else (team2,team1)
        # ÛŒØ§Ø±Ù‡Ø§ÛŒ Ø®Ø±ÛŒØ¯Ø§Ø±ÛŒâ€ŒØ´Ø¯Ù‡ Ø§Ø² Ú©Ù…Ù¾Ø§Ù†ÛŒ Ú©ÛŒØ± Ø´Ù†Ø§Ø³Ù‡â€ŒÛŒ Ù…Ù†ÙÛŒ Ø¯Ø§Ø±Ù†: ØªÙˆÛŒ Ø´Ù…Ø§Ø±Ø´ ØªÛŒÙ… Ø­Ø³Ø§Ø¨ Ù…ÛŒØ´Ù† ÙˆÙ„ÛŒ Ø³Ù‡Ù…ÛŒ Ø§Ø² Ø¬Ø§ÛŒØ²Ù‡ Ù†Ù…ÛŒâ€ŒØ¨Ø±Ù†
        human_count=sum(1 for u,_,_t in members if u>0)
        winners_human=[(u,n) for u,n in winners if u>0]
        total_pot=bet*human_count
        share=total_pot//len(winners_human) if winners_human else 0
        for uid,_ in winners_human:
            c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?",(share,chat_id,uid))
        c.execute("UPDATE mafia_battles SET active=0 WHERE id=?",(bid,))
        db.commit()
        win_names="ØŒ ".join(n for _,n in winners) or "-"
        lose_names="ØŒ ".join(n for _,n in losers) or "-"
        color="ðŸ”´" if wteam==1 else "ðŸ”µ"
        await q.message.edit_text(
            f"ðŸ”« Ù¾Ø§ÛŒØ§Ù† Ø¬Ù†Ú¯ Ù…Ø§ÙÛŒØ§!\n\n"
            f"{color} ØªÛŒÙ… Ø¨Ø±Ù†Ø¯Ù‡ ({len(winners)} Ù†ÙØ±): {win_names}\n"
            f"ðŸ’€ ØªÛŒÙ… Ø¨Ø§Ø²Ù†Ø¯Ù‡ ({len(losers)} Ù†ÙØ±): {lose_names}\n\n"
            f"ðŸ’° Ú©Ù„ Ø¬Ø§ÛŒØ²Ù‡: {total_pot} Ø³Ø§Ù†Øª\n"
            f"ðŸŽ Ø³Ù‡Ù… Ù‡Ø± Ø¨Ø±Ù†Ø¯Ù‡: {share} Ø³Ø§Ù†Øª\n\n"
            f"{'ðŸ˜‚ Ù…Ø³Ø§ÙˆÛŒ Ø¨ÙˆØ¯Ù†ØŒ Ø´Ø§Ù†Ø³ ØªØµÙ…ÛŒÙ… Ú¯Ø±ÙØª!' if tie else 'ðŸ‘‘ ØªÛŒÙ… Ø¨Ø²Ø±Ú¯ØªØ± Ø¨Ø±Ø¯!'}",
            reply_markup=None
        )
        await q.answer("ðŸ Ù†Ø¨Ø±Ø¯ ØªÙ…ÙˆÙ… Ø´Ø¯!")
    except Exception:
        logger.exception("mafia_resolve crashed for data=%s", q.data)
        try:
            await q.answer("âš ï¸ ÛŒÙ‡ Ø®Ø·Ø§ Ù¾ÛŒØ´ Ø§ÙˆÙ…Ø¯ØŒ Ø¯ÙˆØ¨Ø§Ø±Ù‡ Ø§Ù…ØªØ­Ø§Ù† Ú©Ù† ÛŒØ§ Ø¨Ø§ /mafia ÛŒÙ‡ Ù†Ø¨Ø±Ø¯ Ø¬Ø¯ÛŒØ¯ Ø¨Ø³Ø§Ø².", show_alert=True)
        except Exception:
            pass


# ===== Mafia2 Team PvP (reveals only who won, not the team lineup) =====
c.execute("CREATE TABLE IF NOT EXISTS mafia2_battles(id INTEGER PRIMARY KEY AUTOINCREMENT,creator INTEGER,opponent INTEGER,bet INTEGER,active INTEGER DEFAULT 1,chat_id INTEGER)")
c.execute("CREATE TABLE IF NOT EXISTS mafia2_members(battle_id INTEGER,user_id INTEGER,name TEXT,team INTEGER)")
db.commit()

# Ø³ØªÙˆÙ† is_ally Ø¨Ø±Ø§ÛŒ Ù…Ø´Ø®Øµ Ú©Ø±Ø¯Ù† ÛŒØ§Ø±Ù‡Ø§ÛŒÛŒ Ú©Ù‡ Ø§Ø² Ú©Ù…Ù¾Ø§Ù†ÛŒ Ú©ÛŒØ± Ø®Ø±ÛŒØ¯Ø§Ø±ÛŒ Ø´Ø¯Ù† (Ù†Ù‡ Ø¨Ø§Ø²ÛŒÚ©Ù† ÙˆØ§Ù‚Ø¹ÛŒ)
# ÛŒØ§Ø±Ù‡Ø§ Ù‡Ù…ÛŒØ´Ù‡ user_id Ù…Ù†ÙÛŒ Ø¯Ø§Ø±Ù†ØŒ Ù¾Ø³ Ù…Ù†Ø·Ù‚ Ø¨Ø±Ø¯/Ø¨Ø§Ø®Øª Ø¨Ø§ Ù‡Ù…ÙˆÙ† Ø¹Ù„Ø§Ù…ØªÙ Ù…Ù†ÙÛŒ Ù‡Ù… Ù‚Ø§Ø¨Ù„ ØªØ´Ø®ÛŒØµÙ‡Ø›
# Ø§ÛŒÙ† Ø³ØªÙˆÙ† ÙÙ‚Ø· Ø¨Ø±Ø§ÛŒ Ø®ÙˆØ§Ù†Ø§ÛŒÛŒ/Ø¢Ù…Ø§Ø± Ø§Ø¶Ø§ÙÙ‡â€ŒØ³Øª.
for _tbl in ("mafia_members", "mafia2_members"):
    try:
        c.execute(f"ALTER TABLE {_tbl} ADD COLUMN is_ally INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
db.commit()

def mafia2_counts(bid):
    t1=c.execute("SELECT COUNT(*) FROM mafia2_members WHERE battle_id=? AND team=1",(bid,)).fetchone()[0]
    t2=c.execute("SELECT COUNT(*) FROM mafia2_members WHERE battle_id=? AND team=2",(bid,)).fetchone()[0]
    return t1,t2

def mafia2_board(bid,creator_name,opp_name,bet,status="ðŸ”« Ø¬Ù†Ú¯ Ù…Ø§ÙÛŒØ§ Ø´Ø±ÙˆØ¹ Ø´Ø¯!"):
    t1,t2=mafia2_counts(bid)
    return (
        f"{status}\n\n"
        f"ðŸ”´ ØªÛŒÙ… {creator_name}  Ø¯Ø± Ù…Ù‚Ø§Ø¨Ù„  ðŸ”µ ØªÛŒÙ… {opp_name}\n"
        f"ðŸ’° ÙˆØ±ÙˆØ¯ÛŒ Ù‡Ø± Ù†ÙØ±: {bet} Ø³Ø§Ù†Øª\n\n"
        f"Ù‡Ø± Ú©ÛŒ Ù…ÛŒØ®ÙˆØ§Ø¯ ÙˆØ§Ø±Ø¯ Ø¨Ø´Ù‡ Ø¯Ú©Ù…Ù‡ ØªÛŒÙ…Ø´ Ø±Ùˆ Ø¨Ø²Ù†Ù‡ (Ù…Ø®ÙÛŒØ§Ù†Ù‡ Ø«Ø¨Øª Ù…ÛŒØ´Ù‡ØŒ ØªÛŒÙ…â€ŒØ¨Ù†Ø¯ÛŒ Ù…Ø¹Ù„ÙˆÙ… Ù†ÛŒØ³Øª)!\n"
        f"ðŸ‘¥ ØªØ¹Ø¯Ø§Ø¯ Ø´Ø±Ú©Øªâ€ŒÚ©Ù†Ù†Ø¯Ù‡â€ŒÙ‡Ø§: {t1+t2}\n\n"
        f"ÙˆÙ‚ØªÛŒ Ø¢Ù…Ø§Ø¯Ù‡ Ø¨ÙˆØ¯ÛŒØ¯ØŒ Ø³Ø§Ø²Ù†Ø¯Ù‡ ÛŒØ§ Ø­Ø±ÛŒÙ Ø¯Ú©Ù…Ù‡ Â«Ø´Ø±ÙˆØ¹ Ù†Ø¨Ø±Ø¯Â» Ø±Ùˆ Ø¨Ø²Ù†Ù‡.\n"
        f"â„¹ï¸ Ø¯Ø± Ù¾Ø§ÛŒØ§Ù† ÙÙ‚Ø· Ø¨Ø±Ù†Ø¯Ù‡ Ù…Ø´Ø®Øµ Ù…ÛŒØ´Ù‡ØŒ Ù†Ù‡ Ø§ÛŒÙ†Ú©Ù‡ Ú©ÛŒ Ú©Ø¬Ø§ Ø¨ÙˆØ¯."
    )

@dp.message(Command("mafia2"))
async def mafia2_start(m:Message):
    if not m.reply_to_message:
        return await m.reply("âš ï¸ Ø±ÙˆÛŒ Ù¾ÛŒØ§Ù… Ø­Ø±ÛŒÙ Ø±ÛŒÙ¾Ù„Ø§ÛŒ Ú©Ù† Ùˆ Ø¨Ù†ÙˆÛŒØ³ /mafia2 [Ù…Ø¨Ù„Øº]\nÙ…Ø«Ø§Ù„: /mafia2 5")
    try:
        bet=int(m.text.split()[1])
    except:
        return await m.reply("âš ï¸ Ø§Ø³ØªÙØ§Ø¯Ù‡: /mafia2 [Ù…Ø¨Ù„Øº]\nÙ…Ø«Ø§Ù„: /mafia2 5")
    if bet<=0:
        return await m.reply("âŒ Ù…Ø¨Ù„Øº Ø¨Ø§ÛŒØ¯ Ù…Ø«Ø¨Øª Ø¨Ø§Ø´Ù‡!")
    creator=m.from_user.id
    opponent=m.reply_to_message.from_user.id
    if creator==opponent:
        return await m.reply("âŒ Ù†Ù…ÛŒØªÙˆÙ†ÛŒ Ø¨Ø§ Ø®ÙˆØ¯Øª Ù…Ø§ÙÛŒØ§ Ø¨Ø§Ø²ÛŒ Ú©Ù†ÛŒ!")
    if m.reply_to_message.from_user.is_bot:
        return await m.reply("âŒ Ù†Ù…ÛŒØªÙˆÙ†ÛŒ Ø¨Ø§ Ø¨Ø§Øª Ù…Ø§ÙÛŒØ§ Ø¨Ø§Ø²ÛŒ Ú©Ù†ÛŒ!")
    user(m.chat.id,creator,m.from_user.full_name)
    user(m.chat.id,opponent,m.reply_to_message.from_user.full_name)
    s=get_size(m.chat.id,creator)
    if s<bet:
        return await m.reply("âŒ Ø³Ø§Ù†Øª Ú©Ø§ÙÛŒ Ù†Ø¯Ø§Ø±ÛŒ!")
    c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?",(bet,m.chat.id,creator))
    cur=c.execute("INSERT INTO mafia2_battles(creator,opponent,bet,chat_id) VALUES(?,?,?,?)",(creator,opponent,bet,m.chat.id))
    db.commit()
    bid=cur.lastrowid
    c.execute("INSERT INTO mafia2_members(battle_id,user_id,name,team) VALUES(?,?,?,1)",(bid,creator,m.from_user.full_name))
    db.commit()
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"ðŸ”´ ØªÛŒÙ… {m.from_user.full_name}",callback_data=f"m2join:{bid}:1"),
         InlineKeyboardButton(text=f"ðŸ”µ ØªÛŒÙ… {m.reply_to_message.from_user.full_name}",callback_data=f"m2join:{bid}:2")],
        [InlineKeyboardButton(text="ðŸ Ø´Ø±ÙˆØ¹ Ù†Ø¨Ø±Ø¯ Ùˆ Ø´Ù…Ø§Ø±Ø´",callback_data=f"m2start:{bid}")]
    ])
    await m.reply(
        mafia2_board(bid,m.from_user.full_name,m.reply_to_message.from_user.full_name,bet),
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith("m2join:"))
async def mafia2_join(q:CallbackQuery):
    try:
        _,bid,team=q.data.split(":")
        bid=int(bid); team=int(team)
        row=c.execute("SELECT creator,opponent,bet,active,chat_id FROM mafia2_battles WHERE id=?",(bid,)).fetchone()
        if not row or row[3]==0:
            return await q.answer("âš ï¸ Ø§ÛŒÙ† Ù†Ø¨Ø±Ø¯ ØªÙ…ÙˆÙ… Ø´Ø¯Ù‡!",show_alert=True)
        creator,opponent,bet,_,chat_id=row
        uid=q.from_user.id
        already=c.execute("SELECT team FROM mafia2_members WHERE battle_id=? AND user_id=?",(bid,uid)).fetchone()
        if already:
            return await q.answer("âš ï¸ Ù‚Ø¨Ù„Ø§Ù‹ Ù…Ø®ÙÛŒØ§Ù†Ù‡ ÙˆØ§Ø±Ø¯ ÛŒÙ‡ ØªÛŒÙ… Ø´Ø¯ÛŒ!",show_alert=True)
        user(chat_id,uid,q.from_user.full_name)
        s=get_size(chat_id,uid)
        if s<bet:
            return await q.answer("âŒ Ø³Ø§Ù†Øª Ú©Ø§ÙÛŒ Ù†Ø¯Ø§Ø±ÛŒ!",show_alert=True)
        c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?",(bet,chat_id,uid))
        c.execute("INSERT INTO mafia2_members(battle_id,user_id,name,team) VALUES(?,?,?,?)",(bid,uid,q.from_user.full_name,team))
        db.commit()
        creator_name=get_name(chat_id,creator)
        opp_name=get_name(chat_id,opponent)
        await q.answer("âœ… Ù…Ø®ÙÛŒØ§Ù†Ù‡ ÙˆØ§Ø±Ø¯ ØªÛŒÙ… Ø´Ø¯ÛŒ!")
        try:
            await q.message.edit_text(
                mafia2_board(bid,creator_name,opp_name,bet),
                reply_markup=q.message.reply_markup
            )
        except Exception:
            pass
    except Exception:
        logger.exception("mafia2_join crashed for data=%s", q.data)
        try:
            await q.answer("âš ï¸ ÛŒÙ‡ Ø®Ø·Ø§ Ù¾ÛŒØ´ Ø§ÙˆÙ…Ø¯ØŒ Ø¯ÙˆØ¨Ø§Ø±Ù‡ Ø§Ù…ØªØ­Ø§Ù† Ú©Ù†.", show_alert=True)
        except Exception:
            pass

@dp.callback_query(F.data.startswith("m2start:"))
async def mafia2_resolve(q:CallbackQuery):
    try:
        bid=int(q.data.split(":")[1])
        row=c.execute("SELECT creator,opponent,bet,active,chat_id FROM mafia2_battles WHERE id=?",(bid,)).fetchone()
        if not row or row[3]==0:
            return await q.answer("âš ï¸ Ø§ÛŒÙ† Ù†Ø¨Ø±Ø¯ ØªÙ…ÙˆÙ… Ø´Ø¯Ù‡!",show_alert=True)
        creator,opponent,bet,_,chat_id=row
        if q.from_user.id not in (creator,opponent):
            return await q.answer("âš ï¸ ÙÙ‚Ø· Ø³Ø§Ø²Ù†Ø¯Ù‡ ÛŒØ§ Ø­Ø±ÛŒÙ Ù…ÛŒØªÙˆÙ†Ù‡ Ù†Ø¨Ø±Ø¯ Ø±Ùˆ Ø´Ø±ÙˆØ¹ Ú©Ù†Ù‡!",show_alert=True)
        members=c.execute("SELECT user_id,name,team FROM mafia2_members WHERE battle_id=?",(bid,)).fetchall()
        team1=[(u,n) for u,n,t in members if t==1]
        team2=[(u,n) for u,n,t in members if t==2]
        tie=len(team1)==len(team2)
        if len(team1)>len(team2):
            winners,wteam=team1,1
        elif len(team2)>len(team1):
            winners,wteam=team2,2
        else:
            wteam=random.choice([1,2])
            winners=team1 if wteam==1 else team2
        # ÛŒØ§Ø±Ù‡Ø§ÛŒ Ø®Ø±ÛŒØ¯Ø§Ø±ÛŒâ€ŒØ´Ø¯Ù‡ Ø§Ø² Ú©Ù…Ù¾Ø§Ù†ÛŒ Ú©ÛŒØ± Ø´Ù†Ø§Ø³Ù‡â€ŒÛŒ Ù…Ù†ÙÛŒ Ø¯Ø§Ø±Ù†: ØªÙˆÛŒ Ø´Ù…Ø§Ø±Ø´ ØªÛŒÙ… Ø­Ø³Ø§Ø¨ Ù…ÛŒØ´Ù† ÙˆÙ„ÛŒ Ø³Ù‡Ù…ÛŒ Ø§Ø² Ø¬Ø§ÛŒØ²Ù‡ Ù†Ù…ÛŒâ€ŒØ¨Ø±Ù†
        human_count=sum(1 for u,_,_t in members if u>0)
        winners_human=[(u,n) for u,n in winners if u>0]
        total_pot=bet*human_count
        share=total_pot//len(winners_human) if winners_human else 0
        for uid,_ in winners_human:
            c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?",(share,chat_id,uid))
        c.execute("UPDATE mafia2_battles SET active=0 WHERE id=?",(bid,))
        db.commit()
        creator_name=get_name(chat_id,creator)
        opp_name=get_name(chat_id,opponent)
        win_label=f"ðŸ”´ ØªÛŒÙ… {creator_name}" if wteam==1 else f"ðŸ”µ ØªÛŒÙ… {opp_name}"
        await q.message.edit_text(
            f"ðŸ”« Ù¾Ø§ÛŒØ§Ù† Ø¬Ù†Ú¯ Ù…Ø§ÙÛŒØ§!\n\n"
            f"ðŸ‘¥ Ù…Ø¬Ù…ÙˆØ¹ Ø´Ø±Ú©Øªâ€ŒÚ©Ù†Ù†Ø¯Ù‡â€ŒÙ‡Ø§: {len(members)} Ù†ÙØ±\n\n"
            f"ðŸ‘‘ Ø¨Ø±Ù†Ø¯Ù‡: {win_label} ({len(winners)} Ù†ÙØ±)\n"
            f"ðŸ’° Ú©Ù„ Ø¬Ø§ÛŒØ²Ù‡: {total_pot} Ø³Ø§Ù†Øª\n"
            f"ðŸŽ Ø³Ù‡Ù… Ù‡Ø± Ø¨Ø±Ù†Ø¯Ù‡: {share} Ø³Ø§Ù†Øª\n\n"
            f"{'ðŸ˜‚ Ù…Ø³Ø§ÙˆÛŒ Ø¨ÙˆØ¯Ù†ØŒ Ø´Ø§Ù†Ø³ ØªØµÙ…ÛŒÙ… Ú¯Ø±ÙØª!' if tie else 'ðŸ‘‘ ØªÛŒÙ… Ø¨Ø²Ø±Ú¯ØªØ± Ø¨Ø±Ø¯!'}\n\n"
            f"ðŸ¤« Ø§ÛŒÙ†Ú©Ù‡ Ú©ÛŒ ØªÙˆ Ú©Ø¯ÙˆÙ… ØªÛŒÙ… Ø¨ÙˆØ¯ Ù…Ø®ÙÛŒ Ù…ÛŒâ€ŒÙ…ÙˆÙ†Ù‡!",
            reply_markup=None
        )
        await q.answer("ðŸ Ù†Ø¨Ø±Ø¯ ØªÙ…ÙˆÙ… Ø´Ø¯!")
    except Exception:
        logger.exception("mafia2_resolve crashed for data=%s", q.data)
        try:
            await q.answer("âš ï¸ ÛŒÙ‡ Ø®Ø·Ø§ Ù¾ÛŒØ´ Ø§ÙˆÙ…Ø¯ØŒ Ø¯ÙˆØ¨Ø§Ø±Ù‡ Ø§Ù…ØªØ­Ø§Ù† Ú©Ù† ÛŒØ§ Ø¨Ø§ /mafia2 ÛŒÙ‡ Ù†Ø¨Ø±Ø¯ Ø¬Ø¯ÛŒØ¯ Ø¨Ø³Ø§Ø².", show_alert=True)
        except Exception:
            pass


# ===== Celebrity Collection System =====
c.execute("""CREATE TABLE IF NOT EXISTS collections(
    chat_id INTEGER,
    user_id INTEGER,
    celeb TEXT,
    paid_price INTEGER DEFAULT 0,
    locked INTEGER DEFAULT 0
)""")
db.commit()


CELEBS = {
    "realtrelilove": ("PH",630,525,"AgACAgQAAxkBAAEiyFBqsl-5jTz16APdmObyCkIx7YxhswAClQ5rG7ngkFFdW6GmZb8jHQEAAwIAA3MAAz0E"),
    "Reislin": ("PH",630,525,"AgACAgQAAxkBAAEiyFJqsmCJV0lfG4fGyV1NAzacB8Cw-QACmA5rG7ngkFF8Fc3TvW79agEAAwIAA3MAAz0E"),
    "Jenny Kitty": ("PH",630,525,"AgACAgQAAxkBAAEii1tqpsVgDm25Nn44iH4e6bjwlTu2DQACAhBrGxHWOFF506Hdb2bopwEAAwIAA3MAAz0E"),
    "Eva Elfie": ("PH",630,525,"AgACAgQAAxkBAAEii1FqpsQmac1sr7zDK5Xt_G_FbeOM7AACARBrGxHWOFFJWAjEYvCMBwEAAwIAA3MAAz0E"),
    "Eden Ivy": ("PH",630,525,"AgACAgQAAxkBAAEixFxqsbxspcJ6O37kDI4Ha-S_3gGe6AACEBFrG9E-QVHRkUKIZY82rQEAAwIAA3MAAz0E"),
    "Ana Stangle": ("PH",630,525,"AgACAgQAAxkBAAEiixhqprxb_z1tsYNO_q36AAFG7bhvcrcAAu8PaxsR1jhR-H1AmjEhOykBAAMCAANtAAM9BA"),
    "Ana Stangle": ("PH",630,525,"AgACAgQAAxkBAAEiixhqprxb_z1tsYNO_q36AAFG7bhvcrcAAu8PaxsR1jhR-H1AmjEhOykBAAMCAANtAAM9BA"),
    "Polly Yangs": ("PH",630,525,"AgACAgQAAxkBAAEiixZqprwWMSc06gjR6Wf1AfjEMS-bYgAC7g9rGxHWOFF1rqHV_XmcqQEAAwIAA3MAAz0E"),
    "Mia Malkova": ("PH",630,525,"AgACAgQAAxkBAAEiixJqprvaxcqdkRMMLmDFpVVVJ22ycwAC7Q9rGxHWOFHDv3vxo0jSfAEAAwIAA3MAAz0E"),
    "Lyli Philips": ("PH",630,525,"AgACAgQAAxkBAAEiiwpqpruE7F2IrBlMo2Z7kJ7-iGC3hgAC6g9rGxHWOFEDhS0dv-NIdQEAAwIAA3MAAz0E"),
    "Remida": ("PH",630,525,"AgACAgQAAxkBAAEiiwZqprtRYUg6S4AaVWga3nd9oplYegAC6Q9rGxHWOFELW3Aa_kVp9QEAAwIAA3MAAz0E"),
    "Lily Lou": ("PH",630,525,"AgACAgQAAxkBAAEiiv5qprr3COm1SOlfeWjvRoU-Dmz9AgAC6A9rGxHWOFFkcd5sl-uEqwEAAwIAA3MAAz0E"),
    "Lena Paul": ("PH",630,525,"AgACAgQAAxkBAAEiivZqprk0NUKUAwABNROBmv06cviy35UAAvgVaxs3EDhR-L2oRxHNDegBAAMCAANzAAM9BA"),
    "Angela White": ("PH",630,525,"AgACAgQAAxkBAAEiK8tqlX0p5xvvc7RkL8yCDK50C70cMAAC3hBrG4IDsFBEhOBKjPVnEgEAAwIAA3MAAz0E"),
    "Comatozze": ("PH",630,525,"AgACAgQAAxkBAAEiK99qlYOdZfkvzeW8xB9yg8ay0a5E0AAC4w9rG8igqVDkAAH7iUzCMUoBAAMCAANzAAM9BA"),
    "Sweetie Fox": ("PH",630,525,"AgACAgQAAxkBAAEiK-NqlYTmIgPdooRd2A-cfBNbZIDWDwAC5g9rG8igqVDv7lHTLO7LEgEAAwIAA3MAAz0E"),
    "Diana Rider": ("PH",630,525,"AgACAgQAAxkBAAEiiyZqpr0Z6wHI0orDFTTA0FpqPDKxcgAC8g9rGxHWOFEEh3EQeHYcWwEAAwIAA3MAAz0E"),
    "Lana Rhoades": ("PH",630,525,"AgACAgQAAxkBAAEiK-dqlYZjT3rDHHtNt5EPHZTb_o70xwAC6A9rG8igqVCMQM6VNiWu-wEAAwIAA3MAAz0E"),
    "Megan Fox": ("S",542,438,"AgACAgQAAxkBAAEi9L1quYRn9CFuUMLdu_RSP85KMpvENgAC1w9rG2EdyVH6SpUrldkU-gEAAwIAA3MAAz0E"),
    "Shakira": ("S",542,438,"AgACAgQAAxkBAAEi9QABarmNiCiSr3f5U--ZFrDxJ2-j5lIAAuoPaxthHclRrWkgzLInDRMBAAMCAANzAAM9BA"),
    "Ana de Armas": ("S",542,438,"AgACAgQAAxkBAAEiLBRqlYks3xjU5rQCkNXypUQOoS9n3QAC7w9rG8igqVAhpyUv1rvdmwEAAwIAA3MAAz0E"),
    "Kylie Jenner": ("S",542,438,"AgACAgQAAxkBAAEii0NqpsFgJgN8lSjVTyiKBQanxRUV7AAC_Q9rGxHWOFHpMFeQR7I8fQEAAwIAA3MAAz0E"),
    "Sydney Sweeney": ("S",542,438,"AgACAgQAAxkBAAEii0tqpsL7OwOzbu-UicheoiKjfQGvEgAC_w9rGxHWOFEfc0vRD4_BvAEAAwIAA3MAAz0E"),
    "Pinkchyu": ("S",542,438,"AgACAgQAAxkBAAEiiz9qpsDeoCCTvNfIyfhp_0DLu6md9gAC-g9rGxHWOFEwehVusIFDyAEAAwIAA3MAAz0E"),
    "Georgina Rodriguez": ("S",542,438,"AgACAgQAAxkBAAEii0FqpsEls89dT1QptHWD0jEdIhaOXQAC_A9rGxHWOFGfJx1nk0t_GAEAAwIAA3MAAz0E"),
    "Sadie Sink": ("A",350,262,"AgACAgQAAxkBAAEi9QhquY8NQdTDxyaSEIkyj0qKbvzkzgAC8A9rG2EdyVHDaTUVBVAhEwEAAwIAA3MAAz0E"),
    "Lisa": ("A",350,262,"AgACAgQAAxkBAAEi9MxquYYUDrQydMO-aRTNlrogPUOecgAC3A9rG2EdyVHKCB1Va6zX2QEAAwIAA3MAAz0E"),
    "Madison Beer": ("A",350,262,"AgACAgQAAxkBAAEiix5qpry4N-XRCC1BeUeGrBacwO1PxwAC8Q9rGxHWOFEiXTj03FeFEAEAAwIAA3MAAz0E"),
    "Mikey Madison": ("B",175,88,"AgACAgQAAxkBAAEi9TRquZMICh3hQ-4d0uT6olt2gYpHNgAC-Q9rG2EdyVG7dS6nNREO-wEAAwIAA20AAz0E"),
    "Scarlett Johansson": ("A",350,262,"AgACAgQAAxkBAAEijSBqpwXof-3vjZeK_61sIm9brMrWWwAC5Q9rG_HjOVGRBdU_77rF8wEAAwIAA3MAAz0E"),
    "Millie": ("B",175,88,"AgACAgQAAxkBAAEi9R5quZC_gBmpvDQtk0A5jio26nvWHgAC9Q9rG2EdyVG9i7jmqVYQAgEAAwIAA3MAAz0E"),
    "Margaret Qualley": ("B",175,88,"AgACAgQAAxkBAAEi9SJquZEzj2CMR9eg5ep_7YypzZ4jSAAC9g9rG2EdyVF5NwlDNpRMUwEAAwIAA3MAAz0E"),
    "Emma Stone": ("B",175,88,"AgACAgQAAxkBAAEi9QZquY61kojDCq6Nd5T7BPtjGjkHRwAC7w9rG2EdyVFqQPwt2ffK1QEAAwIAA3MAAz0E"),
    "Margot Robbie": ("B",175,88,"AgACAgQAAxkBAAEi9QRquY4jNNKMQ0Dwv0DLXCiFLrmq-QAC6w9rG2EdyVH3gMZRH-1HaAEAAwIAA3MAAz0E"),
    "Anne Hathaway": ("B",175,88,"AgACAgQAAxkBAAEiLHJqlZLNXRVWSN-k7xu-doS7FTDsbgACCRBrG8igqVDk8fgU3uXUFwEAAwIAA3MAAz0E"),
    "Elizabeth Olsen": ("B",175,88,"AgACAgQAAxkBAAEiLHRqlZNem1Ue0rp7IJ182xumcv2XKwACChBrG8igqVDyu9zwySffJAEAAwIAA3MAAz0E"),
    "Olivia Rodrigo": ("B",175,88,"AgACAgQAAxkBAAEiLHZqlZPReBV1oF2fHUcz1MiKfWTuPAACCxBrG8igqVDsVdcPA4GFUAEAAwIAA3MAAz0E"),
    "Emma Watson": ("B",175,88,"AgACAgQAAxkBAAEiLHpqlZRQeIXIaNZcdp3gXLdrXT2anAACDRBrG8igqVC08ITVIg9XMAEAAwIAA3MAAz0E"),
    "Leah Halton": ("B",175,88,"AgACAgQAAxkBAAEiiyhqpr1II4KnLYGLp4wwWO25ZUjnMwAC8w9rGxHWOFHnxgG03-TRhAEAAwIAA3MAAz0E"),
    "Ashlyn Castro": ("B",175,88,"AgACAgQAAxkBAAEiiypqpr2gKFikU1gkAAFPisEKVaAKA5oAAvQPaxsR1jhRLB-aZnzbFkIBAAMCAANtAAM9BA"),
    "Kristen Stewart": ("B",175,88,"AgACAgQAAxkBAAEiLHxqlZSorrGyLnSOBdRqRqdnSvnaXgACDxBrG8igqVDQHpTLZKuoOwEAAwIAA3MAAz0E"),
    "Olivia Cooke": ("B",175,88,"AgACAgQAAxkBAAEi9ShquZHQ0I5I3-tTu1elOoREkW_qowAC9w9rG2EdyVF27Y1U8qnULgEAAwIAA3MAAz0E"),
    "Sabrina Carpenter": ("B",350,175,"AgACAgQAAxkBAAEiLGxqlZJxN_AeZTfMK1e_iZUiC4tvaAACBxBrG8igqVD1mfDtce21cAEAAwIAA3MAAz0E"),
    "Dua Lipa": ("A",350,262,"AgACAgQAAxkBAAEi9RRquY-fqg9SMv_6TBAS1mmMq5P3KAAC8Q9rG2EdyVFvukQd7WcagQEAAwIAA20AAz0E"),
    "Sophie Tatcher": ("A",350,262,"AgACAgQAAxkBAAEiLExqlZBP5UH5p9rTTAUQ6hv3_mUpkAAC_g9rG8igqVABEzpZosgbbAEAAwIAA3MAAz0E"),
    "Billie Eilish": ("S",542,438,"AgACAgQAAxkBAAEii01qpsO9jfgwqGNaCOuxcDI2B_tolAACLRFrG-cKCVH7fF__m9zGrQEAAwIAA3MAAz0E"),
    "Folorance Pugh": ("B",175,88,"AgACAgQAAxkBAAEiizBqpr485700NYU6jwetz6qFBbBYrgAC9g9rGxHWOFFkMl6wX7RergEAAwIAA3MAAz0E"),
}


TIER_CELEBS = {
    "S": [(n, v[1], v[3]) for n, v in CELEBS.items() if v[0] == "S"],
    "A": [(n, v[1], v[3]) for n, v in CELEBS.items() if v[0] == "A"],
    "B": [(n, v[1], v[3]) for n, v in CELEBS.items() if v[0] == "B"],
    "PH": [(n, v[1], v[3]) for n, v in CELEBS.items() if v[0] == "PH"],
}
TIER_LABELS = {
    "S": "ðŸ¥‡ Tier S",
    "A": "ðŸ¥ˆ Tier A",
    "B": "ðŸ¥‰ Tier B",
    "PH": "ðŸ’Ž Tier PH",
}
TIER_PRICES = {"S": (543, 438), "A": (350, 262), "B": (175, 88), "PH": (630, 525)}

def build_market_caption(tier, page):
    celebs = TIER_CELEBS[tier]
    name, price, photo = celebs[page]
    buy_price, spin_price = TIER_PRICES[tier]
    label = TIER_LABELS[tier]
    txt = (
        f"ðŸ›’ Ø¨Ø§Ø²Ø§Ø± Ø³Ù„Ø¨Ø±ÛŒØªÛŒ\n"
        f"{label} â€” ØµÙØ­Ù‡ {page+1}/{len(celebs)}\n\n"
        f"ðŸ‘‘ {name}\n"
        f"ðŸ’° Ø®Ø±ÛŒØ¯: {price} Ø³Ø§Ù†Øª\n"
        f"ðŸŽ° Ø§Ø³Ù¾ÛŒÙ†: {spin_price} Ø³Ø§Ù†Øª\n\n"
        f"ðŸ›’ /buy {name}\n"
        f"ðŸŽ° /spin {tier.lower()}"
    )
    return txt, photo

def build_market_kb(tier, page):
    celebs = TIER_CELEBS[tier]
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="â—€ï¸", callback_data=f"mkt:{tier}:{page-1}"))
    if page < len(celebs) - 1:
        buttons.append(InlineKeyboardButton(text="â–¶ï¸", callback_data=f"mkt:{tier}:{page+1}"))
    return InlineKeyboardMarkup(inline_keyboard=[buttons]) if buttons else None

async def fetch_photo(url: str) -> BufferedInputFile | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    filename = url.split("/")[-1]
                    return BufferedInputFile(data, filename=filename)
    except Exception:
        pass
    return None

# ===== Telegram file_id photo cache (avoid re-downloading/re-uploading every time) =====
# Ø§ÛŒÙ† Ø¬Ø¯ÙˆÙ„ Ø¹Ù…Ø¯Ø§Ù‹ Ø³Ø±Ø§Ø³Ø±ÛŒÙ‡ (Ù†Ù‡ Ø¨Ø± Ø§Ø³Ø§Ø³ Ú†Øª) Ú†ÙˆÙ† ÙÙ‚Ø· Ø¹Ú©Ø³â€ŒÙ‡Ø§ÛŒ Ø³Ù„Ø¨Ø±ÛŒØªÛŒâ€ŒÙ‡Ø§ Ø±Ùˆ Ú©Ø´ Ù…ÛŒâ€ŒÚ©Ù†Ù‡ØŒ
# Ù†Ù‡ Ø¯ÛŒØªØ§ÛŒ Ø§Ù‚ØªØµØ§Ø¯ÛŒ Ú©Ø§Ø±Ø¨Ø±Ø› Ø¹Ú©Ø³â€ŒÙ‡Ø§ ØªÙˆ Ù‡Ù…Ù‡â€ŒÛŒ Ú¯Ø±ÙˆÙ‡â€ŒÙ‡Ø§ ÛŒÚ©Ø³Ø§Ù†Ù†.
c.execute("CREATE TABLE IF NOT EXISTS photo_cache(url TEXT PRIMARY KEY, file_id TEXT)")
db.commit()

async def resolve_photo(url: str):
    """Accepts either a Telegram file_id (used directly, zero download) or an http(s) URL
    (downloaded once, then cached as a file_id from then on)."""
    if not url:
        return None
    if not url.startswith("http://") and not url.startswith("https://"):
        # Already a Telegram file_id â€” use it straight away, nothing to download.
        return url
    row = c.execute("SELECT file_id FROM photo_cache WHERE url=?", (url,)).fetchone()
    if row:
        return row[0]
    return await fetch_photo(url)

def cache_photo(url: str, sent_message):
    """Call after successfully sending/editing a photo that was NOT already cached, to store its file_id."""
    try:
        if sent_message and sent_message.photo:
            c.execute("INSERT OR REPLACE INTO photo_cache(url,file_id) VALUES(?,?)", (url, sent_message.photo[-1].file_id))
            db.commit()
    except Exception:
        pass

@dp.message(Command("getfileid"))
async def get_file_id(m: Message):
    target = m.reply_to_message.photo[-1] if (m.reply_to_message and m.reply_to_message.photo) else (m.photo[-1] if m.photo else None)
    if not target:
        return await m.reply("âš ï¸ ÛŒÙ‡ Ø¹Ú©Ø³ Ø¨ÙØ±Ø³Øª (ÛŒØ§ Ø±ÙˆÛŒ ÛŒÙ‡ Ø¹Ú©Ø³ Ø±ÛŒÙ¾Ù„Ø§ÛŒ Ø¨Ø²Ù†) Ùˆ /getfileid Ø±Ùˆ Ø¨Ù†ÙˆÛŒØ³.")
    await m.reply(f"ðŸ†” file_id:\n`{target.file_id}`", parse_mode="Markdown")

@dp.message(Command("market"))
async def market(m:Message):
    for tier in ["S", "A", "B", "PH"]:
        if not TIER_CELEBS[tier]:
            continue
        txt, photo_url = build_market_caption(tier, 0)
        kb = build_market_kb(tier, 0)
        photo = await resolve_photo(photo_url) if photo_url else None
        try:
            if photo:
                sent = await m.bot.send_photo(m.chat.id, photo, caption=txt, reply_markup=kb)
                if isinstance(photo, BufferedInputFile):
                    cache_photo(photo_url, sent)
            else:
                await m.bot.send_message(m.chat.id, txt, reply_markup=kb)
        except Exception as e:
            # Ø§Ú¯Ù‡ ÙØ±Ø³ØªØ§Ø¯Ù† Ø¹Ú©Ø³ Ø®Ø±Ø§Ø¨ Ø´Ø¯ (Ù…Ø«Ù„Ø§Ù‹ file_id Ù†Ø§Ù…Ø¹ØªØ¨Ø±Ù‡) Ú©Ù„ Ø¯Ø³ØªÙˆØ± /market Ù†Ø¨Ø§ÛŒØ¯ Ø¨ØªØ±Ú©Ù‡Ø›
            # Ø¨Ù‡â€ŒØ¬Ø§Ø´ Ù¾ÛŒØ§Ù… Ù…ØªÙ†ÛŒ Ù…ÛŒâ€ŒÙØ±Ø³ØªÛŒÙ… ØªØ§ Ø¨Ù‚ÛŒÙ‡â€ŒÛŒ ØªÛŒØ±Ù‡Ø§ Ù‡Ù… Ù†Ù…Ø§ÛŒØ´ Ø¯Ø§Ø¯Ù‡ Ø¨Ø´Ù†.
            print(f"[market] Ø®Ø·Ø§ Ø¯Ø± Ø§Ø±Ø³Ø§Ù„ Ø¹Ú©Ø³ ØªÛŒØ± {tier}: {e}")
            await m.bot.send_message(m.chat.id, txt, reply_markup=kb)

@dp.callback_query(F.data.startswith("mkt:"))
async def market_page_nav(q: CallbackQuery):
    _, tier, page = q.data.split(":")
    page = int(page)
    txt, photo_url = build_market_caption(tier, page)
    kb = build_market_kb(tier, page)
    photo = await resolve_photo(photo_url) if photo_url else None
    try:
        if photo and q.message.photo:
            edited = await q.message.edit_media(
                media=InputMediaPhoto(media=photo, caption=txt),
                reply_markup=kb
            )
            if isinstance(photo, BufferedInputFile) and hasattr(edited, "photo"):
                cache_photo(photo_url, edited)
        elif q.message.photo:
            await q.message.edit_caption(caption=txt, reply_markup=kb)
        else:
            await q.message.edit_text(txt, reply_markup=kb)
    except Exception as e:
        await q.answer(f"Ø®Ø·Ø§: {e}", show_alert=True)
        return
    await q.answer()

@dp.message(Command("collection"))
async def collection(m:Message):
    if m.reply_to_message:
        target = m.reply_to_message.from_user
        user(m.chat.id, target.id, target.full_name)
        rows = c.execute("SELECT celeb FROM collections WHERE chat_id=? AND user_id=?", (m.chat.id, target.id)).fetchall()
        if not rows:
            return await m.reply(f"ðŸ“š {target.full_name} Ù‡Ù†ÙˆØ² Ú†ÛŒØ²ÛŒ Ù†Ø¯Ø§Ø±Ù‡.")
        celebs = [r[0] for r in rows]
        await send_collection_page(m.chat.id, target.id, celebs, 0, m.bot, viewer_id=m.from_user.id)
    else:
        user(m.chat.id, m.from_user.id, m.from_user.full_name)
        rows = c.execute("SELECT celeb FROM collections WHERE chat_id=? AND user_id=?", (m.chat.id, m.from_user.id)).fetchall()
        if not rows:
            return await m.reply("ðŸ“š Ù‡Ù†ÙˆØ² Ú†ÛŒØ²ÛŒ Ù†Ø¯Ø§Ø±ÛŒ.")
        celebs = [r[0] for r in rows]
        await send_collection_page(m.chat.id, m.from_user.id, celebs, 0, m.bot, viewer_id=m.from_user.id)

async def send_collection_page(chat_id, owner_id, celebs, page, bot, viewer_id=None):
    name = celebs[page]
    tier, price, spin, photo_url = CELEBS[name]
    tier_label = {"S": "ðŸ¥‡ S", "A": "ðŸ¥ˆ A", "B": "ðŸ¥‰ B", "PH": "ðŸ’Ž PH"}[tier]
    txt = (
        f"ðŸ“š Ú©Ø§Ù„Ú©Ø´Ù† â€” {page+1}/{len(celebs)}\n\n"
        f"ðŸ‘‘ {name}\n"
        f"ðŸ… ØªÛŒØ±: {tier_label}\n"
        f"ðŸ’° Ø§Ø±Ø²Ø´: {price} Ø³Ø§Ù†Øª\n\n"
        f"ðŸ›’ /sell {name}\n"
        f"ðŸª /list {name} [Ù‚ÛŒÙ…Øª]"
    )
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="â—€ï¸", callback_data=f"col:{owner_id}:{page-1}"))
    if page < len(celebs) - 1:
        buttons.append(InlineKeyboardButton(text="â–¶ï¸", callback_data=f"col:{owner_id}:{page+1}"))
    kb = InlineKeyboardMarkup(inline_keyboard=[buttons]) if buttons else None
    photo = await resolve_photo(photo_url) if photo_url else None
    try:
        if photo:
            sent = await bot.send_photo(chat_id, photo, caption=txt, reply_markup=kb)
            if isinstance(photo, BufferedInputFile):
                cache_photo(photo_url, sent)
        else:
            await bot.send_message(chat_id, txt, reply_markup=kb)
    except Exception as e:
        print(f"[collection] Ø®Ø·Ø§ Ø¯Ø± Ø§Ø±Ø³Ø§Ù„ Ø¹Ú©Ø³ {name}: {e}")
        await bot.send_message(chat_id, txt, reply_markup=kb)

@dp.callback_query(F.data.startswith("col:"))
async def collection_nav(q: CallbackQuery):
    _, owner_id, page = q.data.split(":")
    owner_id = int(owner_id)
    page = int(page)
    chat_id = q.message.chat.id
    # allow anyone to browse
    rows = c.execute("SELECT celeb FROM collections WHERE chat_id=? AND user_id=?", (chat_id, owner_id)).fetchall()
    celebs = [r[0] for r in rows]
    if page >= len(celebs):
        page = len(celebs) - 1
    name = celebs[page]
    tier, price, spin, photo_url = CELEBS[name]
    tier_label = {"S": "ðŸ¥‡ S", "A": "ðŸ¥ˆ A", "B": "ðŸ¥‰ B", "PH": "ðŸ’Ž PH"}[tier]
    txt = (
        f"ðŸ“š Ú©Ø§Ù„Ú©Ø´Ù† â€” {page+1}/{len(celebs)}\n\n"
        f"ðŸ‘‘ {name}\n"
        f"ðŸ… ØªÛŒØ±: {tier_label}\n"
        f"ðŸ’° Ø§Ø±Ø²Ø´: {price} Ø³Ø§Ù†Øª\n\n"
        f"ðŸ›’ /sell {name}\n"
        f"ðŸª /list {name} [Ù‚ÛŒÙ…Øª]"
    )
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="â—€ï¸", callback_data=f"col:{owner_id}:{page-1}"))
    if page < len(celebs) - 1:
        buttons.append(InlineKeyboardButton(text="â–¶ï¸", callback_data=f"col:{owner_id}:{page+1}"))
    kb = InlineKeyboardMarkup(inline_keyboard=[buttons]) if buttons else None
    photo = await resolve_photo(photo_url) if photo_url else None
    try:
        if photo and q.message.photo:
            edited = await q.message.edit_media(
                media=InputMediaPhoto(media=photo, caption=txt),
                reply_markup=kb
            )
            if isinstance(photo, BufferedInputFile) and hasattr(edited, "photo"):
                cache_photo(photo_url, edited)
        elif q.message.photo:
            await q.message.edit_caption(caption=txt, reply_markup=kb)
        else:
            await q.message.edit_text(txt, reply_markup=kb)
    except Exception as e:
        await q.answer(f"Ø®Ø·Ø§: {e}", show_alert=True)
        return
    await q.answer()


@dp.message(Command("buy"))
async def buy(m:Message):
    name=strip_command(m.text)

    if name not in CELEBS:
        return await m.reply("âŒ Ø³Ù„Ø¨Ø±ÛŒØªÛŒ Ù¾ÛŒØ¯Ø§ Ù†Ø´Ø¯.")

    tier,price,spin,photo=CELEBS[name]

    user(m.chat.id,m.from_user.id,m.from_user.full_name)

    size=get_size(m.chat.id,m.from_user.id)

    if size<price:
        return await m.reply("ðŸ’¸ Ø³Ø§Ù†Øª Ú©Ø§ÙÛŒ Ù†Ø¯Ø§Ø±ÛŒ!")

    tier_key = CELEBS[name][0]

    # check if user already owns it
    user_owned = c.execute("SELECT 1 FROM collections WHERE chat_id=? AND user_id=? AND celeb=?", (m.chat.id, m.from_user.id, name)).fetchone()
    if user_owned:
        return await m.reply("ðŸ“š Ø§ÛŒÙ† Ø³Ù„Ø¨Ø±ÛŒØªÛŒ Ø±Ùˆ Ø¯Ø§Ø±ÛŒ!")

    # tier S and A are exclusive â€” check if anyone owns it (locked or not)
    # tier B is only exclusive if locked
    if tier_key in ("S", "A"):
        owned = c.execute("SELECT user_id FROM collections WHERE chat_id=? AND celeb=?", (m.chat.id, name)).fetchone()
        if owned:
            owner_name = get_name(m.chat.id, owned[0])
            return await m.reply(f"âŒ Ø§ÛŒÙ† Ø³Ù„Ø¨Ø±ÛŒØªÛŒ Ù‚Ø¨Ù„Ø§Ù‹ ØªÙˆØ³Ø· {owner_name} Ø®Ø±ÛŒØ¯Ø§Ø±ÛŒ Ø´Ø¯Ù‡!")
    else:
        # tier B â€” only block if locked
        locked = c.execute("SELECT user_id FROM collections WHERE chat_id=? AND celeb=? AND locked=1", (m.chat.id, name)).fetchone()
        if locked:
            owner_name = get_name(m.chat.id, locked[0])
            return await m.reply(f"ðŸ”’ Ø§ÛŒÙ† Ø³Ù„Ø¨Ø±ÛŒØªÛŒ ØªÙˆØ³Ø· {owner_name} Ù‚ÙÙ„ Ø´Ø¯Ù‡!")

    c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?",(price,m.chat.id,m.from_user.id))
    c.execute("INSERT INTO collections(chat_id,user_id,celeb,paid_price) VALUES(?,?,?,?)",(m.chat.id,m.from_user.id,name,price))
    db.commit()

    photo_url = photo
    photo = await resolve_photo(photo_url) if photo_url else None
    try:
        if photo:
            sent = await m.bot.send_photo(m.chat.id, photo, caption=f"ðŸŽ‰ Ø®Ø±ÛŒØ¯ Ù…ÙˆÙÙ‚!\n\nðŸ‘‘ {name}")
            if isinstance(photo, BufferedInputFile):
                cache_photo(photo_url, sent)
        else:
            await m.reply(f"ðŸŽ‰ Ø®Ø±ÛŒØ¯ Ù…ÙˆÙÙ‚!\n\nðŸ‘‘ {name}")
    except Exception as e:
        # Ø®Ø±ÛŒØ¯ ØªÙˆÛŒ Ø¯ÛŒØªØ§Ø¨ÛŒØ³ Ù‚Ø¨Ù„Ø§Ù‹ Ø«Ø¨Øª Ø´Ø¯Ù‡ØŒ Ù¾Ø³ Ø­ØªÛŒ Ø§Ú¯Ù‡ Ø¹Ú©Ø³ Ù†Ø±Ù‡ Ø­Ø¯Ø§Ù‚Ù„ ØªØ§ÛŒÛŒØ¯ÛŒÙ‡â€ŒÛŒ Ù…ØªÙ†ÛŒ Ø¨Ø±Ù‡
        print(f"[buy] Ø®Ø·Ø§ Ø¯Ø± Ø§Ø±Ø³Ø§Ù„ Ø¹Ú©Ø³ {name}: {e}")
        await m.reply(f"ðŸŽ‰ Ø®Ø±ÛŒØ¯ Ù…ÙˆÙÙ‚!\n\nðŸ‘‘ {name}")

@dp.message(Command("spin"))
async def spin(m:Message):
    try:
        tier=m.text.split()[1].upper()
    except:
        return await m.reply("Ø§Ø³ØªÙØ§Ø¯Ù‡: /spin s | a | b")

    prices={"S":438,"A":262,"B":88,"PH":525}

    if tier not in prices:
        return await m.reply("Tier Ø¨Ø§ÛŒØ¯ s ÛŒØ§ a ÛŒØ§ b Ø¨Ø§Ø´Ø¯.")

    cost=prices[tier]

    user(m.chat.id,m.from_user.id,m.from_user.full_name)

    size=get_size(m.chat.id,m.from_user.id)

    if size<cost:
        return await m.reply("ðŸ’¸ Ø³Ø§Ù†Øª Ú©Ø§ÙÛŒ Ù†Ø¯Ø§Ø±ÛŒ!")

    pool=[n for n,v in CELEBS.items() if v[0]==tier]
    celeb=random.choice(pool)

    c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?",(cost,m.chat.id,m.from_user.id))

    spin_tier = CELEBS[celeb][0]
    user_owned = c.execute("SELECT 1 FROM collections WHERE chat_id=? AND user_id=? AND celeb=?", (m.chat.id, m.from_user.id, celeb)).fetchone()
    if user_owned:
        c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?",(cost,m.chat.id,m.from_user.id))
        db.commit()
        return await m.reply(f"ðŸ”„ Ø§ÛŒÙ† Ø³Ù„Ø¨Ø±ÛŒØªÛŒ Ø±Ùˆ Ù‚Ø¨Ù„Ø§Ù‹ Ø¯Ø§Ø±ÛŒ!\n\nðŸ‘‘ {celeb}\nðŸ’° {cost} Ø³Ø§Ù†Øª Ø¨Ø±Ú¯Ø´Øª Ø¯Ø§Ø¯Ù‡ Ø´Ø¯.")

    if spin_tier in ("S", "A"):
        owned = c.execute("SELECT user_id FROM collections WHERE chat_id=? AND celeb=?", (m.chat.id, celeb)).fetchone()
        if owned:
            c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?",(cost,m.chat.id,m.from_user.id))
            db.commit()
            owner_name=get_name(m.chat.id,owned[0])
            return await m.reply(f"ðŸ”„ Ø§ÛŒÙ† Ø³Ù„Ø¨Ø±ÛŒØªÛŒ Ù‚Ø¨Ù„Ø§Ù‹ ØªÙˆØ³Ø· {owner_name} Ø®Ø±ÛŒØ¯Ø§Ø±ÛŒ Ø´Ø¯Ù‡!\n\nðŸ‘‘ {celeb}\nðŸ’° {cost} Ø³Ø§Ù†Øª Ø¨Ø±Ú¯Ø´Øª Ø¯Ø§Ø¯Ù‡ Ø´Ø¯.")
    else:
        locked = c.execute("SELECT user_id FROM collections WHERE chat_id=? AND celeb=? AND locked=1", (m.chat.id, celeb)).fetchone()
        if locked:
            c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?",(cost,m.chat.id,m.from_user.id))
            db.commit()
            owner_name=get_name(m.chat.id,locked[0])
            return await m.reply(f"ðŸ”’ Ø§ÛŒÙ† Ø³Ù„Ø¨Ø±ÛŒØªÛŒ ØªÙˆØ³Ø· {owner_name} Ù‚ÙÙ„ Ø´Ø¯Ù‡!\n\nðŸ‘‘ {celeb}\nðŸ’° {cost} Ø³Ø§Ù†Øª Ø¨Ø±Ú¯Ø´Øª Ø¯Ø§Ø¯Ù‡ Ø´Ø¯.")

    # ===== Ø§Ø±Ø²Ø´ ÙØ±ÙˆØ´ (paid_price) Ø¨Ø±Ø§ÛŒ Ø³Ù„Ø¨Ø±ÛŒØªÛŒ Ú¯Ø±ÙØªÙ‡â€ŒØ´Ø¯Ù‡ Ø§Ø² Ø§Ø³Ù¾ÛŒÙ† =====
    # ØªÛŒØ± B â†’ Ù†ØµÙ Ù‡Ø²ÛŒÙ†Ù‡â€ŒÛŒ Ø§Ø³Ù¾ÛŒÙ†ØŒ Ø¨Ù‚ÛŒÙ‡â€ŒÛŒ ØªÛŒØ±Ù‡Ø§ (S/A/PH) â†’ Û·ÛµÙª Ù‡Ø²ÛŒÙ†Ù‡â€ŒÛŒ Ø§Ø³Ù¾ÛŒÙ†.
    resale_value = cost // 2 if spin_tier == "B" else (cost * 3) // 4

    c.execute(
        "INSERT INTO collections(chat_id,user_id,celeb,paid_price) VALUES(?,?,?,?)",
        (m.chat.id,m.from_user.id,celeb,resale_value)
    )
    db.commit()

    photo_url=CELEBS[celeb][3]
    photo = await resolve_photo(photo_url) if photo_url else None
    try:
        if photo:
            sent = await m.bot.send_photo(m.chat.id, photo, caption=f"ðŸŽ° Ø§Ø³Ù¾ÛŒÙ† Ù…ÙˆÙÙ‚!\n\nðŸ‘‘ {celeb}")
            if isinstance(photo, BufferedInputFile):
                cache_photo(photo_url, sent)
        else:
            await m.reply(f"ðŸŽ° Ø§Ø³Ù¾ÛŒÙ† Ù…ÙˆÙÙ‚!\n\nðŸ‘‘ {celeb}")
    except Exception as e:
        print(f"[spin] Ø®Ø·Ø§ Ø¯Ø± Ø§Ø±Ø³Ø§Ù„ Ø¹Ú©Ø³ {celeb}: {e}")
        await m.reply(f"ðŸŽ° Ø§Ø³Ù¾ÛŒÙ† Ù…ÙˆÙÙ‚!\n\nðŸ‘‘ {celeb}")

@dp.message(Command("collectors"))
async def collectors(m:Message):
    rows=c.execute("""
        SELECT users.name,COUNT(collections.celeb) AS total
        FROM users
        LEFT JOIN collections
        ON users.user_id=collections.user_id AND users.chat_id=collections.chat_id
        WHERE users.chat_id=?
        GROUP BY users.chat_id,users.user_id
        ORDER BY total DESC
        LIMIT 10
    """,(m.chat.id,)).fetchall()

    txt="ðŸ† Ø¨Ù‡ØªØ±ÛŒÙ† Ú©Ù„Ú©Ø³ÛŒÙˆÙ†Ø±Ù‡Ø§\n\n"

    for i,(name,total) in enumerate(rows,1):
        txt+=f"{i}. {name} â€” {total} Ø³Ù„Ø¨Ø±ÛŒØªÛŒ\n"

    await m.reply(txt)


@dp.message(Command("list"))
async def list_celeb(m:Message):
    parts = m.text.split(None, 1)
    if len(parts) < 2:
        return await m.reply("Usage: /list [Ù†Ø§Ù…] [Ù‚ÛŒÙ…Øª]\nÙ…Ø«Ø§Ù„: /list Kylie Jenner 500")
    try:
        rest = parts[1].rsplit(None, 1)
        name = rest[0].strip()
        price = int(rest[1])
    except:
        return await m.reply("Usage: /list [Ù†Ø§Ù…] [Ù‚ÛŒÙ…Øª]\nÙ…Ø«Ø§Ù„: /list Kylie Jenner 500")
    if name not in CELEBS:
        return await m.reply("âŒ Ø³Ù„Ø¨Ø±ÛŒØªÛŒ Ù¾ÛŒØ¯Ø§ Ù†Ø´Ø¯.")
    user(m.chat.id, m.from_user.id, m.from_user.full_name)
    owned = c.execute("SELECT 1 FROM collections WHERE chat_id=? AND user_id=? AND celeb=?", (m.chat.id, m.from_user.id, name)).fetchone()
    if not owned:
        return await m.reply("âŒ Ø§ÛŒÙ† Ø³Ù„Ø¨Ø±ÛŒØªÛŒ Ø±Ùˆ Ù†Ø¯Ø§Ø±ÛŒ!")
    # cancel any previous listing for this celeb
    c.execute("UPDATE listings SET active=0 WHERE chat_id=? AND seller_id=? AND celeb=?", (m.chat.id, m.from_user.id, name))
    cur = c.execute("INSERT INTO listings(chat_id, seller_id, celeb, price) VALUES(?,?,?,?)", (m.chat.id, m.from_user.id, name, price))
    db.commit()
    lid = cur.lastrowid
    tier, orig_price, spin, photo_url = CELEBS[name]
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"ðŸ›’ Ø®Ø±ÛŒØ¯ Ø¨Ù‡ Ù‚ÛŒÙ…Øª {price} Ø³Ø§Ù†Øª", callback_data=f"buyoff:{lid}")
    ]])
    caption = (
        f"ðŸª ÙØ±ÙˆØ´ Ø³Ù„Ø¨Ø±ÛŒØªÛŒ!\n\n"
        f"ðŸ‘‘ {name}\n"
        f"ðŸ’° Ù‚ÛŒÙ…Øª: {price} Ø³Ø§Ù†Øª\n"
        f"ðŸ‘¤ ÙØ±ÙˆØ´Ù†Ø¯Ù‡: {m.from_user.full_name}"
    )
    photo = await resolve_photo(photo_url) if photo_url else None
    try:
        if photo:
            sent = await m.bot.send_photo(m.chat.id, photo, caption=caption, reply_markup=kb)
            if isinstance(photo, BufferedInputFile):
                cache_photo(photo_url, sent)
        else:
            await m.reply(caption, reply_markup=kb)
    except Exception as e:
        print(f"[list] Ø®Ø·Ø§ Ø¯Ø± Ø§Ø±Ø³Ø§Ù„ Ø¹Ú©Ø³ {name}: {e}")
        await m.reply(caption, reply_markup=kb)

@dp.callback_query(F.data.startswith("buyoff:"))
async def buyoff(q: CallbackQuery):
    lid = int(q.data.split(":")[1])
    row = c.execute("SELECT chat_id, seller_id, celeb, price, active FROM listings WHERE id=?", (lid,)).fetchone()
    if not row or row[4] == 0:
        return await q.answer("âŒ Ø§ÛŒÙ† Ø¢Ú¯Ù‡ÛŒ Ø¯ÛŒÚ¯Ù‡ ÙØ¹Ø§Ù„ Ù†ÛŒØ³Øª!", show_alert=True)
    chat_id, seller_id, name, price, _ = row
    buyer_id = q.from_user.id
    if buyer_id == seller_id:
        return await q.answer("âŒ Ù†Ù…ÛŒØªÙˆÙ†ÛŒ Ø§Ø² Ø®ÙˆØ¯Øª Ø¨Ø®Ø±ÛŒ!", show_alert=True)
    user(chat_id, buyer_id, q.from_user.full_name)
    buyer_size = get_size(chat_id, buyer_id)
    if buyer_size < price:
        return await q.answer("âŒ Ø³Ø§Ù†Øª Ú©Ø§ÙÛŒ Ù†Ø¯Ø§Ø±ÛŒ!", show_alert=True)
    # transfer
    c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?", (price, chat_id, buyer_id))
    c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?", (price, chat_id, seller_id))
    c.execute("DELETE FROM collections WHERE chat_id=? AND user_id=? AND celeb=?", (chat_id, seller_id, name))
    c.execute("INSERT INTO collections(chat_id, user_id, celeb) VALUES(?,?,?)", (chat_id, buyer_id, name))
    c.execute("UPDATE listings SET active=0 WHERE id=?", (lid,))
    db.commit()
    seller_name = get_name(chat_id, seller_id)
    await q.message.edit_caption(
        caption=(
            f"âœ… Ù…Ø¹Ø§Ù…Ù„Ù‡ Ø§Ù†Ø¬Ø§Ù… Ø´Ø¯!\n\n"
            f"ðŸ‘‘ {name}\n"
            f"ðŸ’° Ù‚ÛŒÙ…Øª: {price} Ø³Ø§Ù†Øª\n"
            f"ðŸ›’ Ø®Ø±ÛŒØ¯Ø§Ø±: {q.from_user.full_name}\n"
            f"ðŸ’¸ ÙØ±ÙˆØ´Ù†Ø¯Ù‡: {seller_name}"
        )
    )
    await q.answer("âœ… Ø®Ø±ÛŒØ¯ Ù…ÙˆÙÙ‚!")

@dp.message(Command("sell"))
async def sell(m:Message):
    name=strip_command(m.text)
    if name not in CELEBS:
        return await m.reply("âŒ Ø³Ù„Ø¨Ø±ÛŒØªÛŒ Ù¾ÛŒØ¯Ø§ Ù†Ø´Ø¯.")
    user(m.chat.id,m.from_user.id,m.from_user.full_name)
    owned=c.execute(
        "SELECT paid_price FROM collections WHERE chat_id=? AND user_id=? AND celeb=?",
        (m.chat.id,m.from_user.id,name)
    ).fetchone()
    if not owned:
        return await m.reply("âŒ Ø§ÛŒÙ† Ø³Ù„Ø¨Ø±ÛŒØªÛŒ Ø±Ùˆ Ù†Ø¯Ø§Ø±ÛŒ!")
    paid=owned[0]
    c.execute("DELETE FROM collections WHERE chat_id=? AND user_id=? AND celeb=?",(m.chat.id,m.from_user.id,name))
    c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?",(paid,m.chat.id,m.from_user.id))
    db.commit()
    await m.reply(f"ðŸ’¸ ÙØ±ÙˆØ´ Ù…ÙˆÙÙ‚!\n\nðŸ‘‘ {name}\nðŸ’° {paid} Ø³Ø§Ù†Øª Ø¨Ù‡ Ø­Ø³Ø§Ø¨Øª Ø§Ø¶Ø§ÙÙ‡ Ø´Ø¯!")

LOCK_COSTS = {"PH": 75, "S": 60, "A": 50, "B": 25}

@dp.message(Command("lock"))
async def lock_celeb(m:Message):
    name = strip_command(m.text)
    if name not in CELEBS:
        return await m.reply("âŒ Ø³Ù„Ø¨Ø±ÛŒØªÛŒ Ù¾ÛŒØ¯Ø§ Ù†Ø´Ø¯.")
    tier_key = CELEBS[name][0]
    if tier_key not in LOCK_COSTS:
        return await m.reply("âŒ Ø§ÛŒÙ† Ø³Ù„Ø¨Ø±ÛŒØªÛŒ Ù†ÛŒØ§Ø² Ø¨Ù‡ Ù‚ÙÙ„ Ù†Ø¯Ø§Ø±Ù‡!")
    lock_cost = LOCK_COSTS[tier_key]
    user(m.chat.id, m.from_user.id, m.from_user.full_name)
    owned = c.execute("SELECT locked FROM collections WHERE chat_id=? AND user_id=? AND celeb=?", (m.chat.id, m.from_user.id, name)).fetchone()
    if not owned:
        return await m.reply("âŒ Ø§ÛŒÙ† Ø³Ù„Ø¨Ø±ÛŒØªÛŒ Ø±Ùˆ Ù†Ø¯Ø§Ø±ÛŒ!")
    if owned[0] == 1:
        return await m.reply("ðŸ”’ Ø§ÛŒÙ† Ø³Ù„Ø¨Ø±ÛŒØªÛŒ Ù‚Ø¨Ù„Ø§Ù‹ Ù‚ÙÙ„Ù‡!")
    size = get_size(m.chat.id, m.from_user.id)
    if size < lock_cost:
        return await m.reply(f"âŒ Ø¨Ø±Ø§ÛŒ Ù‚ÙÙ„ Ú©Ø±Ø¯Ù† Ø¨Ù‡ {lock_cost} Ø³Ø§Ù†Øª Ù†ÛŒØ§Ø² Ø¯Ø§Ø±ÛŒ!")
    c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?", (lock_cost, m.chat.id, m.from_user.id))
    c.execute("UPDATE collections SET locked=1 WHERE chat_id=? AND user_id=? AND celeb=?", (m.chat.id, m.from_user.id, name))
    db.commit()
    await m.reply(f"ðŸ”’ {name} Ù‚ÙÙ„ Ø´Ø¯!\n\nðŸ’° {lock_cost} Ø³Ø§Ù†Øª Ú©Ø³Ø± Ø´Ø¯.\nØ­Ø§Ù„Ø§ Ú©Ø³ÛŒ Ø¯ÛŒÚ¯Ù‡ Ù†Ù…ÛŒØªÙˆÙ†Ù‡ Ø§ÛŒÙ† Ø³Ù„Ø¨Ø±ÛŒØªÛŒ Ø±Ùˆ Ø¨Ø®Ø±Ù‡.")

@dp.message(Command("gloan"))
async def gloan(m:Message):
    try:
        amt = int(m.text.split()[1])
    except:
        return await m.reply("Usage: /gloan [Ù…Ù‚Ø¯Ø§Ø±]\nÙ…Ø«Ø§Ù„: /gloan 50")
    if amt < 1 or amt > 50:
        return await m.reply("âŒ Ø­Ø¯Ø§Ú©Ø«Ø± ÙˆØ§Ù… Ø§Ø² Ø¨Ø§Ø²ÛŒ 50 Ø³Ø§Ù†ØªÙ‡!")
    user(m.chat.id, m.from_user.id, m.from_user.full_name)
    existing = c.execute("SELECT amount, due_time FROM game_loans WHERE chat_id=? AND user_id=?", (m.chat.id, m.from_user.id)).fetchone()
    if existing:
        due = existing[1]
        rem = (due - int(time.time())) // 3600
        return await m.reply(f"âŒ Ù‚Ø¨Ù„Ø§Ù‹ {existing[0]} Ø³Ø§Ù†Øª ÙˆØ§Ù… Ø¯Ø§Ø±ÛŒ!\nâ³ {rem} Ø³Ø§Ø¹Øª ØªØ§ Ù…ÙˆØ¹Ø¯ Ù¾Ø±Ø¯Ø§Ø®Øª")
    due_time = int(time.time()) + 24*60*60
    c.execute("INSERT OR REPLACE INTO game_loans(chat_id, user_id, amount, due_time) VALUES(?,?,?,?)", (m.chat.id, m.from_user.id, amt, due_time))
    c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?", (amt, m.chat.id, m.from_user.id))
    db.commit()
    await m.reply(
        f"ðŸ’° ÙˆØ§Ù… Ø§Ø² Ø¨Ø§Ø²ÛŒ\n\n"
        f"ðŸ’µ Ù…Ù‚Ø¯Ø§Ø±: {amt} Ø³Ø§Ù†Øª\n"
        f"â³ Ù…Ù‡Ù„Øª Ù¾Ø±Ø¯Ø§Ø®Øª: Û²Û´ Ø³Ø§Ø¹Øª\n\n"
        f"Ø¨Ø±Ø§ÛŒ Ù¾Ø±Ø¯Ø§Ø®Øª: /gpay {amt}"
    )

@dp.message(Command("gpay"))
async def gpay(m:Message):
    user(m.chat.id, m.from_user.id, m.from_user.full_name)
    loan = c.execute("SELECT amount, due_time FROM game_loans WHERE chat_id=? AND user_id=?", (m.chat.id, m.from_user.id)).fetchone()
    if not loan:
        return await m.reply("âŒ ÙˆØ§Ù…ÛŒ Ù†Ø¯Ø§Ø±ÛŒ!")
    amt, due_time = loan
    size = get_size(m.chat.id, m.from_user.id)
    if size < amt:
        return await m.reply(f"âŒ Ø³Ø§Ù†Øª Ú©Ø§ÙÛŒ Ù†Ø¯Ø§Ø±ÛŒ! Ø¨Ø§ÛŒØ¯ {amt} Ø³Ø§Ù†Øª Ø¯Ø§Ø´ØªÙ‡ Ø¨Ø§Ø´ÛŒ.")
    c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?", (amt, m.chat.id, m.from_user.id))
    c.execute("DELETE FROM game_loans WHERE chat_id=? AND user_id=?", (m.chat.id, m.from_user.id))
    db.commit()
    await m.reply(f"âœ… ÙˆØ§Ù… {amt} Ø³Ø§Ù†Øª Ù¾Ø±Ø¯Ø§Ø®Øª Ø´Ø¯!")

async def check_loans(bot):
    while True:
        await asyncio.sleep(60)
        now = int(time.time())
        overdue = c.execute("SELECT chat_id, user_id, amount FROM game_loans WHERE due_time<?", (now,)).fetchall()
        for chat_id, uid, amt in overdue:
            size_row = c.execute("SELECT size FROM users WHERE chat_id=? AND user_id=?", (chat_id, uid)).fetchone()
            if not size_row:
                continue
            size = size_row[0]
            paid = 0
            msg = f"âš ï¸ ÙˆØ§Ù… {amt} Ø³Ø§Ù†Øª Ù…ÙˆØ¹Ø¯Ø´ Ú¯Ø°Ø´Øª!\n\n"
            # sell celebs to cover debt
            if size < amt:
                celebs = c.execute("SELECT celeb, paid_price FROM collections WHERE chat_id=? AND user_id=? ORDER BY paid_price DESC", (chat_id, uid)).fetchall()
                for celeb, paid_price in celebs:
                    if paid >= amt:
                        break
                    c.execute("DELETE FROM collections WHERE chat_id=? AND user_id=? AND celeb=?", (chat_id, uid, celeb))
                    c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?", (paid_price, chat_id, uid))
                    paid += paid_price
                    msg += f"ðŸ’¸ {celeb} ÙØ±ÙˆØ®ØªÙ‡ Ø´Ø¯ (+{paid_price} Ø³Ø§Ù†Øª)\n"
                db.commit()
                size = c.execute("SELECT size FROM users WHERE chat_id=? AND user_id=?", (chat_id, uid)).fetchone()[0]
            # deduct what we can
            deduct = min(amt, size)
            c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?", (deduct, chat_id, uid))
            remaining = amt - deduct
            if remaining > 0:
                c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?", (remaining, chat_id, uid))
                msg += f"ðŸ“‰ {remaining} Ø³Ø§Ù†Øª Ø¨Ø¯Ù‡ÛŒ â€” Ø­Ø³Ø§Ø¨ Ù…Ù†ÙÛŒ Ø´Ø¯!"
            else:
                msg += f"âœ… {amt} Ø³Ø§Ù†Øª Ú©Ø³Ø± Ø´Ø¯."
            c.execute("DELETE FROM game_loans WHERE chat_id=? AND user_id=?", (chat_id, uid))
            db.commit()
            try:
                await bot.send_message(uid, msg)
            except:
                pass


# ===== Ù…Ø²Ø§ÛŒØ¯Ù‡ (Ú†Ù†Ø¯ØªØ§ Ù‡Ù…Ø²Ù…Ø§Ù†) =====
AUCTION_IDLE_SECONDS = 12 * 3600   # Ø§Ú¯Ù‡ Û±Û² Ø³Ø§Ø¹Øª Ù¾ÛŒØ´Ù†Ù‡Ø§Ø¯ Ø¨Ø§Ù„Ø§ØªØ±ÛŒ Ù†ÛŒÙˆÙ…Ø¯ØŒ Ø¢Ø®Ø±ÛŒÙ† Ù¾ÛŒØ´Ù†Ù‡Ø§Ø¯ Ø¨Ø±Ù†Ø¯Ù‡â€ŒØ³Øª
AUCTION_START_BID = 10             # Ø­Ø¯Ø§Ù‚Ù„ Ù¾ÛŒØ´Ù†Ù‡Ø§Ø¯ Ø§ÙˆÙ„ (Ø³Ø§Ù†Øª)
AUCTION_MIN_INCREMENT = 5          # Ø­Ø¯Ø§Ù‚Ù„ Ø§ÙØ²Ø§ÛŒØ´ Ù†Ø³Ø¨Øª Ø¨Ù‡ Ù¾ÛŒØ´Ù†Ù‡Ø§Ø¯ Ù‚Ø¨Ù„ÛŒ (Ø³Ø§Ù†Øª)

_AUCTION_COLS = "id,name,photo,top_bid,top_bidder,top_bidder_name,last_activity,msg_id"

def get_active_auctions(chat_id):
    return c.execute(
        f"SELECT {_AUCTION_COLS} FROM auctions WHERE chat_id=? AND status='active' ORDER BY id", (chat_id,)
    ).fetchall()

def resolve_auction(m, token=None):
    """Ù…Ø²Ø§ÛŒØ¯Ù‡â€ŒÛŒ Ù…ÙˆØ±Ø¯Ù†Ø¸Ø± Ø±Ùˆ Ù¾ÛŒØ¯Ø§ Ù…ÛŒâ€ŒÚ©Ù†Ù‡: Ø¨Ø§ Ø´Ù…Ø§Ø±Ù‡ØŒ ÛŒØ§ Ø±ÛŒÙ¾Ù„Ø§ÛŒ Ø±ÙˆÛŒ Ø¹Ú©Ø³Ø´ØŒ ÛŒØ§ Ø§Ú¯Ù‡ ÙÙ‚Ø· ÛŒÚ©ÛŒ ÙØ¹Ø§Ù„Ù‡ Ù‡Ù…ÙˆÙ†.
    Ø®Ø±ÙˆØ¬ÛŒ: (Ø±Ø¯ÛŒÙ Ù…Ø²Ø§ÛŒØ¯Ù‡ ÛŒØ§ NoneØŒ Ù…ØªÙ† Ø®Ø·Ø§ ÛŒØ§ None)"""
    rows = get_active_auctions(m.chat.id)
    if not rows:
        return None, "ðŸ“­ Ø§Ù„Ø§Ù† Ù‡ÛŒÚ† Ù…Ø²Ø§ÛŒØ¯Ù‡â€ŒØ§ÛŒ Ø¯Ø± Ø¬Ø±ÛŒØ§Ù† Ù†ÛŒØ³Øª."
    if token is not None:
        for r in rows:
            if r[0] == token:
                return r, None
        return None, f"âŒ Ù…Ø²Ø§ÛŒØ¯Ù‡â€ŒÛŒ ÙØ¹Ø§Ù„ÛŒ Ø¨Ø§ Ø´Ù…Ø§Ø±Ù‡â€ŒÛŒ #{token} Ù¾ÛŒØ¯Ø§ Ù†Ø´Ø¯."
    if m.reply_to_message:
        rid = m.reply_to_message.message_id
        for r in rows:
            if r[7] == rid:
                return r, None
    if len(rows) == 1:
        return rows[0], None
    listing = "\n".join(f"â€¢ #{r[0]} â€” {r[1]}" for r in rows)
    return None, f"ðŸ“Š Ú†Ù†Ø¯ØªØ§ Ù…Ø²Ø§ÛŒØ¯Ù‡ Ù‡Ù…Ø²Ù…Ø§Ù† ÙØ¹Ø§Ù„Ù‡ØŒ Ù…Ø´Ø®Øµ Ú©Ù† Ú©Ø¯ÙˆÙ…:\n{listing}\n\n(Ø´Ù…Ø§Ø±Ù‡â€ŒØ´ Ø±Ùˆ Ø¨Ù†ÙˆÛŒØ³ ÛŒØ§ Ø±ÙˆÛŒ Ø¹Ú©Ø³ Ù‡Ù…ÙˆÙ† Ù…Ø²Ø§ÛŒØ¯Ù‡ Ø±ÛŒÙ¾Ù„Ø§ÛŒ Ú©Ù†)"

async def finalize_auction(bot, auction_id, cancel=False):
    row = c.execute("SELECT chat_id,name,top_bid,top_bidder,top_bidder_name,status FROM auctions WHERE id=?", (auction_id,)).fetchone()
    if not row or row[5] != 'active':
        return False
    chat_id, name, top_bid, top_bidder, top_bidder_name, _ = row
    c.execute("UPDATE auctions SET status=? WHERE id=?", ('cancelled' if cancel else 'ended', auction_id))
    if cancel and top_bidder:
        c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?", (top_bid, chat_id, top_bidder))
    delivered = False
    if not cancel and top_bidder and name in CELEBS:
        c.execute("INSERT INTO collections(chat_id,user_id,celeb,paid_price) VALUES(?,?,?,?)", (chat_id, top_bidder, name, top_bid))
        delivered = True
    db.commit()
    if cancel:
        txt = f"ðŸ”¨ Ù…Ø²Ø§ÛŒØ¯Ù‡â€ŒÛŒ #{auction_id} (Â«{name}Â») Ù„ØºÙˆ Ø´Ø¯."
        if top_bidder:
            txt += f"\nðŸ’¸ {top_bid} Ø³Ø§Ù†Øª Ø¨Ù‡ {top_bidder_name} Ø¨Ø±Ú¯Ø´Øª."
    elif not top_bidder:
        txt = f"ðŸ”¨ Ù…Ø²Ø§ÛŒØ¯Ù‡â€ŒÛŒ #{auction_id} (Â«{name}Â») ØªÙ…ÙˆÙ… Ø´Ø¯ ÙˆÙ„ÛŒ Ù‡ÛŒÚ†â€ŒÚ©Ø³ Ù¾ÛŒØ´Ù†Ù‡Ø§Ø¯ÛŒ Ù†Ø¯Ø§Ø¯."
    else:
        txt = (
            f"ðŸ”¨ Ù…Ø²Ø§ÛŒØ¯Ù‡â€ŒÛŒ #{auction_id} ØªÙ…ÙˆÙ… Ø´Ø¯!\n\n"
            f"ðŸŽ {name}\n"
            f"ðŸ‘‘ Ø¨Ø±Ù†Ø¯Ù‡: {top_bidder_name}\n"
            f"ðŸ’° Ù…Ø¨Ù„Øº Ù†Ù‡Ø§ÛŒÛŒ: {top_bid} Ø³Ø§Ù†Øª"
        )
        if delivered:
            txt += "\n\nâœ… Ø¨Ù‡ Ú©Ù„Ú©Ø³ÛŒÙˆÙ† Ø¨Ø±Ù†Ø¯Ù‡ Ø§Ø¶Ø§ÙÙ‡ Ø´Ø¯!"
    try:
        await bot.send_message(chat_id, txt)
    except Exception:
        logger.exception("auction announce failed")
    return True

async def auction_loop(bot):
    while True:
        await asyncio.sleep(60)
        try:
            now = int(time.time())
            due = c.execute(
                "SELECT id FROM auctions WHERE status='active' AND ?-last_activity>=?",
                (now, AUCTION_IDLE_SECONDS)
            ).fetchall()
            for (aid,) in due:
                await finalize_auction(bot, aid)
        except Exception:
            logger.exception("auction_loop error")

@dp.message(Command("auction"))
async def auction_start(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return await m.reply("âŒ Ø¯Ø³ØªØ±Ø³ÛŒ Ù†Ø¯Ø§Ø±ÛŒØ¯!")
    if m.chat.type == "private":
        return await m.reply("âŒ Ø§ÛŒÙ† Ø¯Ø³ØªÙˆØ± Ø±Ùˆ Ø¨Ø§ÛŒØ¯ ØªÙˆ Ú¯Ø±ÙˆÙ‡ Ø¨Ø²Ù†ÛŒ.")
    raw = m.text.split(maxsplit=1)
    args = raw[1].strip() if len(raw) > 1 else ""
    photo = name = None
    if m.reply_to_message and m.reply_to_message.photo:
        photo = m.reply_to_message.photo[-1].file_id
        name = args
    else:
        parts = args.split(maxsplit=1)
        if len(parts) == 2:
            photo, name = parts[0], parts[1].strip()
    if not photo or not name:
        return await m.reply(
            "Ø§Ø³ØªÙØ§Ø¯Ù‡:\n/auction [file_id Ø¹Ú©Ø³] [Ø§Ø³Ù…]\n\n"
            "ÛŒØ§ Ø±ÙˆÛŒ ÛŒÙ‡ Ø¹Ú©Ø³ Ø±ÛŒÙ¾Ù„Ø§ÛŒ Ú©Ù† Ùˆ Ø¨Ù†ÙˆÛŒØ³:\n/auction [Ø§Ø³Ù…]\n\n"
            "Ù…ÛŒâ€ŒØªÙˆÙ†ÛŒ Ù‡Ø±Ú†Ù†Ø¯ØªØ§ Ù…Ø²Ø§ÛŒØ¯Ù‡ Ù‡Ù…Ø²Ù…Ø§Ù† Ø¨Ø°Ø§Ø±ÛŒ."
        )
    now = int(time.time())
    cur = c.execute(
        "INSERT INTO auctions(chat_id,name,photo,status,last_activity,created_at) VALUES(?,?,?,'active',?,?)",
        (m.chat.id, name, photo, now, now)
    )
    aid = cur.lastrowid
    db.commit()
    caption = (
        f"ðŸ”¨ Ù…Ø²Ø§ÛŒØ¯Ù‡â€ŒÛŒ #{aid} Ø´Ø±ÙˆØ¹ Ø´Ø¯!\n\n"
        f"ðŸŽ {name}\n"
        f"ðŸ’° Ø­Ø¯Ø§Ù‚Ù„ Ù¾ÛŒØ´Ù†Ù‡Ø§Ø¯ Ø§ÙˆÙ„: {AUCTION_START_BID} Ø³Ø§Ù†Øª\n"
        f"ðŸ“ˆ Ù‡Ø± Ù¾ÛŒØ´Ù†Ù‡Ø§Ø¯ Ø¬Ø¯ÛŒØ¯ Ø­Ø¯Ø§Ù‚Ù„ {AUCTION_MIN_INCREMENT} Ø³Ø§Ù†Øª Ø¨ÛŒØ´ØªØ± Ø§Ø² Ù‚Ø¨Ù„ÛŒ\n"
        f"â³ Ù‡Ø±Ú©Ø³ {AUCTION_IDLE_SECONDS//3600} Ø³Ø§Ø¹Øª Ø¨Ø¯ÙˆÙ† Ù¾ÛŒØ´Ù†Ù‡Ø§Ø¯ Ø¨Ø§Ù„Ø§ØªØ± Ø¨Ù…ÙˆÙ†Ù‡ØŒ Ø¨Ø±Ù†Ø¯Ù‡â€ŒØ³Øª (Ù‡Ø± Ù¾ÛŒØ´Ù†Ù‡Ø§Ø¯ Ø¬Ø¯ÛŒØ¯ ØªØ§ÛŒÙ…Ø± Ø±Ùˆ Ø§Ø² Ø§ÙˆÙ„ Ù…ÛŒâ€ŒÚ©Ù†Ù‡)\n\n"
        f"Ø¨Ø±Ø§ÛŒ Ù¾ÛŒØ´Ù†Ù‡Ø§Ø¯: /bid {aid} [Ù…Ø¨Ù„Øº]\n"
        f"ÛŒØ§ Ø±ÙˆÛŒ Ù‡Ù…ÛŒÙ† Ø¹Ú©Ø³ Ø±ÛŒÙ¾Ù„Ø§ÛŒ Ú©Ù† Ùˆ Ø¨Ù†ÙˆÛŒØ³ /bid [Ù…Ø¨Ù„Øº]"
    )
    try:
        sent = await m.bot.send_photo(m.chat.id, photo, caption=caption)
    except (TelegramBadRequest, TelegramForbiddenError):
        c.execute("DELETE FROM auctions WHERE id=?", (aid,))
        db.commit()
        return await m.reply("âŒ Ø§ÛŒÙ† file_id Ù…Ø¹ØªØ¨Ø± Ù†ÛŒØ³Øª ÛŒØ§ Ø¨Ø±Ø§ÛŒ Ø§ÛŒÙ† Ø±Ø¨Ø§Øª Ú©Ø§Ø± Ù†Ù…ÛŒâ€ŒÚ©Ù†Ù‡. Ø¨Ø§ /getfileid ÛŒÙ‡ file_id Ø¯Ø±Ø³Øª Ø¨Ú¯ÛŒØ±.")
    c.execute("UPDATE auctions SET msg_id=? WHERE id=?", (sent.message_id, aid))
    db.commit()

@dp.message(Command("bid"))
async def auction_bid(m: Message):
    if m.chat.type == "private":
        return await m.reply("âŒ Ù¾ÛŒØ´Ù†Ù‡Ø§Ø¯ Ø±Ùˆ Ø¨Ø§ÛŒØ¯ ØªÙˆ Ú¯Ø±ÙˆÙ‡ Ø¨Ø¯ÛŒ.")
    args = [a.lstrip("#") for a in m.text.split()[1:]]
    token = None
    try:
        if len(args) == 1:
            amount = int(args[0])
        elif len(args) == 2:
            token, amount = int(args[0]), int(args[1])
        else:
            raise ValueError
    except ValueError:
        return await m.reply("Ø§Ø³ØªÙØ§Ø¯Ù‡:\n/bid [Ù…Ø¨Ù„Øº]\n/bid [Ø´Ù…Ø§Ø±Ù‡â€ŒÛŒ Ù…Ø²Ø§ÛŒØ¯Ù‡] [Ù…Ø¨Ù„Øº]\n\n(ÛŒØ§ Ø±ÙˆÛŒ Ø¹Ú©Ø³ Ù…Ø²Ø§ÛŒØ¯Ù‡ Ø±ÛŒÙ¾Ù„Ø§ÛŒ Ú©Ù† Ùˆ Ø¨Ù†ÙˆÛŒØ³ /bid [Ù…Ø¨Ù„Øº])")
    a, err = resolve_auction(m, token)
    if err:
        return await m.reply(err)
    aid, item, _photo, top_bid, top_bidder, top_name, _last, _mid = a
    uid = m.from_user.id
    user(m.chat.id, uid, m.from_user.full_name)
    min_required = AUCTION_START_BID if not top_bidder else top_bid + AUCTION_MIN_INCREMENT
    if amount < min_required:
        return await m.reply(f"âŒ Ù¾ÛŒØ´Ù†Ù‡Ø§Ø¯Øª Ø¨Ø±Ø§ÛŒ Ù…Ø²Ø§ÛŒØ¯Ù‡â€ŒÛŒ #{aid} Ø¨Ø§ÛŒØ¯ Ø­Ø¯Ø§Ù‚Ù„ {min_required} Ø³Ø§Ù†Øª Ø¨Ø§Ø´Ù‡.")
    available = get_size(m.chat.id, uid) + (top_bid if top_bidder == uid else 0)
    if available < amount:
        return await m.reply("âŒ Ø³Ø§Ù†Øª Ú©Ø§ÙÛŒ Ù†Ø¯Ø§Ø±ÛŒ.")
    if top_bidder and top_bidder != uid:
        c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?", (top_bid, m.chat.id, top_bidder))
    if top_bidder == uid:
        c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?", (amount - top_bid, m.chat.id, uid))
    else:
        c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?", (amount, m.chat.id, uid))
    c.execute(
        "UPDATE auctions SET top_bid=?, top_bidder=?, top_bidder_name=?, last_activity=? WHERE id=?",
        (amount, uid, m.from_user.full_name, int(time.time()), aid)
    )
    db.commit()
    await m.reply(
        f"ðŸ”¨ {m.from_user.full_name} Ù¾ÛŒØ´Ù†Ù‡Ø§Ø¯ {amount} Ø³Ø§Ù†Øª Ø¯Ø§Ø¯ Ø¨Ø±Ø§ÛŒ Â«{item}Â» (Ù…Ø²Ø§ÛŒØ¯Ù‡â€ŒÛŒ #{aid})!\n"
        f"â³ ØªØ§ÛŒÙ…Ø± {AUCTION_IDLE_SECONDS//3600} Ø³Ø§Ø¹ØªÙ‡â€ŒÛŒ Ø§ÛŒÙ† Ù…Ø²Ø§ÛŒØ¯Ù‡ Ø§Ø² Ø§ÙˆÙ„ Ø´Ø±ÙˆØ¹ Ø´Ø¯."
    )
    if top_bidder and top_bidder != uid:
        try:
            await m.bot.send_message(top_bidder, f"âš ï¸ Ù¾ÛŒØ´Ù†Ù‡Ø§Ø¯Øª Ø±ÙˆÛŒ Â«{item}Â» (#{aid}) Ø±Ø¯ Ø´Ø¯ Ùˆ {top_bid} Ø³Ø§Ù†ØªØª Ø¨Ø±Ú¯Ø´Øª. ÛŒÚ©ÛŒ {amount} Ø³Ø§Ù†Øª Ø¯Ø§Ø¯!")
        except Exception:
            pass

@dp.message(Command("auctionstatus"))
async def auction_status(m: Message):
    rows = get_active_auctions(m.chat.id)
    if not rows:
        return await m.reply("ðŸ“­ Ø§Ù„Ø§Ù† Ù‡ÛŒÚ† Ù…Ø²Ø§ÛŒØ¯Ù‡â€ŒØ§ÛŒ Ø¯Ø± Ø¬Ø±ÛŒØ§Ù† Ù†ÛŒØ³Øª.")
    now = int(time.time())
    txt = f"ðŸ”¨ Ù…Ø²Ø§ÛŒØ¯Ù‡â€ŒÙ‡Ø§ÛŒ ÙØ¹Ø§Ù„ ({len(rows)} ØªØ§)\n\n"
    for aid, item, _p, top_bid, top_bidder, top_name, last, _mid in rows:
        left = AUCTION_IDLE_SECONDS - (now - last)
        bid_txt = f"{top_bid} Ø³Ø§Ù†Øª ({top_name})" if top_bidder else "Ù‡Ù†ÙˆØ² Ù¾ÛŒØ´Ù†Ù‡Ø§Ø¯ÛŒ Ù†ÛŒÙˆÙ…Ø¯Ù‡"
        txt += f"#{aid} ðŸŽ {item}\n   ðŸ’° {bid_txt}\n   â³ {fmt_time(left)} ØªØ§ Ù¾Ø§ÛŒØ§Ù† (Ø§Ú¯Ù‡ Ù¾ÛŒØ´Ù†Ù‡Ø§Ø¯ Ø¨Ø§Ù„Ø§ØªØ±ÛŒ Ù†ÛŒØ§Ø¯)\n\n"
    txt += "Ø¨Ø±Ø§ÛŒ Ù¾ÛŒØ´Ù†Ù‡Ø§Ø¯: /bid [Ø´Ù…Ø§Ø±Ù‡] [Ù…Ø¨Ù„Øº]"
    await m.reply(txt)

AUCTION_COLLECTION_MAX_LINES = 15   # Ø­Ø¯Ø§Ú©Ø«Ø± ØªØ¹Ø¯Ø§Ø¯ Ù…Ø²Ø§ÛŒØ¯Ù‡â€ŒÛŒ Ø¨Ø±Ø¯Ø´Ø¯Ù‡ Ú©Ù‡ ØªÙˆ Ù„ÛŒØ³Øª Ù†Ø´ÙˆÙ† Ø¯Ø§Ø¯Ù‡ Ù…ÛŒâ€ŒØ´Ù‡

def build_auction_collection_text(chat_id, uid):
    """Ú©Ø§Ù„Ú©Ø´Ù† Ù…Ø²Ø§ÛŒØ¯Ù‡â€ŒÛŒ ÛŒÙ‡ Ù†ÙØ±: Ù¾ÛŒØ´Ù†Ù‡Ø§Ø¯Ù‡Ø§ÛŒ Ø¨Ø§Ù„Ø§ÛŒ ÙØ¹Ù„ÛŒ + Ù‡Ù…Ù‡â€ŒÛŒ Ù…Ø²Ø§ÛŒØ¯Ù‡â€ŒÙ‡Ø§ÛŒÛŒ Ú©Ù‡ Ù‚Ø¨Ù„Ø§Ù‹ Ø¨Ø±Ø¯ÛŒ (Ø§Ø² Ø¯ÛŒØªØ§Ø¨ÛŒØ³ Ø®ÙˆÙ†Ø¯Ù‡ Ù…ÛŒâ€ŒØ´Ù‡ØŒ Ù¾Ø³ Ø³Ø§Ø¨Ù‚Ù‡â€ŒÛŒ Ù‚Ø¨Ù„ Ø§Ø² Ø§ÛŒÙ† Ø¢Ù¾Ø¯ÛŒØª Ù‡Ù… Ù‡Ø³Øª)."""
    now = int(time.time())
    leading = c.execute(
        "SELECT id,name,top_bid,last_activity FROM auctions WHERE chat_id=? AND status='active' AND top_bidder=? ORDER BY top_bid DESC",
        (chat_id, uid)
    ).fetchall()
    won = c.execute(
        "SELECT id,name,top_bid FROM auctions WHERE chat_id=? AND status='ended' AND top_bidder=? ORDER BY id DESC",
        (chat_id, uid)
    ).fetchall()
    locked = sum(r[2] for r in leading)
    free = get_size(chat_id, uid)
    txt = f"ðŸ—‚ï¸ Ú©Ø§Ù„Ú©Ø´Ù† Ù…Ø²Ø§ÛŒØ¯Ù‡â€ŒÛŒ {get_name(chat_id, uid)}\n\n"
    txt += f"ðŸ”¥ Ù¾ÛŒØ´Ù†Ù‡Ø§Ø¯Ù‡Ø§ÛŒ Ø¨Ø§Ù„Ø§ÛŒ ÙØ¹Ù„ÛŒ ({len(leading)}):\n"
    if leading:
        for aid, name, bid, last in leading:
            left = AUCTION_IDLE_SECONDS - (now - last)
            txt += f"â€¢ #{aid} {name} â€” {bid} Ø³Ø§Ù†Øª (â³ {fmt_time(left)})\n"
        txt += f"ðŸ”’ Ø³Ø§Ù†Øª Ø¨Ù„ÙˆÚ©Ù‡â€ŒØ´Ø¯Ù‡ ØªÙˆ Ø§ÛŒÙ† Ù¾ÛŒØ´Ù†Ù‡Ø§Ø¯Ù‡Ø§: {locked}\n"
    else:
        txt += "Ù‡ÛŒÚ†â€ŒÚ©Ø¯ÙˆÙ…\n"
    txt += f"ðŸ’µ Ø³Ø§Ù†Øª Ø¢Ø²Ø§Ø¯ Ùˆ Ø¨Ø§Ù‚ÛŒâ€ŒÙ…ÙˆÙ†Ø¯Ù‡â€ŒØª: {free}\n\n"
    txt += f"ðŸ† Ù…Ø²Ø§ÛŒØ¯Ù‡â€ŒÙ‡Ø§ÛŒÛŒ Ú©Ù‡ Ø¨Ø±Ø¯ÛŒ ({len(won)}):\n"
    if won:
        for aid, name, bid in won[:AUCTION_COLLECTION_MAX_LINES]:
            txt += f"â€¢ #{aid} {name} â€” {bid} Ø³Ø§Ù†Øª\n"
        if len(won) > AUCTION_COLLECTION_MAX_LINES:
            txt += f"... Ùˆ {len(won) - AUCTION_COLLECTION_MAX_LINES} ØªØ§ÛŒ Ø¯ÛŒÚ¯Ù‡\n"
        txt += f"ðŸ’¸ Ø¬Ù…Ø¹ Ù¾ÙˆÙ„ÛŒ Ú©Ù‡ ØªØ§ Ø§Ù„Ø§Ù† Ø®Ø±Ø¬ Ø¨Ø±Ø¯Ù‡Ø§ Ø´Ø¯Ù‡: {sum(r[2] for r in won)} Ø³Ø§Ù†Øª"
    else:
        txt += "Ù‡Ù†ÙˆØ² Ù‡ÛŒÚ† Ù…Ø²Ø§ÛŒØ¯Ù‡â€ŒØ§ÛŒ Ù†Ø¨Ø±Ø¯ÛŒ"
    return txt

@dp.message(Command("myauctions"))
async def my_auctions(m: Message):
    if m.reply_to_message and m.reply_to_message.from_user and not m.reply_to_message.from_user.is_bot:
        target = m.reply_to_message.from_user.id
    else:
        target = m.from_user.id
        user(m.chat.id, target, m.from_user.full_name)
    await m.reply(build_auction_collection_text(m.chat.id, target))

@dp.message(Command("endauction"))
async def auction_end(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return await m.reply("âŒ Ø¯Ø³ØªØ±Ø³ÛŒ Ù†Ø¯Ø§Ø±ÛŒØ¯!")
    tokens = m.text.split()[1:]
    cancel = any(t.lower() == "cancel" for t in tokens)
    nums = [t.lstrip("#") for t in tokens if t.lower() != "cancel"]
    token = int(nums[0]) if nums and nums[0].isdigit() else None
    a, err = resolve_auction(m, token)
    if err:
        return await m.reply(err + "\n\nÙ…Ø«Ø§Ù„: /endauction [Ø´Ù…Ø§Ø±Ù‡]  ÛŒØ§  /endauction [Ø´Ù…Ø§Ø±Ù‡] cancel")
    await finalize_auction(m.bot, a[0], cancel=cancel)

# ===== Ø¨Ú©Ø§Ù¾ Ùˆ Ø¨Ø§Ø²Ú¯Ø±Ø¯Ø§Ù†ÛŒ Ø¯ÛŒØªØ§Ø¨ÛŒØ³ (Ø¨Ø±Ø§ÛŒ Ø¬Ø§Ø¨Ù‡â€ŒØ¬Ø§ÛŒÛŒ Ø¨ÛŒÙ† Ø§Ú©Ø§Ù†Øªâ€ŒÙ‡Ø§/Ø³Ø±ÙˆØ±Ù‡Ø§) =====
TG_UPLOAD_LIMIT = 49 * 1024 * 1024     # Ø³Ù‚Ù Ø¢Ù¾Ù„ÙˆØ¯ ÙØ§ÛŒÙ„ ØªÙˆØ³Ø· Ø±Ø¨Ø§Øª
TG_DOWNLOAD_LIMIT = 20 * 1024 * 1024   # Ø³Ù‚Ù Ø¯Ø§Ù†Ù„ÙˆØ¯ ÙØ§ÛŒÙ„ ØªÙˆØ³Ø· Ø±Ø¨Ø§Øª

def make_db_snapshot(path):
    """ÛŒÙ‡ Ú©Ù¾ÛŒ Ú©Ø§Ù…Ù„Ø§Ù‹ Ù‡Ù…Ø§Ù‡Ù†Ú¯ (consistent) Ø§Ø² Ø¯ÛŒØªØ§Ø¨ÛŒØ³ Ø²Ù†Ø¯Ù‡ Ù…ÛŒâ€ŒØ³Ø§Ø²Ù‡ØŒ Ø­ØªÛŒ ÙˆÙ‚ØªÛŒ Ø±Ø¨Ø§Øª Ø¯Ø§Ø±Ù‡ Ú©Ø§Ø± Ù…ÛŒâ€ŒÚ©Ù†Ù‡."""
    db.commit()
    dst = sqlite3.connect(path)
    try:
        db.backup(dst)
    finally:
        dst.close()

@dp.message(Command("backupdb"))
async def backup_db(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return await m.reply("âŒ Ø¯Ø³ØªØ±Ø³ÛŒ Ù†Ø¯Ø§Ø±ÛŒØ¯!")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    tmp = os.path.join(tempfile.gettempdir(), f"backup_{stamp}.db")
    try:
        make_db_snapshot(tmp)
        size = os.path.getsize(tmp)
        if size > TG_UPLOAD_LIMIT:
            return await m.reply(f"âŒ ÙØ§ÛŒÙ„ Ø¯ÛŒØªØ§Ø¨ÛŒØ³ ({size // (1024*1024)} Ù…Ú¯Ø§Ø¨Ø§ÛŒØª) Ø§Ø² Ø³Ù‚Ù Ø¢Ù¾Ù„ÙˆØ¯ ØªÙ„Ú¯Ø±Ø§Ù… Ø¨Ø²Ø±Ú¯â€ŒØªØ±Ù‡. Ø§Ø² Railway CLI Ø§Ø³ØªÙØ§Ø¯Ù‡ Ú©Ù†:\nrailway volume files download")
        users_n, chats_n = c.execute("SELECT COUNT(*), COUNT(DISTINCT chat_id) FROM users").fetchone()
        # Ù‡Ù…ÛŒØ´Ù‡ ØªÙˆ Ù¾ÛŒÙˆÛŒ Ø®ÙˆØ¯ Ø§Ø¯Ù…ÛŒÙ† Ù…ÛŒâ€ŒÙØ±Ø³ØªÙ‡ØŒ Ù†Ù‡ ØªÙˆ Ú¯Ø±ÙˆÙ‡ (Ø¯ÛŒØªØ§Ø¨ÛŒØ³ Ø§Ø·Ù„Ø§Ø¹Ø§Øª Ù‡Ù…Ù‡ Ø±Ùˆ Ø¯Ø§Ø±Ù‡)
        await m.bot.send_document(
            m.from_user.id,
            FSInputFile(tmp, filename=f"database_backup_{stamp}.db"),
            caption=f"ðŸ’¾ Ø¨Ú©Ø§Ù¾ Ø¯ÛŒØªØ§Ø¨ÛŒØ³\nðŸ‘¥ {users_n} Ú©Ø§Ø±Ø¨Ø± | ðŸ’¬ {chats_n} Ú¯Ø±ÙˆÙ‡\n\nØ¨Ø±Ø§ÛŒ Ø¨Ø§Ø²Ú¯Ø±Ø¯Ø§Ù†ÛŒ: Ù‡Ù…ÛŒÙ† ÙØ§ÛŒÙ„ Ø±Ùˆ ØªÙˆ Ù¾ÛŒÙˆÛŒ Ø±Ø¨Ø§Øª Ø¨ÙØ±Ø³Øª Ø¨Ø§ Ú©Ù¾Ø´Ù†:\n/restoredb CONFIRM"
        )
    except (TelegramForbiddenError, TelegramBadRequest):
        return await m.reply("âŒ Ù†ØªÙˆÙ†Ø³ØªÙ… ØªÙˆ Ù¾ÛŒÙˆÛŒ Ø¨Ù‡Øª Ø¨ÙØ±Ø³ØªÙ…. Ø§ÙˆÙ„ Ø±Ø¨Ø§Øª Ø±Ùˆ ØªÙˆ Ú†Øª Ø®ØµÙˆØµÛŒ Ø§Ø³ØªØ§Ø±Øª Ú©Ù†ØŒ Ø¨Ø¹Ø¯ Ø¯ÙˆØ¨Ø§Ø±Ù‡ Ø§Ù…ØªØ­Ø§Ù† Ú©Ù†.")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    if m.chat.type != "private":
        await m.reply("ðŸ“© ÙØ§ÛŒÙ„ Ø¨Ú©Ø§Ù¾ Ø±Ùˆ Ø¨Ø±Ø§Øª ØªÙˆ Ù¾ÛŒÙˆÛŒ ÙØ±Ø³ØªØ§Ø¯Ù….")

@dp.message(F.document, F.caption.startswith("/restoredb"))
@dp.message(Command("restoredb"))
async def restore_db(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return await m.reply("âŒ Ø¯Ø³ØªØ±Ø³ÛŒ Ù†Ø¯Ø§Ø±ÛŒØ¯!")
    if m.chat.type != "private":
        return await m.reply("âŒ Ø¨Ø§Ø²Ú¯Ø±Ø¯Ø§Ù†ÛŒ Ø±Ùˆ ÙÙ‚Ø· ØªÙˆ Ù¾ÛŒÙˆÛŒ Ø±Ø¨Ø§Øª Ø§Ù†Ø¬Ø§Ù… Ø¨Ø¯Ù‡ØŒ Ù†Ù‡ ØªÙˆ Ú¯Ø±ÙˆÙ‡.")
    raw = (m.text or m.caption or "")
    doc = m.document or (m.reply_to_message.document if m.reply_to_message and m.reply_to_message.document else None)
    # Ø­Ø±ÙˆÙ Ø¨Ø²Ø±Ú¯/Ú©ÙˆÚ†ÛŒÚ© Ùˆ Ú©Ø§Ø±Ø§Ú©ØªØ±Ù‡Ø§ÛŒ Ù†Ø§Ù…Ø±Ø¦ÛŒ (Ù…Ø«Ù„ RLM ØªÙˆ Ú©ÛŒØ¨ÙˆØ±Ø¯ ÙØ§Ø±Ø³ÛŒ) Ù…Ù‡Ù… Ù†ÛŒØ³ØªÙ†
    has_confirm = re.search(r"(?<![A-Za-z])confirm(?![A-Za-z])", raw, re.I) is not None
    if not has_confirm or not doc:
        logger.warning("restoredb rejected: raw=%r has_confirm=%s has_doc=%s", raw, has_confirm, bool(doc))
        return await m.reply(
            "âš ï¸ Ø§ÛŒÙ† Ú©Ø§Ø± Ú©Ù„ Ø¯ÛŒØªØ§Ø¨ÛŒØ³ ÙØ¹Ù„ÛŒ (Ù‡Ù…Ù‡â€ŒÛŒ Ú¯Ø±ÙˆÙ‡â€ŒÙ‡Ø§) Ø±Ùˆ Ø¨Ø§ ÙØ§ÛŒÙ„ Ø¨Ú©Ø§Ù¾ Ø¬Ø§ÛŒÚ¯Ø²ÛŒÙ† Ù…ÛŒâ€ŒÚ©Ù†Ù‡.\n\n"
            "ÙØ§ÛŒÙ„ Ø¨Ú©Ø§Ù¾ (.db) Ø±Ùˆ Ø¨ÙØ±Ø³Øª Ùˆ ØªÙˆ Ú©Ù¾Ø´Ù†Ø´ Ø¨Ù†ÙˆÛŒØ³:\n/restoredb CONFIRM\n"
            "(ÛŒØ§ Ø±ÙˆÛŒ ÙØ§ÛŒÙ„ Ø¨Ú©Ø§Ù¾ Ø±ÛŒÙ¾Ù„Ø§ÛŒ Ú©Ù† Ùˆ Ù‡Ù…ÛŒÙ† Ø±Ùˆ Ø¨Ù†ÙˆÛŒØ³)"
        )
    if doc.file_size and doc.file_size > TG_DOWNLOAD_LIMIT:
        return await m.reply("âŒ Ø§ÛŒÙ† ÙØ§ÛŒÙ„ Ø§Ø² Ø³Ù‚Ù Ø¯Ø§Ù†Ù„ÙˆØ¯ Ø±Ø¨Ø§Øª (Û²Û° Ù…Ú¯Ø§Ø¨Ø§ÛŒØª) Ø¨Ø²Ø±Ú¯â€ŒØªØ±Ù‡.")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    tmp = os.path.join(tempfile.gettempdir(), f"restore_{stamp}.db")
    try:
        await m.bot.download(doc, destination=tmp)
        try:
            chk = sqlite3.connect(tmp)
            integrity = chk.execute("PRAGMA integrity_check").fetchone()[0]
            has_users = chk.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'").fetchone() is not None
            chk.close()
        except sqlite3.DatabaseError:
            integrity, has_users = "bad", False
        if integrity != "ok" or not has_users:
            return await m.reply("âŒ Ø§ÛŒÙ† ÙØ§ÛŒÙ„ ÛŒÙ‡ Ø¯ÛŒØªØ§Ø¨ÛŒØ³ Ø³Ø§Ù„Ù…Ù Ø§ÛŒÙ† Ø¨Ø§Øª Ù†ÛŒØ³Øª. Ú†ÛŒØ²ÛŒ ØªØºÛŒÛŒØ± Ù†Ú©Ø±Ø¯.")
        # Ù‚Ø¨Ù„ Ø§Ø² Ø¬Ø§ÛŒÚ¯Ø²ÛŒÙ†ÛŒØŒ Ø§Ø² Ø¯ÛŒØªØ§Ø¨ÛŒØ³ ÙØ¹Ù„ÛŒ ÛŒÙ‡ Ú©Ù¾ÛŒ Ø§ÛŒÙ…Ù†ÛŒ Ú©Ù†Ø§Ø± ÙØ§ÛŒÙ„ Ø§ØµÙ„ÛŒ Ù…ÛŒâ€ŒØ°Ø§Ø±Ù‡
        safety = f"{DB}.pre_restore_{stamp}"
        make_db_snapshot(safety)
        db.commit()
        src = sqlite3.connect(tmp)
        try:
            src.backup(db)
        finally:
            src.close()
        db.commit()
        users_n, chats_n = c.execute("SELECT COUNT(*), COUNT(DISTINCT chat_id) FROM users").fetchone()
        await m.reply(
            f"âœ… Ø¯ÛŒØªØ§Ø¨ÛŒØ³ Ø¨Ø§Ø²Ú¯Ø±Ø¯Ø§Ù†ÛŒ Ø´Ø¯.\nðŸ‘¥ {users_n} Ú©Ø§Ø±Ø¨Ø± | ðŸ’¬ {chats_n} Ú¯Ø±ÙˆÙ‡\n\n"
            f"ðŸ›Ÿ Ú©Ù¾ÛŒ Ø§ÛŒÙ…Ù†ÛŒÙ Ø¯ÛŒØªØ§Ø¨ÛŒØ³ Ù‚Ø¨Ù„ÛŒ: {os.path.basename(safety)}\n\n"
            "Ø§Ú¯Ù‡ Ø§ÛŒÙ† Ø¨Ú©Ø§Ù¾ Ø§Ø² ÛŒÙ‡ Ù†Ø³Ø®Ù‡â€ŒÛŒ Ù‚Ø¯ÛŒÙ…ÛŒâ€ŒØªØ± Ú©Ø¯ Ø¨ÙˆØ¯Ù‡ØŒ ÛŒÙ‡ Ø¨Ø§Ø± Ø³Ø±ÙˆÛŒØ³ Ø±Ùˆ Ø±ÛŒâ€ŒØ§Ø³ØªØ§Ø±Øª/Ø±ÛŒâ€ŒØ¯ÛŒÙ¾Ù„ÙˆÛŒ Ú©Ù† ØªØ§ Ø¬Ø¯ÙˆÙ„â€ŒÙ‡Ø§ÛŒ Ø¬Ø¯ÛŒØ¯ Ø³Ø§Ø®ØªÙ‡ Ø¨Ø´Ù†."
        )
    except Exception:
        logger.exception("restore_db failed")
        await m.reply("âŒ Ø¨Ø§Ø²Ú¯Ø±Ø¯Ø§Ù†ÛŒ Ø¨Ø§ Ø®Ø·Ø§ Ù…ÙˆØ§Ø¬Ù‡ Ø´Ø¯. Ø¯ÛŒØªØ§Ø¨ÛŒØ³ ÙØ¹Ù„ÛŒ Ø¯Ø³Øªâ€ŒÙ†Ø®ÙˆØ±Ø¯Ù‡ Ù…ÙˆÙ†Ø¯ (Ø¬Ø²Ø¦ÛŒØ§Øª ØªÙˆ Ù„Ø§Ú¯).")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

@dp.message(Command("addcm"))
async def addcm(m:Message):
    if m.from_user.id not in ADMIN_IDS:
        return await m.reply("âŒ Ø¯Ø³ØªØ±Ø³ÛŒ Ù†Ø¯Ø§Ø±ÛŒØ¯!")
    try:
        parts = m.text.split()
        amount = int(parts[1])
    except:
        return await m.reply("Usage: /addcm [amount] (reply to a user)")
    if not m.reply_to_message:
        return await m.reply("Reply to a user to add cm.")
    target = m.reply_to_message.from_user.id
    user(m.chat.id, target, m.reply_to_message.from_user.full_name)
    c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?", (amount, m.chat.id, target))
    db.commit()
    new_size = get_size(m.chat.id, target)
    await m.reply(f"âœ… {amount} Ø³Ø§Ù†Øª Ø¨Ù‡ {m.reply_to_message.from_user.full_name} Ø§Ø¶Ø§ÙÙ‡ Ø´Ø¯!\nðŸ“ Ø§Ù†Ø¯Ø§Ø²Ù‡ Ø¬Ø¯ÛŒØ¯: {new_size} Ø³Ø§Ù†Øª")

@dp.message(Command("luckydrop"))
async def lucky_drop(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return await m.reply("âŒ Ø¯Ø³ØªØ±Ø³ÛŒ Ù†Ø¯Ø§Ø±ÛŒØ¯!")
    prize = 50
    try:
        parts = m.text.split()
        if len(parts) > 1:
            prize = int(parts[1])
    except:
        pass
    players = c.execute("SELECT user_id,name FROM users WHERE chat_id=?", (m.chat.id,)).fetchall()
    if not players:
        return await m.reply("âŒ Ù‡Ù†ÙˆØ² Ú©Ø³ÛŒ ØªÙˆ Ø§ÛŒÙ† Ú¯Ø±ÙˆÙ‡ Ø¨Ø§Ø²ÛŒ Ù†Ú©Ø±Ø¯Ù‡ Ú©Ù‡ Ù‚Ø±Ø¹Ù‡â€ŒÚ©Ø´ÛŒ Ø¨Ø´Ù‡.")
    winner_id, winner_name = random.choice(players)
    c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?", (prize, m.chat.id, winner_id))
    db.commit()
    new_size = get_size(m.chat.id, winner_id)
    await m.reply(f"ðŸŽ‰ Ù‚Ø±Ø¹Ù‡â€ŒÚ©Ø´ÛŒ Ø±Ù†Ø¯ÙˆÙ…!\n\nðŸ† {winner_name} Ø®ÙˆØ´â€ŒØ´Ø§Ù†Ø³ Ø¨ÙˆØ¯ Ùˆ {prize} Ø³Ø§Ù†Øª Ù…Ø¬Ø§Ù†ÛŒ Ú¯Ø±ÙØª!\nðŸ“ Ø§Ù†Ø¯Ø§Ø²Ù‡â€ŒÛŒ Ø¬Ø¯ÛŒØ¯Ø´: {new_size} Ø³Ø§Ù†Øª")

@dp.message(Command("resetgroup"))
async def reset_group(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return await m.reply("âŒ Ø¯Ø³ØªØ±Ø³ÛŒ Ù†Ø¯Ø§Ø±ÛŒØ¯!")
    parts = m.text.split()
    if len(parts) < 2 or parts[1] != "CONFIRM":
        return await m.reply(
            "âš ï¸ Ø§ÛŒÙ† Ú©Ø§Ø± Ù‡Ù…Ù‡â€ŒÛŒ Ø¯Ø§Ø¯Ù‡â€ŒÙ‡Ø§ÛŒ Ø§ÛŒÙ† Ú¯Ø±ÙˆÙ‡ Ø±Ùˆ Ú©Ø§Ù…Ù„Ø§Ù‹ Ùˆ Ø¨Ø±Ø§ÛŒ Ù‡Ù…ÛŒØ´Ù‡ Ù¾Ø§Ú© Ù…ÛŒâ€ŒÚ©Ù†Ù‡:\n"
            "Ø³Ø§ÛŒØ²/Ø§Ø³Ù¾Ø±Ù… Ù‡Ù…Ù‡ØŒ Ø±Ù†Ú©ØŒ Ù…Ø§ÙÛŒØ§ØŒ Ø¨ÙˆØ±Ø³ØŒ Ú©Ù„Ú©Ø³ÛŒÙˆÙ† Ø³Ù„Ø¨Ø±ÛŒØªÛŒâ€ŒÙ‡Ø§ØŒ ÙˆØ§Ù…â€ŒÙ‡Ø§ Ùˆ Ù…Ø²Ø±Ø¹Ù‡.\n\n"
            "Ø§Ú¯Ù‡ Ù…Ø·Ù…Ø¦Ù†ÛŒØŒ Ø¨Ù†ÙˆÛŒØ³:\n/resetgroup CONFIRM"
        )
    chat_id = m.chat.id
    # Ø¬Ø¯ÙˆÙ„â€ŒÙ‡Ø§ÛŒÛŒ Ú©Ù‡ Ù…Ø³ØªÙ‚ÛŒÙ… Ø³ØªÙˆÙ† chat_id Ø¯Ø§Ø±Ù†
    for table in (
        "users", "pvp_stats", "rank_stats", "loans", "listings",
        "game_loans", "mafia_battles", "mafia2_battles", "collections",
        "company_rounds", "company_options", "company_investments",
        "company_participants", "owned_companies",
        "farm_tiles", "farm_inventory", "farm_records", "auctions",
    ):
        c.execute(f"DELETE FROM {table} WHERE chat_id=?", (chat_id,))
    # Ø¬Ø¯ÙˆÙ„â€ŒÙ‡Ø§ÛŒÛŒ Ú©Ù‡ ÙÙ‚Ø· Ø§Ø² Ø·Ø±ÛŒÙ‚ battle_id Ø¨Ù‡ Ú¯Ø±ÙˆÙ‡ ÙˆØµÙ„Ù†
    c.execute("DELETE FROM mafia_members WHERE battle_id IN (SELECT id FROM mafia_battles WHERE chat_id=?)", (chat_id,))
    c.execute("DELETE FROM mafia2_members WHERE battle_id IN (SELECT id FROM mafia2_battles WHERE chat_id=?)", (chat_id,))
    db.commit()
    await m.reply("âœ… Ù‡Ù…Ù‡â€ŒÛŒ Ø¯Ø§Ø¯Ù‡â€ŒÙ‡Ø§ÛŒ Ø§ÛŒÙ† Ú¯Ø±ÙˆÙ‡ Ù¾Ø§Ú© Ø´Ø¯. Ø¨Ø§Ø²ÛŒ Ø§Ø² ØµÙØ± Ø´Ø±ÙˆØ¹ Ù…ÛŒâ€ŒØ´Ù‡.")


async def addsperm(m:Message):
    if m.from_user.id not in ADMIN_IDS:
        return await m.reply("âŒ Ø¯Ø³ØªØ±Ø³ÛŒ Ù†Ø¯Ø§Ø±ÛŒØ¯!")
    try:
        parts = m.text.split()
        amount = int(parts[1])
    except:
        return await m.reply("Usage: /addsperm [amount] (reply to a user)")
    if not m.reply_to_message:
        return await m.reply("Reply to a user to add sperm.")
    target = m.reply_to_message.from_user.id
    user(m.chat.id, target, m.reply_to_message.from_user.full_name)
    c.execute("UPDATE users SET sperm=sperm+? WHERE chat_id=? AND user_id=?", (amount, m.chat.id, target))
    db.commit()
    new_sperm = get_sperm(m.chat.id, target)
    await m.reply(f"âœ… {amount} Ø§Ø³Ù¾Ø±Ù… Ø¨Ù‡ {m.reply_to_message.from_user.full_name} Ø§Ø¶Ø§ÙÙ‡ Ø´Ø¯!\nðŸ§¬ Ø§Ø³Ù¾Ø±Ù… Ø¬Ø¯ÛŒØ¯: {new_sperm}")


@dp.message(Command("addspermall"))
async def addsperm_all(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return await m.reply("âŒ Ø¯Ø³ØªØ±Ø³ÛŒ Ù†Ø¯Ø§Ø±ÛŒØ¯!")
    try:
        amount = int(m.text.split()[1])
    except:
        return await m.reply("Usage: /addspermall [amount]\nÙ…Ø«Ø§Ù„: /addspermall 100")
    c.execute("UPDATE users SET sperm=sperm+? WHERE chat_id=?", (amount, m.chat.id))
    affected = c.rowcount
    db.commit()
    await m.reply(f"âœ… {amount} Ø§Ø³Ù¾Ø±Ù… Ø¨Ù‡ Ù‡Ù…Ù‡â€ŒÛŒ {affected} Ú©Ø§Ø±Ø¨Ø± Ø§ÛŒÙ† Ú¯Ø±ÙˆÙ‡ Ø§Ø¶Ø§ÙÙ‡ Ø´Ø¯!")


@dp.message(Command("addcb"))
async def addcb(m:Message):
    if m.from_user.id not in ADMIN_IDS:
        return await m.reply("âŒ Ø¯Ø³ØªØ±Ø³ÛŒ Ù†Ø¯Ø§Ø±ÛŒØ¯!")
    raw = strip_command(m.text)
    if not raw:
        return await m.reply(
            "Usage: /addcb [Ù†Ø§Ù… Ø³Ù„Ø¨Ø±ÛŒØªÛŒ] (reply to a user)\nÙ…Ø«Ø§Ù„: /addcb Dua Lipa\n\n"
            "Ø¨Ø±Ø§ÛŒ Ú¯Ø±ÙØªÙ† Ø³Ù„Ø¨Ø±ÛŒØªÛŒ Ø§Ø² Ú©Ø³ÛŒØŒ ÛŒÙ‡ Ù…Ù†ÙÛŒ Ø¬Ù„ÙˆØ´ Ø¨Ø°Ø§Ø±:\nÙ…Ø«Ø§Ù„: /addcb -Dua Lipa"
        )
    remove_mode = raw.startswith("-")
    name = raw[1:].strip() if remove_mode else raw
    if name not in CELEBS:
        return await m.reply("âŒ Ø³Ù„Ø¨Ø±ÛŒØªÛŒ Ù¾ÛŒØ¯Ø§ Ù†Ø´Ø¯.")
    if not m.reply_to_message:
        return await m.reply("Reply to a user to give/take the celeb.")
    target = m.reply_to_message.from_user.id
    user(m.chat.id, target, m.reply_to_message.from_user.full_name)
    already = c.execute("SELECT 1 FROM collections WHERE chat_id=? AND user_id=? AND celeb=?", (m.chat.id, target, name)).fetchone()
    if remove_mode:
        if not already:
            return await m.reply(f"âŒ {m.reply_to_message.from_user.full_name} Ø§ØµÙ„Ø§Ù‹ Ø§ÛŒÙ† Ø³Ù„Ø¨Ø±ÛŒØªÛŒ Ø±Ùˆ Ù†Ø¯Ø§Ø±Ù‡!")
        c.execute("DELETE FROM collections WHERE chat_id=? AND user_id=? AND celeb=?", (m.chat.id, target, name))
        db.commit()
        return await m.reply(f"ðŸ—‘ {name} Ø§Ø² {m.reply_to_message.from_user.full_name} Ú¯Ø±ÙØªÙ‡ Ø´Ø¯!")
    if already:
        return await m.reply(f"âŒ {m.reply_to_message.from_user.full_name} Ø§ÛŒÙ† Ø³Ù„Ø¨Ø±ÛŒØªÛŒ Ø±Ùˆ Ø¯Ø§Ø±Ù‡!")
    tier, price, spin, photo = CELEBS[name]
    c.execute("INSERT INTO collections(chat_id,user_id,celeb,paid_price,locked) VALUES(?,?,?,?,0)", (m.chat.id, target, name, price))
    db.commit()
    await m.reply(f"âœ… {name} Ø¨Ù‡ {m.reply_to_message.from_user.full_name} Ø¯Ø§Ø¯Ù‡ Ø´Ø¯!\nðŸ‘‘ Tier {tier}")


# ================== Ú©Ù…Ù¾Ø§Ù†ÛŒ Ú©ÛŒØ± (Ø¨Ø§Ø²Ø§Ø± Ø¨ÙˆØ±Ø³) ==================
# ÙØ±Ø¶ÛŒØ§Øª Ù¾ÛŒØ§Ø¯Ù‡â€ŒØ³Ø§Ø²ÛŒ (Ø§Ú¯Ù‡ ÙØ±Ù‚ Ø¯Ø§Ø´Øª Ø¨Ú¯Ùˆ Ø¹ÙˆØ¶ Ú©Ù†Ù…):
# - ÙÙ‚Ø· Ø§Ø¯Ù…ÛŒÙ† Ø¨Ø§Ø²Ø§Ø± Ø±Ùˆ Ø¨Ø§Ø²/Ø¨Ø³ØªÙ‡ Ù…ÛŒâ€ŒÚ©Ù†Ù‡ (/copen Ùˆ /cclose)
# - Ø¨ÛŒÙ† Ø¯ÙˆØªØ§ /copen Ù‡ÛŒÚ† Ù…Ø­Ø¯ÙˆØ¯ÛŒØª Ø²Ù…Ø§Ù†ÛŒ ÙˆØ¬ÙˆØ¯ Ù†Ø¯Ø§Ø±Ù‡Ø› Ø§Ø¯Ù…ÛŒÙ† Ù‡Ø± ÙˆÙ‚Øª Ø®ÙˆØ§Ø³Øª Ø¨Ø§Ø²/Ø¨Ø³ØªÙ‡ Ù…ÛŒâ€ŒÚ©Ù†Ù‡
# - Ø­Ø¯Ø§Ù‚Ù„ Ø¨ÙˆØ¯Ø¬Ù‡â€ŒÛŒ Ù‡Ø± Ø´Ø±Ú©Øª Ø±Ù†Ø¯ÙˆÙ…Ù‡ (Ø¨ÛŒÙ† Ûµ ØªØ§ Û±Ûµ Ø³Ø§Ù†Øª) Ùˆ Ø¨Ø±Ø§ÛŒ Ù‡Ø± Ø´Ø±Ú©Øª Ø¬Ø¯Ø§ ØªØ¹ÛŒÛŒÙ† Ù…ÛŒØ´Ù‡
# - Ù‡Ø± Ø³Ø±Ù…Ø§ÛŒÙ‡â€ŒÚ¯Ø°Ø§Ø±ÛŒ Ø¨Ø§ÛŒØ¯ Ø­Ø¯Ø§Ù‚Ù„ Û±Û°Ùª Ø³Ø§ÛŒØ² Ù„Ø­Ø¸Ù‡â€ŒØ§ÛŒ ÙØ±Ø¯ Ø¨Ø§Ø´Ù‡Ø› Ø³Ù‚ÙÛŒ Ø¨Ø±Ø§ÛŒ Ø­Ø¯Ø§Ú©Ø«Ø±Ø´ Ù†ÛŒØ³Øª (Ù†Ø§Ù…Ø­Ø¯ÙˆØ¯)
# - Ø´Ø±Ú©ØªÛŒ Ú©Ù‡ Ø¨ÛŒØ´ØªØ±ÛŒÙ† Ø³Ø±Ù…Ø§ÛŒÙ‡ Ø±Ùˆ Ø¬Ù…Ø¹ Ú©Ø±Ø¯Ù‡ Ø­Ø°Ù Ù…ÛŒØ´Ù‡ (Ú¯Ù†Ø¯Ù‡ Ø´Ø¯Ù‡, ØªØ±Ú©ÛŒØ¯Ù‡) + Ø´Ø±Ú©ØªÛŒ Ú©Ù‡ Ø¨Ù‡ Ø­Ø¯Ø§Ù‚Ù„ Ø¨ÙˆØ¯Ø¬Ù‡â€ŒÛŒ Ø®ÙˆØ¯Ø´ Ù†Ø±Ø³ÛŒØ¯Ù‡
# - Ø¨ÛŒÙ† Ø¨Ù‚ÛŒÙ‡ØŒ Ø¨ÛŒØ´ØªØ±ÛŒÙ† Ø³Ù‡Ù…â€ŒØ¯Ø§Ø± Ù‡Ø± Ø´Ø±Ú©ØªØŒ Ù‡Ù…ÙˆÙ† Ø´Ø±Ú©Øª Ø±Ùˆ Ø¨Ø§ Ú©Ù„ Ø³Ø±Ù…Ø§ÛŒÙ‡â€ŒÛŒ Ø¬Ù…Ø¹â€ŒØ´Ø¯Ù‡ ØªÙˆØ´ Ù…ÛŒâ€ŒØ¨Ø±Ù‡ (Ø¨Ù‚ÛŒÙ‡ Ø³Ø±Ù…Ø§ÛŒÙ‡â€ŒØ´ÙˆÙ† Ø±Ùˆ Ø§Ø² Ø¯Ø³Øª Ù…ÛŒØ¯Ù†)
# - Ù‡Ø± Ø´Ø±Ú©Øª Ø¨Ø¹Ø¯ Ø§Ø² Ø¨Ø±Ø¯ØŒ Ø±ÙˆØ²ÛŒ ÛŒÙ‡ Ø¨Ø§Ø± Û±Û°Ùª Ø§Ø±Ø²Ø´Ø´ Ø³ÙˆØ¯ Ù…ÛŒØ¯Ù‡
# - Ù‡Ø± Ø´Ø±Ú©Øª Û² ÛŒØ§ Û³ "ÛŒØ§Ø±" Ø±Ù†Ø¯ÙˆÙ… Ø¯Ø§Ø±Ù‡ Ú©Ù‡ ØµØ§Ø­Ø¨Ø´ Ù…ÛŒâ€ŒØªÙˆÙ†Ù‡ Ø¨Ø§ /hire Ø¨Ø®Ø±Ù‡ Ùˆ Ø¨Ø§ /useyar Ø¨ÙØ±Ø³ØªÙ‡ ØªÙˆÛŒ Ù†Ø¨Ø±Ø¯ Ù…Ø§ÙÛŒØ§ÛŒ ÙØ¹Ù„ÛŒØ´
#   (ÛŒØ§Ø± ÙÙ‚Ø· ØªØ¹Ø¯Ø§Ø¯ ØªÛŒÙ… Ø±Ùˆ Ø²ÛŒØ§Ø¯ Ù…ÛŒâ€ŒÚ©Ù†Ù‡Ø› Ø³Ù‡Ù…ÛŒ Ø§Ø² Ø¬Ø§ÛŒØ²Ù‡â€ŒÛŒ Ù†Ù‚Ø¯ÛŒ Ù†Ù…ÛŒâ€ŒØ¨Ø±Ù‡ ØªØ§ Ø§Ù‚ØªØµØ§Ø¯ Ø¨Ø§Ø²ÛŒ Ø®Ø±Ø§Ø¨ Ù†Ø´Ù‡)
# - /cashout Ù†ØµÙ Ø§Ø±Ø²Ø´ ÙØ¹Ù„ÛŒ Ø´Ø±Ú©Øª Ø±Ùˆ Ù†Ù‚Ø¯ Ù…ÛŒâ€ŒÚ©Ù†Ù‡ Ùˆ Ø§Ø² Ø§Ø±Ø²Ø´ Ø´Ø±Ú©Øª (Ùˆ Ø³ÙˆØ¯ Ø±ÙˆØ²Ø§Ù†Ù‡â€ŒÛŒ Ø¨Ø¹Ø¯ÛŒØ´) Ú©Ù… Ù…ÛŒâ€ŒÚ©Ù†Ù‡

COMPANY_COOLDOWN = 0                # Ù…Ø­Ø¯ÙˆØ¯ÛŒØª Ø²Ù…Ø§Ù†ÛŒ Ø¨Ø§Ø² Ú©Ø±Ø¯Ù† Ø¨Ø§Ø²Ø§Ø± Ø­Ø°Ù Ø´Ø¯Ù‡Ø› ÙÙ‚Ø· Ø§Ø¯Ù…ÛŒÙ† Ú©Ù†ØªØ±Ù„ Ù…ÛŒâ€ŒÚ©Ù†Ø¯
COMPANY_MIN_INVEST_PCT = 0.10       # Ú©Ù Ø³Ø±Ù…Ø§ÛŒÙ‡â€ŒÚ¯Ø°Ø§Ø±ÛŒ Ù‡Ø± Ù†ÙØ± ØªÙˆÛŒ Ù‡Ø± Ø¨Ø§Ø± /invest: Û±Û°Ùª Ø³Ø§ÛŒØ²Ø´ (Ù†Ù‡ Ø³Ù‚Ù!)
COMPANY_MIN_BUDGET_LOW = 5          # Ù¾Ø§ÛŒÛŒÙ†â€ŒØªØ±ÛŒÙ† Ù…Ù‚Ø¯Ø§Ø± Ù…Ù…Ú©Ù† Ø¨Ø±Ø§ÛŒ Ø­Ø¯Ø§Ù‚Ù„ Ø¨ÙˆØ¯Ø¬Ù‡â€ŒÛŒ ÛŒÙ‡ Ø´Ø±Ú©Øª
COMPANY_MIN_BUDGET_HIGH = 15        # Ø¨Ø§Ù„Ø§ØªØ±ÛŒÙ† Ù…Ù‚Ø¯Ø§Ø± Ù…Ù…Ú©Ù† Ø¨Ø±Ø§ÛŒ Ø­Ø¯Ø§Ù‚Ù„ Ø¨ÙˆØ¯Ø¬Ù‡â€ŒÛŒ ÛŒÙ‡ Ø´Ø±Ú©Øª
COMPANY_DIVIDEND_PCT = 0.20         # Ø³ÙˆØ¯ Ø±ÙˆØ²Ø§Ù†Ù‡â€ŒÛŒ Ø´Ø±Ú©Øª Ø¨Ù‡ ØµØ§Ø­Ø¨Ø´
COMPANY_WORKER_COST = 15            # Ù‚ÛŒÙ…Øª Ø®Ø±ÛŒØ¯ Ù‡Ø± ÛŒØ§Ø± Ù…Ø§ÙÛŒØ§ Ø§Ø² Ø´Ø±Ú©Øª

COMPANY_NAME_POOL = [
    "Ù‡Ù„Ø¯ÛŒÙ†Ú¯ Ú©Ù„ÙØªâ€ŒÚ©Ø§Ø±Ø§Ù†", "Ø´Ø±Ú©Øª Ø¯Ø±Ø§Ø²Ú¯Ø³ØªØ±", "Ú¯Ø±ÙˆÙ‡ ØµÙ†Ø¹ØªÛŒ Ú¯Ø±Ø¯Ù†â€ŒÚ©Ù„ÙØª",
    "Ú©Ø§Ø±Ø®Ø§Ù†Ù‡ Ø´Ù‚â€ŒØ§Ù„Ù‚Ù…Ø±", "Ø´Ø±Ú©Øª Ø±Ø§Ø³Øªâ€ŒÙ‚Ø§Ù…ØªØ§Ù†", "Ù‡Ù„Ø¯ÛŒÙ†Ú¯ Ù‚Ø¯Ø¨Ù„Ù†Ø¯ Ù¾Ù„Ø§Ø³",
    "Ú¯Ø±ÙˆÙ‡ Ø¨Ø§Ø²Ø±Ú¯Ø§Ù†ÛŒ Ø³ØªÙˆÙ†â€ŒÙ…Ø­Ú©Ù…", "Ø´Ø±Ú©Øª Ø®Ø´ØªÚ©â€ŒÙ¾Ø§Ø±Ù‡",
    "Ú©Ø§Ø±Ø®Ø§Ù†Ù‡ Ø³Ù‡â€ŒØ³Ø§Ù†ØªÛŒ Ùˆ Ø´Ø±Ú©Ø§", "Ù‡Ù„Ø¯ÛŒÙ†Ú¯ Ù‚Ø¯Ú©Ø´â€ŒÙ‡Ø§",
    "Ø´Ø±Ú©Øª Ø¯Ø±Ø§Ø² Ùˆ Ø¯Ø±Ø¯Ø³Ø±", "Ú¯Ø±ÙˆÙ‡ ØµÙ†Ø¹ØªÛŒ Ú†ÙˆØ¨â€ŒØ®Ø·",
    "Ø´Ø±Ú©Øª Ú©Ù„ÙØªâ€ŒÚ¯Ø³ØªØ± Ø´Ø±Ù‚", "Ú©Ø§Ø±Ø®Ø§Ù†Ù‡ Ù…ÛŒÙ„Ù‡â€ŒÙ…Ø­Ú©Ù…",
    "Ù‡Ù„Ø¯ÛŒÙ†Ú¯ ØµØ§Ùâ€ŒÙˆâ€ŒØµÙˆÙ", "Ø´Ø±Ú©Øª Ú¯Ø±Ø¯Ù†â€ŒÚ©Ù„ÙØª ØºØ±Ø¨",
    "Ú¯Ø±ÙˆÙ‡ ØµÙ†Ø¹ØªÛŒ Ø®Ø·â€ŒÚ©Ø´â€ŒØ·Ù„Ø§ÛŒÛŒ", "Ø´Ø±Ú©Øª Ù‚Ø¯Ø¨Ù„Ù†Ø¯Ø³ØªØ§Ù†",
    "Ú©Ø§Ø±Ø®Ø§Ù†Ù‡ Ø³ØªÙˆÙ†â€ŒØ³Ø§Ø²Ø§Ù†", "Ù‡Ù„Ø¯ÛŒÙ†Ú¯ Ø§Ù†Ø¯Ø§Ø²Ù‡â€ŒÚ¯ÛŒØ±Ø§Ù†",
]

c.execute("""CREATE TABLE IF NOT EXISTS company_rounds(
    chat_id INTEGER,
    round_id INTEGER DEFAULT 0,
    status TEXT DEFAULT 'closed',
    open_time INTEGER DEFAULT 0,
    PRIMARY KEY(chat_id, round_id)
)""")
c.execute("""CREATE TABLE IF NOT EXISTS company_options(
    chat_id INTEGER,
    round_id INTEGER,
    slot INTEGER,
    name TEXT,
    min_budget INTEGER DEFAULT 20,
    PRIMARY KEY(chat_id, round_id, slot)
)""")
c.execute("""CREATE TABLE IF NOT EXISTS company_investments(
    chat_id INTEGER,
    round_id INTEGER,
    slot INTEGER,
    user_id INTEGER,
    amount INTEGER DEFAULT 0,
    PRIMARY KEY(chat_id, round_id, slot, user_id)
)""")
c.execute("""CREATE TABLE IF NOT EXISTS company_participants(
    chat_id INTEGER,
    round_id INTEGER,
    user_id INTEGER,
    cap INTEGER,
    invested INTEGER DEFAULT 0,
    PRIMARY KEY(chat_id, round_id, user_id)
)""")
c.execute("""CREATE TABLE IF NOT EXISTS owned_companies(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    owner_id INTEGER,
    name TEXT,
    value INTEGER,
    workers INTEGER,
    workers_bought INTEGER DEFAULT 0,
    workers_used_mafia INTEGER DEFAULT 0,
    last_payout INTEGER
)""")
db.commit()

try:
    c.execute("ALTER TABLE company_options ADD COLUMN min_budget INTEGER DEFAULT 20")
except sqlite3.OperationalError:
    pass
db.commit()

# Ø§Ú¯Ù‡ Ø¯ÛŒØªØ§Ø¨ÛŒØ³ Ù‚Ø¯ÛŒÙ…ÛŒ Ù‡Ù†ÙˆØ² Ø§Ø³Ú©ÛŒÙ…Ø§ÛŒ ØªÚ©-Ø¨Ø§Ø²Ø§Ø±Ù‡ (chat_id ØªÙ†Ù‡Ø§ Ú©Ù„ÛŒØ¯ Ø§ØµÙ„ÛŒ)ØŒ Ù…Ù†ØªÙ‚Ù„Ø´ Ú©Ù† Ø¨Ù‡ Ø§Ø³Ú©ÛŒÙ…Ø§ÛŒ Ú†Ù†Ø¯Ø¨Ø§Ø²Ø§Ø±Ù‡
_pk_cols = [row[1] for row in c.execute("PRAGMA table_info(company_rounds)").fetchall() if row[5] > 0]
if _pk_cols == ["chat_id"]:
    c.execute("ALTER TABLE company_rounds RENAME TO company_rounds_old_single")
    c.execute("""CREATE TABLE company_rounds(
        chat_id INTEGER,
        round_id INTEGER DEFAULT 0,
        status TEXT DEFAULT 'closed',
        open_time INTEGER DEFAULT 0,
        PRIMARY KEY(chat_id, round_id)
    )""")
    c.execute("INSERT INTO company_rounds(chat_id,round_id,status,open_time) SELECT chat_id,round_id,status,open_time FROM company_rounds_old_single")
    c.execute("DROP TABLE company_rounds_old_single")
    db.commit()

ALLY_NAME_POOL = [
    "ÛŒØ§Ø± Ø®ÙÙ† Ø´Ø±Ú©Øª", "Ù¾Ø³Ø±Ø¹Ù…ÙˆÛŒ Ú©Ù„ÙØª", "Ú©Ø§Ø±Ù…Ù†Ø¯ Ø¨ÛŒâ€ŒØ³Ø±ÙˆÙ¾Ø§", "ÛŒØ§Ø±Ù Ø²ÛŒØ±Ù Ù…ÛŒØ²ÛŒ",
    "Ø¨Ø§Ø¯ÛŒÚ¯Ø§Ø±Ø¯ Ú©ÛŒØ±ÛŒ", "Ù‡Ù…Ú©Ø§Ø± Ù…Ø´Ú©ÙˆÚ©", "ÛŒØ§Ø± Ù‚Ø§Ú†Ø§Ù‚ÛŒ", "Ú©Ø§Ø±Ú¯Ø± Ø´ÛŒÙØª Ø´Ø¨",
]


def find_active_membership(chat_id, uid):
    """Ø¢Ø®Ø±ÛŒÙ† Ù†Ø¨Ø±Ø¯ ÙØ¹Ø§Ù„ Ù…Ø§ÙÛŒØ§/Ù…Ø§ÙÛŒØ§Û² Ú©Ù‡ Ø§ÛŒÙ† Ú©Ø§Ø±Ø¨Ø± ÙˆØ§Ù‚Ø¹Ø§Ù‹ (Ù†Ù‡ Ø¨Ù‡ Ø¹Ù†ÙˆØ§Ù† ÛŒØ§Ø±) ØªÙˆØ´ Ø¹Ø¶ÙˆÙ‡ Ø±Ùˆ Ù¾ÛŒØ¯Ø§ Ù…ÛŒâ€ŒÚ©Ù†Ù‡.
    Ø®Ø±ÙˆØ¬ÛŒ: (kind, battle_id, team) ÛŒØ§ None Ø§Ú¯Ù‡ ØªÙˆÛŒ Ù‡ÛŒÚ† Ù†Ø¨Ø±Ø¯ÛŒ Ù†Ø¨Ø§Ø´Ù‡."""
    row = c.execute(
        """SELECT mb.id, mm.team FROM mafia_battles mb
           JOIN mafia_members mm ON mm.battle_id=mb.id
           WHERE mb.chat_id=? AND mb.active=1 AND mm.user_id=?
           ORDER BY mb.id DESC LIMIT 1""",
        (chat_id, uid)
    ).fetchone()
    if row:
        return ("mafia", row[0], row[1])
    row = c.execute(
        """SELECT mb.id, mm.team FROM mafia2_battles mb
           JOIN mafia2_members mm ON mm.battle_id=mb.id
           WHERE mb.chat_id=? AND mb.active=1 AND mm.user_id=?
           ORDER BY mb.id DESC LIMIT 1""",
        (chat_id, uid)
    ).fetchone()
    if row:
        return ("mafia2", row[0], row[1])
    return None


def get_open_rounds(chat_id):
    """Ù„ÛŒØ³Øª Ù‡Ù…Ù‡â€ŒÛŒ Ø¨Ø§Ø²Ø§Ø±Ù‡Ø§ÛŒÛŒ Ú©Ù‡ Ù‡Ù…ÛŒÙ† Ø§Ù„Ø§Ù† ØªÙˆ Ø§ÛŒÙ† Ú¯Ø±ÙˆÙ‡ Ø¨Ø§Ø²Ù†."""
    return c.execute(
        "SELECT round_id, open_time FROM company_rounds WHERE chat_id=? AND status='open' ORDER BY round_id",
        (chat_id,)
    ).fetchall()

def get_round_status(chat_id, round_id):
    row = c.execute("SELECT status FROM company_rounds WHERE chat_id=? AND round_id=?", (chat_id, round_id)).fetchone()
    return row[0] if row else None

def next_round_id(chat_id):
    row = c.execute("SELECT MAX(round_id) FROM company_rounds WHERE chat_id=?", (chat_id,)).fetchone()
    return (row[0] or 0) + 1


@dp.message(Command("copen"))
async def company_open(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return await m.reply("âŒ ÙÙ‚Ø· Ø§Ø¯Ù…ÛŒÙ† Ù…ÛŒâ€ŒØªÙˆÙ†Ù‡ Ø¨Ø§Ø²Ø§Ø± Ø±Ùˆ Ø¨Ø§Ø² Ú©Ù†Ù‡!")
    now = int(time.time())
    new_round = next_round_id(m.chat.id)
    names = random.sample(COMPANY_NAME_POOL, 4)
    min_budgets = []
    for i, name in enumerate(names, 1):
        mb = random.randint(COMPANY_MIN_BUDGET_LOW, COMPANY_MIN_BUDGET_HIGH)
        min_budgets.append(mb)
        c.execute("INSERT INTO company_options(chat_id,round_id,slot,name,min_budget) VALUES(?,?,?,?,?)", (m.chat.id, new_round, i, name, mb))
    c.execute("INSERT INTO company_rounds(chat_id,round_id,status,open_time) VALUES(?,?,'open',?)", (m.chat.id, new_round, now))
    db.commit()
    open_count = len(get_open_rounds(m.chat.id))
    txt = f"ðŸ“ˆ ÛŒÙ‡ Ø¨Ø§Ø²Ø§Ø± Ø¨ÙˆØ±Ø³ Ø¬Ø¯ÛŒØ¯ Ø¨Ø§Ø² Ø´Ø¯! (Ø¨Ø§Ø²Ø§Ø± Ø´Ù…Ø§Ø±Ù‡â€ŒÛŒ #{new_round})\n\n"
    for i, (name, mb) in enumerate(zip(names, min_budgets), 1):
        txt += f"{i}. {name} (Ø­Ø¯Ø§Ù‚Ù„ Ø¨ÙˆØ¯Ø¬Ù‡: {mb} Ø§Ø³Ù¾Ø±Ù…)\n"
    txt += (
        f"\nðŸ§¬ Ù‡Ø± Ø³Ø±Ù…Ø§ÛŒÙ‡â€ŒÚ¯Ø°Ø§Ø±ÛŒ Ø¨Ø§ÛŒØ¯ Ø­Ø¯Ø§Ù‚Ù„ {int(COMPANY_MIN_INVEST_PCT*100)}Ùª Ø§Ø³Ù¾Ø±Ù…Øª Ø¨Ø§Ø´Ù‡Ø› Ø³Ù‚ÙÛŒ Ù†Ø¯Ø§Ø±Ù‡!\n"
        f"(Ù†Ø¯Ø§Ø±ÛŒØŸ Ø¨Ø§ /tosperm Ø³Ø§Ù†ØªØª Ø±Ùˆ ØªØ¨Ø¯ÛŒÙ„ Ú©Ù† â€” Ù‡Ø± Û± Ø³Ø§Ù†Øª = {SPERM_RATE} Ø§Ø³Ù¾Ø±Ù…)\n\n"
        f"Ø¨Ø±Ø§ÛŒ Ø³Ø±Ù…Ø§ÛŒÙ‡â€ŒÚ¯Ø°Ø§Ø±ÛŒ ÙÙ‚Ø· Ø¨Ù†ÙˆÛŒØ³ /invest (Ø¨Ø¯ÙˆÙ† Ù‡ÛŒÚ† Ø¹Ø¯Ø¯ÛŒ!)\n"
        f"Ø±Ø¨Ø§Øª Ù…ÛŒØ§Ø¯ Ù¾ÛŒÙˆÛŒ Ø®ØµÙˆØµÛŒ Ø¨Ø§Ù‡Ø§Øª Ù‡Ù…Ø§Ù‡Ù†Ú¯ Ù…ÛŒâ€ŒÚ©Ù†Ù‡ Ú©Ù‡ Ú©Ø³ÛŒ Ù†ÙÙ‡Ù…Ù‡ Ø±Ùˆ Ú†ÛŒ Ùˆ Ú†Ù‚Ø¯Ø± Ø³Ø±Ù…Ø§ÛŒÙ‡â€ŒÚ¯Ø°Ø§Ø±ÛŒ Ú©Ø±Ø¯ÛŒ."
    )
    if open_count > 1:
        txt += f"\n\nðŸ“Š Ø§Ù„Ø§Ù† {open_count} ØªØ§ Ø¨Ø§Ø²Ø§Ø± Ù‡Ù…Ø²Ù…Ø§Ù† Ø¨Ø§Ø² Ù‡Ø³ØªÙ† ØªÙˆ Ø§ÛŒÙ† Ú¯Ø±ÙˆÙ‡."
    await m.reply(txt)


def build_company_picker_kb(chat_id, round_id):
    opts = c.execute("SELECT slot,name FROM company_options WHERE chat_id=? AND round_id=? ORDER BY slot", (chat_id, round_id)).fetchall()
    return opts, InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{slot}. {name}", callback_data=f"investpick:{chat_id}:{round_id}:{slot}")]
        for slot, name in opts
    ])

@dp.message(Command("invest"))
async def company_invest_start(m: Message):
    if m.chat.type == "private":
        return await m.reply("âŒ Ø§ÛŒÙ† Ø¯Ø³ØªÙˆØ± Ø±Ùˆ Ø¨Ø§ÛŒØ¯ ØªÙˆÛŒ Ù‡Ù…ÙˆÙ† Ú¯Ø±ÙˆÙ‡ÛŒ Ú©Ù‡ Ø¨Ø§Ø²ÛŒ Ù…ÛŒâ€ŒÚ©Ù†ÛŒ Ø¨Ø²Ù†ÛŒ.")
    open_rounds = get_open_rounds(m.chat.id)
    if not open_rounds:
        return await m.reply("âŒ Ø§Ù„Ø§Ù† Ù‡ÛŒÚ† Ø¨Ø§Ø²Ø§Ø±ÛŒ Ø¨Ø§Ø² Ù†ÛŒØ³Øª!")
    user(m.chat.id, m.from_user.id, m.from_user.full_name)
    tip = ""
    if len(m.text.split()) > 1:
        tip = "\n\nðŸ’¡ Ø¯ÛŒÚ¯Ù‡ Ù„Ø§Ø²Ù… Ù†ÛŒØ³Øª Ø¨Ø¹Ø¯ /invest Ø¹Ø¯Ø¯ Ø¨Ù†ÙˆÛŒØ³ÛŒ â€” Ú©Ù„ Ø§Ù†ØªØ®Ø§Ø¨ Ø±Ùˆ Ù‡Ù…ÛŒÙ†Ø¬Ø§ Ø¨Ø§ Ø¯Ú©Ù…Ù‡ Ø§Ù†Ø¬Ø§Ù… Ø¨Ø¯Ù‡."

    if len(open_rounds) == 1:
        round_id = open_rounds[0][0]
        opts, kb = build_company_picker_kb(m.chat.id, round_id)
        if not opts:
            return await m.reply("âŒ Ø´Ø±Ú©ØªÛŒ Ø¨Ø±Ø§ÛŒ Ø§ÛŒÙ† Ø¨Ø§Ø²Ø§Ø± Ù¾ÛŒØ¯Ø§ Ù†Ø´Ø¯.")
        try:
            await m.bot.send_message(
                m.from_user.id,
                "ðŸ“ˆ Ø±ÙˆÛŒ Ú©Ø¯ÙˆÙ… Ø´Ø±Ú©Øª Ù…ÛŒâ€ŒØ®ÙˆØ§ÛŒ Ø³Ø±Ù…Ø§ÛŒÙ‡â€ŒÚ¯Ø°Ø§Ø±ÛŒ Ú©Ù†ÛŒØŸ\n(Ø§ÛŒÙ† Ù¾ÛŒØ§Ù… ÙÙ‚Ø· Ø¨Ø±Ø§ÛŒ Ø®ÙˆØ¯ØªÙ‡)" + tip,
                reply_markup=kb
            )
        except (TelegramForbiddenError, TelegramBadRequest):
            return await m.reply("âŒ Ø§ÙˆÙ„ Ø¨Ø§ÛŒØ¯ Ø±Ø¨Ø§Øª Ø±Ùˆ ØªÙˆÛŒ Ù¾ÛŒÙˆÛŒ (Ú†Øª Ø®ØµÙˆØµÛŒ) Ø§Ø³ØªØ§Ø±Øª Ú©Ù†ÛŒØŒ Ø¨Ø¹Ø¯ Ø¯ÙˆØ¨Ø§Ø±Ù‡ Ø§ÛŒÙ†Ø¬Ø§ /invest Ø¨Ø²Ù†.")
        return await m.reply("ðŸ“© Ø¨Ø±Ø§Øª Ù¾ÛŒØ§Ù… Ø®ØµÙˆØµÛŒ ÙØ±Ø³ØªØ§Ø¯Ù…! Ø¨Ù‚ÛŒÙ‡â€ŒÛŒ Ø³Ø±Ù…Ø§ÛŒÙ‡â€ŒÚ¯Ø°Ø§Ø±ÛŒ Ø±Ùˆ Ø§ÙˆÙ†Ø¬Ø§ Ø§Ù†Ø¬Ø§Ù… Ø¨Ø¯Ù‡ ØªØ§ Ù„Ùˆ Ù†Ø±Ù‡.")

    # Ú†Ù†Ø¯ØªØ§ Ø¨Ø§Ø²Ø§Ø± Ù‡Ù…Ø²Ù…Ø§Ù† Ø¨Ø§Ø² Ù‡Ø³ØªÙ† â€” Ø§ÙˆÙ„ Ø¨Ø§ÛŒØ¯ Ø§Ù†ØªØ®Ø§Ø¨ Ú©Ù†Ù‡ Ú©Ø¯ÙˆÙ… Ø±Ùˆ Ù…ÛŒâ€ŒØ®ÙˆØ§Ø¯
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"ðŸ“ˆ Ø¨Ø§Ø²Ø§Ø± #{rid}", callback_data=f"investmarket:{m.chat.id}:{rid}")]
        for rid, _ in open_rounds
    ])
    try:
        await m.bot.send_message(
            m.from_user.id,
            f"ðŸ“Š Ø§Ù„Ø§Ù† {len(open_rounds)} ØªØ§ Ø¨Ø§Ø²Ø§Ø± Ù‡Ù…Ø²Ù…Ø§Ù† Ø¨Ø§Ø² Ù‡Ø³ØªÙ†. Ú©Ø¯ÙˆÙ…Ø´ Ø±Ùˆ Ù…ÛŒâ€ŒØ®ÙˆØ§ÛŒ Ø³Ø±Ù…Ø§ÛŒÙ‡â€ŒÚ¯Ø°Ø§Ø±ÛŒ Ú©Ù†ÛŒØŸ" + tip,
            reply_markup=kb
        )
    except (TelegramForbiddenError, TelegramBadRequest):
        return await m.reply("âŒ Ø§ÙˆÙ„ Ø¨Ø§ÛŒØ¯ Ø±Ø¨Ø§Øª Ø±Ùˆ ØªÙˆÛŒ Ù¾ÛŒÙˆÛŒ (Ú†Øª Ø®ØµÙˆØµÛŒ) Ø§Ø³ØªØ§Ø±Øª Ú©Ù†ÛŒØŒ Ø¨Ø¹Ø¯ Ø¯ÙˆØ¨Ø§Ø±Ù‡ Ø§ÛŒÙ†Ø¬Ø§ /invest Ø¨Ø²Ù†.")
    await m.reply("ðŸ“© Ø¨Ø±Ø§Øª Ù¾ÛŒØ§Ù… Ø®ØµÙˆØµÛŒ ÙØ±Ø³ØªØ§Ø¯Ù…! Ø¨Ù‚ÛŒÙ‡â€ŒÛŒ Ø³Ø±Ù…Ø§ÛŒÙ‡â€ŒÚ¯Ø°Ø§Ø±ÛŒ Ø±Ùˆ Ø§ÙˆÙ†Ø¬Ø§ Ø§Ù†Ø¬Ø§Ù… Ø¨Ø¯Ù‡ ØªØ§ Ù„Ùˆ Ù†Ø±Ù‡.")

@dp.callback_query(F.data.startswith("investmarket:"))
async def company_invest_pick_market(q: CallbackQuery):
    _, chat_id, round_id = q.data.split(":")
    chat_id, round_id = int(chat_id), int(round_id)
    if get_round_status(chat_id, round_id) != "open":
        return await q.answer("âŒ Ø§ÛŒÙ† Ø¨Ø§Ø²Ø§Ø± Ø¯ÛŒÚ¯Ù‡ Ø¨Ø³ØªÙ‡ Ø´Ø¯Ù‡.", show_alert=True)
    opts, kb = build_company_picker_kb(chat_id, round_id)
    if not opts:
        return await q.answer("âŒ Ø´Ø±Ú©ØªÛŒ Ø¨Ø±Ø§ÛŒ Ø§ÛŒÙ† Ø¨Ø§Ø²Ø§Ø± Ù¾ÛŒØ¯Ø§ Ù†Ø´Ø¯.", show_alert=True)
    await q.message.edit_text(f"ðŸ“ˆ Ø¨Ø§Ø²Ø§Ø± #{round_id} â€” Ø±ÙˆÛŒ Ú©Ø¯ÙˆÙ… Ø´Ø±Ú©Øª Ù…ÛŒâ€ŒØ®ÙˆØ§ÛŒ Ø³Ø±Ù…Ø§ÛŒÙ‡â€ŒÚ¯Ø°Ø§Ø±ÛŒ Ú©Ù†ÛŒØŸ", reply_markup=kb)
    await q.answer()


@dp.callback_query(F.data.startswith("investpick:"))
async def company_invest_pick(q: CallbackQuery):
    _, chat_id, round_id, slot = q.data.split(":")
    chat_id, round_id, slot = int(chat_id), int(round_id), int(slot)
    if get_round_status(chat_id, round_id) != "open":
        return await q.answer("âŒ Ø§ÛŒÙ† Ø¨Ø§Ø²Ø§Ø± Ø¯ÛŒÚ¯Ù‡ Ø¨Ø³ØªÙ‡ ÛŒØ§ Ù…Ù†Ù‚Ø¶ÛŒ Ø´Ø¯Ù‡.", show_alert=True)
    opt = c.execute("SELECT name FROM company_options WHERE chat_id=? AND round_id=? AND slot=?", (chat_id, round_id, slot)).fetchone()
    if not opt:
        return await q.answer("âŒ Ù‡Ù…Ú†ÛŒÙ† Ø´Ø±Ú©ØªÛŒ Ù¾ÛŒØ¯Ø§ Ù†Ø´Ø¯.", show_alert=True)
    pending_invest[q.from_user.id] = {"chat_id": chat_id, "round_id": round_id, "slot": slot, "ts": int(time.time())}
    await q.answer()
    await q.message.edit_text(f"ðŸ§¬ Ú†Ù†Ø¯ Ø§Ø³Ù¾Ø±Ù… Ù…ÛŒâ€ŒØ®ÙˆØ§ÛŒ Ø±ÙˆÛŒ Â«{opt[0]}Â» Ø³Ø±Ù…Ø§ÛŒÙ‡â€ŒÚ¯Ø°Ø§Ø±ÛŒ Ú©Ù†ÛŒØŸ\nÙÙ‚Ø· Ø¹Ø¯Ø¯Ø´Ùˆ Ø¨ÙØ±Ø³Øª (Ù…Ø«Ù„Ø§Ù‹ 12).\n(Ù†Ø¯Ø§Ø±ÛŒØŸ Ø¨Ø§ /tosperm Ø³Ø§Ù†ØªØª Ø±Ùˆ ØªØ¨Ø¯ÛŒÙ„ Ú©Ù†.)")


@dp.message(F.chat.type == "private", F.text.regexp(r'^\d+$'))
async def company_invest_amount(m: Message):
    pending = pending_invest.get(m.from_user.id)
    if not pending:
        return
    if int(time.time()) - pending["ts"] > PENDING_INVEST_TTL:
        del pending_invest[m.from_user.id]
        return await m.reply("âŒ›ï¸ Ø²Ù…Ø§Ù† Ø§Ù†ØªØ®Ø§Ø¨Øª ØªÙ…ÙˆÙ… Ø´Ø¯ØŒ Ø¯ÙˆØ¨Ø§Ø±Ù‡ Ø§Ø² ØªÙˆÛŒ Ú¯Ø±ÙˆÙ‡ /invest Ø¨Ø²Ù†.")
    amount = int(m.text)
    chat_id, round_id, slot = pending["chat_id"], pending["round_id"], pending["slot"]
    if amount <= 0:
        return await m.reply("âŒ Ù…Ù‚Ø¯Ø§Ø± Ø¨Ø§ÛŒØ¯ Ù…Ø«Ø¨Øª Ø¨Ø§Ø´Ù‡.")
    if get_round_status(chat_id, round_id) != "open":
        del pending_invest[m.from_user.id]
        return await m.reply("âŒ Ø§ÙˆÙ† Ø¨Ø§Ø²Ø§Ø± Ø¨Ø³ØªÙ‡ Ø´Ø¯Ù‡ØŒ Ø¯ÙˆØ¨Ø§Ø±Ù‡ Ø§Ø² ØªÙˆÛŒ Ú¯Ø±ÙˆÙ‡ /invest Ø¨Ø²Ù†.")
    opt = c.execute("SELECT name FROM company_options WHERE chat_id=? AND round_id=? AND slot=?", (chat_id, round_id, slot)).fetchone()
    if not opt:
        del pending_invest[m.from_user.id]
        return await m.reply("âŒ Ø§ÛŒÙ† Ø´Ø±Ú©Øª Ø¯ÛŒÚ¯Ù‡ ÙˆØ¬ÙˆØ¯ Ù†Ø¯Ø§Ø±Ù‡.")
    sperm = get_sperm(chat_id, m.from_user.id)
    if sperm < amount:
        return await m.reply(f"âŒ Ø§Ø³Ù¾Ø±Ù… Ú©Ø§ÙÛŒ Ù†Ø¯Ø§Ø±ÛŒ. (Ù…ÙˆØ¬ÙˆØ¯ÛŒ: {sperm})\nØ¨Ø§ /tosperm Ù…ÛŒâ€ŒØªÙˆÙ†ÛŒ Ø³Ø§Ù†ØªØª Ø±Ùˆ ØªØ¨Ø¯ÛŒÙ„ Ú©Ù†ÛŒ.")
    min_required = max(1, int(sperm * COMPANY_MIN_INVEST_PCT))
    if amount < min_required:
        return await m.reply(f"âŒ Ù‡Ø± Ø³Ø±Ù…Ø§ÛŒÙ‡â€ŒÚ¯Ø°Ø§Ø±ÛŒ Ø¨Ø§ÛŒØ¯ Ø­Ø¯Ø§Ù‚Ù„ {int(COMPANY_MIN_INVEST_PCT*100)}Ùª Ø§Ø³Ù¾Ø±Ù…Øª Ø¨Ø§Ø´Ù‡!\nðŸ“Š Ø­Ø¯Ø§Ù‚Ù„ Ù…Ø¬Ø§Ø² Ø§Ù„Ø§Ù†: {min_required} Ø§Ø³Ù¾Ø±Ù…")
    part = c.execute("SELECT invested FROM company_participants WHERE chat_id=? AND round_id=? AND user_id=?", (chat_id, round_id, m.from_user.id)).fetchone()
    if not part:
        c.execute("INSERT INTO company_participants(chat_id,round_id,user_id,invested) VALUES(?,?,?,0)", (chat_id, round_id, m.from_user.id))
        db.commit()
    c.execute("UPDATE users SET sperm=sperm-? WHERE chat_id=? AND user_id=?", (amount, chat_id, m.from_user.id))
    c.execute("""INSERT INTO company_investments(chat_id,round_id,slot,user_id,amount) VALUES(?,?,?,?,?)
                 ON CONFLICT(chat_id,round_id,slot,user_id) DO UPDATE SET amount=amount+excluded.amount""",
              (chat_id, round_id, slot, m.from_user.id, amount))
    c.execute("UPDATE company_participants SET invested=invested+? WHERE chat_id=? AND round_id=? AND user_id=?", (amount, chat_id, round_id, m.from_user.id))
    db.commit()
    del pending_invest[m.from_user.id]
    await m.reply("âœ… Ø³Ø±Ù…Ø§ÛŒÙ‡â€ŒÚ¯Ø°Ø§Ø±ÛŒØª Ø¨Ø§ Ù…ÙˆÙÙ‚ÛŒØª Ùˆ Ú©Ø§Ù…Ù„Ø§Ù‹ Ù…Ø­Ø±Ù…Ø§Ù†Ù‡ Ø«Ø¨Øª Ø´Ø¯!")


@dp.message(Command("cclose"))
async def company_close(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return await m.reply("âŒ ÙÙ‚Ø· Ø§Ø¯Ù…ÛŒÙ† Ù…ÛŒâ€ŒØªÙˆÙ†Ù‡ Ø¨Ø§Ø²Ø§Ø± Ø±Ùˆ Ø¨Ø¨Ù†Ø¯Ù‡!")
    open_rounds = get_open_rounds(m.chat.id)
    if not open_rounds:
        return await m.reply("âŒ Ù‡ÛŒÚ† Ø¨Ø§Ø²Ø§Ø±ÛŒ Ø¨Ø§Ø² Ù†ÛŒØ³Øª.")
    parts = m.text.split()
    if len(open_rounds) == 1:
        round_id = open_rounds[0][0]
    elif len(parts) > 1 and parts[1].isdigit() and int(parts[1]) in {r for r, _ in open_rounds}:
        round_id = int(parts[1])
    else:
        listing = "\n".join(f"â€¢ #{r}" for r, _ in open_rounds)
        return await m.reply(f"ðŸ“Š Ú†Ù†Ø¯ØªØ§ Ø¨Ø§Ø²Ø§Ø± Ù‡Ù…Ø²Ù…Ø§Ù† Ø¨Ø§Ø²Ù‡ØŒ Ù…Ø´Ø®Øµ Ú©Ù† Ú©Ø¯ÙˆÙ…Ùˆ Ø¨Ø¨Ù†Ø¯Ù…:\n{listing}\n\nÙ…Ø«Ø§Ù„: /cclose {open_rounds[0][0]}")
    opts = c.execute("SELECT slot,name,min_budget FROM company_options WHERE chat_id=? AND round_id=?", (m.chat.id, round_id)).fetchall()
    if not opts:
        return await m.reply("âŒ Ø´Ø±Ú©ØªÛŒ Ø¨Ø±Ø§ÛŒ Ø§ÛŒÙ† Ø¯ÙˆØ± Ù¾ÛŒØ¯Ø§ Ù†Ø´Ø¯.")
    totals = {}
    for slot, name, min_budget in opts:
        total = c.execute("SELECT COALESCE(SUM(amount),0) FROM company_investments WHERE chat_id=? AND round_id=? AND slot=?", (m.chat.id, round_id, slot)).fetchone()[0]
        totals[slot] = (name, total, min_budget)

    max_slot = max(totals, key=lambda s: totals[s][1])
    eliminated = {max_slot}
    for slot, (name, total, min_budget) in totals.items():
        if total < min_budget:
            eliminated.add(slot)

    now = int(time.time())
    txt = f"ðŸ“‰ Ù†ØªÛŒØ¬Ù‡â€ŒÛŒ Ø¨Ø§Ø²Ø§Ø± Ø¨ÙˆØ±Ø³ #{round_id}!\n\n"
    for slot, (name, total, min_budget) in totals.items():
        if slot in eliminated:
            reason = "Ú¯Ù†Ø¯Ù‡ Ø´Ø¯ Ùˆ ØªØ±Ú©ÛŒØ¯ ðŸ’¥" if slot == max_slot else f"Ø¨Ù‡ Ø­Ø¯Ø§Ù‚Ù„ Ø¨ÙˆØ¯Ø¬Ù‡â€ŒØ´ ({min_budget} Ø§Ø³Ù¾Ø±Ù…) Ù†Ø±Ø³ÛŒØ¯ ðŸ“‰"
            txt += f"âŒ {name} ({total} Ø§Ø³Ù¾Ø±Ù…) â€” {reason}\n"
            continue
        top = c.execute(
            "SELECT user_id,amount FROM company_investments WHERE chat_id=? AND round_id=? AND slot=? ORDER BY amount DESC LIMIT 1",
            (m.chat.id, round_id, slot)
        ).fetchone()
        if not top:
            txt += f"âšªï¸ {name} â€” Ú©Ø³ÛŒ Ø³Ø±Ù…Ø§ÛŒÙ‡â€ŒÚ¯Ø°Ø§Ø±ÛŒ Ù†Ú©Ø±Ø¯ØŒ Ø¨Ø±Ù†Ø¯Ù‡â€ŒØ§ÛŒ Ù†Ø¯Ø§Ø´Øª\n"
            continue
        winner_id, winner_amount = top
        workers = random.randint(2, 3)
        c.execute(
            "INSERT INTO owned_companies(chat_id,owner_id,name,value,workers,last_payout) VALUES(?,?,?,?,?,?)",
            (m.chat.id, winner_id, name, total, workers, now)
        )
        winner_name = get_name(m.chat.id, winner_id)
        txt += f"ðŸ‘‘ {name} ({total} Ø§Ø³Ù¾Ø±Ù…) â€” Ø¨Ø±Ù†Ø¯Ù‡: {winner_name} (Ø³Ù‡Ù… {winner_amount} Ø§Ø³Ù¾Ø±Ù…)\n"

    c.execute("UPDATE company_rounds SET status='closed' WHERE chat_id=? AND round_id=?", (m.chat.id, round_id))
    db.commit()
    await m.reply(txt)


@dp.message(Command("mycompanies"))
async def my_companies(m: Message):
    rows = c.execute("SELECT id,name,value,workers,workers_bought,workers_used_mafia FROM owned_companies WHERE chat_id=? AND owner_id=?", (m.chat.id, m.from_user.id)).fetchall()
    if not rows:
        return await m.reply("ðŸ“­ Ù‡Ù†ÙˆØ² Ù‡ÛŒÚ† Ø´Ø±Ú©ØªÛŒ Ù†Ø¯Ø§Ø±ÛŒ! ÙˆÙ‚ØªÛŒ Ø¨Ø§Ø²Ø§Ø± Ø¨ÙˆØ±Ø³ Ø¨Ø§Ø²Ù‡ Ø¨Ø§ /invest Ø´Ø±Ú©Øª Ú©Ù†.")
    txt = "ðŸ¢ Ø´Ø±Ú©Øªâ€ŒÙ‡Ø§ÛŒ ØªÙˆ:\n\n"
    for cid, name, value, workers, bought, used in rows:
        income = int(value * COMPANY_DIVIDEND_PCT)
        available = bought - used
        txt += f"#{cid} {name}\nðŸ§¬ Ø§Ø±Ø²Ø´: {value} Ø§Ø³Ù¾Ø±Ù… | ðŸ“ˆ Ø³ÙˆØ¯ Ø±ÙˆØ²Ø§Ù†Ù‡: {income} Ø§Ø³Ù¾Ø±Ù…\nðŸ‘¥ ÛŒØ§Ø±: {bought}/{workers} Ø®Ø±ÛŒØ¯Ø§Ø±ÛŒâ€ŒØ´Ø¯Ù‡ ({available} Ø¢Ù…Ø§Ø¯Ù‡â€ŒÛŒ Ø§Ø³ØªÙØ§Ø¯Ù‡ Ø¨Ø§ /useyar)\n\n"
    await m.reply(txt)


# ===== Ø±Ù†Ú© Ø¨ÙˆØ±Ø³ Ø¨Ø± Ø§Ø³Ø§Ø³ Ø§Ø±Ø²Ø´ Ø®Ø§Ù„Øµ Ø´Ø±Ú©Øªâ€ŒÙ‡Ø§ =====
BOURSE_RANK_TIERS = [
    (0,    "ðŸ¥« Ø¯Ø³ØªÙØ±ÙˆØ´"),
    (50,   "ðŸª Ù…ØºØ§Ø²Ù‡â€ŒØ¯Ø§Ø±"),
    (150,  "ðŸ¢ ØªØ§Ø¬Ø±"),
    (400,  "ðŸ¦ Ù…ÛŒÙ„ÛŒØ§Ø±Ø¯Ø±"),
    (800,  "ðŸš€ Ø§ÛŒÙ„Ø§Ù† Ù…Ø§Ø³Ú©"),
]

def get_bourse_tier(net_worth):
    tier = BOURSE_RANK_TIERS[0][1]
    for threshold, name in BOURSE_RANK_TIERS:
        if net_worth >= threshold:
            tier = name
    return tier

@dp.message(Command("bourseleader"))
async def bourse_leaderboard(m: Message):
    rows = c.execute(
        "SELECT owner_id, value FROM owned_companies WHERE chat_id=?",
        (m.chat.id,)
    ).fetchall()
    if not rows:
        return await m.reply("ðŸ“­ Ù‡Ù†ÙˆØ² Ú©Ø³ÛŒ ØªÙˆ Ø¨ÙˆØ±Ø³ Ø§ÛŒÙ† Ú¯Ø±ÙˆÙ‡ Ø¨Ø±Ù†Ø¯Ù‡ Ù†Ø´Ø¯Ù‡!")
    stats = {}
    for owner_id, value in rows:
        s = stats.setdefault(owner_id, {"net_worth": 0, "companies": 0, "wins": 0, "daily_income": 0})
        s["wins"] += 1
        if value > 0:
            s["net_worth"] += value
            s["companies"] += 1
            s["daily_income"] += int(value * COMPANY_DIVIDEND_PCT)
    leaderboard = sorted(stats.items(), key=lambda kv: kv[1]["net_worth"], reverse=True)[:10]
    txt = "ðŸ“Š Ø¬Ø¯ÙˆÙ„ Ø¨ÙˆØ±Ø³ Ø§ÛŒÙ† Ú¯Ø±ÙˆÙ‡\n\n"
    for i, (owner_id, s) in enumerate(leaderboard, 1):
        name = get_name(m.chat.id, owner_id)
        tier = get_bourse_tier(s["net_worth"])
        txt += (
            f"{i}. {name}\n"
            f"   {tier}\n"
            f"   ðŸ§¬ Ø§Ø±Ø²Ø´ Ø®Ø§Ù„Øµ: {s['net_worth']} Ø§Ø³Ù¾Ø±Ù… | ðŸ¢ Ø´Ø±Ú©Øªâ€ŒÙ‡Ø§ÛŒ ÙØ¹Ø§Ù„: {s['companies']} | ðŸ† Ú©Ù„ Ø¨Ø±Ø¯Ù‡Ø§: {s['wins']}\n"
            f"   ðŸ“ˆ Ù…Ø¬Ù…ÙˆØ¹ Ø³ÙˆØ¯ Ø±ÙˆØ²Ø§Ù†Ù‡: {s['daily_income']} Ø§Ø³Ù¾Ø±Ù…\n\n"
        )
    await m.reply(txt)



async def hire_worker(m: Message):
    try:
        cid = int(m.text.split()[1])
    except:
        return await m.reply("Usage: /hire [Ø´Ù…Ø§Ø±Ù‡ Ø´Ø±Ú©Øª] (Ø´Ù…Ø§Ø±Ù‡â€ŒÙ‡Ø§ Ø±Ùˆ Ø§Ø² /mycompanies Ø¨Ø¨ÛŒÙ†)")
    row = c.execute("SELECT owner_id,name,workers,workers_bought FROM owned_companies WHERE id=? AND chat_id=?", (cid, m.chat.id)).fetchone()
    if not row:
        return await m.reply("âŒ Ù‡Ù…Ú†ÛŒÙ† Ø´Ø±Ú©ØªÛŒ Ù¾ÛŒØ¯Ø§ Ù†Ø´Ø¯.")
    owner_id, name, workers, bought = row
    if owner_id != m.from_user.id:
        return await m.reply("âŒ Ø§ÛŒÙ† Ø´Ø±Ú©Øª Ù…Ø§Ù„ ØªÙˆ Ù†ÛŒØ³Øª!")
    if bought >= workers:
        return await m.reply(f"âŒ Ù‡Ù…Ù‡â€ŒÛŒ {workers} ÛŒØ§Ø± Ø§ÛŒÙ† Ø´Ø±Ú©Øª Ø±Ùˆ Ù‚Ø¨Ù„Ø§Ù‹ Ø®Ø±ÛŒØ¯ÛŒ!")
    sperm = get_sperm(m.chat.id, m.from_user.id)
    if sperm < COMPANY_WORKER_COST:
        return await m.reply(f"âŒ Ø¨Ø±Ø§ÛŒ Ø®Ø±ÛŒØ¯ ÛŒØ§Ø± Ø¨Ù‡ {COMPANY_WORKER_COST} Ø§Ø³Ù¾Ø±Ù… Ù†ÛŒØ§Ø² Ø¯Ø§Ø±ÛŒ.")
    c.execute("UPDATE users SET sperm=sperm-? WHERE chat_id=? AND user_id=?", (COMPANY_WORKER_COST, m.chat.id, m.from_user.id))
    c.execute("UPDATE owned_companies SET workers_bought=workers_bought+1 WHERE id=?", (cid,))
    db.commit()
    await m.reply(f"âœ… ÛŒÙ‡ ÛŒØ§Ø± Ø§Ø² Â«{name}Â» Ø®Ø±ÛŒØ¯ÛŒ! ({bought+1}/{workers})\nðŸ”« Ø¨Ø±Ø§ÛŒ ÙØ±Ø³ØªØ§Ø¯Ù†Ø´ Ø¨Ù‡ ÛŒÙ‡ Ù†Ø¨Ø±Ø¯ Ù…Ø§ÙÛŒØ§ Ú©Ù‡ ØªÙˆØ´ Ù‡Ø³ØªÛŒ: /useyar")


@dp.message(Command("useyar"))
async def use_yar(m: Message):
    membership = find_active_membership(m.chat.id, m.from_user.id)
    if not membership:
        return await m.reply("âŒ Ø§Ù„Ø§Ù† ØªÙˆÛŒ Ù‡ÛŒÚ† Ù†Ø¨Ø±Ø¯ Ù…Ø§ÙÛŒØ§ÛŒ ÙØ¹Ø§Ù„ÛŒ Ù†ÛŒØ³ØªÛŒ! Ø§ÙˆÙ„ Ø¨Ø§ Ø¯Ú©Ù…Ù‡â€ŒÛŒ ØªÛŒÙ… ÙˆØ§Ø±Ø¯ ÛŒÙ‡ Ù†Ø¨Ø±Ø¯ (/mafia ÛŒØ§ /mafia2) Ø´Ùˆ.")
    kind, bid, team = membership
    company = c.execute(
        "SELECT id,name FROM owned_companies WHERE chat_id=? AND owner_id=? AND workers_bought>workers_used_mafia LIMIT 1",
        (m.chat.id, m.from_user.id)
    ).fetchone()
    if not company:
        return await m.reply("âŒ Ù‡ÛŒÚ† ÛŒØ§Ø±Ù Ø¢Ù…Ø§Ø¯Ù‡â€ŒØ§ÛŒ Ù†Ø¯Ø§Ø±ÛŒ! Ø§ÙˆÙ„ Ø¨Ø§ /hire ÛŒØ§Ø± Ø¨Ø®Ø±.")
    cid, cname = company
    ally_name = random.choice(ALLY_NAME_POOL)
    table = "mafia_members" if kind == "mafia" else "mafia2_members"
    fake_uid = -(cid * 1000000 + random.randint(1, 999999))
    c.execute(f"INSERT INTO {table}(battle_id,user_id,name,team,is_ally) VALUES(?,?,?,?,1)", (bid, fake_uid, ally_name, team))
    c.execute("UPDATE owned_companies SET workers_used_mafia=workers_used_mafia+1 WHERE id=?", (cid,))
    db.commit()
    await m.reply(f"ðŸ”« Â«{ally_name}Â» Ø§Ø² Â«{cname}Â» Ù…Ø®ÙÛŒØ§Ù†Ù‡ ÙˆØ§Ø±Ø¯ ØªÛŒÙ…Øª Ø´Ø¯!\n(Ø§ÛŒÙ† ÛŒØ§Ø± Ø³Ù‡Ù…ÛŒ Ø§Ø² Ø¬Ø§ÛŒØ²Ù‡ Ù†Ù…ÛŒâ€ŒØ¨Ø±Ù‡ØŒ ÙÙ‚Ø· ØªØ¹Ø¯Ø§Ø¯ ØªÛŒÙ…Øª Ø±Ùˆ Ø²ÛŒØ§Ø¯ Ù…ÛŒâ€ŒÚ©Ù†Ù‡)")


@dp.message(Command("cashout"))
async def cashout_company(m: Message):
    try:
        cid = int(m.text.split()[1])
    except:
        return await m.reply("Usage: /cashout [Ø´Ù…Ø§Ø±Ù‡ Ø´Ø±Ú©Øª] (Ø´Ù…Ø§Ø±Ù‡â€ŒÙ‡Ø§ Ø±Ùˆ Ø§Ø² /mycompanies Ø¨Ø¨ÛŒÙ†)")
    row = c.execute("SELECT owner_id,name,value FROM owned_companies WHERE id=? AND chat_id=?", (cid, m.chat.id)).fetchone()
    if not row:
        return await m.reply("âŒ Ù‡Ù…Ú†ÛŒÙ† Ø´Ø±Ú©ØªÛŒ Ù¾ÛŒØ¯Ø§ Ù†Ø´Ø¯.")
    owner_id, name, value = row
    if owner_id != m.from_user.id:
        return await m.reply("âŒ Ø§ÛŒÙ† Ø´Ø±Ú©Øª Ù…Ø§Ù„ ØªÙˆ Ù†ÛŒØ³Øª!")
    cashed = value // 2
    if cashed <= 0:
        return await m.reply("âŒ Ø§Ø±Ø²Ø´ Ø´Ø±Ú©Øª Ø®ÛŒÙ„ÛŒ Ú©Ù…Ù‡ Ú©Ù‡ Ú†ÛŒØ²ÛŒ Ù†Ù‚Ø¯ Ø¨Ø´Ù‡.")
    c.execute("UPDATE owned_companies SET value=value-? WHERE id=?", (cashed, cid))
    c.execute("UPDATE users SET sperm=sperm+? WHERE chat_id=? AND user_id=?", (cashed, m.chat.id, m.from_user.id))
    db.commit()
    await m.reply(f"ðŸ§¬ Ù†ØµÙ Ø§Ø±Ø²Ø´ Â«{name}Â» Ù†Ù‚Ø¯ Ø´Ø¯!\nðŸ’° {cashed} Ø§Ø³Ù¾Ø±Ù… Ø¨Ù‡ Ø­Ø³Ø§Ø¨Øª Ø§Ø¶Ø§ÙÙ‡ Ø´Ø¯.\nðŸ“‰ Ø§Ø±Ø²Ø´ Ø¨Ø§Ù‚ÛŒâ€ŒÙ…ÙˆÙ†Ø¯Ù‡â€ŒÛŒ Ø´Ø±Ú©Øª: {value-cashed} Ø§Ø³Ù¾Ø±Ù…\n(Ø¨Ø±Ø§ÛŒ ØªØ¨Ø¯ÛŒÙ„ Ø¨Ù‡ Ø³Ø§Ù†Øª: /tocent)")


async def company_dividend_loop(bot):
    while True:
        await asyncio.sleep(300)  # Ù‡Ø± Ûµ Ø¯Ù‚ÛŒÙ‚Ù‡ Ú†Ú© Ù…ÛŒâ€ŒÚ©Ù†Ù‡ Ú©Ø¯ÙˆÙ… Ø´Ø±Ú©Øª Ø¨Ø§ÛŒØ¯ Ø³ÙˆØ¯ Ø¨Ø¯Ù‡
        now = int(time.time())
        day = 24*60*60
        rows = c.execute("SELECT id,chat_id,owner_id,name,value,last_payout FROM owned_companies").fetchall()
        for cid, chat_id, owner_id, name, value, last_payout in rows:
            if now - last_payout < day:
                continue
            if value <= 0:
                c.execute("UPDATE owned_companies SET last_payout=? WHERE id=?", (now, cid))
                db.commit()
                continue
            income = int(value * COMPANY_DIVIDEND_PCT)
            c.execute("UPDATE users SET sperm=sperm+? WHERE chat_id=? AND user_id=?", (income, chat_id, owner_id))
            c.execute("UPDATE owned_companies SET last_payout=? WHERE id=?", (now, cid))
            db.commit()
            try:
                await bot.send_message(owner_id, f"ðŸ“ˆ Ø³ÙˆØ¯ Ø±ÙˆØ²Ø§Ù†Ù‡â€ŒÛŒ Ø´Ø±Ú©ØªØª Â«{name}Â»!\nðŸ§¬ {income} Ø§Ø³Ù¾Ø±Ù… Ø¨Ù‡ Ø­Ø³Ø§Ø¨Øª Ø§Ø¶Ø§ÙÙ‡ Ø´Ø¯.")
            except:
                pass
# ================== Ù¾Ø§ÛŒØ§Ù† Ú©Ù…Ù¾Ø§Ù†ÛŒ Ú©ÛŒØ± ==================

async def main():
    bot=Bot(TOKEN)
    from aiogram.types import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeDefault
    commands = [
        BotCommand(command="help", description="ðŸ“– Ø±Ø§Ù‡Ù†Ù…Ø§ÛŒ Ú©Ø§Ù…Ù„ Ø¨Ø§Ø²ÛŒ"),
        BotCommand(command="grow", description="ðŸŒ± Ø±Ø´Ø¯ Ú©Ù†"),
        BotCommand(command="size", description="ðŸ“Š Ø§Ù†Ø¯Ø§Ø²Ù‡ Ùˆ Ù¾Ø±ÙˆÙØ§ÛŒÙ„"),
        BotCommand(command="rank", description="ðŸ… Ø±Ù†Ú© Ùˆ Ù¾ÛŒØ´Ø±ÙØª Ø±ÙˆØ²Ø§Ù†Ù‡"),
        BotCommand(command="ranktop", description="ðŸ† Ø¨Ø±ØªØ±ÛŒÙ†â€ŒÙ‡Ø§ÛŒ Ø±Ù†Ú© Ú¯Ø±ÙˆÙ‡"),
        BotCommand(command="farm", description="ðŸŒ¾ Ù¾Ù†Ù„ Ù…Ø²Ø±Ø¹Ù‡â€ŒÛŒ Ø§Ø³Ù¾Ø±Ù…"),
        BotCommand(command="farmrank", description="ðŸŒ¾ Ø±Ù†Ú© Ù…Ø²Ø±Ø¹Ù‡â€ŒÛŒ Ù…Ù† (Ø²Ù†Ø¯Ù‡)"),
        BotCommand(command="farmleader", description="ðŸ“Š Ø¬Ø¯ÙˆÙ„ Ø±Ù†Ú© Ù…Ø²Ø±Ø¹Ù‡â€ŒÛŒ Ú¯Ø±ÙˆÙ‡"),
        BotCommand(command="tosperm", description="ðŸ§¬ ØªØ¨Ø¯ÛŒÙ„ Ø³Ø§Ù†Øª Ø¨Ù‡ Ø§Ø³Ù¾Ø±Ù…"),
        BotCommand(command="tocent", description="ðŸ’° ØªØ¨Ø¯ÛŒÙ„ Ø§Ø³Ù¾Ø±Ù… Ø¨Ù‡ Ø³Ø§Ù†Øª"),
        BotCommand(command="top", description="ðŸ† Ø¬Ø¯ÙˆÙ„ Ø¨Ø²Ø±Ú¯Ø§Ù†"),
        BotCommand(command="market", description="ðŸ›’ Ø¨Ø§Ø²Ø§Ø± Ø³Ù„Ø¨Ø±ÛŒØªÛŒ"),
        BotCommand(command="collection", description="ðŸ“š Ú©Ø§Ù„Ú©Ø´Ù† Ù…Ù†"),
        BotCommand(command="spin", description="ðŸŽ° Ø§Ø³Ù¾ÛŒÙ† Ø³Ù„Ø¨Ø±ÛŒØªÛŒ"),
        BotCommand(command="buy", description="ðŸ› Ø®Ø±ÛŒØ¯ Ø³Ù„Ø¨Ø±ÛŒØªÛŒ"),
        BotCommand(command="sell", description="ðŸ’¸ ÙØ±ÙˆØ´ Ø³Ù„Ø¨Ø±ÛŒØªÛŒ"),
        BotCommand(command="list", description="ðŸª ÙØ±ÙˆØ´ Ø¨Ù‡ Ø¯ÛŒÚ¯Ø±Ø§Ù†"),
        BotCommand(command="lock", description="ðŸ”’ Ù‚ÙÙ„ Ú©Ø±Ø¯Ù† Ø³Ù„Ø¨Ø±ÛŒØªÛŒ"),
        BotCommand(command="pvp", description="âš”ï¸ Ø¯ÙˆØ¦Ù„"),
        BotCommand(command="mafia", description="ðŸ”« Ø¬Ù†Ú¯ Ù…Ø§ÙÛŒØ§ ØªÛŒÙ…ÛŒ"),
        BotCommand(command="mafia2", description="ðŸ”« Ù…Ø§ÙÛŒØ§ (ÙØ§Ø´â€ŒØ´Ø¯Ù† ØªÛŒÙ…â€ŒÙ‡Ø§ Ø¯Ø± Ù¾Ø§ÛŒØ§Ù†)"),
        BotCommand(command="loan", description="ðŸ’° ÙˆØ§Ù… Ø¯Ø§Ø¯Ù†"),
        BotCommand(command="repay", description="âœ… Ù¾Ø±Ø¯Ø§Ø®Øª Ø¨Ø¯Ù‡ÛŒ"),
        BotCommand(command="collectors", description="ðŸ† Ø¨Ù‡ØªØ±ÛŒÙ† Ú©Ù„Ú©Ø³ÛŒÙˆÙ†Ø±Ù‡Ø§"),
        BotCommand(command="gloan", description="ðŸ¦ ÙˆØ§Ù… Ú¯Ø±ÙØªÙ† Ø§Ø² Ø¨Ø§Ø²ÛŒ"),
        BotCommand(command="gpay", description="âœ… Ù¾Ø±Ø¯Ø§Ø®Øª ÙˆØ§Ù… Ø¨Ø§Ø²ÛŒ"),
        BotCommand(command="copen", description="ðŸ“ˆ Ø¨Ø§Ø² Ú©Ø±Ø¯Ù† Ø¨Ø§Ø²Ø§Ø± Ú©Ù…Ù¾Ø§Ù†ÛŒ (Ø§Ø¯Ù…ÛŒÙ†)"),
        BotCommand(command="invest", description="ðŸ’° Ø³Ø±Ù…Ø§ÛŒÙ‡â€ŒÚ¯Ø°Ø§Ø±ÛŒ Ø±ÙˆÛŒ ÛŒÙ‡ Ú©Ù…Ù¾Ø§Ù†ÛŒ"),
        BotCommand(command="cclose", description="ðŸ“‰ Ø¨Ø³ØªÙ† Ø¨Ø§Ø²Ø§Ø± Ùˆ Ø§Ø¹Ù„Ø§Ù… Ø¨Ø±Ù†Ø¯Ù‡ (Ø§Ø¯Ù…ÛŒÙ†)"),
        BotCommand(command="mycompanies", description="ðŸ¢ Ú©Ù…Ù¾Ø§Ù†ÛŒâ€ŒÙ‡Ø§ÛŒ Ù…Ù†"),
        BotCommand(command="bourseleader", description="ðŸ“Š Ø¬Ø¯ÙˆÙ„ Ø±Ù†Ú© Ø¨ÙˆØ±Ø³ Ú¯Ø±ÙˆÙ‡"),
        BotCommand(command="hire", description="ðŸ”« Ø®Ø±ÛŒØ¯ ÛŒØ§Ø± Ø¨Ø±Ø§ÛŒ Ú©Ù…Ù¾Ø§Ù†ÛŒ"),
        BotCommand(command="useyar", description="ðŸ•µï¸ ÙØ±Ø³ØªØ§Ø¯Ù† ÛŒØ§Ø± Ø¨Ù‡ Ù†Ø¨Ø±Ø¯ Ù…Ø§ÙÛŒØ§ÛŒ ÙØ¹Ù„ÛŒØª"),
        BotCommand(command="cashout", description="ðŸ’¸ Ù†Ù‚Ø¯ Ú©Ø±Ø¯Ù† Ù†ØµÙ Ø§Ø±Ø²Ø´ Ú©Ù…Ù¾Ø§Ù†ÛŒ"),
        BotCommand(command="addcm", description="âž• Ø§ÙØ²ÙˆØ¯Ù† Ø³Ø§Ù†Øª Ø¨Ù‡ Ú©Ø§Ø±Ø¨Ø± (Ø§Ø¯Ù…ÛŒÙ†)"),
        BotCommand(command="luckydrop", description="ðŸŽ‰ Ø¯Ø§Ø¯Ù† Ø³Ø§Ù†Øª Ø¨Ù‡ ÛŒÙ‡ Ø¨Ø§Ø²ÛŒÚ©Ù† Ø±Ù†Ø¯ÙˆÙ… (Ø§Ø¯Ù…ÛŒÙ†)"),
        BotCommand(command="bid", description="ðŸ”¨ Ù¾ÛŒØ´Ù†Ù‡Ø§Ø¯ Ø¯Ø§Ø¯Ù† ØªÙˆ Ù…Ø²Ø§ÛŒØ¯Ù‡"),
        BotCommand(command="auctionstatus", description="ðŸ“‹ ÙˆØ¶Ø¹ÛŒØª Ù…Ø²Ø§ÛŒØ¯Ù‡â€ŒÙ‡Ø§ÛŒ ÙØ¹Ø§Ù„"),
        BotCommand(command="myauctions", description="ðŸ—‚ï¸ Ú©Ø§Ù„Ú©Ø´Ù† Ù…Ø²Ø§ÛŒØ¯Ù‡â€ŒÛŒ Ù…Ù†"),
        BotCommand(command="auction", description="ðŸ”¨ Ø´Ø±ÙˆØ¹ Ù…Ø²Ø§ÛŒØ¯Ù‡ (Ø§Ø¯Ù…ÛŒÙ†)"),
        BotCommand(command="endauction", description="ðŸ Ù¾Ø§ÛŒØ§Ù† Ù…Ø²Ø§ÛŒØ¯Ù‡ (Ø§Ø¯Ù…ÛŒÙ†)"),
        BotCommand(command="resetgroup", description="âš ï¸ Ù¾Ø§Ú© Ú©Ø±Ø¯Ù† Ú©Ø§Ù…Ù„ Ø¯Ø§Ø¯Ù‡â€ŒÙ‡Ø§ÛŒ Ø§ÛŒÙ† Ú¯Ø±ÙˆÙ‡ (Ø§Ø¯Ù…ÛŒÙ†)"),
        BotCommand(command="backupdb", description="ðŸ’¾ Ø¨Ú©Ø§Ù¾ Ø¯ÛŒØªØ§Ø¨ÛŒØ³ ØªÙˆ Ù¾ÛŒÙˆÛŒ (Ø§Ø¯Ù…ÛŒÙ†)"),
        BotCommand(command="restoredb", description="â™»ï¸ Ø¨Ø§Ø²Ú¯Ø±Ø¯Ø§Ù†ÛŒ Ø¯ÛŒØªØ§Ø¨ÛŒØ³ Ø§Ø² ÙØ§ÛŒÙ„ Ø¨Ú©Ø§Ù¾ (Ø§Ø¯Ù…ÛŒÙ†)"),
        BotCommand(command="addsperm", description="âž• Ø§ÙØ²ÙˆØ¯Ù† Ø§Ø³Ù¾Ø±Ù… Ø¨Ù‡ Ú©Ø§Ø±Ø¨Ø± (Ø§Ø¯Ù…ÛŒÙ†)"),
        BotCommand(command="addspermall", description="âž• Ø§ÙØ²ÙˆØ¯Ù† Ø§Ø³Ù¾Ø±Ù… Ø¨Ù‡ Ù‡Ù…Ù‡ (Ø§Ø¯Ù…ÛŒÙ†)"),
        BotCommand(command="addcb", description="ðŸ‘‘ Ø¯Ø§Ø¯Ù†/Ú¯Ø±ÙØªÙ† Ø³Ù„Ø¨Ø±ÛŒØªÛŒ Ø§Ø² Ú©Ø§Ø±Ø¨Ø± (Ø§Ø¯Ù…ÛŒÙ†)"),
        BotCommand(command="getfileid", description="ðŸ†” Ú¯Ø±ÙØªÙ† file_id Ø¹Ú©Ø³ (Ø§Ø¯Ù…ÛŒÙ†)"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    await bot.set_my_commands(commands, scope=BotCommandScopeAllGroupChats())
    asyncio.create_task(check_loans(bot))
    asyncio.create_task(company_dividend_loop(bot))
    asyncio.create_task(auction_loop(bot))
    await dp.start_polling(bot)

if __name__=="__main__":
    import asyncio
    asyncio.run(main())
