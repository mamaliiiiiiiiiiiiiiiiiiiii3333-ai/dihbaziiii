import os, sqlite3, random, time, re, logging, traceback, math
import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaPhoto
from aiogram.types import BufferedInputFile
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

# ===== همه‌ی جدول‌های اقتصادی حالا با chat_id اسکوپ میشن =====
# یعنی هر گروه (یا چت خصوصی) یه اقتصاد کاملاً مستقل داره؛
# آیدی عددی کاربر تو گروه‌های مختلف به‌صورت جدا شمرده میشه.
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

try:
    c.execute("ALTER TABLE users ADD COLUMN tokens INTEGER DEFAULT 0")
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

SPERM_RATE = 2  # ۱ سانت = ۲ اسپرم (واحد جداگانه‌ی بخش بورس)

def strip_command(text: str) -> str:
    """حذف /command یا /command@botusername از ابتدای متن و برگردوندن بقیه‌ی متن.
    این کار لازمه چون تو گروه‌ها تلگرام معمولاً @یوزرنیم بات رو به دستور می‌چسبونه
    (مثلاً /buy@YourBot Kylie Jenner) و replace ساده‌ی رشته این حالت رو درست پارس نمی‌کنه."""
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
    return row[0] if row else "کاربر"

# ===== توکن بازی 🎟 =====
# - هر دست مینی‌گیم (/box ، /climb ، /bj) ۱ توکن ورودی می‌خواد (جدا از شرط)
# - قیمت هر توکن = ۵٪ سایز لحظه‌ی خرید (گرد‌شده به نزدیک‌ترین عدد، حداقل ۱ سانت)؛ تو یه خرید قیمت ثابته
# - برنده‌ی دوئل (/pvp) با شانس بالا یه توکن هم می‌گیره
TOKEN_PRICE_PCT = 0.05
TOKEN_MAX_BUY = 20
DUEL_TOKEN_CHANCE = 0.7

# ===== مالیات 🏛 =====
# - مالیات کاشت: از صفحه‌ی ۴ پنل مزرعه به بعد (هر صفحه ۹ زمین) هر بار کاشتن ۱۰۰ سانت
# - مالیات ثروت: هر ۲۴ ساعت ۵٪ ثروت پولدارترین فرد هر گروه (ثروت = سایز + اسپرم؛ اسپرم بورس هم حساب می‌شه)
# - هر دو مالیات بین ۳ تا از فعال‌ترین بازیکنای گروه (به‌جز پرداخت‌کننده) پخش می‌شن؛ اگه فعالی نباشه می‌سوزن
FARM_TAX_FROM_PAGE = 4
TAX_RECIPIENTS = 3
ACTIVITY_WINDOW_DAYS = 7
# راه فرار مالیاتی 🕵️: هر کی تو ۲۴ ساعت اخیر ۱۵ دوئل + ۱۰ مینی‌گیم (/box ، /climb ، /bj) انجام داده باشه از مالیات ۵٪ پولدارترین معافه
# (مالیات کاشت مزرعه معافیت نداره و برای همه قطعیه)
TAX_EVASION_DUELS = 15
TAX_EVASION_GAMES = 10
TAX_EVASION_WINDOW = 24 * 3600
# پولدارترین فرد گروه حداقل شرط دوئلش این درصد از سایزشه (تا با دوئل‌های ریز و الکی فرار مالیاتی نگیره)
RICHEST_MIN_DUEL_PCT = 0.015

# ===== بازار کریپتو (ثابت‌های قابل تنظیم؛ خود کوین‌ها بالای بخش کریپتو تعریف شدن) =====
CRYPTO_FEE_PCT = 0.01            # کارمزد خرید و فروش
CRYPTO_MIN_TRADE = 5             # حداقل معامله (سانت)
CRYPTO_MAX_TRADE_PCT = 0.30      # سقف هر خرید/تزریق نسبت به سایز
CRYPTO_COOLDOWN = 15             # ثانیه بین دو معامله‌ی یه نفر
CRYPTO_INJECT_MIN = 20           # حداقل تزریق (سانت)
FARM_PLANT_TAX = 100
WEALTH_TAX_PCT = 0.05
WEALTH_TAX_INTERVAL = 24 * 3600

def plot_has_tax(plot_index):
    """plot_index از ۰ شروع می‌شه؛ هر صفحه‌ی پنل FARM_PAGE_SIZE تا زمین داره."""
    return plot_index // FARM_PAGE_SIZE + 1 >= FARM_TAX_FROM_PAGE

def get_tokens(chat_id, uid):
    row = c.execute("SELECT tokens FROM users WHERE chat_id=? AND user_id=?", (chat_id, uid)).fetchone()
    return (row[0] or 0) if row else 0

def token_price(size_cm):
    return max(1, int(size_cm * TOKEN_PRICE_PCT + 0.5))

def add_tokens(chat_id, uid, n=1):
    c.execute("UPDATE users SET tokens=COALESCE(tokens,0)+? WHERE chat_id=? AND user_id=?", (n, chat_id, uid))
    db.commit()

def take_token(chat_id, uid):
    """یه توکن مصرف می‌کنه؛ اگه نداشت False برمی‌گردونه."""
    cur = c.execute(
        "UPDATE users SET tokens=tokens-1 WHERE chat_id=? AND user_id=? AND COALESCE(tokens,0)>=1",
        (chat_id, uid)
    )
    db.commit()
    return cur.rowcount > 0

def no_token_text(chat_id, uid):
    price = token_price(get_size(chat_id, uid))
    return (
        "🎟 برای این بازی توکن لازمه!\n"
        f"💰 الان هر توکن {price} سانته ({int(TOKEN_PRICE_PCT*100)}٪ سایزت)\n"
        "🛒 /buytoken [تعداد] — خرید توکن\n"
        "⚔️ برنده‌ی دوئل‌ها هم با شانس بالا توکن می‌گیره!"
    )

dp=Dispatcher()

# ===== قفل دکمه‌های جابه‌جایی: هر پیام مال کسیه که دستور رو زده =====
# callback_data همه‌ی دکمه‌های ◀️ ▶️ آیدی «بیننده» (کسی که دستور رو زده) رو داره؛
# اگه کس دیگه‌ای بزنه فقط هشدار می‌گیره و پیام عوض نمی‌شه.
NAV_LOCK_MSG = "🔒 این پیام مال کسیه که دستور رو زده — خودت دستورش رو بزن تا کالکشن مال خودت باشه."
NAV_LEGACY_MSG = "⌛️ این پیام قدیمیه؛ دوباره دستورش رو بزن."

async def nav_guard(q, viewer_id):
    if q.from_user.id != viewer_id:
        await q.answer(NAV_LOCK_MSG, show_alert=True)
        return False
    return True

# ===== راهنمای بازی =====
HELP_SECTIONS = {
    "econ": (
        "💰 اقتصاد پایه",
        "🍆 /grow — هر چندساعت یه‌بار سایزت رو رشد بده\n"
        "📊 /size — دیدن اندازه، اسپرم و بدهیت\n"
        "🏆 /top — لیدربرد بزرگ‌ترین‌های گروه\n"
        "💳 /loan — گرفتن وام (با بهره)\n"
        "💵 /repay [مقدار] — پرداخت وام\n"
        "🧬 /tosperm [مقدار سانت] — تبدیل سانت به اسپرم (نرخ ۱ به ۲)\n"
        "💰 /tocent [مقدار اسپرم] — تبدیل اسپرم به سانت\n"
        "🎟 /token — دیدن توکن‌ها و قیمت فعلی هر توکن\n"
        f"🛒 /buytoken [تعداد] — خرید توکن بازی (هر توکن = {int(TOKEN_PRICE_PCT*100)}٪ سایزت)\n"
        f"🏛 /tax — مالیات: هر {WEALTH_TAX_INTERVAL//3600} ساعت {int(WEALTH_TAX_PCT*100)}٪ ثروت پولدارترین فرد گروه (سایز + اسپرم + کوین؛ هر {SPERM_RATE} اسپرم = ۱ سانت و اسپرم بورس و کوین‌ها هم حساب می‌شن) کم می‌شه و بین {TAX_RECIPIENTS} فعال‌ترین بازیکن (بیشترین پیام تو {ACTIVITY_WINDOW_DAYS} روز اخیر) پخش می‌شه؛ این‌جا می‌بینی کی پولدارترینه و فعال‌ترین‌ها کی‌ان\n"
        f"🕵️ فرار مالیاتی: اگه تو {TAX_EVASION_WINDOW//3600} ساعت اخیر {TAX_EVASION_DUELS} دوئل (/pvp) و {TAX_EVASION_GAMES} مینی‌گیم (/box ، /climb ، /bj) انجام داده باشی از مالیات {int(WEALTH_TAX_PCT*100)}٪ پولدارترین معافی؛ مالیات مزرعه معافیت نداره (پیشرفتت تو /tax)\n\n"
        "🎮 بازی‌های سریع (جعبه، نردبان، بلک‌جک) تو بخش «مینی‌گیم‌ها» هستن و برای هر دست توکن می‌خوان."
    ),
    "games": (
        "🎮 مینی‌گیم‌ها",
        "همه‌ی این بازی‌ها با سانت کار می‌کنن، فقط تو گروه اجرا می‌شن و دکمه‌هاشون فقط برای کسیه که دستور رو زده.\n\n"
        "🎟 رایگان نیستن! هر دست ۱ توکن ورودی می‌خواد (جدا از شرط):\n"
        f"• خرید: /buytoken [تعداد] — هر توکن {int(TOKEN_PRICE_PCT*100)}٪ سایزت (حداقل ۱ سانت)\n"
        f"• دوئل: برنده‌ی /pvp با {int(DUEL_TOKEN_CHANCE*100)}٪ شانس یه توکن هم می‌گیره\n"
        "• موجودی: /token یا /size\n\n"
        "🎁 /box [مبلغ] — جعبه‌ی شانس\n"
        "۴ جعبه‌ی بسته میاد و یکی رو انتخاب می‌کنی: 💎 ×۳ | 🔄 شرطت برمی‌گرده | 💣💣 می‌سوزه. جای جعبه‌ها هر دور رندومه و آخرش همه‌شون باز می‌شن.\n"
        "(حداکثر شرط ۱۰۰ سانت)\n\n"
        "🪜 /climb [مبلغ] — نردبان\n"
        "هر بار «برو بالاتر» رو بزنی ۷۵٪ شانس داری یه پله بری بالا و ضریبت بزرگ‌تر بشه (×۱.۳ تا ×۵.۶ تو پله‌ی ۶)؛ ۲۵٪ می‌افتی و کل شرط می‌سوزه. هر لحظه می‌تونی «برداشت» رو بزنی. رسیدن به پله‌ی ۶ خودکار برداشت می‌شه.\n"
        "(حداکثر شرط ۱۰۰ سانت | ۳ دقیقه بی‌حرکتی = خودکار برداشت)\n\n"
        "🃏 /bj [مبلغ] — بلک‌جک (۲۱)\n"
        "بازی کارتی علیه دیلر: به ۲۱ نزدیک شو ولی ردش نکن! آموزش کامل با مثال تو بخش «🃏 بلک‌جک» همین راهنماست.\n"
        "(حداکثر شرط ۱۰۰ سانت)\n\n"
        "💡 شرط تو نردبان و بلک‌جک همون اول کم می‌شه؛ هر نفر تو هر گروه فقط یه دست فعال از هر کدوم داره و با ریستارت ربات هم چیزی گم نمی‌شه.\n"
        "⚔️ بازی‌های دونفره (دوئل و مافیا) تو بخش «دوئل و رنک» و «مافیا» هستن."
    ),
    "blackjack": (
        "🃏 بلک‌جک (۲۱)",
        "🎯 هدف\n"
        "دستت رو به ۲۱ نزدیک‌تر از دیلر کن، بدون اینکه از ۲۱ رد بشی. رد شدن از ۲۱ یعنی سوختن (Bust) و باخت فوری.\n\n"
        "▶️ شروع بازی\n"
        "/bj [مبلغ] — مثلاً /bj 20 (بین ۱ تا ۱۰۰ سانت؛ /blackjack هم کار می‌کنه)\n"
        "هر دست ۱ توکن ورودی می‌خواد (با /buytoken می‌خری). شرطت همون اول کم می‌شه. دو کارت رو می‌گیری، دیلر هم دو کارت داره ولی فقط یکیش رو می‌بینی و اون یکی 🂠 مخفیه.\n\n"
        "🔢 ارزش کارت‌ها\n"
        "• ۲ تا ۱۰ → همون عدد\n"
        "• J ، Q ، K → ۱۰ تا\n"
        "• A (آس) → ۱۱ یا ۱؛ خودکار طوری حساب می‌شه که به نفعت باشه (مثلاً A + 9 = ۲۰، ولی A + 9 + 5 = ۱۵)\n\n"
        "🎮 نوبت تو (دو دکمه)\n"
        "🃏 کارت بگیر — یه کارت دیگه می‌گیری. اگه جمع بیشتر از ۲۱ شد می‌سوزی و دیلر اصلاً بازی نمی‌کنه. اگه دقیقاً ۲۱ شد، خودکار «بایست» زده می‌شه.\n"
        "✋ بایست — دستت همین‌جا بسته می‌شه و نوبت دیلره.\n\n"
        "🎩 نوبت دیلر\n"
        "کارت مخفیش رو رو می‌کنه و تا وقتی جمعش کمتر از ۱۷ باشه کارت می‌گیره؛ روی ۱۷ یا بیشتر می‌ایسته. دیلر انتخابی نداره، همیشه همین قانون رو اجرا می‌کنه.\n\n"
        "💰 نتیجه و پرداخت (مثلاً شرط ۲۰ سانتی)\n"
        "🏆 جمعت از دیلر بیشتر (یا دیلر سوخت) → ×۲ → ۴۰ سانت می‌گیری (۲۰ سود)\n"
        "🂡 بلک‌جک → ×۲.۵ → ۵۰ سانت می‌گیری (۳۰ سود)\n"
        "🤝 جمع مساوی → شرطت برمی‌گرده (۲۰ سانت)\n"
        "💥 جمعت از دیلر کمتر یا سوختی → ۲۰ سانت از دست میره\n\n"
        "🂡 بلک‌جک یعنی چی؟\n"
        "فقط وقتی که با همون دو کارت اول به ۲۱ برسی: یه آس + یه کارت ده‌تایی (۱۰ ، J ، Q ، K). ۲۱ با سه کارت و بیشتر بلک‌جک حساب نمی‌شه و فقط برد معمولیه. بلک‌جک همون اول بازی تموم می‌شه. اگه دیلر هم بلک‌جک بیاره مساویه؛ اگه فقط دیلر بیاره همون اول می‌بازی.\n\n"
        "📖 مثال\n"
        "دست تو: K♠ 6♥ (۱۶) | دیلر: 9♦ 🂠\n"
        "«کارت بگیر» می‌زنی و 4♣ میاد → ۲۰. «بایست» می‌زنی. دیلر کارت مخفیش رو باز می‌کنه: 9♦ 7♣ = ۱۶ → کمتر از ۱۷ پس کارت می‌گیره و 8♠ میاد → ۲۴ و می‌سوزه. بردی!\n\n"
        "💡 نکته‌ها\n"
        "• ۱۷ یا بیشتر معمولاً امنه، بایست بزن. زیر ۱۲ هیچ خطری نداری و بگیر.\n"
        "• اگه دیلر کارت رویی ضعیف داره (۲ تا ۶)، احتمال سوختنش بالاست.\n"
        "• دابل و اسپلیت نداره، بازی ساده‌ست.\n\n"
        "⏳ هر نفر تو هر گروه فقط یه دست فعال داره. اگه ۳ دقیقه هیچ حرکتی نکنی خودکار «بایست» زده می‌شه، و با ریستارت ربات هم دستت گم نمی‌شه."
    ),
    "crypto": (
        "🪙 بازار کریپتو",
        "بازار مشترک هر گروه؛ واحد همه‌چیز سانته. هر کوین «پول رسمی» یه حزبه و هرچی شرکت‌های اون حزب موفق‌تر باشن، کوینش ارزشمندتر می‌شه (مثل دنیای واقعی).\n\n"
        "🟠 BTK بیتکیر | 🔷 ETK اترکص | 🍈 BGT بیگتیت (پرنوسان)\n\n"
        "🔒 معامله (خرید، فروش، تزریق) فقط تو پیوی ربات انجام می‌شه تا کسی نفهمه چی می‌خری؛ اگه تو گروه بزنی ربات می‌فرستتت پیوی. اگه تو چند گروه بازی می‌کنی با /tgroup گروه رو انتخاب کن. خبرِ معامله‌های خیلی بزرگ تو گروه میاد ولی اسم نهنگ ناشناسه.\n\n"
        "🛒 /cbuy [کوین] [سانت] — خرید (مثلاً /cbuy BTK 100)\n"
        "💰 /csell [کوین] [مقدار یا all] — فروش\n"
        "📈 /cchart [کوین] — چارت قیمت | 🪙 /crypto — قیمت‌ها | 👛 /cwallet — کیف پول\n"
        "💉 /cinject [کوین] [سانت] — تزریق به بازار: سانتت بدون گرفتن کوین می‌ره تو استخر و قیمت بالا می‌ره (برای همه‌ی دارنده‌ها)؛ تو اخبار اعلام می‌شه\n"
        "📰 /cnews — اخبار بازار (معامله‌ی سنگین، تزریق، ورود شرکت‌ها به حزب‌ها، فروش اجباری مالیات)\n"
        "📊 هر ۱۰ دقیقه بازار یه قدم حرکت می‌کنه و چارت عکسی تو گروه میاد (ادمین با /cauto خاموش/روشنش می‌کنه)\n\n"
        "⚙️ قیمت چطور ساخته می‌شه؟\n"
        "هر کوین یه استخر نقدینگی داره (قیمت = سانتِ استخر ÷ کوینِ استخر). خرید قیمت رو بالا می‌بره و فروش پایین میاره؛ هرچی معامله بزرگ‌تر، اثرش بیشتر (اسلیپیج). کوین‌های کم‌عمق مثل BGT خیلی تکون می‌خورن.\n\n"
        "🏛 حزب‌ها\n"
        "/party — وضعیت حزب‌ها، شرکت‌هاشون و قدرت اقتصادی‌شون\n"
        "برنده‌ی هر شرکت تو بورس (/copen) خودش با /joinparty [شماره شرکت] [کوین] انتخاب می‌کنه شرکتش پشت کدوم حزب (و پول رسمی) وایسته؛ بعد از انتخاب ۲۴ ساعت نمی‌تونه عوضش کنه، و شرکتِ بدون حزب به هیچ کوینی کمک نمی‌کنه. قدرت یه حزب = جمع ارزش شرکت‌هایی که پشتشونن (نسبت به میانگین حزب‌ها). ارزش واقعی کوین = قیمت پایه × سیکل بازار × حال‌وهوای خبرها × قدرت حزب؛ و ربات‌های بازارساز هر ۱۰ دقیقه قیمت رو به‌سمت همین ارزش می‌برن. شرکتی که به یه حزب بپیونده کوینش رو بالا می‌بره، رفتنش یا نقد کردن (/cashout) ارزش شرکت، حزب رو ضعیف می‌کنه.\n\n"
        "📏 قوانین\n"
        f"• کارمزد هر خرید و فروش {int(CRYPTO_FEE_PCT*100)}٪ (بین فعال‌ترین بازیکنا پخش می‌شه)\n"
        f"• حداقل معامله {CRYPTO_MIN_TRADE} سانت؛ هر خرید یا تزریق حداکثر {int(CRYPTO_MAX_TRADE_PCT*100)}٪ سایزت\n"
        f"• بین دو معامله {CRYPTO_COOLDOWN} ثانیه صبر کن\n"
        "• ارزش کوین‌ها (با اسلیپیج فروش) تو ثروتِ مالیات ۵٪ پولدارترین حساب می‌شه؛ اگه سانت و اسپرم کافی نباشه کوین‌هاش اجباری فروخته می‌شن"
    ),
    "pvp": (
        "⚔️ دوئل و رنک",
        "⚔️ /pvp [مبلغ شرط] — چالش دادن به یه نفر برای دوئل ۱ به ۱\n"
        "🏅 /rank — دیدن رنک، امتیاز (RP) و پیشرفت روزانه‌ت\n"
        "🏆 /ranktop — لیدربرد رنک گروه\n"
        "\nنکته: شانس بردت تو دوئل ثابت نیست — اگه زیادی برده باشی شانست کم می‌شه، اگه زیادی باخته باشی شانست زیاد می‌شه تا عادلانه بمونه.\n\n"
        f"🎟 برنده‌ی دوئل علاوه بر جایزه با {int(DUEL_TOKEN_CHANCE*100)}٪ شانس یه توکن بازی هم می‌گیره (/token).\n\n"
        f"👑 پولدارترین فرد گروه حداقل شرط دوئلش {RICHEST_MIN_DUEL_PCT*100:g}٪ سایزشه (تا با دوئل‌های ریز فرار مالیاتی نگیره)."
    ),
    "mafia": (
        "🔫 مافیا",
        "🔫 /mafia [مبلغ شرط] — ساختن یه نبرد مافیای تیمی (بدون محدودیت نفرات)\n"
        "🕵️ /mafia2 [مبلغ شرط] — نسخه‌ی مخفیانه‌ی مافیا (تیم‌ها لو نمی‌رن)\n\n"
        "بقیه با زدن دکمه‌ی داخل پیام به یه تیم ملحق می‌شن، بعد سازنده یا حریف با «شروع نبرد» بازی رو تموم می‌کنه. تیم بزرگ‌تر می‌بره و جایزه بین برنده‌ها تقسیم می‌شه."
    ),
    "celeb": (
        "🌟 سلبریتی‌ها",
        "🎰 /spin [تیر: S/A/B/PH] — اسپین گرفتن یه سلبریتی رندوم از یه تیر\n"
        "🏪 /market — دیدن سلبریتی‌های قابل‌خرید\n"
        "🛒 /buy [اسم] — خرید مستقیم یه سلبریتی از مارکت\n"
        "📁 /collection — دیدن کلکسیون خودت\n"
        "📜 /list — لیست کردن یه سلبریتی برای فروش به بقیه\n"
        "💸 /sell [اسم] — فروش یه سلبریتی\n"
        "🔒 /lock [اسم] — قفل کردن یه سلبریتی در برابر فروش خودکار (هزینه بر اساس تیرش فرق داره)\n"
        "🏅 /collectors — کی بیشترین سلبریتی رو داره\n"
        "💳 /gloan — وام مخصوص خرید سلبریتی\n"
        "💵 /gpay [مقدار] — پرداخت اون وام"
    ),
    "bourse": (
        "📈 بورس",
        "📈 /copen — باز کردن یه بازار بورس جدید (ادمین، می‌شه چندتا رو همزمان باز داشت)\n"
        "🧬 /invest — سرمایه‌گذاری مخفیانه روی یه شرکت (با اسپرم، از طریق پیوی؛ اگه چندتا بازار همزمان باز باشه اول انتخاب می‌کنی کدوم)\n"
        "📉 /cclose [شماره بازار] — بستن یه بازار خاص و اعلام برنده‌ها (ادمین؛ اگه فقط یکی باز باشه نیازی به شماره نیست)\n"
        "🏢 /mycompanies — شرکت‌هایی که بردی\n"
        "📊 /bourseleader — جدول رنک بورس گروه (ارزش خالص، تعداد شرکت، بردها، سود روزانه)\n"
        "🕵️ /useyar — فرستادن یه یار (کارگر) از شرکتت به یه نبرد مافیای فعلیت\n"
        "💰 /cashout [شماره شرکت] — نقد کردن نصف ارزش یه شرکت به اسپرم\n\n"
        "بورس با «اسپرم» کار می‌کنه، نه سانت — اول با /tosperm سانتت رو تبدیل کن."
    ),
    "farm": (
        "🌾 مزرعه‌ی اسپرم",
        "🌾 /farm — باز کردن پنل مزرعه (یه گرید از زمین‌هات با دکمه)\n\n"
        "➕ زمین خالی → بزن روش تا تخمی که تو انبارت داری رو بکاری\n"
        "⏳ در حال رشد → بزن روش تا ببینی چقدر مونده\n"
        "✅ آماده‌ی برداشت → بزن روش تا اسپرم بگیری\n"
        "💀 فاسدشده → اگه دیر بجنبی نصف ارزشش رو می‌گیری\n\n"
        "از همون پنل می‌تونی زمین جدید باز کنی، یه تخم تکی شانسی بخری (۷ سانت)، یا یه پک ۳تایی بخری (۴۰ سانت). رنگ‌های ارزون (⚪🟢) شانس دارن موقع برداشت یه تخم دیگه از خودشون بندازن؛ بقیه (🔷🔵🟪🟣🟡) هیچ‌وقت تکرار نمی‌شن ولی سودشون بیشتره — هرچی کمیاب‌تر، دیرتر می‌رسه ولی سودش نامتناسب بیشتره.\n\n"
        f"💰 مالیات کاشت: از صفحه‌ی {FARM_TAX_FROM_PAGE} پنل به بعد (زمین‌های با علامت ➕💰) هر بار کاشتن {FARM_PLANT_TAX} سانت مالیات داره؛ جدا از قیمت تخمه از سانتت کم می‌شه و بین {TAX_RECIPIENTS} فعال‌ترین بازیکن گروه پخش می‌شه. سانت کافی نداشته باشی نمی‌تونی بکاری. این مالیات برای همه قطعیه و فرار مالیاتی روش اثر نداره.\n\n"
        "🌾 /farmrank — رنک مزرعه‌ی خودت، بر اساس دقیقاً چیزی که الان تو زمین‌ها و انبارته\n"
        "📊 /farmleader — جدول رنک مزرعه‌ی کل گروه"
    ),
    "auction": (
        "🔨 مزایده",
        "🔨 /bid [مبلغ] — پیشنهاد دادن (اگه چندتا مزایده همزمان فعاله: /bid [شماره] [مبلغ] یا ریپلای روی عکس همون مزایده)\n"
        "📋 /auctionstatus — دیدن همه‌ی مزایده‌های فعال، بالاترین پیشنهادها و زمان باقی‌مونده\n"
        "🗂 /aucol — کالکشن همه‌ی مزایده‌های فعال با عکس، بالاترین پیشنهاد، حداقل پیشنهاد بعدی و زمان باقی‌مونده\n"
        "🖼 /bidcol — کالکشن مزایده‌ی تو: سلبریتی‌هایی که الان بالاترین پیشنهاد روشونه (با عکس) + مجموعشون و سانتی که بعد خرید همه می‌مونه (ریپلای کنی مال یکی دیگه رو می‌بینی)\n"
        "❌ /cancelbid [شماره] — لغو بالاترین پیشنهادت (کل سانتش برمی‌گرده و مزایده بدون پیشنهاد می‌مونه؛ دکمه‌ی لغو تو /bidcol هم همینو انجام میده)\n\n"
        "🔨 تیر مزایده: هر سلبریتی که تو مزایده ببری خودکار با عکسش میره تو /collection (تیر «🔨 مزایده»)؛ ارزشش همون مبلغیه که برنده شدی ولی قابل فروش نیست (/sell برای این تیر کار نمی‌کنه). اگه قبلاً داشته باشیش مبلغ برمی‌گرده.\n"
        "👑 ادمین: /addau [file_id] [اسم] ثبت سلبریتی تو تیر مزایده | /aulist لیستش | /auction [اسم] شروع مزایده‌ش | /giveau [file_id] [اسم] (ریپلای روی کاربر) دادن مستقیم به یه نفر\n\n"
        "🔒 دکمه‌های ◀️ ▶️ کالکشن‌ها فقط برای کسیه که دستور رو زده؛ هرکی بخواد کالکشن خودش رو ببینه باید دستورش رو بزنه.\n\n"
        "سانت پیشنهادت همون لحظه بلوکه می‌شه و اگه کسی بالاتر بده برمی‌گرده. هر پیشنهاد جدید تایمر ۱۲ ساعته‌ی همون مزایده رو از اول می‌کنه؛ هرکس ۱۲ ساعت بدون پیشنهاد بالاتر بمونه برنده‌ست.\n\n"
        "ادمین:\n"
        "🔨 /auction [file_id] [اسم] — شروع یه مزایده‌ی جدید (یا ریپلای رو یه عکس: /auction [اسم])؛ هرچندتا که بخوای همزمان\n"
        "🏁 /endauction [شماره] — پایان زودتر یه مزایده؛ با /endauction [شماره] cancel لغو می‌شه و پول برمی‌گرده"
    ),
}

def help_main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 اقتصاد پایه", callback_data="help:econ")],
        [InlineKeyboardButton(text="🎮 مینی‌گیم‌ها", callback_data="help:games")],
        [InlineKeyboardButton(text="🃏 بلک‌جک", callback_data="help:blackjack")],
        [InlineKeyboardButton(text="🪙 کریپتو", callback_data="help:crypto")],
        [InlineKeyboardButton(text="⚔️ دوئل و رنک", callback_data="help:pvp")],
        [InlineKeyboardButton(text="🔫 مافیا", callback_data="help:mafia")],
        [InlineKeyboardButton(text="🌟 سلبریتی‌ها", callback_data="help:celeb")],
        [InlineKeyboardButton(text="📈 بورس", callback_data="help:bourse")],
        [InlineKeyboardButton(text="🌾 مزرعه", callback_data="help:farm")],
        [InlineKeyboardButton(text="🔨 مزایده", callback_data="help:auction")],
    ])

@dp.message(Command("help"))
async def help_cmd(m: Message):
    kb = help_main_kb()
    await m.reply(
        "📖 راهنمای بازی\n\n"
        "یه بخش رو انتخاب کن تا کامندهاش رو ببینی:",
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith("help:"))
async def help_section(q: CallbackQuery):
    key = q.data.split(":")[1]
    main_kb = help_main_kb()
    if key == "back" or key not in HELP_SECTIONS:
        await q.message.edit_text("📖 راهنمای بازی\n\nیه بخش رو انتخاب کن تا کامندهاش رو ببینی:", reply_markup=main_kb)
        return await q.answer()
    title, body = HELP_SECTIONS[key]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ برگشت به فهرست", callback_data="help:back")]
    ])
    await q.message.edit_text(f"{title}\n\n{body}", reply_markup=kb)
    await q.answer()

# نگهداری موقت سرمایه‌گذاری‌هایی که کاربر توی گروه دکمه‌ش رو زده ولی هنوز مبلغ رو توی پیوی نفرستاده
pending_invest = {}  # user_id -> {"chat_id":..., "round_id":..., "slot":..., "ts":...}
PENDING_INVEST_TTL = 10 * 60  # بعد از ۱۰ دقیقه منقضی می‌شه

@dp.message(Command("grow"))
async def grow(m:Message):
    user(m.chat.id,m.from_user.id,m.from_user.full_name)
    size,last=c.execute("SELECT size,last_grow FROM users WHERE chat_id=? AND user_id=?",(m.chat.id,m.from_user.id)).fetchone()
    now=int(time.time())
    if now-last<COOLDOWN:
        rem=(COOLDOWN-(now-last))//60
        return await m.reply(f"⏳ هنوز {rem} دقیقه تا رشد بعدی مونده!")
    delta=random.randint(5,20)
    size=max(0,size+delta)
    c.execute("UPDATE users SET size=?,last_grow=? WHERE chat_id=? AND user_id=?",(size,now,m.chat.id,m.from_user.id)); db.commit()
    await m.reply(
        f"🌱 نتیجه رشد\n\n🍆 تغییر: {delta:+} سانت\n📏 اندازه فعلی: {size} سانت\n😎 ادامه بده قهرمان!"
    )

@dp.message(Command("size"))
async def size(m:Message):
    user(m.chat.id,m.from_user.id,m.from_user.full_name)
    s,sp,d=c.execute("SELECT size,sperm,debt FROM users WHERE chat_id=? AND user_id=?",(m.chat.id,m.from_user.id)).fetchone()
    await m.reply(
        f"📊 پروفایل شما\n\n🍆 اندازه: {s} سانت\n🧬 اسپرم (بورس): {sp}\n💸 بدهی: {d} سانت\n🎟 توکن بازی: {get_tokens(m.chat.id, m.from_user.id)}"
    )

@dp.message(Command("tosperm"))
async def to_sperm(m:Message):
    try:
        amount=int(m.text.split()[1])
    except:
        return await m.reply(f"استفاده: /tosperm [مقدار سانت]\nنرخ: هر ۱ سانت = {SPERM_RATE} اسپرم")
    if amount<=0:
        return await m.reply("❌ مقدار باید مثبت باشه.")
    user(m.chat.id,m.from_user.id,m.from_user.full_name)
    if get_size(m.chat.id,m.from_user.id)<amount:
        return await m.reply("❌ سانت کافی نداری.")
    gained=amount*SPERM_RATE
    c.execute("UPDATE users SET size=size-?,sperm=sperm+? WHERE chat_id=? AND user_id=?",(amount,gained,m.chat.id,m.from_user.id))
    db.commit()
    await m.reply(f"🧬 {amount} سانت تبدیل شد به {gained} اسپرم!")

@dp.message(Command("tocent"))
async def to_cent(m:Message):
    try:
        amount=int(m.text.split()[1])
    except:
        return await m.reply(f"استفاده: /tocent [مقدار اسپرم]\nنرخ: هر {SPERM_RATE} اسپرم = ۱ سانت")
    if amount<=0:
        return await m.reply("❌ مقدار باید مثبت باشه.")
    user(m.chat.id,m.from_user.id,m.from_user.full_name)
    if get_sperm(m.chat.id,m.from_user.id)<amount:
        return await m.reply("❌ اسپرم کافی نداری.")
    gained=amount//SPERM_RATE
    if gained<=0:
        return await m.reply(f"❌ حداقل {SPERM_RATE} اسپرم لازمه تا ۱ سانت بگیری.")
    used=gained*SPERM_RATE
    c.execute("UPDATE users SET sperm=sperm-?,size=size+? WHERE chat_id=? AND user_id=?",(used,gained,m.chat.id,m.from_user.id))
    db.commit()
    await m.reply(f"💰 {used} اسپرم تبدیل شد به {gained} سانت!")

# ===== مزرعه‌ی اسپرم =====
EGGS = {
    "white":  {"emoji": "⚪", "name": "تخم شل",         "chance": 45, "time": 30*60,   "min": 5,   "max": 10,  "replicate": 30},
    "green":  {"emoji": "🟢", "name": "تخم آبدار",      "chance": 20, "time": 2*3600,  "min": 20,  "max": 35,  "replicate": 15},
    "cyan":   {"emoji": "🔷", "name": "تخم فیروزه‌ای",   "chance": 15, "time": 4*3600,  "min": 40,  "max": 60,  "replicate": 0},
    "blue":   {"emoji": "🔵", "name": "تخم پرقدرت",     "chance": 10, "time": 6*3600,  "min": 60,  "max": 100, "replicate": 0},
    "indigo": {"emoji": "🟪", "name": "تخم سرمه‌ای",     "chance": 6,  "time": 9*3600,  "min": 100, "max": 150, "replicate": 0},
    "purple": {"emoji": "🟣", "name": "تخم رعدآسا",     "chance": 3,  "time": 12*3600, "min": 150, "max": 250, "replicate": 0},
    "gold":   {"emoji": "🟡", "name": "تخم ایلان ماسک", "chance": 1,  "time": 24*3600, "min": 500, "max": 800, "replicate": 0},
}
EGG_SURPRISE_CHANCE = 0.02   # شانس اینکه یه تخم ارزون در واقع طلایی مخفی دربیاد
FARM_SPOIL_MULTIPLIER = 2    # بعد این‌قدر برابر زمان اصلی، تخم فاسد میشه و نصف ارزش میده
FARM_PAGE_SIZE = 9           # هر صفحه از پنل چندتا خونه نشون بده (۳ در ۳)
EGG_SINGLE_COST = 7          # هزینه‌ی یه تخم تکی شانسی
EGG_PACK_COST = 40           # هزینه‌ی هر پک (۳ تخم شانسی)
EGG_PACK_SIZE = 3
PLOT_BASE_COST = 20          # هزینه‌ی باز کردن اولین زمین‌های اضافه؛ هرچی بیشتر داشته باشی گرون‌تر میشه

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
    """برمی‌گردونه: ('growing'|'ready'|'spoiled', ثانیه‌ی باقی‌مونده یا گذشته)"""
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
            row.append(InlineKeyboardButton(text="🔒", callback_data="farm:noop"))
        elif i in tiles:
            egg_type, planted_at = tiles[i]
            state, _ = tile_state(egg_type, planted_at)
            emoji = EGGS[egg_type]["emoji"]
            label = {"growing": f"{emoji}⏳", "ready": f"✅{emoji}", "spoiled": f"💀{emoji}"}[state]
            row.append(InlineKeyboardButton(text=label, callback_data=f"farm:tile:{page}:{i}"))
        else:
            row.append(InlineKeyboardButton(text="➕💰" if plot_has_tax(i) else "➕", callback_data=f"farm:tile:{page}:{i}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"farm:page:{page-1}"))
    nav.append(InlineKeyboardButton(text=f"📄 {page+1}/{total_pages}", callback_data="farm:noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"farm:page:{page+1}"))
    rows.append(nav)
    rows.append([InlineKeyboardButton(text=f"➕ باز کردن زمین جدید ({plot_unlock_cost(owned)} سانت)", callback_data=f"farm:unlock:{page}")])
    rows.append([InlineKeyboardButton(text=f"🥚 یه تخم تکی ({EGG_SINGLE_COST} سانت)", callback_data=f"farm:buyegg:{page}")])
    rows.append([InlineKeyboardButton(text=f"📦 پک ۳تایی ({EGG_PACK_COST} سانت)", callback_data=f"farm:buypack:{page}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def build_farm_text(chat_id, uid):
    inv = get_inventory(chat_id, uid)
    inv_txt = "، ".join(f"{EGGS[t]['emoji']}×{n}" for t, n in inv.items()) if inv else "خالیه"
    return (
        f"🌾 مزرعه‌ی اسپرم\n\n📦 انبار تخم: {inv_txt}\n\n➕ زمین خالی | ⏳ در حال رشد | ✅ آماده‌ی برداشت | 💀 فاسدشده (نصف ارزش)\n\n"
        f"💰 کاشتن از صفحه‌ی {FARM_TAX_FROM_PAGE} به بعد (➕💰) هر بار {FARM_PLANT_TAX} سانت مالیات داره (بین {TAX_RECIPIENTS} فعال‌ترین بازیکن پخش می‌شه)"
    )

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
        return await q.answer(f"❌ {cost} سانت لازم داری!", show_alert=True)
    c.execute("UPDATE users SET size=size-?, farm_plots=farm_plots+1 WHERE chat_id=? AND user_id=?", (cost, chat_id, uid))
    bump_farm_record(chat_id, uid, plots_opened=1, spent_cm=cost)
    db.commit()
    await q.answer("✅ یه زمین جدید باز شد!")
    await q.message.edit_text(build_farm_text(chat_id, uid), reply_markup=build_farm_keyboard(chat_id, uid, page))

@dp.callback_query(F.data.startswith("farm:buyegg:"))
async def farm_buyegg(q: CallbackQuery):
    page = int(q.data.split(":")[2])
    chat_id, uid = q.message.chat.id, q.from_user.id
    user(chat_id, uid, q.from_user.full_name)
    if get_size(chat_id, uid) < EGG_SINGLE_COST:
        return await q.answer(f"❌ {EGG_SINGLE_COST} سانت لازم داری!", show_alert=True)
    c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?", (EGG_SINGLE_COST, chat_id, uid))
    egg, surprise = roll_egg()
    add_egg_to_inventory(chat_id, uid, egg, 1)
    bump_farm_record(chat_id, uid, eggs_bought=1, spent_cm=EGG_SINGLE_COST)
    db.commit()
    alert = f"🥚 گرفتی: {EGGS[egg]['emoji']} {EGGS[egg]['name']}!"
    if surprise:
        alert = "🎉🎉 چی؟! این یکی اصلاً معمولی نبود!\n\n" + alert
    await q.answer(alert, show_alert=True)
    await q.message.edit_text(build_farm_text(chat_id, uid), reply_markup=build_farm_keyboard(chat_id, uid, page))

@dp.callback_query(F.data.startswith("farm:buypack:"))
async def farm_buypack(q: CallbackQuery):
    page = int(q.data.split(":")[2])
    chat_id, uid = q.message.chat.id, q.from_user.id
    user(chat_id, uid, q.from_user.full_name)
    if get_size(chat_id, uid) < EGG_PACK_COST:
        return await q.answer(f"❌ {EGG_PACK_COST} سانت لازم داری!", show_alert=True)
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
    alert = "🎉 پک باز شد:\n" + lines
    if surprise:
        alert = "🎉🎉 چی؟! یکیشون اصلاً معمولی نبود!\n\n" + alert
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
            return await q.answer(f"{info['emoji']} {info['name']} — {fmt_time(delta)} مونده", show_alert=True)
        gained = random.randint(info["min"], info["max"])
        if state == "spoiled":
            gained //= 2
        c.execute("UPDATE users SET sperm=sperm+? WHERE chat_id=? AND user_id=?", (gained, chat_id, uid))
        c.execute("DELETE FROM farm_tiles WHERE chat_id=? AND user_id=? AND plot_num=?", (chat_id, uid, num))
        bump_farm_record(chat_id, uid, eggs_harvested=1, total_harvest_value=gained)
        msg = f"{'💀 فاسد شده بود ولی بازم چیزی گیرت اومد!' if state=='spoiled' else '✅ برداشت شد!'}\n{info['emoji']} {info['name']}: +{gained} اسپرم"
        if info["replicate"] and random.randint(1, 100) <= info["replicate"]:
            add_egg_to_inventory(chat_id, uid, egg_type, 1)
            msg += f"\n🍀 یه {info['emoji']} {info['name']} دیگه هم افتاد تو انبارت!"
        db.commit()
        await q.answer(msg, show_alert=True)
        return await q.message.edit_text(build_farm_text(chat_id, uid), reply_markup=build_farm_keyboard(chat_id, uid, page))
    # زمین خالیه — نشون بده چی تو انبار داره که بکاره
    inv = get_inventory(chat_id, uid)
    if not inv:
        return await q.answer("📭 انبارت خالیه! اول یه پک تخم بخر.", show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{EGGS[t]['emoji']} {EGGS[t]['name']} ({n} تا)", callback_data=f"farm:plant:{page}:{num}:{t}")]
        for t, n in inv.items()
    ] + [[InlineKeyboardButton(text="⬅️ برگشت", callback_data=f"farm:page:{page}")]])
    tax_note = f"\n\n💰 کاشتن تو این زمین {FARM_PLANT_TAX} سانت مالیات داره (از صفحه‌ی {FARM_TAX_FROM_PAGE} به بعد)" if plot_has_tax(num) else ""
    await q.message.edit_text(f"🌱 کدوم تخم رو تو این زمین بکاری؟{tax_note}", reply_markup=kb)
    await q.answer()

@dp.callback_query(F.data.startswith("farm:plant:"))
async def farm_plant(q: CallbackQuery):
    _, _, page, num, egg_type = q.data.split(":")
    page, num = int(page), int(num)
    chat_id, uid = q.message.chat.id, q.from_user.id
    row = c.execute("SELECT count FROM farm_inventory WHERE chat_id=? AND user_id=? AND egg_type=?", (chat_id, uid, egg_type)).fetchone()
    if not row or row[0] <= 0:
        return await q.answer("❌ دیگه از این نداری!", show_alert=True)
    tax = FARM_PLANT_TAX if plot_has_tax(num) else 0
    if tax and get_size(chat_id, uid) < tax:
        return await q.answer(f"💸 کاشتن تو این زمین {tax} سانت مالیات داره و سانت کافی نداری!", show_alert=True)
    c.execute("UPDATE farm_inventory SET count=count-1 WHERE chat_id=? AND user_id=? AND egg_type=?", (chat_id, uid, egg_type))
    c.execute("INSERT INTO farm_tiles(chat_id,user_id,plot_num,egg_type,planted_at) VALUES(?,?,?,?,?)", (chat_id, uid, num, egg_type, int(time.time())))
    paid_to = []
    if tax:
        c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?", (tax, chat_id, uid))
        paid_to = distribute_tax(chat_id, uid, tax)
    bump_farm_record(chat_id, uid, eggs_planted=1, spent_cm=tax)
    db.commit()
    tax_msg = ""
    if tax:
        tax_msg = f"\n💰 {tax} سانت مالیات کاشت رفت" + (" و بین فعال‌ترین‌ها پخش شد." if paid_to else " (فعالی نبود، سوخت).")
    await q.answer(f"🌱 {EGGS[egg_type]['name']} کاشته شد!" + tax_msg)
    await q.message.edit_text(build_farm_text(chat_id, uid), reply_markup=build_farm_keyboard(chat_id, uid, page))

# ===== رنک مزرعه بر اساس وضعیت فعلی پنل =====
FARM_RANK_TIERS = [
    (0,    "🌱 نوزمین‌دار"),
    (100,  "🌾 کشاورز"),
    (300,  "🚜 تراکتوردار"),
    (700,  "🏭 صنعتی"),
    (1500, "👑 پادشاه مزرعه"),
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
    """محاسبه‌ی زنده‌ی وضعیت فعلی مزرعه: هرچی الان تو زمین‌ها و انبار داره."""
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
        f"🌾 رنک مزرعه‌ی شما\n\n"
        f"{tier}\n"
        f"💰 ارزش خالص فعلی: {st['net_worth']} اسپرم (تخمینی)\n"
        f"🟫 زمین‌های باز: {st['plots_owned']}\n"
        f"🌱 کاشته‌شده الان: {st['planted']} (⏳{st['growing']} در حال رشد | ✅{st['ready']} آماده | 💀{st['spoiled']} فاسد)\n"
        f"📦 تخم تو انبار: {st['inv_count']}\n\n"
        f"📜 رکورد کلی (از اول تا الان):\n"
        f"🥚 تخم خریده: {rec['eggs_bought']}\n"
        f"🌱 تخم کاشته: {rec['eggs_planted']}\n"
        f"🌾 تخم برداشت‌کرده: {rec['eggs_harvested']}\n"
        f"💰 کل اسپرم به‌دست‌اومده از برداشت: {rec['total_harvest_value']}\n"
        f"🟫 کل زمین‌های باز‌شده: {rec['plots_opened']}\n"
        f"💸 کل سانت خرج‌شده تو مزرعه: {rec['spent_cm']}"
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
        return await m.reply("📭 هنوز کسی تو این گروه مزرعه راه ننداخته!")
    board = []
    for (uid,) in candidates:
        st = compute_farm_stats(chat_id, uid)
        board.append((uid, st))
    board.sort(key=lambda x: x[1]["net_worth"], reverse=True)
    txt = "📊 جدول رنک مزرعه‌ی این گروه\n\n"
    for i, (uid, st) in enumerate(board[:10], 1):
        name = get_name(chat_id, uid)
        rec = get_farm_record(chat_id, uid)
        tier = get_farm_tier(st["net_worth"])
        txt += (
            f"{i}. {name}\n"
            f"   {tier}\n"
            f"   💰 ارزش الان: {st['net_worth']} اسپرم | 🟫 زمین: {st['plots_owned']} | "
            f"🌱 کاشته: {st['planted']} (✅{st['ready']}/⏳{st['growing']}/💀{st['spoiled']}) | 📦 انبار: {st['inv_count']}\n"
            f"   📜 رکورد: {rec['eggs_harvested']} برداشت | {rec['total_harvest_value']} اسپرم کل | {rec['plots_opened']} زمین باز‌شده\n\n"
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
            f"❌ این کاربر امروز {borrowed_today} سانت وام گرفته!\n"
            f"حداکثر روزانه ۵۰ سانته.\n"
            f"{'دیگه نمیتونه وام بگیره!' if remaining == 0 else f'فقط {remaining} سانت دیگه میتونه بگیره.'}"
        )

    c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?",(amt,m.chat.id,lender))
    c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?",(amt,m.chat.id,borrower))
    c.execute("INSERT INTO loans(chat_id,lender_id,borrower_id,amount,loan_time) VALUES(?,?,?,?,?)",(m.chat.id,lender,borrower,amt,int(time.time())))
    db.commit()

    await m.reply(f"💸 وام انجام شد!\n\nمقدار: {amt} سانت\n📊 این کاربر امروز {borrowed_today+amt}/50 سانت وام گرفته")

@dp.message(Command("repay"))
async def repay(m:Message):
    try: amt=int(m.text.split()[1])
    except: return await m.reply("Usage: /repay 5")
    user(m.chat.id,m.from_user.id,m.from_user.full_name)
    s,d=c.execute("SELECT size,debt FROM users WHERE chat_id=? AND user_id=?",(m.chat.id,m.from_user.id)).fetchone()
    amt=min(amt,s,d)
    c.execute("UPDATE users SET size=?,debt=? WHERE chat_id=? AND user_id=?",(s-amt,d-amt,m.chat.id,m.from_user.id)); db.commit()
    await m.reply(f"✅ Repaid {amt} cm")

@dp.message(Command("top"))
async def top(m:Message):
    rows=c.execute("SELECT name,size FROM users WHERE chat_id=? ORDER BY size DESC LIMIT 10",(m.chat.id,)).fetchall()
    txt="🏆 جدول بزرگان\n\n"
    for i,(n,s) in enumerate(rows,1): txt+=f"{i}. {n} — {s} سانت\n"
    await m.reply(txt)

PVP_MIN_GAMES = 3          # قبل از این تعداد دوئل، اصلاً تصحیح انجام نمی‌شه (شانس خام 50-50 می‌مونه)
PVP_BALANCE_STRENGTH = 0.6 # هرچقدر بیشتر، میل به 50٪ قوی‌تره (0 = بی‌اثر، 1 = خیلی قوی)
PVP_PROB_MIN = 0.25        # کف احتمال برد (هیچ‌وقت شانس کسی از این کمتر نمی‌شه)
PVP_PROB_MAX = 0.75        # سقف احتمال برد (هیچ‌وقت شانس کسی از این بیشتر نمی‌شه)

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

# ===== سیستم رنک =====
RANK_DAILY_QUOTA = 6          # حداقل دوئل لازم در روز تا رنک نریزه
RANK_WIN_RP = 20              # امتیاز رنک برای برد
RANK_LOSS_RP = 10             # امتیاز رنک کم‌شده برای باخت
RANK_DECAY_PER_MISSED_DAY = 15  # ریزش رنک به‌ازای هر روزی که حدنصاب رعایت نشده
RANK_TIERS = [
    (0,    "🥒 نوپا"),
    (100,  "🌭 آماتور"),
    (250,  "🍆 حرفه‌ای"),
    (500,  "🚀 استاد"),
    (900,  "👑 افسانه‌ای"),
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
    """اگه از آخرین باری که دوئل زده روز(ها) گذشته باشه و اون روزها حدنصاب رعایت نشده، رنک می‌ریزه."""
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
    quota_txt = "✅ حدنصاب امروز رعایت شده!" if left == 0 else f"⚠️ {left} دوئل دیگه مونده تا رنکت فردا نریزه!"
    await m.reply(
        f"🏅 رنک شما\n\n"
        f"{tier}\n"
        f"📊 امتیاز: {rp} RP\n"
        f"⚔️ دوئل امروز: {duels_today}/{RANK_DAILY_QUOTA}\n\n"
        f"{quota_txt}"
    )

@dp.message(Command("ranktop"))
async def rank_top(m: Message):
    rows = c.execute(
        "SELECT user_id,rp FROM rank_stats WHERE chat_id=? ORDER BY rp DESC LIMIT 10", (m.chat.id,)
    ).fetchall()
    if not rows:
        return await m.reply("📭 هنوز کسی تو این گروه دوئل نزده!")
    txt = "🏆 برترین‌های رنک این گروه\n\n"
    for i, (uid, rp) in enumerate(rows, 1):
        name = get_name(m.chat.id, uid)
        txt += f"{i}. {name} — {rp} RP ({get_rank_tier(rp)})\n"
    await m.reply(txt)

@dp.message(Command("pvp"))
async def pvp(m:Message):
    try: bet=int(m.text.split()[1])
    except: return await m.reply("Usage: /pvp 30")
    if bet<=0: return await m.reply("❌ مقدار شرط باید عدد مثبت باشه!")
    user(m.chat.id,m.from_user.id,m.from_user.full_name)
    s=get_size(m.chat.id,m.from_user.id)
    if s<bet: return await m.reply("Not enough cm.")
    need = richest_min_duel(m.chat.id, m.from_user.id)
    if bet < need:
        return await m.reply(
            f"👑 تو پولدارترین فرد گروهی! حداقل شرط دوئل تو {RICHEST_MIN_DUEL_PCT*100:g}٪ سایزته = {need} سانت.\n"
            f"مثلاً: /pvp {need}"
        )
    cur = c.execute(
        "INSERT INTO battles(creator,bet) VALUES(?,?)",
        (m.from_user.id, bet)
    )
    db.commit()
    bid=cur.lastrowid
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚔️ قبول دوئل",callback_data=f"pvp:{bid}")]])
    await m.reply(f"⚔️ دوئل مرگبار!\n\n💰 شرط: {bet} سانت\n\nبرنده همه رو می‌بره!",reply_markup=kb)

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
    need_op = richest_min_duel(chat_id, opponent)
    if bet < need_op:
        return await q.answer(f"👑 تو پولدارترین فرد گروهی؛ حداقل شرط دوئلت {need_op} سانته ({RICHEST_MIN_DUEL_PCT*100:g}٪ سایزت).", show_alert=True)
    need_cr = richest_min_duel(chat_id, creator)
    if bet < need_cr:
        return await q.answer(f"👑 سازنده‌ی این دوئل الان پولدارترین فرد گروهه و حداقل شرطش {need_cr} سانته؛ این دوئل معتبر نیست.", show_alert=True)
    wr_creator, _ = get_pvp_winrate(chat_id, creator)
    wr_opponent, _ = get_pvp_winrate(chat_id, opponent)
    # هرکی نرخ بردش بالاتر از 50٪ باشه شانسش کم می‌شه، هرکی پایین‌تره شانسش زیاد می‌شه
    p_creator = 0.5 + PVP_BALANCE_STRENGTH * (wr_opponent - wr_creator)
    p_creator = max(PVP_PROB_MIN, min(PVP_PROB_MAX, p_creator))
    winner = creator if random.random() < p_creator else opponent
    loser = opponent if winner == creator else creator
    bump_pvp_stats(chat_id, winner, loser)
    log_play(chat_id, winner, "duel")
    log_play(chat_id, loser, "duel")
    record_rank_duel(chat_id, winner, loser)
    c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?",(bet,chat_id,winner))
    c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?",(bet,chat_id,loser))
    c.execute("UPDATE battles SET active=0 WHERE id=?",(bid,))
    db.commit()
    token_line = ""
    if random.random() < DUEL_TOKEN_CHANCE:
        add_tokens(chat_id, winner, 1)
        token_line = "\n🎟 جایزه‌ی ویژه: یه توکن بازی هم به برنده رسید!"
    winner_name=get_name(chat_id,winner)
    await q.message.edit_text(f"🏆 پایان دوئل!\n\n👑 برنده: {winner_name}\n💰 جایزه: {bet} سانت{token_line}\n🏅 +{RANK_WIN_RP} RP برنده | -{RANK_LOSS_RP} RP بازنده\n\n😂 بازنده باید بیشتر تمرین کنه!")


# ===== Mafia Team PvP System =====
c.execute("CREATE TABLE IF NOT EXISTS mafia_battles(id INTEGER PRIMARY KEY AUTOINCREMENT,creator INTEGER,opponent INTEGER,bet INTEGER,active INTEGER DEFAULT 1,chat_id INTEGER)")
c.execute("CREATE TABLE IF NOT EXISTS mafia_members(battle_id INTEGER,user_id INTEGER,name TEXT,team INTEGER)")
db.commit()

def mafia_counts(bid):
    t1=c.execute("SELECT COUNT(*) FROM mafia_members WHERE battle_id=? AND team=1",(bid,)).fetchone()[0]
    t2=c.execute("SELECT COUNT(*) FROM mafia_members WHERE battle_id=? AND team=2",(bid,)).fetchone()[0]
    return t1,t2

def mafia_board(bid,creator_name,opp_name,bet,status="🔫 جنگ مافیا شروع شد!"):
    t1,t2=mafia_counts(bid)
    return (
        f"{status}\n\n"
        f"🔴 تیم {creator_name}  در مقابل  🔵 تیم {opp_name}\n"
        f"💰 ورودی هر نفر: {bet} سانت\n\n"
        f"هر کی میخواد وارد بشه دکمه تیمش رو بزنه (مخفیانه ثبت میشه، تیم‌بندی معلوم نیست)!\n"
        f"👥 تعداد شرکت‌کننده‌ها: {t1+t2}\n\n"
        f"وقتی آماده بودید، سازنده یا حریف دکمه «شروع نبرد» رو بزنه."
    )

@dp.message(Command("mafia"))
async def mafia_start(m:Message):
    if not m.reply_to_message:
        return await m.reply("⚠️ روی پیام حریف ریپلای کن و بنویس /mafia [مبلغ]\nمثال: /mafia 5")
    try:
        bet=int(m.text.split()[1])
    except:
        return await m.reply("⚠️ استفاده: /mafia [مبلغ]\nمثال: /mafia 5")
    if bet<=0:
        return await m.reply("❌ مبلغ باید مثبت باشه!")
    creator=m.from_user.id
    opponent=m.reply_to_message.from_user.id
    if creator==opponent:
        return await m.reply("❌ نمیتونی با خودت مافیا بازی کنی!")
    if m.reply_to_message.from_user.is_bot:
        return await m.reply("❌ نمیتونی با بات مافیا بازی کنی!")
    user(m.chat.id,creator,m.from_user.full_name)
    user(m.chat.id,opponent,m.reply_to_message.from_user.full_name)
    s=get_size(m.chat.id,creator)
    if s<bet:
        return await m.reply("❌ سانت کافی نداری!")
    c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?",(bet,m.chat.id,creator))
    cur=c.execute("INSERT INTO mafia_battles(creator,opponent,bet,chat_id) VALUES(?,?,?,?)",(creator,opponent,bet,m.chat.id))
    db.commit()
    bid=cur.lastrowid
    c.execute("INSERT INTO mafia_members(battle_id,user_id,name,team) VALUES(?,?,?,1)",(bid,creator,m.from_user.full_name))
    db.commit()
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔴 تیم {m.from_user.full_name}",callback_data=f"mjoin:{bid}:1"),
         InlineKeyboardButton(text=f"🔵 تیم {m.reply_to_message.from_user.full_name}",callback_data=f"mjoin:{bid}:2")],
        [InlineKeyboardButton(text="🏁 شروع نبرد و شمارش",callback_data=f"mstart:{bid}")]
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
            return await q.answer("⚠️ این نبرد تموم شده!",show_alert=True)
        creator,opponent,bet,_,chat_id=row
        uid=q.from_user.id
        already=c.execute("SELECT team FROM mafia_members WHERE battle_id=? AND user_id=?",(bid,uid)).fetchone()
        if already:
            return await q.answer("⚠️ قبلاً مخفیانه وارد یه تیم شدی!",show_alert=True)
        user(chat_id,uid,q.from_user.full_name)
        s=get_size(chat_id,uid)
        if s<bet:
            return await q.answer("❌ سانت کافی نداری!",show_alert=True)
        c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?",(bet,chat_id,uid))
        c.execute("INSERT INTO mafia_members(battle_id,user_id,name,team) VALUES(?,?,?,?)",(bid,uid,q.from_user.full_name,team))
        db.commit()
        creator_name=get_name(chat_id,creator)
        opp_name=get_name(chat_id,opponent)
        await q.answer("✅ مخفیانه وارد تیم شدی!")
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
            await q.answer("⚠️ یه خطا پیش اومد، دوباره امتحان کن.", show_alert=True)
        except Exception:
            pass

@dp.callback_query(F.data.startswith("mstart:"))
async def mafia_resolve(q:CallbackQuery):
    try:
        bid=int(q.data.split(":")[1])
        row=c.execute("SELECT creator,opponent,bet,active,chat_id FROM mafia_battles WHERE id=?",(bid,)).fetchone()
        if not row or row[3]==0:
            return await q.answer("⚠️ این نبرد تموم شده!",show_alert=True)
        creator,opponent,bet,_,chat_id=row
        if q.from_user.id not in (creator,opponent):
            return await q.answer("⚠️ فقط سازنده یا حریف میتونه نبرد رو شروع کنه!",show_alert=True)
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
        # یارهای خریداری‌شده از کمپانی کیر شناسه‌ی منفی دارن: توی شمارش تیم حساب میشن ولی سهمی از جایزه نمی‌برن
        human_count=sum(1 for u,_,_t in members if u>0)
        winners_human=[(u,n) for u,n in winners if u>0]
        total_pot=bet*human_count
        share=total_pot//len(winners_human) if winners_human else 0
        for uid,_ in winners_human:
            c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?",(share,chat_id,uid))
        c.execute("UPDATE mafia_battles SET active=0 WHERE id=?",(bid,))
        db.commit()
        win_names="، ".join(n for _,n in winners) or "-"
        lose_names="، ".join(n for _,n in losers) or "-"
        color="🔴" if wteam==1 else "🔵"
        await q.message.edit_text(
            f"🔫 پایان جنگ مافیا!\n\n"
            f"{color} تیم برنده ({len(winners)} نفر): {win_names}\n"
            f"💀 تیم بازنده ({len(losers)} نفر): {lose_names}\n\n"
            f"💰 کل جایزه: {total_pot} سانت\n"
            f"🎁 سهم هر برنده: {share} سانت\n\n"
            f"{'😂 مساوی بودن، شانس تصمیم گرفت!' if tie else '👑 تیم بزرگتر برد!'}",
            reply_markup=None
        )
        await q.answer("🏁 نبرد تموم شد!")
    except Exception:
        logger.exception("mafia_resolve crashed for data=%s", q.data)
        try:
            await q.answer("⚠️ یه خطا پیش اومد، دوباره امتحان کن یا با /mafia یه نبرد جدید بساز.", show_alert=True)
        except Exception:
            pass


# ===== Mafia2 Team PvP (reveals only who won, not the team lineup) =====
c.execute("CREATE TABLE IF NOT EXISTS mafia2_battles(id INTEGER PRIMARY KEY AUTOINCREMENT,creator INTEGER,opponent INTEGER,bet INTEGER,active INTEGER DEFAULT 1,chat_id INTEGER)")
c.execute("CREATE TABLE IF NOT EXISTS mafia2_members(battle_id INTEGER,user_id INTEGER,name TEXT,team INTEGER)")
db.commit()

# ستون is_ally برای مشخص کردن یارهایی که از کمپانی کیر خریداری شدن (نه بازیکن واقعی)
# یارها همیشه user_id منفی دارن، پس منطق برد/باخت با همون علامتِ منفی هم قابل تشخیصه؛
# این ستون فقط برای خوانایی/آمار اضافه‌ست.
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

def mafia2_board(bid,creator_name,opp_name,bet,status="🔫 جنگ مافیا شروع شد!"):
    t1,t2=mafia2_counts(bid)
    return (
        f"{status}\n\n"
        f"🔴 تیم {creator_name}  در مقابل  🔵 تیم {opp_name}\n"
        f"💰 ورودی هر نفر: {bet} سانت\n\n"
        f"هر کی میخواد وارد بشه دکمه تیمش رو بزنه (مخفیانه ثبت میشه، تیم‌بندی معلوم نیست)!\n"
        f"👥 تعداد شرکت‌کننده‌ها: {t1+t2}\n\n"
        f"وقتی آماده بودید، سازنده یا حریف دکمه «شروع نبرد» رو بزنه.\n"
        f"ℹ️ در پایان فقط برنده مشخص میشه، نه اینکه کی کجا بود."
    )

@dp.message(Command("mafia2"))
async def mafia2_start(m:Message):
    if not m.reply_to_message:
        return await m.reply("⚠️ روی پیام حریف ریپلای کن و بنویس /mafia2 [مبلغ]\nمثال: /mafia2 5")
    try:
        bet=int(m.text.split()[1])
    except:
        return await m.reply("⚠️ استفاده: /mafia2 [مبلغ]\nمثال: /mafia2 5")
    if bet<=0:
        return await m.reply("❌ مبلغ باید مثبت باشه!")
    creator=m.from_user.id
    opponent=m.reply_to_message.from_user.id
    if creator==opponent:
        return await m.reply("❌ نمیتونی با خودت مافیا بازی کنی!")
    if m.reply_to_message.from_user.is_bot:
        return await m.reply("❌ نمیتونی با بات مافیا بازی کنی!")
    user(m.chat.id,creator,m.from_user.full_name)
    user(m.chat.id,opponent,m.reply_to_message.from_user.full_name)
    s=get_size(m.chat.id,creator)
    if s<bet:
        return await m.reply("❌ سانت کافی نداری!")
    c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?",(bet,m.chat.id,creator))
    cur=c.execute("INSERT INTO mafia2_battles(creator,opponent,bet,chat_id) VALUES(?,?,?,?)",(creator,opponent,bet,m.chat.id))
    db.commit()
    bid=cur.lastrowid
    c.execute("INSERT INTO mafia2_members(battle_id,user_id,name,team) VALUES(?,?,?,1)",(bid,creator,m.from_user.full_name))
    db.commit()
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔴 تیم {m.from_user.full_name}",callback_data=f"m2join:{bid}:1"),
         InlineKeyboardButton(text=f"🔵 تیم {m.reply_to_message.from_user.full_name}",callback_data=f"m2join:{bid}:2")],
        [InlineKeyboardButton(text="🏁 شروع نبرد و شمارش",callback_data=f"m2start:{bid}")]
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
            return await q.answer("⚠️ این نبرد تموم شده!",show_alert=True)
        creator,opponent,bet,_,chat_id=row
        uid=q.from_user.id
        already=c.execute("SELECT team FROM mafia2_members WHERE battle_id=? AND user_id=?",(bid,uid)).fetchone()
        if already:
            return await q.answer("⚠️ قبلاً مخفیانه وارد یه تیم شدی!",show_alert=True)
        user(chat_id,uid,q.from_user.full_name)
        s=get_size(chat_id,uid)
        if s<bet:
            return await q.answer("❌ سانت کافی نداری!",show_alert=True)
        c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?",(bet,chat_id,uid))
        c.execute("INSERT INTO mafia2_members(battle_id,user_id,name,team) VALUES(?,?,?,?)",(bid,uid,q.from_user.full_name,team))
        db.commit()
        creator_name=get_name(chat_id,creator)
        opp_name=get_name(chat_id,opponent)
        await q.answer("✅ مخفیانه وارد تیم شدی!")
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
            await q.answer("⚠️ یه خطا پیش اومد، دوباره امتحان کن.", show_alert=True)
        except Exception:
            pass

@dp.callback_query(F.data.startswith("m2start:"))
async def mafia2_resolve(q:CallbackQuery):
    try:
        bid=int(q.data.split(":")[1])
        row=c.execute("SELECT creator,opponent,bet,active,chat_id FROM mafia2_battles WHERE id=?",(bid,)).fetchone()
        if not row or row[3]==0:
            return await q.answer("⚠️ این نبرد تموم شده!",show_alert=True)
        creator,opponent,bet,_,chat_id=row
        if q.from_user.id not in (creator,opponent):
            return await q.answer("⚠️ فقط سازنده یا حریف میتونه نبرد رو شروع کنه!",show_alert=True)
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
        # یارهای خریداری‌شده از کمپانی کیر شناسه‌ی منفی دارن: توی شمارش تیم حساب میشن ولی سهمی از جایزه نمی‌برن
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
        win_label=f"🔴 تیم {creator_name}" if wteam==1 else f"🔵 تیم {opp_name}"
        await q.message.edit_text(
            f"🔫 پایان جنگ مافیا!\n\n"
            f"👥 مجموع شرکت‌کننده‌ها: {len(members)} نفر\n\n"
            f"👑 برنده: {win_label} ({len(winners)} نفر)\n"
            f"💰 کل جایزه: {total_pot} سانت\n"
            f"🎁 سهم هر برنده: {share} سانت\n\n"
            f"{'😂 مساوی بودن، شانس تصمیم گرفت!' if tie else '👑 تیم بزرگتر برد!'}\n\n"
            f"🤫 اینکه کی تو کدوم تیم بود مخفی می‌مونه!",
            reply_markup=None
        )
        await q.answer("🏁 نبرد تموم شد!")
    except Exception:
        logger.exception("mafia2_resolve crashed for data=%s", q.data)
        try:
            await q.answer("⚠️ یه خطا پیش اومد، دوباره امتحان کن یا با /mafia2 یه نبرد جدید بساز.", show_alert=True)
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
    "S": "🥇 Tier S",
    "A": "🥈 Tier A",
    "B": "🥉 Tier B",
    "PH": "💎 Tier PH",
}
TIER_PRICES = {"S": (543, 438), "A": (350, 262), "B": (175, 88), "PH": (630, 525)}

# ===== تیر مزایده (AU) 🔨 =====
# - سلبریتی‌های این تیر فقط از مزایده به‌دست میان (تو /market و /spin و /buy نیستن)
# - هر کی تو مزایده برنده شه، سلبریتی با عکسش میره تو /collection با تیر «🔨 مزایده»
#   (اگه اسم مزایده تو کاتالوگ نباشه، خودکار با عکس مزایده تو همین تیر ثبت می‌شه)
# - ارزش اون سلبریتی تو کالکشن = مبلغی که برنده‌ش شدی؛ ولی /sell برای این تیر بسته‌ست
# - کاتالوگ تو دیتابیسه، پس با ریستارت ربات از بین نمی‌ره (ادمین با /addau اضافه می‌کنه)
TIER_CELEBS["AU"] = []
TIER_LABELS["AU"] = "🔨 Tier مزایده"
TIER_SHORT = {"S": "🥇 S", "A": "🥈 A", "B": "🥉 B", "PH": "💎 PH", "AU": "🔨 مزایده"}

c.execute("""CREATE TABLE IF NOT EXISTS auction_celebs(
    name TEXT PRIMARY KEY,
    photo TEXT,
    added_by INTEGER DEFAULT 0,
    created_at INTEGER DEFAULT 0
)""")
db.commit()

def register_au_celeb(name, photo, added_by=0, persist=True):
    CELEBS[name] = ("AU", 0, 0, photo)
    TIER_CELEBS["AU"] = [(n, v[1], v[3]) for n, v in CELEBS.items() if v[0] == "AU"]
    if persist:
        c.execute(
            "INSERT OR REPLACE INTO auction_celebs(name,photo,added_by,created_at) VALUES(?,?,?,?)",
            (name, photo, added_by, int(time.time()))
        )
        db.commit()

def celeb_paid_value(chat_id, uid, name):
    row = c.execute(
        "SELECT paid_price FROM collections WHERE chat_id=? AND user_id=? AND celeb=?",
        (chat_id, uid, name)
    ).fetchone()
    return row[0] if row else 0

for _n, _p in c.execute("SELECT name, photo FROM auction_celebs").fetchall():
    if _n not in CELEBS or CELEBS[_n][0] == "AU":
        register_au_celeb(_n, _p, persist=False)

def build_market_caption(tier, page):
    celebs = TIER_CELEBS[tier]
    name, price, photo = celebs[page]
    buy_price, spin_price = TIER_PRICES[tier]
    label = TIER_LABELS[tier]
    txt = (
        f"🛒 بازار سلبریتی\n"
        f"{label} — صفحه {page+1}/{len(celebs)}\n\n"
        f"👑 {name}\n"
        f"💰 خرید: {price} سانت\n"
        f"🎰 اسپین: {spin_price} سانت\n\n"
        f"🛒 /buy {name}\n"
        f"🎰 /spin {tier.lower()}"
    )
    return txt, photo

def build_market_kb(tier, page, viewer_id):
    celebs = TIER_CELEBS[tier]
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"mkt:{viewer_id}:{tier}:{page-1}"))
    if page < len(celebs) - 1:
        buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"mkt:{viewer_id}:{tier}:{page+1}"))
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
# این جدول عمداً سراسریه (نه بر اساس چت) چون فقط عکس‌های سلبریتی‌ها رو کش می‌کنه،
# نه دیتای اقتصادی کاربر؛ عکس‌ها تو همه‌ی گروه‌ها یکسانن.
c.execute("CREATE TABLE IF NOT EXISTS photo_cache(url TEXT PRIMARY KEY, file_id TEXT)")
db.commit()

async def resolve_photo(url: str):
    """Accepts either a Telegram file_id (used directly, zero download) or an http(s) URL
    (downloaded once, then cached as a file_id from then on)."""
    if not url:
        return None
    if not url.startswith("http://") and not url.startswith("https://"):
        # Already a Telegram file_id — use it straight away, nothing to download.
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
        return await m.reply("⚠️ یه عکس بفرست (یا روی یه عکس ریپلای بزن) و /getfileid رو بنویس.")
    await m.reply(f"🆔 file_id:\n`{target.file_id}`", parse_mode="Markdown")

@dp.message(Command("market"))
async def market(m:Message):
    for tier in ["S", "A", "B", "PH"]:
        if not TIER_CELEBS[tier]:
            continue
        txt, photo_url = build_market_caption(tier, 0)
        kb = build_market_kb(tier, 0, m.from_user.id)
        photo = await resolve_photo(photo_url) if photo_url else None
        try:
            if photo:
                sent = await m.bot.send_photo(m.chat.id, photo, caption=txt, reply_markup=kb)
                if isinstance(photo, BufferedInputFile):
                    cache_photo(photo_url, sent)
            else:
                await m.bot.send_message(m.chat.id, txt, reply_markup=kb)
        except Exception as e:
            # اگه فرستادن عکس خراب شد (مثلاً file_id نامعتبره) کل دستور /market نباید بترکه؛
            # به‌جاش پیام متنی می‌فرستیم تا بقیه‌ی تیرها هم نمایش داده بشن.
            print(f"[market] خطا در ارسال عکس تیر {tier}: {e}")
            await m.bot.send_message(m.chat.id, txt, reply_markup=kb)

@dp.callback_query(F.data.startswith("mkt:"))
async def market_page_nav(q: CallbackQuery):
    parts = q.data.split(":")
    if len(parts) != 4:
        return await q.answer(NAV_LEGACY_MSG, show_alert=True)
    _, viewer_id, tier, page = parts
    viewer_id, page = int(viewer_id), int(page)
    if not await nav_guard(q, viewer_id):
        return
    txt, photo_url = build_market_caption(tier, page)
    kb = build_market_kb(tier, page, viewer_id)
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
        await q.answer(f"خطا: {e}", show_alert=True)
        return
    await q.answer()

@dp.message(Command("collection"))
async def collection(m:Message):
    if m.reply_to_message:
        target = m.reply_to_message.from_user
        user(m.chat.id, target.id, target.full_name)
        rows = c.execute("SELECT celeb FROM collections WHERE chat_id=? AND user_id=?", (m.chat.id, target.id)).fetchall()
        if not rows:
            return await m.reply(f"📚 {target.full_name} هنوز چیزی نداره.")
        celebs = [r[0] for r in rows]
        await send_collection_page(m.chat.id, target.id, celebs, 0, m.bot, viewer_id=m.from_user.id)
    else:
        user(m.chat.id, m.from_user.id, m.from_user.full_name)
        rows = c.execute("SELECT celeb FROM collections WHERE chat_id=? AND user_id=?", (m.chat.id, m.from_user.id)).fetchall()
        if not rows:
            return await m.reply("📚 هنوز چیزی نداری.")
        celebs = [r[0] for r in rows]
        await send_collection_page(m.chat.id, m.from_user.id, celebs, 0, m.bot, viewer_id=m.from_user.id)

async def send_collection_page(chat_id, owner_id, celebs, page, bot, viewer_id=None):
    name = celebs[page]
    tier, price, spin, photo_url = CELEBS[name]
    tier_label = TIER_SHORT.get(tier, tier)
    if tier == "AU":
        price = celeb_paid_value(chat_id, owner_id, name)
    sell_line = "" if tier == "AU" else f"🛒 /sell {name}\n"
    txt = (
        f"📚 کالکشن — {page+1}/{len(celebs)}\n\n"
        f"👑 {name}\n"
        f"🏅 تیر: {tier_label}\n"
        f"💰 ارزش: {price} سانت\n\n"
        f"{sell_line}"
        f"🏪 /list {name} [قیمت]"
    )
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"col:{viewer_id}:{owner_id}:{page-1}"))
    if page < len(celebs) - 1:
        buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"col:{viewer_id}:{owner_id}:{page+1}"))
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
        print(f"[collection] خطا در ارسال عکس {name}: {e}")
        await bot.send_message(chat_id, txt, reply_markup=kb)

@dp.callback_query(F.data.startswith("col:"))
async def collection_nav(q: CallbackQuery):
    parts = q.data.split(":")
    if len(parts) != 4:
        return await q.answer(NAV_LEGACY_MSG, show_alert=True)
    _, viewer_id, owner_id, page = parts
    viewer_id, owner_id, page = int(viewer_id), int(owner_id), int(page)
    if not await nav_guard(q, viewer_id):
        return
    chat_id = q.message.chat.id
    rows = c.execute("SELECT celeb FROM collections WHERE chat_id=? AND user_id=?", (chat_id, owner_id)).fetchall()
    celebs = [r[0] for r in rows]
    if page >= len(celebs):
        page = len(celebs) - 1
    name = celebs[page]
    tier, price, spin, photo_url = CELEBS[name]
    tier_label = TIER_SHORT.get(tier, tier)
    if tier == "AU":
        price = celeb_paid_value(chat_id, owner_id, name)
    sell_line = "" if tier == "AU" else f"🛒 /sell {name}\n"
    txt = (
        f"📚 کالکشن — {page+1}/{len(celebs)}\n\n"
        f"👑 {name}\n"
        f"🏅 تیر: {tier_label}\n"
        f"💰 ارزش: {price} سانت\n\n"
        f"{sell_line}"
        f"🏪 /list {name} [قیمت]"
    )
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"col:{viewer_id}:{owner_id}:{page-1}"))
    if page < len(celebs) - 1:
        buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"col:{viewer_id}:{owner_id}:{page+1}"))
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
        await q.answer(f"خطا: {e}", show_alert=True)
        return
    await q.answer()


@dp.message(Command("buy"))
async def buy(m:Message):
    name=strip_command(m.text)

    if name not in CELEBS:
        return await m.reply("❌ سلبریتی پیدا نشد.")

    tier,price,spin,photo=CELEBS[name]
    if tier == "AU":
        return await m.reply("🔨 این سلبریتی مال تیر مزایده‌ست و فقط با برنده شدن تو مزایده به‌دست میاد!")

    user(m.chat.id,m.from_user.id,m.from_user.full_name)

    size=get_size(m.chat.id,m.from_user.id)

    if size<price:
        return await m.reply("💸 سانت کافی نداری!")

    tier_key = CELEBS[name][0]

    # check if user already owns it
    user_owned = c.execute("SELECT 1 FROM collections WHERE chat_id=? AND user_id=? AND celeb=?", (m.chat.id, m.from_user.id, name)).fetchone()
    if user_owned:
        return await m.reply("📚 این سلبریتی رو داری!")

    # tier S and A are exclusive — check if anyone owns it (locked or not)
    # tier B is only exclusive if locked
    if tier_key in ("S", "A"):
        owned = c.execute("SELECT user_id FROM collections WHERE chat_id=? AND celeb=?", (m.chat.id, name)).fetchone()
        if owned:
            owner_name = get_name(m.chat.id, owned[0])
            return await m.reply(f"❌ این سلبریتی قبلاً توسط {owner_name} خریداری شده!")
    else:
        # tier B — only block if locked
        locked = c.execute("SELECT user_id FROM collections WHERE chat_id=? AND celeb=? AND locked=1", (m.chat.id, name)).fetchone()
        if locked:
            owner_name = get_name(m.chat.id, locked[0])
            return await m.reply(f"🔒 این سلبریتی توسط {owner_name} قفل شده!")

    c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?",(price,m.chat.id,m.from_user.id))
    c.execute("INSERT INTO collections(chat_id,user_id,celeb,paid_price) VALUES(?,?,?,?)",(m.chat.id,m.from_user.id,name,price))
    db.commit()

    photo_url = photo
    photo = await resolve_photo(photo_url) if photo_url else None
    try:
        if photo:
            sent = await m.bot.send_photo(m.chat.id, photo, caption=f"🎉 خرید موفق!\n\n👑 {name}")
            if isinstance(photo, BufferedInputFile):
                cache_photo(photo_url, sent)
        else:
            await m.reply(f"🎉 خرید موفق!\n\n👑 {name}")
    except Exception as e:
        # خرید توی دیتابیس قبلاً ثبت شده، پس حتی اگه عکس نره حداقل تاییدیه‌ی متنی بره
        print(f"[buy] خطا در ارسال عکس {name}: {e}")
        await m.reply(f"🎉 خرید موفق!\n\n👑 {name}")

@dp.message(Command("spin"))
async def spin(m:Message):
    try:
        tier=m.text.split()[1].upper()
    except:
        return await m.reply("استفاده: /spin s | a | b")

    prices={"S":438,"A":262,"B":88,"PH":525}

    if tier not in prices:
        return await m.reply("Tier باید s یا a یا b باشد.")

    cost=prices[tier]

    user(m.chat.id,m.from_user.id,m.from_user.full_name)

    size=get_size(m.chat.id,m.from_user.id)

    if size<cost:
        return await m.reply("💸 سانت کافی نداری!")

    pool=[n for n,v in CELEBS.items() if v[0]==tier]
    celeb=random.choice(pool)

    c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?",(cost,m.chat.id,m.from_user.id))

    spin_tier = CELEBS[celeb][0]
    user_owned = c.execute("SELECT 1 FROM collections WHERE chat_id=? AND user_id=? AND celeb=?", (m.chat.id, m.from_user.id, celeb)).fetchone()
    if user_owned:
        c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?",(cost,m.chat.id,m.from_user.id))
        db.commit()
        return await m.reply(f"🔄 این سلبریتی رو قبلاً داری!\n\n👑 {celeb}\n💰 {cost} سانت برگشت داده شد.")

    if spin_tier in ("S", "A"):
        owned = c.execute("SELECT user_id FROM collections WHERE chat_id=? AND celeb=?", (m.chat.id, celeb)).fetchone()
        if owned:
            c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?",(cost,m.chat.id,m.from_user.id))
            db.commit()
            owner_name=get_name(m.chat.id,owned[0])
            return await m.reply(f"🔄 این سلبریتی قبلاً توسط {owner_name} خریداری شده!\n\n👑 {celeb}\n💰 {cost} سانت برگشت داده شد.")
    else:
        locked = c.execute("SELECT user_id FROM collections WHERE chat_id=? AND celeb=? AND locked=1", (m.chat.id, celeb)).fetchone()
        if locked:
            c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?",(cost,m.chat.id,m.from_user.id))
            db.commit()
            owner_name=get_name(m.chat.id,locked[0])
            return await m.reply(f"🔒 این سلبریتی توسط {owner_name} قفل شده!\n\n👑 {celeb}\n💰 {cost} سانت برگشت داده شد.")

    # ===== ارزش فروش (paid_price) برای سلبریتی گرفته‌شده از اسپین =====
    # تیر B → نصف هزینه‌ی اسپین، بقیه‌ی تیرها (S/A/PH) → ۷۵٪ هزینه‌ی اسپین.
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
            sent = await m.bot.send_photo(m.chat.id, photo, caption=f"🎰 اسپین موفق!\n\n👑 {celeb}")
            if isinstance(photo, BufferedInputFile):
                cache_photo(photo_url, sent)
        else:
            await m.reply(f"🎰 اسپین موفق!\n\n👑 {celeb}")
    except Exception as e:
        print(f"[spin] خطا در ارسال عکس {celeb}: {e}")
        await m.reply(f"🎰 اسپین موفق!\n\n👑 {celeb}")

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

    txt="🏆 بهترین کلکسیونرها\n\n"

    for i,(name,total) in enumerate(rows,1):
        txt+=f"{i}. {name} — {total} سلبریتی\n"

    await m.reply(txt)


@dp.message(Command("list"))
async def list_celeb(m:Message):
    parts = m.text.split(None, 1)
    if len(parts) < 2:
        return await m.reply("Usage: /list [نام] [قیمت]\nمثال: /list Kylie Jenner 500")
    try:
        rest = parts[1].rsplit(None, 1)
        name = rest[0].strip()
        price = int(rest[1])
    except:
        return await m.reply("Usage: /list [نام] [قیمت]\nمثال: /list Kylie Jenner 500")
    if name not in CELEBS:
        return await m.reply("❌ سلبریتی پیدا نشد.")
    user(m.chat.id, m.from_user.id, m.from_user.full_name)
    owned = c.execute("SELECT 1 FROM collections WHERE chat_id=? AND user_id=? AND celeb=?", (m.chat.id, m.from_user.id, name)).fetchone()
    if not owned:
        return await m.reply("❌ این سلبریتی رو نداری!")
    # cancel any previous listing for this celeb
    c.execute("UPDATE listings SET active=0 WHERE chat_id=? AND seller_id=? AND celeb=?", (m.chat.id, m.from_user.id, name))
    cur = c.execute("INSERT INTO listings(chat_id, seller_id, celeb, price) VALUES(?,?,?,?)", (m.chat.id, m.from_user.id, name, price))
    db.commit()
    lid = cur.lastrowid
    tier, orig_price, spin, photo_url = CELEBS[name]
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"🛒 خرید به قیمت {price} سانت", callback_data=f"buyoff:{lid}")
    ]])
    caption = (
        f"🏪 فروش سلبریتی!\n\n"
        f"👑 {name}\n"
        f"💰 قیمت: {price} سانت\n"
        f"👤 فروشنده: {m.from_user.full_name}"
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
        print(f"[list] خطا در ارسال عکس {name}: {e}")
        await m.reply(caption, reply_markup=kb)

@dp.callback_query(F.data.startswith("buyoff:"))
async def buyoff(q: CallbackQuery):
    lid = int(q.data.split(":")[1])
    row = c.execute("SELECT chat_id, seller_id, celeb, price, active FROM listings WHERE id=?", (lid,)).fetchone()
    if not row or row[4] == 0:
        return await q.answer("❌ این آگهی دیگه فعال نیست!", show_alert=True)
    chat_id, seller_id, name, price, _ = row
    buyer_id = q.from_user.id
    if buyer_id == seller_id:
        return await q.answer("❌ نمیتونی از خودت بخری!", show_alert=True)
    user(chat_id, buyer_id, q.from_user.full_name)
    buyer_size = get_size(chat_id, buyer_id)
    if buyer_size < price:
        return await q.answer("❌ سانت کافی نداری!", show_alert=True)
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
            f"✅ معامله انجام شد!\n\n"
            f"👑 {name}\n"
            f"💰 قیمت: {price} سانت\n"
            f"🛒 خریدار: {q.from_user.full_name}\n"
            f"💸 فروشنده: {seller_name}"
        )
    )
    await q.answer("✅ خرید موفق!")

@dp.message(Command("sell"))
async def sell(m:Message):
    name=strip_command(m.text)
    if name not in CELEBS:
        return await m.reply("❌ سلبریتی پیدا نشد.")
    if CELEBS[name][0] == "AU":
        return await m.reply("🔨 سلبریتی‌های تیر مزایده قابل فروش نیستن! این سلبریتی برای همیشه تو کالکشنته.")
    user(m.chat.id,m.from_user.id,m.from_user.full_name)
    owned=c.execute(
        "SELECT paid_price FROM collections WHERE chat_id=? AND user_id=? AND celeb=?",
        (m.chat.id,m.from_user.id,name)
    ).fetchone()
    if not owned:
        return await m.reply("❌ این سلبریتی رو نداری!")
    paid=owned[0]
    c.execute("DELETE FROM collections WHERE chat_id=? AND user_id=? AND celeb=?",(m.chat.id,m.from_user.id,name))
    c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?",(paid,m.chat.id,m.from_user.id))
    db.commit()
    await m.reply(f"💸 فروش موفق!\n\n👑 {name}\n💰 {paid} سانت به حسابت اضافه شد!")

LOCK_COSTS = {"PH": 75, "S": 60, "A": 50, "B": 25}

@dp.message(Command("lock"))
async def lock_celeb(m:Message):
    name = strip_command(m.text)
    if name not in CELEBS:
        return await m.reply("❌ سلبریتی پیدا نشد.")
    tier_key = CELEBS[name][0]
    if tier_key not in LOCK_COSTS:
        return await m.reply("❌ این سلبریتی نیاز به قفل نداره!")
    lock_cost = LOCK_COSTS[tier_key]
    user(m.chat.id, m.from_user.id, m.from_user.full_name)
    owned = c.execute("SELECT locked FROM collections WHERE chat_id=? AND user_id=? AND celeb=?", (m.chat.id, m.from_user.id, name)).fetchone()
    if not owned:
        return await m.reply("❌ این سلبریتی رو نداری!")
    if owned[0] == 1:
        return await m.reply("🔒 این سلبریتی قبلاً قفله!")
    size = get_size(m.chat.id, m.from_user.id)
    if size < lock_cost:
        return await m.reply(f"❌ برای قفل کردن به {lock_cost} سانت نیاز داری!")
    c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?", (lock_cost, m.chat.id, m.from_user.id))
    c.execute("UPDATE collections SET locked=1 WHERE chat_id=? AND user_id=? AND celeb=?", (m.chat.id, m.from_user.id, name))
    db.commit()
    await m.reply(f"🔒 {name} قفل شد!\n\n💰 {lock_cost} سانت کسر شد.\nحالا کسی دیگه نمیتونه این سلبریتی رو بخره.")

@dp.message(Command("gloan"))
async def gloan(m:Message):
    try:
        amt = int(m.text.split()[1])
    except:
        return await m.reply("Usage: /gloan [مقدار]\nمثال: /gloan 50")
    if amt < 1 or amt > 50:
        return await m.reply("❌ حداکثر وام از بازی 50 سانته!")
    user(m.chat.id, m.from_user.id, m.from_user.full_name)
    existing = c.execute("SELECT amount, due_time FROM game_loans WHERE chat_id=? AND user_id=?", (m.chat.id, m.from_user.id)).fetchone()
    if existing:
        due = existing[1]
        rem = (due - int(time.time())) // 3600
        return await m.reply(f"❌ قبلاً {existing[0]} سانت وام داری!\n⏳ {rem} ساعت تا موعد پرداخت")
    due_time = int(time.time()) + 24*60*60
    c.execute("INSERT OR REPLACE INTO game_loans(chat_id, user_id, amount, due_time) VALUES(?,?,?,?)", (m.chat.id, m.from_user.id, amt, due_time))
    c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?", (amt, m.chat.id, m.from_user.id))
    db.commit()
    await m.reply(
        f"💰 وام از بازی\n\n"
        f"💵 مقدار: {amt} سانت\n"
        f"⏳ مهلت پرداخت: ۲۴ ساعت\n\n"
        f"برای پرداخت: /gpay {amt}"
    )

@dp.message(Command("gpay"))
async def gpay(m:Message):
    user(m.chat.id, m.from_user.id, m.from_user.full_name)
    loan = c.execute("SELECT amount, due_time FROM game_loans WHERE chat_id=? AND user_id=?", (m.chat.id, m.from_user.id)).fetchone()
    if not loan:
        return await m.reply("❌ وامی نداری!")
    amt, due_time = loan
    size = get_size(m.chat.id, m.from_user.id)
    if size < amt:
        return await m.reply(f"❌ سانت کافی نداری! باید {amt} سانت داشته باشی.")
    c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?", (amt, m.chat.id, m.from_user.id))
    c.execute("DELETE FROM game_loans WHERE chat_id=? AND user_id=?", (m.chat.id, m.from_user.id))
    db.commit()
    await m.reply(f"✅ وام {amt} سانت پرداخت شد!")

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
            msg = f"⚠️ وام {amt} سانت موعدش گذشت!\n\n"
            # sell celebs to cover debt
            if size < amt:
                celebs = c.execute("SELECT celeb, paid_price FROM collections WHERE chat_id=? AND user_id=? ORDER BY paid_price DESC", (chat_id, uid)).fetchall()
                for celeb, paid_price in celebs:
                    if paid >= amt:
                        break
                    c.execute("DELETE FROM collections WHERE chat_id=? AND user_id=? AND celeb=?", (chat_id, uid, celeb))
                    c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?", (paid_price, chat_id, uid))
                    paid += paid_price
                    msg += f"💸 {celeb} فروخته شد (+{paid_price} سانت)\n"
                db.commit()
                size = c.execute("SELECT size FROM users WHERE chat_id=? AND user_id=?", (chat_id, uid)).fetchone()[0]
            # deduct what we can
            deduct = min(amt, size)
            c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?", (deduct, chat_id, uid))
            remaining = amt - deduct
            if remaining > 0:
                c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?", (remaining, chat_id, uid))
                msg += f"📉 {remaining} سانت بدهی — حساب منفی شد!"
            else:
                msg += f"✅ {amt} سانت کسر شد."
            c.execute("DELETE FROM game_loans WHERE chat_id=? AND user_id=?", (chat_id, uid))
            db.commit()
            try:
                await bot.send_message(uid, msg)
            except:
                pass


# ===== مزایده (چندتا همزمان) =====
AUCTION_IDLE_SECONDS = 12 * 3600   # اگه ۱۲ ساعت پیشنهاد بالاتری نیومد، آخرین پیشنهاد برنده‌ست
AUCTION_START_BID = 10             # حداقل پیشنهاد اول (سانت)
AUCTION_MIN_INCREMENT = 5          # حداقل افزایش نسبت به پیشنهاد قبلی (سانت)

_AUCTION_COLS = "id,name,photo,top_bid,top_bidder,top_bidder_name,last_activity,msg_id"

def get_active_auctions(chat_id):
    return c.execute(
        f"SELECT {_AUCTION_COLS} FROM auctions WHERE chat_id=? AND status='active' ORDER BY id", (chat_id,)
    ).fetchall()

def resolve_auction(m, token=None):
    """مزایده‌ی موردنظر رو پیدا می‌کنه: با شماره، یا ریپلای روی عکسش، یا اگه فقط یکی فعاله همون.
    خروجی: (ردیف مزایده یا None، متن خطا یا None)"""
    rows = get_active_auctions(m.chat.id)
    if not rows:
        return None, "📭 الان هیچ مزایده‌ای در جریان نیست."
    if token is not None:
        for r in rows:
            if r[0] == token:
                return r, None
        return None, f"❌ مزایده‌ی فعالی با شماره‌ی #{token} پیدا نشد."
    if m.reply_to_message:
        rid = m.reply_to_message.message_id
        for r in rows:
            if r[7] == rid:
                return r, None
    if len(rows) == 1:
        return rows[0], None
    listing = "\n".join(f"• #{r[0]} — {r[1]}" for r in rows)
    return None, f"📊 چندتا مزایده همزمان فعاله، مشخص کن کدوم:\n{listing}\n\n(شماره‌ش رو بنویس یا روی عکس همون مزایده ریپلای کن)"

async def finalize_auction(bot, auction_id, cancel=False):
    row = c.execute("SELECT chat_id,name,top_bid,top_bidder,top_bidder_name,status,photo FROM auctions WHERE id=?", (auction_id,)).fetchone()
    if not row or row[5] != 'active':
        return False
    chat_id, name, top_bid, top_bidder, top_bidder_name, _, a_photo = row
    c.execute("UPDATE auctions SET status=? WHERE id=?", ('cancelled' if cancel else 'ended', auction_id))
    if cancel and top_bidder:
        c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?", (top_bid, chat_id, top_bidder))
    delivered = False
    dup_refund = False
    if not cancel and top_bidder:
        if name not in CELEBS:
            register_au_celeb(name, a_photo)  # تیر مزایده: خودکار با عکس مزایده ثبت می‌شه
        already = c.execute("SELECT 1 FROM collections WHERE chat_id=? AND user_id=? AND celeb=?", (chat_id, top_bidder, name)).fetchone()
        if already:
            c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?", (top_bid, chat_id, top_bidder))
            dup_refund = True
        else:
            c.execute("INSERT INTO collections(chat_id,user_id,celeb,paid_price) VALUES(?,?,?,?)", (chat_id, top_bidder, name, top_bid))
            delivered = True
    db.commit()
    if cancel:
        txt = f"🔨 مزایده‌ی #{auction_id} («{name}») لغو شد."
        if top_bidder:
            txt += f"\n💸 {top_bid} سانت به {top_bidder_name} برگشت."
    elif not top_bidder:
        txt = f"🔨 مزایده‌ی #{auction_id} («{name}») تموم شد ولی هیچ‌کس پیشنهادی نداد."
    else:
        txt = (
            f"🔨 مزایده‌ی #{auction_id} تموم شد!\n\n"
            f"🎁 {name}\n"
            f"👑 برنده: {top_bidder_name}\n"
            f"💰 مبلغ نهایی: {top_bid} سانت"
        )
        if delivered:
            tier_note = " (تیر 🔨 مزایده)" if CELEBS.get(name, ("",))[0] == "AU" else ""
            txt += f"\n\n✅ به کلکسیون برنده اضافه شد!{tier_note}"
        elif dup_refund:
            txt += f"\n\n↩️ این سلبریتی از قبل تو کلکسیون برنده بود، پس {top_bid} سانت بهش برگشت."
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

# ===== افزودن سلبریتی به تیر مزایده =====
@dp.message(Command("addau"))
async def add_au_celeb(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return await m.reply("❌ دسترسی ندارید!")
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
            "🔨 افزودن سلبریتی به تیر مزایده\n\n"
            "استفاده:\n/addau [file_id عکس] [اسم]\n\n"
            "یا روی یه عکس ریپلای کن و بنویس:\n/addau [اسم]\n\n"
            "بعدش با /auction [اسم] مزایده‌ش رو شروع کن؛ هرکی ببره تو کالکشنش میاد.\n"
            "(file_id رو با /getfileid بگیر. اگه اسم قبلاً تو این تیر بود، عکسش عوض می‌شه.)"
        )
    if len(name) > 60 or name.startswith("-") or "\n" in name:
        return await m.reply("❌ اسم نامعتبره (حداکثر ۶۰ حرف، با - شروع نشه).")
    if name in CELEBS and CELEBS[name][0] != "AU":
        return await m.reply(f"❌ «{name}» از قبل تو یه تیر دیگه‌ست ({TIER_SHORT.get(CELEBS[name][0])}). یه اسم دیگه بذار.")
    updating = name in CELEBS
    try:
        await m.bot.send_photo(
            m.chat.id, photo,
            caption=f"{'♻️ عکس به‌روز شد' if updating else '✅ به تیر مزایده اضافه شد'}\n\n👑 {name}\n🏅 تیر: {TIER_SHORT['AU']}\n\n🔨 /auction {name}"
        )
    except (TelegramBadRequest, TelegramForbiddenError):
        return await m.reply("❌ این file_id معتبر نیست یا برای این ربات کار نمی‌کنه. با /getfileid یه file_id درست بگیر.")
    register_au_celeb(name, photo, m.from_user.id)

@dp.message(Command("aulist"))
async def au_list(m: Message):
    names = [n for n, v in CELEBS.items() if v[0] == "AU"]
    if not names:
        return await m.reply("🔨 هنوز سلبریتی‌ای تو تیر مزایده ثبت نشده.\n(ادمین با /addau اضافه می‌کنه)")
    listing = "\n".join(f"• {n}" for n in sorted(names))
    await m.reply(f"🔨 سلبریتی‌های تیر مزایده ({len(names)} تا):\n\n{listing}")

# ===== دادن مستقیم سلبریتی تیر مزایده به یه کاربر (ادمین) =====
# روی پیام کاربر ریپلای کن: /giveau [file_id عکس] [اسم]
# اگه اسم از قبل تو تیر مزایده ثبت شده، فقط اسم کافیه: /giveau [اسم]
@dp.message(Command("giveau"))
async def give_au_celeb(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return await m.reply("❌ دسترسی ندارید!")
    if m.chat.type == "private":
        return await m.reply("❌ این دستور رو باید تو گروه بزنی.")
    usage = (
        "🎁 دادن سلبریتی تیر مزایده به یه کاربر\n\n"
        "روی پیام همون کاربر ریپلای کن و بنویس:\n/giveau [file_id عکس] [اسم]\n\n"
        "اگه اسم قبلاً تو تیر مزایده ثبت شده (/aulist) فقط اسم کافیه:\n/giveau [اسم]\n\n"
        "(file_id رو با /getfileid بگیر. ارزش تو کالکشن ۰ می‌شه و قابل /sell نیست.)"
    )
    if not m.reply_to_message or not m.reply_to_message.from_user:
        return await m.reply(usage)
    target = m.reply_to_message.from_user
    if target.is_bot:
        return await m.reply("❌ نمی‌تونی به ربات سلبریتی بدی!")
    raw = m.text.split(maxsplit=1)
    args = raw[1].strip() if len(raw) > 1 else ""
    if not args:
        return await m.reply(usage)
    photo = name = None
    if args in CELEBS and CELEBS[args][0] == "AU":
        name, photo = args, CELEBS[args][3]  # از کاتالوگ تیر مزایده
    else:
        parts = args.split(maxsplit=1)
        if len(parts) == 2:
            photo, name = parts[0], parts[1].strip()
    if not photo or not name:
        return await m.reply(usage)
    if len(name) > 60 or name.startswith("-") or "\n" in name:
        return await m.reply("❌ اسم نامعتبره (حداکثر ۶۰ حرف، با - شروع نشه).")
    if name in CELEBS and CELEBS[name][0] != "AU":
        return await m.reply(f"❌ «{name}» از قبل تو یه تیر دیگه‌ست ({TIER_SHORT.get(CELEBS[name][0])}). یه اسم دیگه بذار.")
    chat_id = m.chat.id
    user(chat_id, target.id, target.full_name)
    already = c.execute(
        "SELECT 1 FROM collections WHERE chat_id=? AND user_id=? AND celeb=?", (chat_id, target.id, name)
    ).fetchone()
    if already:
        return await m.reply(f"❌ {target.full_name} این سلبریتی رو از قبل داره!")
    try:
        await m.bot.send_photo(
            chat_id, photo,
            caption=(
                f"🎁 هدیه از تیر مزایده!\n\n"
                f"👑 {name}\n"
                f"🏅 تیر: {TIER_SHORT['AU']}\n"
                f"👤 گیرنده: {target.full_name}\n\n"
                f"✅ به کالکشنش اضافه شد."
            )
        )
    except (TelegramBadRequest, TelegramForbiddenError):
        return await m.reply("❌ این file_id معتبر نیست یا برای این ربات کار نمی‌کنه. با /getfileid یه file_id درست بگیر.")
    register_au_celeb(name, photo, m.from_user.id)  # اگه جدیده تو کاتالوگ ثبت می‌شه، وگرنه عکسش همونه
    c.execute(
        "INSERT INTO collections(chat_id,user_id,celeb,paid_price,locked) VALUES(?,?,?,0,0)",
        (chat_id, target.id, name)
    )
    db.commit()

@dp.message(Command("auction"))
async def auction_start(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return await m.reply("❌ دسترسی ندارید!")
    if m.chat.type == "private":
        return await m.reply("❌ این دستور رو باید تو گروه بزنی.")
    raw = m.text.split(maxsplit=1)
    args = raw[1].strip() if len(raw) > 1 else ""
    photo = name = None
    if not (m.reply_to_message and m.reply_to_message.photo) and args in CELEBS and CELEBS[args][0] == "AU":
        name, photo = args, CELEBS[args][3]  # از کاتالوگ تیر مزایده
    elif m.reply_to_message and m.reply_to_message.photo:
        photo = m.reply_to_message.photo[-1].file_id
        name = args
    else:
        parts = args.split(maxsplit=1)
        if len(parts) == 2:
            photo, name = parts[0], parts[1].strip()
    if not photo or not name:
        return await m.reply(
            "استفاده:\n/auction [file_id عکس] [اسم]\n\n"
            "یا روی یه عکس ریپلای کن و بنویس:\n/auction [اسم]\n\n"
            "یا فقط اسم یه سلبریتی که تو تیر مزایده ثبت کردی:\n/auction [اسم]  (لیست: /aulist)\n\n"
            "می‌تونی هرچندتا مزایده همزمان بذاری."
        )
    now = int(time.time())
    cur = c.execute(
        "INSERT INTO auctions(chat_id,name,photo,status,last_activity,created_at) VALUES(?,?,?,'active',?,?)",
        (m.chat.id, name, photo, now, now)
    )
    aid = cur.lastrowid
    db.commit()
    caption = (
        f"🔨 مزایده‌ی #{aid} شروع شد!\n\n"
        f"🎁 {name}\n"
        f"💰 حداقل پیشنهاد اول: {AUCTION_START_BID} سانت\n"
        f"📈 هر پیشنهاد جدید حداقل {AUCTION_MIN_INCREMENT} سانت بیشتر از قبلی\n"
        f"⏳ هرکس {AUCTION_IDLE_SECONDS//3600} ساعت بدون پیشنهاد بالاتر بمونه، برنده‌ست (هر پیشنهاد جدید تایمر رو از اول می‌کنه)\n\n"
        f"برای پیشنهاد: /bid {aid} [مبلغ]\n"
        f"یا روی همین عکس ریپلای کن و بنویس /bid [مبلغ]"
    )
    try:
        sent = await m.bot.send_photo(m.chat.id, photo, caption=caption)
    except (TelegramBadRequest, TelegramForbiddenError):
        c.execute("DELETE FROM auctions WHERE id=?", (aid,))
        db.commit()
        return await m.reply("❌ این file_id معتبر نیست یا برای این ربات کار نمی‌کنه. با /getfileid یه file_id درست بگیر.")
    c.execute("UPDATE auctions SET msg_id=? WHERE id=?", (sent.message_id, aid))
    db.commit()

@dp.message(Command("bid"))
async def auction_bid(m: Message):
    if m.chat.type == "private":
        return await m.reply("❌ پیشنهاد رو باید تو گروه بدی.")
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
        return await m.reply("استفاده:\n/bid [مبلغ]\n/bid [شماره‌ی مزایده] [مبلغ]\n\n(یا روی عکس مزایده ریپلای کن و بنویس /bid [مبلغ])")
    a, err = resolve_auction(m, token)
    if err:
        return await m.reply(err)
    aid, item, _photo, top_bid, top_bidder, top_name, _last, _mid = a
    uid = m.from_user.id
    user(m.chat.id, uid, m.from_user.full_name)
    min_required = AUCTION_START_BID if not top_bidder else top_bid + AUCTION_MIN_INCREMENT
    if amount < min_required:
        return await m.reply(f"❌ پیشنهادت برای مزایده‌ی #{aid} باید حداقل {min_required} سانت باشه.")
    available = get_size(m.chat.id, uid) + (top_bid if top_bidder == uid else 0)
    if available < amount:
        return await m.reply("❌ سانت کافی نداری.")
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
        f"🔨 {m.from_user.full_name} پیشنهاد {amount} سانت داد برای «{item}» (مزایده‌ی #{aid})!\n"
        f"⏳ تایمر {AUCTION_IDLE_SECONDS//3600} ساعته‌ی این مزایده از اول شروع شد."
    )
    if top_bidder and top_bidder != uid:
        try:
            await m.bot.send_message(top_bidder, f"⚠️ پیشنهادت روی «{item}» (#{aid}) رد شد و {top_bid} سانتت برگشت. یکی {amount} سانت داد!")
        except Exception:
            pass

@dp.message(Command("auctionstatus"))
async def auction_status(m: Message):
    rows = get_active_auctions(m.chat.id)
    if not rows:
        return await m.reply("📭 الان هیچ مزایده‌ای در جریان نیست.")
    now = int(time.time())
    txt = f"🔨 مزایده‌های فعال ({len(rows)} تا)\n\n"
    for aid, item, _p, top_bid, top_bidder, top_name, last, _mid in rows:
        left = AUCTION_IDLE_SECONDS - (now - last)
        bid_txt = f"{top_bid} سانت ({top_name})" if top_bidder else "هنوز پیشنهادی نیومده"
        txt += f"#{aid} 🎁 {item}\n   💰 {bid_txt}\n   ⏳ {fmt_time(left)} تا پایان (اگه پیشنهاد بالاتری نیاد)\n\n"
    txt += "برای پیشنهاد: /bid [شماره] [مبلغ]"
    await m.reply(txt)

# ===== کالکشن مزایده: سلبریتی‌هایی که الان بالاترین پیشنهاد روشونه =====
# - هیچ سانت جدیدی کم/زیاد نمی‌شه؛ این بخش فقط نمایشیه (حساب‌وکتاب).
# - /bid از قبل سانت پیشنهاد رو همون لحظه بلوکه می‌کنه، پس سانت «آزاد» الان یعنی
#   همون چیزی که بعد از خریدن همه‌ی این سلبریتی‌ها برات می‌مونه.
# - وقتی مزایده تموم بشه، سلبریتی خودکار میره تو /collection (finalize_auction)
def get_top_bid_auctions(chat_id, uid):
    return c.execute(
        "SELECT id,name,photo,top_bid,last_activity FROM auctions "
        "WHERE chat_id=? AND status='active' AND top_bidder=? ORDER BY top_bid DESC, id",
        (chat_id, uid)
    ).fetchall()

def build_bidcol_page(chat_id, owner_id, page, viewer_id):
    """خروجی: (متن، file_id عکس، کیبورد) یا (None, None, None) اگه چیزی نباشه."""
    rows = get_top_bid_auctions(chat_id, owner_id)
    if not rows:
        return None, None, None
    page = max(0, min(page, len(rows) - 1))
    aid, name, photo, bid, last = rows[page]
    total = sum(r[3] for r in rows)
    free = get_size(chat_id, owner_id)
    left = AUCTION_IDLE_SECONDS - (int(time.time()) - last)
    owner_name = get_name(chat_id, owner_id)
    txt = (
        f"🔨 کالکشن مزایده‌ی {owner_name} — {page+1}/{len(rows)}\n\n"
        f"👑 {name}\n"
        f"🆔 مزایده‌ی #{aid}\n"
        f"💰 بالاترین پیشنهاد (مال {owner_name}): {bid} سانت\n"
        f"⏳ {fmt_time(left)} تا پایان (اگه پیشنهاد بالاتری نیاد)\n\n"
        f"━━━━━━━━━━━━\n"
        f"🧮 جمع حساب ({len(rows)} سلبریتی)\n"
        f"💼 مجموع پیشنهادهای برتر: {total} سانت\n"
        f"📏 سانت قبل از پیشنهادها: {free + total}\n"
        f"➖ کم‌شده برای خریدشون: {total}\n"
        f"✅ سانت باقی‌مونده اگه همه‌شون رو ببره: {free}\n"
        f"(سانت پیشنهادها از قبل تو مزایده بلوکه شده؛ چیز جدیدی کم نمی‌شه)"
    )
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"bcol:{viewer_id}:{owner_id}:{page-1}"))
    if page < len(rows) - 1:
        buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"bcol:{viewer_id}:{owner_id}:{page+1}"))
    rows_kb = [buttons] if buttons else []
    if viewer_id == owner_id:  # دکمه‌ی لغو فقط تو کالکشن خود صاحب پیشنهاد
        rows_kb.append([InlineKeyboardButton(text="❌ لغو این پیشنهاد", callback_data=f"cbid:{owner_id}:{aid}")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows_kb) if rows_kb else None
    return txt, photo, kb

@dp.message(Command("bidcol"))
async def bid_collection(m: Message):
    if m.reply_to_message and m.reply_to_message.from_user:
        t = m.reply_to_message.from_user
        user(m.chat.id, t.id, t.full_name)
        owner_id, owner_name = t.id, t.full_name
    else:
        user(m.chat.id, m.from_user.id, m.from_user.full_name)
        owner_id, owner_name = m.from_user.id, m.from_user.full_name
    txt, photo_ref, kb = build_bidcol_page(m.chat.id, owner_id, 0, m.from_user.id)
    if not txt:
        return await m.reply(
            f"🔨 {owner_name} الان بالاترین پیشنهاد هیچ مزایده‌ای رو نداره.\n"
            f"📏 سانت آزاد: {get_size(m.chat.id, owner_id)}\n\n"
            f"📋 /auctionstatus برای دیدن مزایده‌های فعال"
        )
    photo = await resolve_photo(photo_ref) if photo_ref else None
    try:
        if photo:
            sent = await m.bot.send_photo(m.chat.id, photo, caption=txt, reply_markup=kb)
            if isinstance(photo, BufferedInputFile):
                cache_photo(photo_ref, sent)
        else:
            await m.bot.send_message(m.chat.id, txt, reply_markup=kb)
    except Exception as e:
        logger.warning("bidcol photo failed: %s", e)
        await m.bot.send_message(m.chat.id, txt, reply_markup=kb)

@dp.callback_query(F.data.startswith("bcol:"))
async def bid_collection_nav(q: CallbackQuery):
    parts = q.data.split(":")
    if len(parts) != 4:
        return await q.answer(NAV_LEGACY_MSG, show_alert=True)
    _, viewer_id, owner_id, page = parts
    viewer_id, owner_id, page = int(viewer_id), int(owner_id), int(page)
    if not await nav_guard(q, viewer_id):
        return
    txt, photo_ref, kb = build_bidcol_page(q.message.chat.id, owner_id, page, viewer_id)
    if not txt:
        try:
            await q.message.edit_caption(caption="🔨 دیگه پیشنهاد برتری برای این کاربر نمونده (مزایده‌ها تموم شدن یا کسی بالاتر داده).")
        except Exception:
            pass
        return await q.answer()
    photo = await resolve_photo(photo_ref) if photo_ref else None
    try:
        if photo and q.message.photo:
            edited = await q.message.edit_media(media=InputMediaPhoto(media=photo, caption=txt), reply_markup=kb)
            if isinstance(photo, BufferedInputFile) and hasattr(edited, "photo"):
                cache_photo(photo_ref, edited)
        elif q.message.photo:
            await q.message.edit_caption(caption=txt, reply_markup=kb)
        else:
            await q.message.edit_text(txt, reply_markup=kb)
    except TelegramBadRequest as e:
        if "not modified" not in str(e).lower():
            return await q.answer(f"خطا: {e}", show_alert=True)
    except Exception as e:
        return await q.answer(f"خطا: {e}", show_alert=True)
    await q.answer()

# ===== لغو پیشنهاد =====
# - فقط کسی که الان بالاترین پیشنهاد رو داره می‌تونه لغو کنه
# - کل مبلغ بلوکه‌شده برمی‌گرده و مزایده بدون پیشنهاد می‌مونه
#   (پیشنهاد نفر قبلی از وقتی ردش کردن برگشته، پس چیزی برای برگردوندن بهش نیست)
# - تایمر مزایده از اول شروع می‌شه
def cancel_top_bid(chat_id, uid, aid):
    """خروجی: (موفق؟، پیام)"""
    row = c.execute(
        "SELECT name,top_bid,top_bidder FROM auctions WHERE id=? AND chat_id=? AND status='active'",
        (aid, chat_id)
    ).fetchone()
    if not row:
        return False, "❌ این مزایده دیگه فعال نیست."
    name, top_bid, top_bidder = row
    if top_bidder != uid:
        return False, "❌ الان بالاترین پیشنهاد مال تو نیست، چیزی برای لغو نداری."
    c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?", (top_bid, chat_id, uid))
    c.execute(
        "UPDATE auctions SET top_bid=0, top_bidder=0, top_bidder_name='', last_activity=? WHERE id=?",
        (int(time.time()), aid)
    )
    db.commit()
    return True, (
        f"✅ پیشنهادت روی «{name}» (مزایده‌ی #{aid}) لغو شد.\n"
        f"💸 {top_bid} سانت بهت برگشت. سانت فعلی: {get_size(chat_id, uid)}\n"
        f"🔨 مزایده دوباره بدون پیشنهاده (حداقل پیشنهاد اول: {AUCTION_START_BID} سانت)."
    )

@dp.message(Command("cancelbid"))
async def cancel_bid_cmd(m: Message):
    if m.chat.type == "private":
        return await m.reply("❌ این دستور رو باید تو گروه بزنی.")
    uid = m.from_user.id
    user(m.chat.id, uid, m.from_user.full_name)
    mine = get_top_bid_auctions(m.chat.id, uid)
    if not mine:
        return await m.reply("📭 الان بالاترین پیشنهاد هیچ مزایده‌ای مال تو نیست.")
    args = [a.lstrip("#") for a in m.text.split()[1:]]
    mine_ids = {r[0] for r in mine}
    aid = None
    if args and args[0].isdigit():
        aid = int(args[0])
        if aid not in mine_ids:
            return await m.reply(f"❌ تو الان بالاترین پیشنهاد مزایده‌ی #{aid} رو نداری.")
    elif m.reply_to_message:
        row = c.execute(
            "SELECT id FROM auctions WHERE chat_id=? AND status='active' AND msg_id=?",
            (m.chat.id, m.reply_to_message.message_id)
        ).fetchone()
        if row and row[0] in mine_ids:
            aid = row[0]
    if aid is None:
        if len(mine) == 1:
            aid = mine[0][0]
        else:
            listing = "\n".join(f"• #{r[0]} — {r[1]} ({r[3]} سانت)" for r in mine)
            return await m.reply(
                f"📊 چندتا پیشنهاد برتر داری، مشخص کن کدوم رو لغو کنم:\n{listing}\n\n"
                f"مثال: /cancelbid {mine[0][0]}\n(یا از دکمه‌ی ❌ تو /bidcol استفاده کن)"
            )
    _ok, msg = cancel_top_bid(m.chat.id, uid, aid)
    await m.reply(msg)

@dp.callback_query(F.data.startswith("cbid:"))
async def cancel_bid_btn(q: CallbackQuery):
    _, owner_id, aid = q.data.split(":")
    owner_id, aid = int(owner_id), int(aid)
    if q.from_user.id != owner_id:
        return await q.answer("❌ این پیشنهاد مال تو نیست!", show_alert=True)
    ok, msg = cancel_top_bid(q.message.chat.id, owner_id, aid)
    if not ok:
        return await q.answer(msg, show_alert=True)
    await q.answer("✅ پیشنهاد لغو شد و سانتت برگشت.", show_alert=True)
    await q.message.reply(msg)
    txt, photo_ref, kb = build_bidcol_page(q.message.chat.id, owner_id, 0, owner_id)
    try:
        if not txt:
            txt = f"🔨 دیگه بالاترین پیشنهاد هیچ مزایده‌ای مال تو نیست.\n📏 سانت آزاد: {get_size(q.message.chat.id, owner_id)}"
            if q.message.photo:
                await q.message.edit_caption(caption=txt, reply_markup=None)
            else:
                await q.message.edit_text(txt, reply_markup=None)
            return
        photo = await resolve_photo(photo_ref) if photo_ref else None
        if photo and q.message.photo:
            await q.message.edit_media(media=InputMediaPhoto(media=photo, caption=txt), reply_markup=kb)
        elif q.message.photo:
            await q.message.edit_caption(caption=txt, reply_markup=kb)
        else:
            await q.message.edit_text(txt, reply_markup=kb)
    except Exception as e:
        logger.warning("cancel_bid_btn refresh failed: %s", e)

# ===== کالکشن مزایده‌های فعال (همه‌ی مزایده‌های در جریان، با عکس) =====
def build_aucol_page(chat_id, page, viewer_id):
    """خروجی: (متن، file_id عکس، کیبورد) یا (None, None, None) اگه مزایده‌ی فعالی نباشه."""
    rows = get_active_auctions(chat_id)
    if not rows:
        return None, None, None
    page = max(0, min(page, len(rows) - 1))
    aid, name, photo, top_bid, top_bidder, top_name, last, _mid = rows[page]
    if top_bidder:
        bid_txt = f"{top_bid} سانت — 👑 {top_name}"
        min_next = top_bid + AUCTION_MIN_INCREMENT
    else:
        bid_txt = "هنوز پیشنهادی نیومده"
        min_next = AUCTION_START_BID
    left = AUCTION_IDLE_SECONDS - (int(time.time()) - last)
    txt = (
        f"🔨 مزایده‌های فعال — {page+1}/{len(rows)}\n\n"
        f"🎁 {name}\n"
        f"🆔 مزایده‌ی #{aid}\n"
        f"💰 بالاترین پیشنهاد: {bid_txt}\n"
        f"📈 حداقل پیشنهاد بعدی: {min_next} سانت\n"
        f"⏳ {fmt_time(left)} تا پایان (اگه پیشنهاد بالاتری نیاد)\n\n"
        f"🔨 /bid {aid} {min_next}"
    )
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"acol:{viewer_id}:{page-1}"))
    if page < len(rows) - 1:
        buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"acol:{viewer_id}:{page+1}"))
    kb = InlineKeyboardMarkup(inline_keyboard=[buttons]) if buttons else None
    return txt, photo, kb

@dp.message(Command("aucol"))
async def auction_collection(m: Message):
    txt, photo_ref, kb = build_aucol_page(m.chat.id, 0, m.from_user.id)
    if not txt:
        return await m.reply("📭 الان هیچ مزایده‌ای در جریان نیست.")
    photo = await resolve_photo(photo_ref) if photo_ref else None
    try:
        if photo:
            sent = await m.bot.send_photo(m.chat.id, photo, caption=txt, reply_markup=kb)
            if isinstance(photo, BufferedInputFile):
                cache_photo(photo_ref, sent)
        else:
            await m.bot.send_message(m.chat.id, txt, reply_markup=kb)
    except Exception as e:
        logger.warning("aucol photo failed: %s", e)
        await m.bot.send_message(m.chat.id, txt, reply_markup=kb)

@dp.callback_query(F.data.startswith("acol:"))
async def auction_collection_nav(q: CallbackQuery):
    parts = q.data.split(":")
    if len(parts) != 3:
        return await q.answer(NAV_LEGACY_MSG, show_alert=True)
    viewer_id, page = int(parts[1]), int(parts[2])
    if not await nav_guard(q, viewer_id):
        return
    txt, photo_ref, kb = build_aucol_page(q.message.chat.id, page, viewer_id)
    if not txt:
        try:
            if q.message.photo:
                await q.message.edit_caption(caption="📭 دیگه مزایده‌ی فعالی نمونده.", reply_markup=None)
            else:
                await q.message.edit_text("📭 دیگه مزایده‌ی فعالی نمونده.", reply_markup=None)
        except Exception:
            pass
        return await q.answer()
    photo = await resolve_photo(photo_ref) if photo_ref else None
    try:
        if photo and q.message.photo:
            edited = await q.message.edit_media(media=InputMediaPhoto(media=photo, caption=txt), reply_markup=kb)
            if isinstance(photo, BufferedInputFile) and hasattr(edited, "photo"):
                cache_photo(photo_ref, edited)
        elif q.message.photo:
            await q.message.edit_caption(caption=txt, reply_markup=kb)
        else:
            await q.message.edit_text(txt, reply_markup=kb)
    except TelegramBadRequest as e:
        if "not modified" not in str(e).lower():
            return await q.answer(f"خطا: {e}", show_alert=True)
    except Exception as e:
        return await q.answer(f"خطا: {e}", show_alert=True)
    await q.answer()

@dp.message(Command("endauction"))
async def auction_end(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return await m.reply("❌ دسترسی ندارید!")
    tokens = m.text.split()[1:]
    cancel = any(t.lower() == "cancel" for t in tokens)
    nums = [t.lstrip("#") for t in tokens if t.lower() != "cancel"]
    token = int(nums[0]) if nums and nums[0].isdigit() else None
    a, err = resolve_auction(m, token)
    if err:
        return await m.reply(err + "\n\nمثال: /endauction [شماره]  یا  /endauction [شماره] cancel")
    await finalize_auction(m.bot, a[0], cancel=cancel)

@dp.message(Command("addcm"))
async def addcm(m:Message):
    if m.from_user.id not in ADMIN_IDS:
        return await m.reply("❌ دسترسی ندارید!")
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
    await m.reply(f"✅ {amount} سانت به {m.reply_to_message.from_user.full_name} اضافه شد!\n📏 اندازه جدید: {new_size} سانت")

@dp.message(Command("luckydrop"))
async def lucky_drop(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return await m.reply("❌ دسترسی ندارید!")
    prize = 50
    try:
        parts = m.text.split()
        if len(parts) > 1:
            prize = int(parts[1])
    except:
        pass
    players = c.execute("SELECT user_id,name FROM users WHERE chat_id=?", (m.chat.id,)).fetchall()
    if not players:
        return await m.reply("❌ هنوز کسی تو این گروه بازی نکرده که قرعه‌کشی بشه.")
    winner_id, winner_name = random.choice(players)
    c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?", (prize, m.chat.id, winner_id))
    db.commit()
    new_size = get_size(m.chat.id, winner_id)
    await m.reply(f"🎉 قرعه‌کشی رندوم!\n\n🍆 {winner_name} خوش‌شانس بود و {prize} سانت مجانی گرفت!\n📏 اندازه‌ی جدیدش: {new_size} سانت")

@dp.message(Command("resetgroup"))
async def reset_group(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return await m.reply("❌ دسترسی ندارید!")
    parts = m.text.split()
    if len(parts) < 2 or parts[1] != "CONFIRM":
        return await m.reply(
            "⚠️ این کار همه‌ی داده‌های این گروه رو کاملاً و برای همیشه پاک می‌کنه:\n"
            "سایز/اسپرم همه، رنک، مافیا، بورس، کلکسیون سلبریتی‌ها، وام‌ها و مزرعه.\n\n"
            "اگه مطمئنی، بنویس:\n/resetgroup CONFIRM"
        )
    chat_id = m.chat.id
    # جدول‌هایی که مستقیم ستون chat_id دارن
    for table in (
        "users", "pvp_stats", "rank_stats", "loans", "listings",
        "game_loans", "mafia_battles", "mafia2_battles", "collections",
        "company_rounds", "company_options", "company_investments",
        "company_participants", "owned_companies",
        "farm_tiles", "farm_inventory", "farm_records", "auctions", "climb_games", "blackjack_games", "wealth_tax", "activity", "play_log",
        "crypto_pools", "crypto_wallet", "crypto_prices", "crypto_npc", "crypto_settings", "crypto_news",
    ):
        c.execute(f"DELETE FROM {table} WHERE chat_id=?", (chat_id,))
    # جدول‌هایی که فقط از طریق battle_id به گروه وصلن
    c.execute("DELETE FROM mafia_members WHERE battle_id IN (SELECT id FROM mafia_battles WHERE chat_id=?)", (chat_id,))
    c.execute("DELETE FROM mafia2_members WHERE battle_id IN (SELECT id FROM mafia2_battles WHERE chat_id=?)", (chat_id,))
    db.commit()
    await m.reply("✅ همه‌ی داده‌های این گروه پاک شد. بازی از صفر شروع می‌شه.")


async def addsperm(m:Message):
    if m.from_user.id not in ADMIN_IDS:
        return await m.reply("❌ دسترسی ندارید!")
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
    await m.reply(f"✅ {amount} اسپرم به {m.reply_to_message.from_user.full_name} اضافه شد!\n🧬 اسپرم جدید: {new_sperm}")


@dp.message(Command("addspermall"))
async def addsperm_all(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return await m.reply("❌ دسترسی ندارید!")
    try:
        amount = int(m.text.split()[1])
    except:
        return await m.reply("Usage: /addspermall [amount]\nمثال: /addspermall 100")
    c.execute("UPDATE users SET sperm=sperm+? WHERE chat_id=?", (amount, m.chat.id))
    affected = c.rowcount
    db.commit()
    await m.reply(f"✅ {amount} اسپرم به همه‌ی {affected} کاربر این گروه اضافه شد!")


@dp.message(Command("addcb"))
async def addcb(m:Message):
    if m.from_user.id not in ADMIN_IDS:
        return await m.reply("❌ دسترسی ندارید!")
    raw = strip_command(m.text)
    if not raw:
        return await m.reply(
            "Usage: /addcb [نام سلبریتی] (reply to a user)\nمثال: /addcb Dua Lipa\n\n"
            "برای گرفتن سلبریتی از کسی، یه منفی جلوش بذار:\nمثال: /addcb -Dua Lipa"
        )
    remove_mode = raw.startswith("-")
    name = raw[1:].strip() if remove_mode else raw
    if name not in CELEBS:
        return await m.reply("❌ سلبریتی پیدا نشد.")
    if not m.reply_to_message:
        return await m.reply("Reply to a user to give/take the celeb.")
    target = m.reply_to_message.from_user.id
    user(m.chat.id, target, m.reply_to_message.from_user.full_name)
    already = c.execute("SELECT 1 FROM collections WHERE chat_id=? AND user_id=? AND celeb=?", (m.chat.id, target, name)).fetchone()
    if remove_mode:
        if not already:
            return await m.reply(f"❌ {m.reply_to_message.from_user.full_name} اصلاً این سلبریتی رو نداره!")
        c.execute("DELETE FROM collections WHERE chat_id=? AND user_id=? AND celeb=?", (m.chat.id, target, name))
        db.commit()
        return await m.reply(f"🗑 {name} از {m.reply_to_message.from_user.full_name} گرفته شد!")
    if already:
        return await m.reply(f"❌ {m.reply_to_message.from_user.full_name} این سلبریتی رو داره!")
    tier, price, spin, photo = CELEBS[name]
    c.execute("INSERT INTO collections(chat_id,user_id,celeb,paid_price,locked) VALUES(?,?,?,?,0)", (m.chat.id, target, name, price))
    db.commit()
    await m.reply(f"✅ {name} به {m.reply_to_message.from_user.full_name} داده شد!\n👑 Tier {tier}")


# ================== کمپانی کیر (بازار بورس) ==================
# فرضیات پیاده‌سازی (اگه فرق داشت بگو عوض کنم):
# - فقط ادمین بازار رو باز/بسته می‌کنه (/copen و /cclose)
# - بین دوتا /copen هیچ محدودیت زمانی وجود نداره؛ ادمین هر وقت خواست باز/بسته می‌کنه
# - حداقل بودجه‌ی هر شرکت رندومه (بین ۵ تا ۱۵ سانت) و برای هر شرکت جدا تعیین میشه
# - هر سرمایه‌گذاری باید حداقل ۱۰٪ سایز لحظه‌ای فرد باشه؛ سقفی برای حداکثرش نیست (نامحدود)
# - شرکتی که بیشترین سرمایه رو جمع کرده حذف میشه (گنده شده, ترکیده) + شرکتی که به حداقل بودجه‌ی خودش نرسیده
# - بین بقیه، بیشترین سهم‌دار هر شرکت، همون شرکت رو با کل سرمایه‌ی جمع‌شده توش می‌بره (بقیه سرمایه‌شون رو از دست میدن)
# - هر شرکت بعد از برد، روزی یه بار ۱۰٪ ارزشش سود میده
# - هر شرکت ۲ یا ۳ "یار" رندوم داره که صاحبش می‌تونه با /hire بخره و با /useyar بفرسته توی نبرد مافیای فعلیش
#   (یار فقط تعداد تیم رو زیاد می‌کنه؛ سهمی از جایزه‌ی نقدی نمی‌بره تا اقتصاد بازی خراب نشه)
# - /cashout نصف ارزش فعلی شرکت رو نقد می‌کنه و از ارزش شرکت (و سود روزانه‌ی بعدیش) کم می‌کنه

COMPANY_COOLDOWN = 0                # محدودیت زمانی باز کردن بازار حذف شده؛ فقط ادمین کنترل می‌کند
COMPANY_MIN_INVEST_PCT = 0.10       # کف سرمایه‌گذاری هر نفر توی هر بار /invest: ۱۰٪ سایزش (نه سقف!)
COMPANY_MIN_BUDGET_LOW = 5          # پایین‌ترین مقدار ممکن برای حداقل بودجه‌ی یه شرکت
COMPANY_MIN_BUDGET_HIGH = 15        # بالاترین مقدار ممکن برای حداقل بودجه‌ی یه شرکت
COMPANY_DIVIDEND_PCT = 0.20         # سود روزانه‌ی شرکت به صاحبش
COMPANY_WORKER_COST = 15            # قیمت خرید هر یار مافیا از شرکت

COMPANY_NAME_POOL = [
    "هلدینگ کلفت‌کاران", "شرکت درازگستر", "گروه صنعتی گردن‌کلفت",
    "کارخانه شق‌القمر", "شرکت راست‌قامتان", "هلدینگ قدبلند پلاس",
    "گروه بازرگانی ستون‌محکم", "شرکت خشتک‌پاره",
    "کارخانه سه‌سانتی و شرکا", "هلدینگ قدکش‌ها",
    "شرکت دراز و دردسر", "گروه صنعتی چوب‌خط",
    "شرکت کلفت‌گستر شرق", "کارخانه میله‌محکم",
    "هلدینگ صاف‌و‌صوف", "شرکت گردن‌کلفت غرب",
    "گروه صنعتی خط‌کش‌طلایی", "شرکت قدبلندستان",
    "کارخانه ستون‌سازان", "هلدینگ اندازه‌گیران",
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

# اگه دیتابیس قدیمی هنوز اسکیمای تک-بازاره (chat_id تنها کلید اصلی)، منتقلش کن به اسکیمای چندبازاره
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
    "یار خفن شرکت", "پسرعموی کلفت", "کارمند بی‌سروپا", "یارِ زیرِ میزی",
    "بادیگارد کیری", "همکار مشکوک", "یار قاچاقی", "کارگر شیفت شب",
]


def find_active_membership(chat_id, uid):
    """آخرین نبرد فعال مافیا/مافیا۲ که این کاربر واقعاً (نه به عنوان یار) توش عضوه رو پیدا می‌کنه.
    خروجی: (kind, battle_id, team) یا None اگه توی هیچ نبردی نباشه."""
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
    """لیست همه‌ی بازارهایی که همین الان تو این گروه بازن."""
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
        return await m.reply("❌ فقط ادمین می‌تونه بازار رو باز کنه!")
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
    txt = f"📈 یه بازار بورس جدید باز شد! (بازار شماره‌ی #{new_round})\n\n"
    for i, (name, mb) in enumerate(zip(names, min_budgets), 1):
        txt += f"{i}. {name} (حداقل بودجه: {mb} اسپرم)\n"
    txt += "\n🏛 برنده‌ی هر شرکت بعداً با /joinparty انتخاب می‌کنه شرکتش پشت کدوم حزب (و پول رسمی) وایسته. وضعیت حزب‌ها: /party\n"
    txt += (
        f"\n🧬 هر سرمایه‌گذاری باید حداقل {int(COMPANY_MIN_INVEST_PCT*100)}٪ اسپرمت باشه؛ سقفی نداره!\n"
        f"(نداری؟ با /tosperm سانتت رو تبدیل کن — هر ۱ سانت = {SPERM_RATE} اسپرم)\n\n"
        f"برای سرمایه‌گذاری فقط بنویس /invest (بدون هیچ عددی!)\n"
        f"ربات میاد پیوی خصوصی باهات هماهنگ می‌کنه که کسی نفهمه رو چی و چقدر سرمایه‌گذاری کردی."
    )
    if open_count > 1:
        txt += f"\n\n📊 الان {open_count} تا بازار همزمان باز هستن تو این گروه."
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
        return await m.reply("❌ این دستور رو باید توی همون گروهی که بازی می‌کنی بزنی.")
    open_rounds = get_open_rounds(m.chat.id)
    if not open_rounds:
        return await m.reply("❌ الان هیچ بازاری باز نیست!")
    user(m.chat.id, m.from_user.id, m.from_user.full_name)
    tip = ""
    if len(m.text.split()) > 1:
        tip = "\n\n💡 دیگه لازم نیست بعد /invest عدد بنویسی — کل انتخاب رو همینجا با دکمه انجام بده."

    if len(open_rounds) == 1:
        round_id = open_rounds[0][0]
        opts, kb = build_company_picker_kb(m.chat.id, round_id)
        if not opts:
            return await m.reply("❌ شرکتی برای این بازار پیدا نشد.")
        try:
            await m.bot.send_message(
                m.from_user.id,
                "📈 روی کدوم شرکت می‌خوای سرمایه‌گذاری کنی؟\n(این پیام فقط برای خودته)" + tip,
                reply_markup=kb
            )
        except (TelegramForbiddenError, TelegramBadRequest):
            return await m.reply("❌ اول باید ربات رو توی پیوی (چت خصوصی) استارت کنی، بعد دوباره اینجا /invest بزن.")
        return await m.reply("📩 برات پیام خصوصی فرستادم! بقیه‌ی سرمایه‌گذاری رو اونجا انجام بده تا لو نره.")

    # چندتا بازار همزمان باز هستن — اول باید انتخاب کنه کدوم رو می‌خواد
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📈 بازار #{rid}", callback_data=f"investmarket:{m.chat.id}:{rid}")]
        for rid, _ in open_rounds
    ])
    try:
        await m.bot.send_message(
            m.from_user.id,
            f"📊 الان {len(open_rounds)} تا بازار همزمان باز هستن. کدومش رو می‌خوای سرمایه‌گذاری کنی؟" + tip,
            reply_markup=kb
        )
    except (TelegramForbiddenError, TelegramBadRequest):
        return await m.reply("❌ اول باید ربات رو توی پیوی (چت خصوصی) استارت کنی، بعد دوباره اینجا /invest بزن.")
    await m.reply("📩 برات پیام خصوصی فرستادم! بقیه‌ی سرمایه‌گذاری رو اونجا انجام بده تا لو نره.")

@dp.callback_query(F.data.startswith("investmarket:"))
async def company_invest_pick_market(q: CallbackQuery):
    _, chat_id, round_id = q.data.split(":")
    chat_id, round_id = int(chat_id), int(round_id)
    if get_round_status(chat_id, round_id) != "open":
        return await q.answer("❌ این بازار دیگه بسته شده.", show_alert=True)
    opts, kb = build_company_picker_kb(chat_id, round_id)
    if not opts:
        return await q.answer("❌ شرکتی برای این بازار پیدا نشد.", show_alert=True)
    await q.message.edit_text(f"📈 بازار #{round_id} — روی کدوم شرکت می‌خوای سرمایه‌گذاری کنی؟", reply_markup=kb)
    await q.answer()


@dp.callback_query(F.data.startswith("investpick:"))
async def company_invest_pick(q: CallbackQuery):
    _, chat_id, round_id, slot = q.data.split(":")
    chat_id, round_id, slot = int(chat_id), int(round_id), int(slot)
    if get_round_status(chat_id, round_id) != "open":
        return await q.answer("❌ این بازار دیگه بسته یا منقضی شده.", show_alert=True)
    opt = c.execute("SELECT name FROM company_options WHERE chat_id=? AND round_id=? AND slot=?", (chat_id, round_id, slot)).fetchone()
    if not opt:
        return await q.answer("❌ همچین شرکتی پیدا نشد.", show_alert=True)
    pending_invest[q.from_user.id] = {"chat_id": chat_id, "round_id": round_id, "slot": slot, "ts": int(time.time())}
    await q.answer()
    await q.message.edit_text(f"🧬 چند اسپرم می‌خوای روی «{opt[0]}» سرمایه‌گذاری کنی؟\nفقط عددشو بفرست (مثلاً 12).\n(نداری؟ با /tosperm سانتت رو تبدیل کن.)")


@dp.message(F.chat.type == "private", F.text.regexp(r'^\d+$'))
async def company_invest_amount(m: Message):
    pending = pending_invest.get(m.from_user.id)
    if not pending:
        return
    if int(time.time()) - pending["ts"] > PENDING_INVEST_TTL:
        del pending_invest[m.from_user.id]
        return await m.reply("⌛️ زمان انتخابت تموم شد، دوباره از توی گروه /invest بزن.")
    amount = int(m.text)
    chat_id, round_id, slot = pending["chat_id"], pending["round_id"], pending["slot"]
    if amount <= 0:
        return await m.reply("❌ مقدار باید مثبت باشه.")
    if get_round_status(chat_id, round_id) != "open":
        del pending_invest[m.from_user.id]
        return await m.reply("❌ اون بازار بسته شده، دوباره از توی گروه /invest بزن.")
    opt = c.execute("SELECT name FROM company_options WHERE chat_id=? AND round_id=? AND slot=?", (chat_id, round_id, slot)).fetchone()
    if not opt:
        del pending_invest[m.from_user.id]
        return await m.reply("❌ این شرکت دیگه وجود نداره.")
    sperm = get_sperm(chat_id, m.from_user.id)
    if sperm < amount:
        return await m.reply(f"❌ اسپرم کافی نداری. (موجودی: {sperm})\nبا /tosperm می‌تونی سانتت رو تبدیل کنی.")
    min_required = max(1, int(sperm * COMPANY_MIN_INVEST_PCT))
    if amount < min_required:
        return await m.reply(f"❌ هر سرمایه‌گذاری باید حداقل {int(COMPANY_MIN_INVEST_PCT*100)}٪ اسپرمت باشه!\n📊 حداقل مجاز الان: {min_required} اسپرم")
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
    await m.reply("✅ سرمایه‌گذاریت با موفقیت و کاملاً محرمانه ثبت شد!")


@dp.message(Command("cclose"))
async def company_close(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return await m.reply("❌ فقط ادمین می‌تونه بازار رو ببنده!")
    open_rounds = get_open_rounds(m.chat.id)
    if not open_rounds:
        return await m.reply("❌ هیچ بازاری باز نیست.")
    parts = m.text.split()
    if len(open_rounds) == 1:
        round_id = open_rounds[0][0]
    elif len(parts) > 1 and parts[1].isdigit() and int(parts[1]) in {r for r, _ in open_rounds}:
        round_id = int(parts[1])
    else:
        listing = "\n".join(f"• #{r}" for r, _ in open_rounds)
        return await m.reply(f"📊 چندتا بازار همزمان بازه، مشخص کن کدومو ببندم:\n{listing}\n\nمثال: /cclose {open_rounds[0][0]}")
    opts = c.execute("SELECT slot,name,min_budget FROM company_options WHERE chat_id=? AND round_id=?", (m.chat.id, round_id)).fetchall()
    if not opts:
        return await m.reply("❌ شرکتی برای این دور پیدا نشد.")
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
    txt = f"📉 نتیجه‌ی بازار بورس #{round_id}!\n\n"
    for slot, (name, total, min_budget) in totals.items():
        if slot in eliminated:
            reason = "گنده شد و ترکید 💥" if slot == max_slot else f"به حداقل بودجه‌ش ({min_budget} اسپرم) نرسید 📉"
            txt += f"❌ {name} ({total} اسپرم) — {reason}\n"
            continue
        top = c.execute(
            "SELECT user_id,amount FROM company_investments WHERE chat_id=? AND round_id=? AND slot=? ORDER BY amount DESC LIMIT 1",
            (m.chat.id, round_id, slot)
        ).fetchone()
        if not top:
            txt += f"⚪️ {name} — کسی سرمایه‌گذاری نکرد، برنده‌ای نداشت\n"
            continue
        winner_id, winner_amount = top
        workers = random.randint(2, 3)
        c.execute(
            "INSERT INTO owned_companies(chat_id,owner_id,name,value,workers,last_payout) VALUES(?,?,?,?,?,?)",
            (m.chat.id, winner_id, name, total, workers, now)
        )
        new_cid = c.lastrowid
        winner_name = get_name(m.chat.id, winner_id)
        txt += f"👑 #{new_cid} {name} ({total} اسپرم) — برنده: {winner_name} (سهم {winner_amount} اسپرم)\n"

    c.execute("UPDATE company_rounds SET status='closed' WHERE chat_id=? AND round_id=?", (m.chat.id, round_id))
    db.commit()
    if "👑" in txt:
        txt += ("\n🏛 صاحب‌های شرکت‌ها: با /joinparty [شماره شرکت] [کوین] حزب شرکتتون رو انتخاب کنین "
                "(مثلاً /joinparty 5 BTK). تا حزب انتخاب نشه، شرکت به هیچ کوینی کمک نمی‌کنه. لیست حزب‌ها: /party\n")
    await m.reply(txt)


@dp.message(Command("mycompanies"))
async def my_companies(m: Message):
    rows = c.execute("SELECT id,name,value,workers,workers_bought,workers_used_mafia,party FROM owned_companies WHERE chat_id=? AND owner_id=?", (m.chat.id, m.from_user.id)).fetchall()
    if not rows:
        return await m.reply("📭 هنوز هیچ شرکتی نداری! وقتی بازار بورس بازه با /invest شرکت کن.")
    txt = "🏢 شرکت‌های تو:\n\n"
    for cid, name, value, workers, bought, used, party in rows:
        income = int(value * COMPANY_DIVIDEND_PCT)
        available = bought - used
        txt += f"#{cid} {name}{party_tag(party)}\n🧬 ارزش: {value} اسپرم | 📈 سود روزانه: {income} اسپرم\n👥 یار: {bought}/{workers} خریداری‌شده ({available} آماده‌ی استفاده با /useyar)\n\n"
    await m.reply(txt)


# ===== رنک بورس بر اساس ارزش خالص شرکت‌ها =====
BOURSE_RANK_TIERS = [
    (0,    "🥫 دستفروش"),
    (50,   "🏪 مغازه‌دار"),
    (150,  "🏢 تاجر"),
    (400,  "🏦 میلیاردر"),
    (800,  "🚀 ایلان ماسک"),
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
        return await m.reply("📭 هنوز کسی تو بورس این گروه برنده نشده!")
    stats = {}
    for owner_id, value in rows:
        s = stats.setdefault(owner_id, {"net_worth": 0, "companies": 0, "wins": 0, "daily_income": 0})
        s["wins"] += 1
        if value > 0:
            s["net_worth"] += value
            s["companies"] += 1
            s["daily_income"] += int(value * COMPANY_DIVIDEND_PCT)
    leaderboard = sorted(stats.items(), key=lambda kv: kv[1]["net_worth"], reverse=True)[:10]
    txt = "📊 جدول بورس این گروه\n\n"
    for i, (owner_id, s) in enumerate(leaderboard, 1):
        name = get_name(m.chat.id, owner_id)
        tier = get_bourse_tier(s["net_worth"])
        txt += (
            f"{i}. {name}\n"
            f"   {tier}\n"
            f"   🧬 ارزش خالص: {s['net_worth']} اسپرم | 🏢 شرکت‌های فعال: {s['companies']} | 🏆 کل بردها: {s['wins']}\n"
            f"   📈 مجموع سود روزانه: {s['daily_income']} اسپرم\n\n"
        )
    await m.reply(txt)



async def hire_worker(m: Message):
    try:
        cid = int(m.text.split()[1])
    except:
        return await m.reply("Usage: /hire [شماره شرکت] (شماره‌ها رو از /mycompanies ببین)")
    row = c.execute("SELECT owner_id,name,workers,workers_bought FROM owned_companies WHERE id=? AND chat_id=?", (cid, m.chat.id)).fetchone()
    if not row:
        return await m.reply("❌ همچین شرکتی پیدا نشد.")
    owner_id, name, workers, bought = row
    if owner_id != m.from_user.id:
        return await m.reply("❌ این شرکت مال تو نیست!")
    if bought >= workers:
        return await m.reply(f"❌ همه‌ی {workers} یار این شرکت رو قبلاً خریدی!")
    sperm = get_sperm(m.chat.id, m.from_user.id)
    if sperm < COMPANY_WORKER_COST:
        return await m.reply(f"❌ برای خرید یار به {COMPANY_WORKER_COST} اسپرم نیاز داری.")
    c.execute("UPDATE users SET sperm=sperm-? WHERE chat_id=? AND user_id=?", (COMPANY_WORKER_COST, m.chat.id, m.from_user.id))
    c.execute("UPDATE owned_companies SET workers_bought=workers_bought+1 WHERE id=?", (cid,))
    db.commit()
    await m.reply(f"✅ یه یار از «{name}» خریدی! ({bought+1}/{workers})\n🔫 برای فرستادنش به یه نبرد مافیا که توش هستی: /useyar")


@dp.message(Command("useyar"))
async def use_yar(m: Message):
    membership = find_active_membership(m.chat.id, m.from_user.id)
    if not membership:
        return await m.reply("❌ الان توی هیچ نبرد مافیای فعالی نیستی! اول با دکمه‌ی تیم وارد یه نبرد (/mafia یا /mafia2) شو.")
    kind, bid, team = membership
    company = c.execute(
        "SELECT id,name FROM owned_companies WHERE chat_id=? AND owner_id=? AND workers_bought>workers_used_mafia LIMIT 1",
        (m.chat.id, m.from_user.id)
    ).fetchone()
    if not company:
        return await m.reply("❌ هیچ یارِ آماده‌ای نداری! اول با /hire یار بخر.")
    cid, cname = company
    ally_name = random.choice(ALLY_NAME_POOL)
    table = "mafia_members" if kind == "mafia" else "mafia2_members"
    fake_uid = -(cid * 1000000 + random.randint(1, 999999))
    c.execute(f"INSERT INTO {table}(battle_id,user_id,name,team,is_ally) VALUES(?,?,?,?,1)", (bid, fake_uid, ally_name, team))
    c.execute("UPDATE owned_companies SET workers_used_mafia=workers_used_mafia+1 WHERE id=?", (cid,))
    db.commit()
    await m.reply(f"🔫 «{ally_name}» از «{cname}» مخفیانه وارد تیمت شد!\n(این یار سهمی از جایزه نمی‌بره، فقط تعداد تیمت رو زیاد می‌کنه)")


@dp.message(Command("cashout"))
async def cashout_company(m: Message):
    try:
        cid = int(m.text.split()[1])
    except:
        return await m.reply("Usage: /cashout [شماره شرکت] (شماره‌ها رو از /mycompanies ببین)")
    row = c.execute("SELECT owner_id,name,value,party FROM owned_companies WHERE id=? AND chat_id=?", (cid, m.chat.id)).fetchone()
    if not row:
        return await m.reply("❌ همچین شرکتی پیدا نشد.")
    owner_id, name, value, party = row
    if owner_id != m.from_user.id:
        return await m.reply("❌ این شرکت مال تو نیست!")
    cashed = value // 2
    if cashed <= 0:
        return await m.reply("❌ ارزش شرکت خیلی کمه که چیزی نقد بشه.")
    c.execute("UPDATE owned_companies SET value=value-? WHERE id=?", (cashed, cid))
    c.execute("UPDATE users SET sperm=sperm+? WHERE chat_id=? AND user_id=?", (cashed, m.chat.id, m.from_user.id))
    db.commit()
    if party in COINS:
        party_company_event(m.chat.id, party, name, cashed, False)
    await m.reply(f"🧬 نصف ارزش «{name}» نقد شد!\n💰 {cashed} اسپرم به حسابت اضافه شد.\n📉 ارزش باقی‌مونده‌ی شرکت: {value-cashed} اسپرم\n(برای تبدیل به سانت: /tocent)")


async def company_dividend_loop(bot):
    while True:
        await asyncio.sleep(300)  # هر ۵ دقیقه چک می‌کنه کدوم شرکت باید سود بده
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
                await bot.send_message(owner_id, f"📈 سود روزانه‌ی شرکتت «{name}»!\n🧬 {income} اسپرم به حسابت اضافه شد.")
            except:
                pass
# ================== پایان کمپانی کیر ==================

# ===== خرید و دیدن توکن =====
@dp.message(Command("token", "tokens"))
async def token_info(m: Message):
    user(m.chat.id, m.from_user.id, m.from_user.full_name)
    size_cm = get_size(m.chat.id, m.from_user.id)
    await m.reply(
        f"🎟 توکن‌های تو: {get_tokens(m.chat.id, m.from_user.id)}\n\n"
        f"💰 قیمت هر توکن الان: {token_price(size_cm)} سانت ({int(TOKEN_PRICE_PCT*100)}٪ سایزت — سایزت الان {size_cm} سانته)\n"
        f"🛒 /buytoken [تعداد] — خرید (حداکثر {TOKEN_MAX_BUY} تا تو هر خرید)\n\n"
        "🎮 هر دست /box و /climb و /bj ۱ توکن می‌خواد.\n"
        f"⚔️ برنده‌ی دوئل با {int(DUEL_TOKEN_CHANCE*100)}٪ شانس یه توکن هم می‌گیره."
    )

@dp.message(Command("buytoken", "buytokens"))
async def buy_token(m: Message):
    uid, chat_id = m.from_user.id, m.chat.id
    user(chat_id, uid, m.from_user.full_name)
    args = m.text.split()[1:]
    if not args:
        n = 1
    elif args[0].isdigit():
        n = int(args[0])
    else:
        return await m.reply("استفاده: /buytoken [تعداد]  (مثلاً /buytoken 3)")
    if n < 1 or n > TOKEN_MAX_BUY:
        return await m.reply(f"❌ تعداد باید بین ۱ تا {TOKEN_MAX_BUY} باشه.")
    size_cm = get_size(chat_id, uid)
    price = token_price(size_cm)
    total = price * n
    if size_cm < total:
        return await m.reply(f"❌ سانت کافی نداری. {n} توکن = {total} سانت (هر توکن {price}) ولی سایزت {size_cm} سانته.")
    c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?", (total, chat_id, uid))
    db.commit()
    add_tokens(chat_id, uid, n)
    await m.reply(
        f"✅ {n} توکن خریدی!\n"
        f"💸 {total} سانت کم شد (هر توکن {price} سانت)\n"
        f"🎟 توکن‌هات: {get_tokens(chat_id, uid)} | 📏 سایزت: {get_size(chat_id, uid)}"
    )

# ===== مینی‌گیم: جعبه‌ی شانس 🎁 =====
# - /box [مبلغ] → ۴ تا جعبه‌ی بسته میاد؛ یکی رو انتخاب می‌کنی
# - تو هر دور یه جعبه‌ی 💎 (۳ برابر شرط)، یه 🔄 (شرط برمی‌گرده) و دوتا 💣 (شرط می‌سوزه) هست
# - میانگین برد = ۱ برابر شرط (نه تورم می‌سازه نه سانت می‌خوره)
# - سانت فقط لحظه‌ی انتخاب کم/زیاد می‌شه؛ اگه بازی نیمه‌کاره بمونه هیچی از دست نمیری
BOX_MAX_BET = 100
BOX_PAYOUTS = [0, 0, 1, 3]
BOX_TTL = 120
BOX_EMOJI = {0: "💣", 1: "🔄", 3: "💎"}
BOX_GAMES = {}  # gid -> {chat, uid, bet, ts}

@dp.message(Command("box"))
async def box_start(m: Message):
    if m.chat.type == "private":
        return await m.reply("❌ این بازی رو باید تو گروه بزنی.")
    args = m.text.split()[1:]
    if not args or not args[0].isdigit():
        return await m.reply(f"🎁 جعبه‌ی شانس\n\nاستفاده: /box [مبلغ شرط]\n(حداکثر {BOX_MAX_BET} سانت)\n\n"
                             "۴ تا جعبه هست: 💎 (۳ برابر) | 🔄 (شرطت برمی‌گرده) | 💣💣 (شرط می‌سوزه)\n\n🎟 ورودی: ۱ توکن (/buytoken)")
    bet = int(args[0])
    uid = m.from_user.id
    user(m.chat.id, uid, m.from_user.full_name)
    if bet < 1 or bet > BOX_MAX_BET:
        return await m.reply(f"❌ شرط باید بین ۱ تا {BOX_MAX_BET} سانت باشه.")
    if get_size(m.chat.id, uid) < bet:
        return await m.reply("❌ سانت کافی نداری.")
    if not take_token(m.chat.id, uid):
        return await m.reply(no_token_text(m.chat.id, uid))
    log_play(m.chat.id, uid, "game")
    now = int(time.time())
    for k in [k for k, g in BOX_GAMES.items() if now - g["ts"] > BOX_TTL]:
        BOX_GAMES.pop(k, None)
    gid = str(random.randint(100000, 999999))
    while gid in BOX_GAMES:
        gid = str(random.randint(100000, 999999))
    BOX_GAMES[gid] = {"chat": m.chat.id, "uid": uid, "bet": bet, "ts": now}
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🎁", callback_data=f"box:{uid}:{gid}:{i}") for i in range(len(BOX_PAYOUTS))
    ]])
    await m.reply(
        f"🎁 جعبه‌ی شانس — {m.from_user.full_name}\n"
        f"💰 شرط: {bet} سانت | 🎟 ۱ توکن خرج شد (باقی: {get_tokens(m.chat.id, uid)})\n\n"
        f"یه جعبه انتخاب کن! ({BOX_TTL//60} دقیقه وقت داری)\n"
        f"💎 ×۳ | 🔄 ×۱ | 💣 ×۰ (دوتا)",
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith("box:"))
async def box_pick(q: CallbackQuery):
    parts = q.data.split(":")
    if len(parts) != 4:
        return await q.answer(NAV_LEGACY_MSG, show_alert=True)
    _, viewer_id, gid, idx = parts
    if not await nav_guard(q, int(viewer_id)):
        return
    g = BOX_GAMES.pop(gid, None)  # pop = هر بازی فقط یه بار قابل انتخابه
    if not g or g["chat"] != q.message.chat.id:
        return await q.answer("⌛️ این بازی تموم شده یا منقضی شده.", show_alert=True)
    uid, bet = g["uid"], g["bet"]
    if int(time.time()) - g["ts"] > BOX_TTL:
        await q.message.edit_text("⌛️ وقت انتخابت تموم شد؛ چیزی کم نشد. دوباره /box بزن.", reply_markup=None)
        return await q.answer()
    if get_size(q.message.chat.id, uid) < bet:
        await q.message.edit_text("❌ الان سانت کافی برای این شرط نداری؛ بازی لغو شد.", reply_markup=None)
        return await q.answer()
    picked = int(idx)
    boxes = BOX_PAYOUTS[:]
    random.shuffle(boxes)
    mult = boxes[picked]
    delta = bet * mult - bet
    c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?", (delta, q.message.chat.id, uid))
    db.commit()
    row = " ".join(f"[{BOX_EMOJI[b]}]" if i == picked else BOX_EMOJI[b] for i, b in enumerate(boxes))
    if mult == 3:
        res = f"💎 جکپات! +{delta} سانت"
    elif mult == 1:
        res = "🔄 شرطت برگشت، نه بردی نه باختی."
    else:
        res = f"💣 بوووم! {bet} سانت سوخت."
    await q.message.edit_text(
        f"🎁 جعبه‌ی شانس — {get_name(q.message.chat.id, uid)}\n\n{row}\n\n{res}\n"
        f"📏 سانت فعلی: {get_size(q.message.chat.id, uid)}",
        reply_markup=None
    )
    await q.answer()

# ===== مینی‌گیم: نردبان 🪜 =====
# - /climb [مبلغ] → شرط رو می‌ذاری و از پایین نردبان شروع می‌کنی
# - هر بار «برو بالاتر» رو بزنی ۷۵٪ شانس داری یه پله بری بالا و ضریبت بزرگ‌تر بشه؛ ۲۵٪ می‌افتی و شرط می‌سوزه
# - هر لحظه می‌تونی «برداشت» رو بزنی و پول رو برداری؛ رسیدن به پله‌ی ۶ خودکار برداشت می‌شه
# - ضریب هر پله = (۱/۰.۷۵)^پله، پس میانگین برد ≈ ۱ برابر شرطه (اقتصاد رو خراب نمی‌کنه)
# - شرط همون اول کم می‌شه (تا با چندتا بازی همزمان نشه تقلب کرد)؛ ذخیره تو دیتابیسه، پس با ریستارت ربات هم گم نمی‌شه
# - اگه ۳ دقیقه هیچ حرکتی نکنی، بازی خودکار برداشت می‌شه (پله‌ی ۰ = شرط برمی‌گرده)
CLIMB_MAX_BET = 100
CLIMB_P = 0.75
CLIMB_MAX_STEPS = 6
CLIMB_TTL = 180

c.execute("""CREATE TABLE IF NOT EXISTS climb_games(
    chat_id INTEGER,
    user_id INTEGER,
    bet INTEGER,
    step INTEGER DEFAULT 0,
    ts INTEGER,
    msg_id INTEGER DEFAULT 0,
    PRIMARY KEY(chat_id, user_id)
)""")
db.commit()

def climb_mult(step):
    return (1 / CLIMB_P) ** step

def climb_payout(bet, step):
    return bet if step <= 0 else int(bet * climb_mult(step))

def climb_load(chat_id, uid):
    return c.execute("SELECT bet,step,ts,msg_id FROM climb_games WHERE chat_id=? AND user_id=?", (chat_id, uid)).fetchone()

def climb_cash(chat_id, uid, bet, step):
    payout = climb_payout(bet, step)
    c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?", (payout, chat_id, uid))
    c.execute("DELETE FROM climb_games WHERE chat_id=? AND user_id=?", (chat_id, uid))
    db.commit()
    return payout

def climb_view(name, bet, step, viewer_id):
    lines = []
    for i in range(CLIMB_MAX_STEPS, 0, -1):
        mark = "🧗" if i == step else ("✅" if i < step else "▫️")
        lines.append(f"{mark} پله {i}: ×{climb_mult(i):.1f}")
    if step == 0:
        lines.append("🧗 پایین نردبان")
    txt = (
        f"🪜 نردبان — {name}\n"
        f"💰 شرط: {bet} سانت\n\n"
        + "\n".join(lines) +
        f"\n\n🎯 شانس هر پله: {int(CLIMB_P*100)}٪"
    )
    rows = [[InlineKeyboardButton(text="⬆️ برو بالاتر", callback_data=f"clb:{viewer_id}:up")]]
    if step >= 1:
        rows.append([InlineKeyboardButton(
            text=f"💰 برداشت ({climb_payout(bet, step)} سانت)", callback_data=f"clb:{viewer_id}:cash")])
    return txt, InlineKeyboardMarkup(inline_keyboard=rows)

@dp.message(Command("climb"))
async def climb_start(m: Message):
    if m.chat.type == "private":
        return await m.reply("❌ این بازی رو باید تو گروه بزنی.")
    args = m.text.split()[1:]
    if not args or not args[0].isdigit():
        return await m.reply(
            f"🪜 نردبان\n\nاستفاده: /climb [مبلغ شرط]\n(حداکثر {CLIMB_MAX_BET} سانت)\n\n"
            f"هر پله {int(CLIMB_P*100)}٪ شانس داره و ضریبت بزرگ‌تر می‌شه، ولی با ۲۵٪ می‌افتی و همه‌چی می‌سوزه. "
            f"هر وقت خواستی «برداشت» رو بزن!\n\n🎟 ورودی: ۱ توکن (/buytoken)"
        )
    bet = int(args[0])
    uid, chat_id = m.from_user.id, m.chat.id
    user(chat_id, uid, m.from_user.full_name)
    now = int(time.time())
    g = climb_load(chat_id, uid)
    if g:
        if now - g[2] > CLIMB_TTL:
            payout = climb_cash(chat_id, uid, g[0], g[1])
            await m.reply(f"⌛️ نردبان قبلیت منقضی شد و خودکار برداشت شد: {payout} سانت.")
        else:
            return await m.reply("❌ یه نردبان نیمه‌کاره داری! اول همون رو تموم کن.")
    if bet < 1 or bet > CLIMB_MAX_BET:
        return await m.reply(f"❌ شرط باید بین ۱ تا {CLIMB_MAX_BET} سانت باشه.")
    if get_size(chat_id, uid) < bet:
        return await m.reply("❌ سانت کافی نداری.")
    if not take_token(chat_id, uid):
        return await m.reply(no_token_text(chat_id, uid))
    log_play(chat_id, uid, "game")
    c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?", (bet, chat_id, uid))
    c.execute("INSERT OR REPLACE INTO climb_games(chat_id,user_id,bet,step,ts,msg_id) VALUES(?,?,?,0,?,0)", (chat_id, uid, bet, now))
    db.commit()
    txt, kb = climb_view(m.from_user.full_name, bet, 0, uid)
    try:
        sent = await m.reply(txt, reply_markup=kb)
    except Exception:
        climb_cash(chat_id, uid, bet, 0)  # ارسال خراب شد: شرط برگرده
        add_tokens(chat_id, uid, 1)       # توکن هم برگرده
        raise
    c.execute("UPDATE climb_games SET msg_id=? WHERE chat_id=? AND user_id=?", (sent.message_id, chat_id, uid))
    db.commit()

@dp.callback_query(F.data.startswith("clb:"))
async def climb_press(q: CallbackQuery):
    parts = q.data.split(":")
    if len(parts) != 3:
        return await q.answer(NAV_LEGACY_MSG, show_alert=True)
    _, viewer_id, action = parts
    viewer_id = int(viewer_id)
    if not await nav_guard(q, viewer_id):
        return
    chat_id = q.message.chat.id
    g = climb_load(chat_id, viewer_id)
    if not g or g[3] != q.message.message_id:
        return await q.answer("⌛️ این بازی تموم شده.", show_alert=True)
    bet, step, ts, _mid = g
    name = get_name(chat_id, viewer_id)
    if int(time.time()) - ts > CLIMB_TTL:
        payout = climb_cash(chat_id, viewer_id, bet, step)
        await q.message.edit_text(
            f"⌛️ نردبان — {name}\n\nوقتت تموم شد و خودکار برداشت شد: {payout} سانت\n📏 سانت فعلی: {get_size(chat_id, viewer_id)}",
            reply_markup=None)
        return await q.answer()
    if action == "cash":
        if step < 1:
            return await q.answer("اول یه پله برو بالا!", show_alert=True)
        payout = climb_cash(chat_id, viewer_id, bet, step)
        await q.message.edit_text(
            f"🪜 نردبان — {name}\n\n💰 برداشت کردی! {payout} سانت (پله‌ی {step}، ×{climb_mult(step):.1f})\n"
            f"{'📈 سود' if payout > bet else '📉 تغییر'}: {payout - bet:+d} سانت\n"
            f"📏 سانت فعلی: {get_size(chat_id, viewer_id)}",
            reply_markup=None)
        return await q.answer()
    if action != "up":
        return await q.answer()
    if random.random() < CLIMB_P:
        step += 1
        if step >= CLIMB_MAX_STEPS:
            payout = climb_cash(chat_id, viewer_id, bet, step)
            await q.message.edit_text(
                f"🪜 نردبان — {name}\n\n🏆 به قله رسیدی! (×{climb_mult(step):.1f})\n"
                f"💰 {payout} سانت برداشت شد ({payout - bet:+d})\n"
                f"📏 سانت فعلی: {get_size(chat_id, viewer_id)}",
                reply_markup=None)
            return await q.answer("🏆 قله!")
        c.execute("UPDATE climb_games SET step=?, ts=? WHERE chat_id=? AND user_id=?", (step, int(time.time()), chat_id, viewer_id))
        db.commit()
        txt, kb = climb_view(name, bet, step, viewer_id)
        await q.message.edit_text(txt, reply_markup=kb)
        return await q.answer(f"⬆️ پله‌ی {step}!")
    c.execute("DELETE FROM climb_games WHERE chat_id=? AND user_id=?", (chat_id, viewer_id))
    db.commit()
    await q.message.edit_text(
        f"🪜 نردبان — {name}\n\n💥 از پله‌ی {step + 1} افتادی! {bet} سانت سوخت.\n"
        f"📏 سانت فعلی: {get_size(chat_id, viewer_id)}",
        reply_markup=None)
    await q.answer("💥 افتادی!")

# ===== بازی کارتی: بلک‌جک (۲۱) 🃏 =====
# - /bj [مبلغ] → دو کارت می‌گیری، دیلر هم دو کارت (یکیش مخفی)
# - «🃏 کارت بگیر» یا «✋ بایست»؛ نزدیک‌تر به ۲۱ برنده‌ست، بیشتر از ۲۱ = باخت
# - دیلر تا ۱۷ کارت می‌گیره و رو ۱۷ می‌ایسته
# - برد = ۲ برابر شرط | بلک‌جک (A + ده‌تایی تو دو کارت اول) = ۲.۵ برابر | مساوی = شرط برمی‌گرده
# - شرط همون اول کم می‌شه و بازی تو دیتابیسه (با ریستارت ربات گم نمی‌شه)؛ ۳ دقیقه بی‌حرکتی = خودکار «بایست»
# - ساده‌ست: دابل و اسپلیت نداره
BJ_MAX_BET = 100
BJ_TTL = 180
BJ_RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
BJ_SUITS = ["♠", "♥", "♦", "♣"]

c.execute("""CREATE TABLE IF NOT EXISTS blackjack_games(
    chat_id INTEGER,
    user_id INTEGER,
    bet INTEGER,
    player TEXT,
    dealer TEXT,
    deck TEXT,
    ts INTEGER,
    msg_id INTEGER DEFAULT 0,
    PRIMARY KEY(chat_id, user_id)
)""")
db.commit()

def bj_new_deck():
    deck = [r + s_ for r in BJ_RANKS for s_ in BJ_SUITS]
    random.shuffle(deck)
    return deck

def bj_val(hand):
    total, aces = 0, 0
    for card in hand:
        r = card[:-1]
        if r == "A":
            total += 11
            aces += 1
        elif r in ("J", "Q", "K"):
            total += 10
        else:
            total += int(r)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total

def bj_is_blackjack(hand):
    return len(hand) == 2 and bj_val(hand) == 21

def bj_load(chat_id, uid):
    row = c.execute(
        "SELECT bet,player,dealer,deck,ts,msg_id FROM blackjack_games WHERE chat_id=? AND user_id=?",
        (chat_id, uid)
    ).fetchone()
    if not row:
        return None
    bet, player, dealer, deck, ts, msg_id = row
    return {"bet": bet, "player": player.split(","), "dealer": dealer.split(","),
            "deck": deck.split(",") if deck else [], "ts": ts, "msg_id": msg_id}

def bj_save(chat_id, uid, g):
    c.execute(
        "UPDATE blackjack_games SET player=?, dealer=?, deck=?, ts=? WHERE chat_id=? AND user_id=?",
        (",".join(g["player"]), ",".join(g["dealer"]), ",".join(g["deck"]), int(time.time()), chat_id, uid)
    )
    db.commit()

def bj_settle(chat_id, uid, payout):
    """پول برنده رو بده و بازی رو پاک کن."""
    if payout:
        c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?", (payout, chat_id, uid))
    c.execute("DELETE FROM blackjack_games WHERE chat_id=? AND user_id=?", (chat_id, uid))
    db.commit()

def bj_render(name, g, reveal, note=""):
    pv = bj_val(g["player"])
    if reveal:
        dealer_txt = f"{' '.join(g['dealer'])} ({bj_val(g['dealer'])})"
    else:
        dealer_txt = f"{g['dealer'][0]} 🂠"
    txt = (
        f"🃏 بلک‌جک — {name}\n"
        f"💰 شرط: {g['bet']} سانت\n\n"
        f"🧑 دست تو: {' '.join(g['player'])} ({pv})\n"
        f"🎩 دست دیلر: {dealer_txt}"
    )
    if note:
        txt += f"\n\n{note}"
    return txt

def bj_kb(viewer_id):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🃏 کارت بگیر", callback_data=f"bjk:{viewer_id}:hit"),
        InlineKeyboardButton(text="✋ بایست", callback_data=f"bjk:{viewer_id}:stand"),
    ]])

def bj_finish(chat_id, uid, g, name):
    """دیلر بازی می‌کنه، نتیجه حساب و پرداخت می‌شه. خروجی: متن نهایی."""
    bet = g["bet"]
    pv = bj_val(g["player"])
    while bj_val(g["dealer"]) < 17:
        g["dealer"].append(g["deck"].pop())
    dv = bj_val(g["dealer"])
    if dv > 21:
        payout, note = bet * 2, f"🏆 دیلر بیشتر از ۲۱ شد! بردی: +{bet} سانت"
    elif pv > dv:
        payout, note = bet * 2, f"🏆 بردی! +{bet} سانت"
    elif pv == dv:
        payout, note = bet, "🤝 مساوی — شرطت برگشت."
    else:
        payout, note = 0, f"💥 باختی! {bet} سانت سوخت."
    bj_settle(chat_id, uid, payout)
    return bj_render(name, g, True, note + f"\n📏 سانت فعلی: {get_size(chat_id, uid)}")

@dp.message(Command("bj", "blackjack"))
async def bj_start(m: Message):
    if m.chat.type == "private":
        return await m.reply("❌ این بازی رو باید تو گروه بزنی.")
    args = m.text.split()[1:]
    if not args or not args[0].isdigit():
        return await m.reply(
            f"🃏 بلک‌جک (۲۱)\n\nاستفاده: /bj [مبلغ شرط]\n(حداکثر {BJ_MAX_BET} سانت)\n\n"
            "به ۲۱ نزدیک شو ولی ردش نکن! دیلر تا ۱۷ کارت می‌گیره.\n"
            "برد ×۲ | بلک‌جک ×۲.۵ | مساوی = شرطت برمی‌گرده\n\n🎟 ورودی: ۱ توکن (/buytoken)"
        )
    bet = int(args[0])
    uid, chat_id = m.from_user.id, m.chat.id
    name = m.from_user.full_name
    user(chat_id, uid, name)
    g = bj_load(chat_id, uid)
    if g:
        if int(time.time()) - g["ts"] > BJ_TTL:
            res = bj_finish(chat_id, uid, g, name)
            await m.reply("⌛️ بازی قبلیت منقضی شد و خودکار «بایست» زده شد:\n\n" + res)
        else:
            return await m.reply("❌ یه دست نیمه‌کاره داری! اول همون رو تموم کن.")
    if bet < 1 or bet > BJ_MAX_BET:
        return await m.reply(f"❌ شرط باید بین ۱ تا {BJ_MAX_BET} سانت باشه.")
    if get_size(chat_id, uid) < bet:
        return await m.reply("❌ سانت کافی نداری.")
    if not take_token(chat_id, uid):
        return await m.reply(no_token_text(chat_id, uid))
    log_play(chat_id, uid, "game")
    deck = bj_new_deck()
    player = [deck.pop(), deck.pop()]
    dealer = [deck.pop(), deck.pop()]
    c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?", (bet, chat_id, uid))
    c.execute(
        "INSERT OR REPLACE INTO blackjack_games(chat_id,user_id,bet,player,dealer,deck,ts,msg_id) VALUES(?,?,?,?,?,?,?,0)",
        (chat_id, uid, bet, ",".join(player), ",".join(dealer), ",".join(deck), int(time.time()))
    )
    db.commit()
    g = {"bet": bet, "player": player, "dealer": dealer, "deck": deck}
    # بلک‌جک طبیعی (یا دیلر)، همون اول تموم می‌شه
    if bj_is_blackjack(player) or bj_is_blackjack(dealer):
        if bj_is_blackjack(player) and bj_is_blackjack(dealer):
            payout, note = bet, "🤝 هر دو بلک‌جک — شرطت برگشت."
        elif bj_is_blackjack(player):
            payout = int(bet * 2.5)
            note = f"🂡 بلک‌جک! +{payout - bet} سانت"
        else:
            payout, note = 0, f"💥 دیلر بلک‌جک زد! {bet} سانت سوخت."
        bj_settle(chat_id, uid, payout)
        return await m.reply(bj_render(name, g, True, note + f"\n📏 سانت فعلی: {get_size(chat_id, uid)}"))
    try:
        sent = await m.reply(bj_render(name, g, False), reply_markup=bj_kb(uid))
    except Exception:
        bj_settle(chat_id, uid, bet)  # ارسال خراب شد: شرط برگرده
        add_tokens(chat_id, uid, 1)   # توکن هم برگرده
        raise
    c.execute("UPDATE blackjack_games SET msg_id=? WHERE chat_id=? AND user_id=?", (sent.message_id, chat_id, uid))
    db.commit()

@dp.callback_query(F.data.startswith("bjk:"))
async def bj_press(q: CallbackQuery):
    parts = q.data.split(":")
    if len(parts) != 3:
        return await q.answer(NAV_LEGACY_MSG, show_alert=True)
    _, viewer_id, action = parts
    viewer_id = int(viewer_id)
    if not await nav_guard(q, viewer_id):
        return
    chat_id = q.message.chat.id
    g = bj_load(chat_id, viewer_id)
    if not g or g["msg_id"] != q.message.message_id:
        return await q.answer("⌛️ این دست تموم شده.", show_alert=True)
    name = get_name(chat_id, viewer_id)
    if int(time.time()) - g["ts"] > BJ_TTL:
        res = bj_finish(chat_id, viewer_id, g, name)
        await q.message.edit_text("⌛️ وقتت تموم شد؛ خودکار «بایست» زده شد.\n\n" + res, reply_markup=None)
        return await q.answer()
    if action == "hit":
        g["player"].append(g["deck"].pop())
        pv = bj_val(g["player"])
        if pv > 21:
            bj_settle(chat_id, viewer_id, 0)
            await q.message.edit_text(
                bj_render(name, g, True, f"💥 بیشتر از ۲۱ شد! {g['bet']} سانت سوخت.\n📏 سانت فعلی: {get_size(chat_id, viewer_id)}"),
                reply_markup=None)
            return await q.answer("💥 باختی!")
        if pv == 21:
            await q.message.edit_text(bj_finish(chat_id, viewer_id, g, name), reply_markup=None)
            return await q.answer("۲۱!")
        bj_save(chat_id, viewer_id, g)
        await q.message.edit_text(bj_render(name, g, False), reply_markup=bj_kb(viewer_id))
        return await q.answer()
    if action == "stand":
        await q.message.edit_text(bj_finish(chat_id, viewer_id, g, name), reply_markup=None)
        return await q.answer()
    await q.answer()

# ===== فعالیت بازیکنا (برای پخش مالیات) =====
# هر پیام تو گروه حساب می‌شه؛ «فعال‌ترین‌ها» = بیشترین پیام تو ACTIVITY_WINDOW_DAYS روز اخیر (فقط کسایی که بازیکن هستن)
from aiogram import BaseMiddleware

c.execute("""CREATE TABLE IF NOT EXISTS activity(
    chat_id INTEGER,
    user_id INTEGER,
    day INTEGER,
    cnt INTEGER DEFAULT 0,
    PRIMARY KEY(chat_id, user_id, day)
)""")
db.commit()

def record_activity(chat_id, uid):
    day = int(time.time() // 86400)
    c.execute(
        "INSERT INTO activity(chat_id,user_id,day,cnt) VALUES(?,?,?,1) "
        "ON CONFLICT(chat_id,user_id,day) DO UPDATE SET cnt=cnt+1",
        (chat_id, uid, day)
    )
    db.commit()

class ActivityMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        try:
            if (isinstance(event, Message) and event.chat.type in ("group", "supergroup")
                    and event.from_user and not event.from_user.is_bot):
                record_activity(event.chat.id, event.from_user.id)
        except Exception:
            logger.exception("activity record failed")
        return await handler(event, data)

dp.message.outer_middleware(ActivityMiddleware())

def top_active(chat_id, exclude_uid=0, limit=TAX_RECIPIENTS):
    since = int(time.time() // 86400) - ACTIVITY_WINDOW_DAYS + 1
    rows = c.execute(
        "SELECT a.user_id, SUM(a.cnt) AS n FROM activity a "
        "JOIN users u ON u.chat_id=a.chat_id AND u.user_id=a.user_id "
        "WHERE a.chat_id=? AND a.day>=? AND a.user_id!=? "
        "GROUP BY a.user_id ORDER BY n DESC, a.user_id LIMIT ?",
        (chat_id, since, exclude_uid, limit)
    ).fetchall()
    return [(r[0], r[1]) for r in rows]

def distribute_tax(chat_id, payer_uid, amount):
    """مالیات رو بین فعال‌ترین‌ها (به‌جز پرداخت‌کننده) پخش می‌کنه؛ commit با خود صدازننده‌ست.
    خروجی: لیست (user_id, سهم). اگه فعالی نباشه لیست خالیه (مالیات می‌سوزه)."""
    recips = [u for u, _ in top_active(chat_id, payer_uid)]
    if not recips or amount <= 0:
        return []
    share, rem = divmod(amount, len(recips))
    out = []
    for i, uid in enumerate(recips):
        part = share + (rem if i == 0 else 0)  # باقی‌مونده‌ی تقسیم می‌ره به فعال‌ترین
        if part > 0:
            c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?", (part, chat_id, uid))
            out.append((uid, part))
    return out

# ===== راه فرار مالیاتی: لاگ دوئل‌ها و مینی‌گیم‌ها =====
c.execute("""CREATE TABLE IF NOT EXISTS play_log(
    chat_id INTEGER,
    user_id INTEGER,
    kind TEXT,
    ts INTEGER
)""")
c.execute("CREATE INDEX IF NOT EXISTS idx_play_log ON play_log(chat_id, user_id, kind, ts)")
db.commit()

def log_play(chat_id, uid, kind):
    """kind: 'duel' (دوئل تموم‌شده) یا 'game' (شروع یه مینی‌گیم)"""
    c.execute("INSERT INTO play_log(chat_id,user_id,kind,ts) VALUES(?,?,?,?)", (chat_id, uid, kind, int(time.time())))
    db.commit()

def tax_exempt(chat_id, uid):
    """خروجی: (معافه؟، تعداد دوئل، تعداد بازی) تو TAX_EVASION_WINDOW اخیر."""
    since = int(time.time()) - TAX_EVASION_WINDOW
    def count(kind):
        return c.execute(
            "SELECT COUNT(*) FROM play_log WHERE chat_id=? AND user_id=? AND kind=? AND ts>=?",
            (chat_id, uid, kind, since)
        ).fetchone()[0]
    duels, games = count("duel"), count("game")
    return (duels >= TAX_EVASION_DUELS and games >= TAX_EVASION_GAMES), duels, games

def richest_min_duel(chat_id, uid):
    """اگه uid پولدارترین فرد گروه باشه، حداقل شرط دوئلش (RICHEST_MIN_DUEL_PCT سایزش، گرد به بالا)؛ وگرنه ۰."""
    row = get_richest(chat_id)
    if not row or row[0] != uid or row[1] <= 0:
        return 0
    return max(1, math.ceil(round(get_size(chat_id, uid) * RICHEST_MIN_DUEL_PCT, 6)))  # درصد از سایز واقعی (شرط دوئل با سانته)

def evade_status_text(chat_id, uid):
    ex, nd, ng = tax_exempt(chat_id, uid)
    state = "✅ الان از مالیات ۵٪ معافی!" if ex else "❌ هنوز نرسیدی"
    return (
        f"🕵️ راه فرار مالیاتی: {TAX_EVASION_DUELS} دوئل + {TAX_EVASION_GAMES} مینی‌گیم تو {TAX_EVASION_WINDOW//3600} ساعت اخیر = معافیت از مالیات {int(WEALTH_TAX_PCT*100)}٪ پولدارترین (مالیات مزرعه معافیت نداره)\n"
        f"📈 پیشرفت تو: {nd}/{TAX_EVASION_DUELS} دوئل | {ng}/{TAX_EVASION_GAMES} بازی — {state}"
    )

# ===== مالیات ثروت: هر ۲۴ ساعت ۵٪ سایز پولدارترین فرد گروه =====
c.execute("""CREATE TABLE IF NOT EXISTS wealth_tax(
    chat_id INTEGER PRIMARY KEY,
    last_ts INTEGER
)""")
db.commit()

# ثروت (به سانت) = سایز + اسپرم آزاد و اسپرمِ سرمایه‌گذاری‌شده تو بورس‌های باز (هر SPERM_RATE اسپرم = ۱ سانت)
# تا کسی با نگه داشتن اسپرم یا قایم کردنش تو بورس از مالیات فرار نکنه.
def invested_sperm(chat_id, uid):
    return c.execute(
        "SELECT COALESCE(SUM(ci.amount),0) FROM company_investments ci "
        "JOIN company_rounds cr ON cr.chat_id=ci.chat_id AND cr.round_id=ci.round_id AND cr.status='open' "
        "WHERE ci.chat_id=? AND ci.user_id=?",
        (chat_id, uid)
    ).fetchone()[0]

def net_worth(chat_id, uid):
    return get_size(chat_id, uid) + (get_sperm(chat_id, uid) + invested_sperm(chat_id, uid)) // SPERM_RATE + crypto_value_of(chat_id, uid)

def get_richest(chat_id):
    """خروجی: (user_id, ثروت به سانت) پولدارترین؛ ثروت = سایز + اسپرم (آزاد و بورس) + ارزش کوین‌ها. مساوی بود کم‌ترین user_id."""
    rows = c.execute(
        "SELECT u.user_id, "
        "u.size + (COALESCE(u.sperm,0) + COALESCE((SELECT SUM(ci.amount) FROM company_investments ci "
        "JOIN company_rounds cr ON cr.chat_id=ci.chat_id AND cr.round_id=ci.round_id AND cr.status='open' "
        "WHERE ci.chat_id=u.chat_id AND ci.user_id=u.user_id),0)) / ? AS worth "
        "FROM users u WHERE u.chat_id=?",
        (SPERM_RATE, chat_id)
    ).fetchall()
    if not rows:
        return None
    crypto = crypto_values(chat_id)
    best = max(rows, key=lambda r: (r[1] + crypto.get(r[0], 0), -r[0]))
    return (best[0], best[1] + crypto.get(best[0], 0))

def wealth_tax_amount(size_cm):
    return 0 if size_cm <= 0 else max(1, int(size_cm * WEALTH_TAX_PCT + 0.5))

async def apply_wealth_tax(bot, chat_id):
    row = get_richest(chat_id)
    if not row or row[1] <= 0:
        return
    uid, worth = row
    size_cm = get_size(chat_id, uid)
    free_sperm = get_sperm(chat_id, uid)
    sperm_cm = (free_sperm + invested_sperm(chat_id, uid)) // SPERM_RATE
    coin_cm = crypto_value_of(chat_id, uid)
    exempt, nd, ng = tax_exempt(chat_id, uid)
    if exempt:
        await bot.send_message(
            chat_id,
            f"🕵️ فرار مالیاتی موفق!\n\n"
            f"👑 {get_name(chat_id, uid)} پولدارترین فرد گروهه (ثروت {worth} سانت) ولی تو {TAX_EVASION_WINDOW//3600} ساعت اخیر "
            f"{nd} دوئل و {ng} بازی انجام داد و از مالیات امروز معاف شد.\n\n"
            f"⏳ مالیات بعدی {WEALTH_TAX_INTERVAL//3600} ساعت دیگه"
        )
        return
    tax = wealth_tax_amount(worth)  # ۵٪ کل ثروت (سایز + اسپرم + کوین)
    from_size = min(size_cm, tax)
    rest = tax - from_size
    cm_from_sperm = min(free_sperm // SPERM_RATE, rest)  # کمبود رو از اسپرم آزاد برمی‌داریم
    from_sperm = cm_from_sperm * SPERM_RATE
    rest -= cm_from_sperm
    from_coin, sold = 0, []
    if rest > 0 and coin_cm > 0:  # هنوز کمبود هست: کوین‌ها اجباری فروخته می‌شن
        got, sold = liquidate_for_tax(chat_id, uid, rest)
        from_coin = min(got, rest)
        if got > from_coin:  # اضافه‌ی فروش به سایز برمی‌گرده
            c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?", (got - from_coin, chat_id, uid))
    paid = from_size + cm_from_sperm + from_coin
    if paid <= 0:
        return
    c.execute(
        "UPDATE users SET size=size-?, sperm=sperm-? WHERE chat_id=? AND user_id=?",
        (from_size, from_sperm, chat_id, uid)
    )
    payouts = distribute_tax(chat_id, uid, paid)
    if sold:
        add_news(chat_id, "⚖️ فروش اجباری برای مالیات: " + "، ".join(
            f"{fmt_qty(q)} {COINS[sym]['emoji']} {sym}" for sym, q, _g in sold) + f" از {get_name(chat_id, uid)} فروخته شد")
    db.commit()
    if payouts:
        dist = f"\n\n🏆 مالیات بین {len(payouts)} فعال‌ترین بازیکن پخش شد:\n" + "\n".join(
            f"🎁 {get_name(chat_id, u)}: +{amt} سانت" for u, amt in payouts)
    else:
        dist = "\n\n(بازیکن فعالی ثبت نشده بود؛ این بار مالیات سوخت.)"
    src_txt = f"از سایز {from_size} سانت"
    if from_sperm:
        src_txt += f" + از اسپرم {from_sperm} اسپرم"
    if from_coin:
        src_txt += f" + فروش اجباری کوین {from_coin} سانت"
    await bot.send_message(
        chat_id,
        f"🏛 مالیات روزانه!\n\n"
        f"👑 پولدارترین فرد گروه: {get_name(chat_id, uid)}\n"
        f"📏 سایز: {size_cm} سانت | 🧬 اسپرم: ≈ {sperm_cm} سانت | 🪙 کوین: ≈ {coin_cm} سانت\n"
        f"💎 ثروت کل: {worth} سانت\n"
        f"💸 مالیات {int(WEALTH_TAX_PCT*100)}٪: {tax} سانت ({src_txt})"
        f"{dist}\n\n"
        f"⏳ مالیات بعدی {WEALTH_TAX_INTERVAL//3600} ساعت دیگه"
    )

async def wealth_tax_loop(bot):
    while True:
        try:
            now = int(time.time())
            c.execute("DELETE FROM play_log WHERE ts<?", (now - 2 * TAX_EVASION_WINDOW,))
            c.execute("DELETE FROM activity WHERE day<?", (now // 86400 - 30,))
            db.commit()
            chats = [r[0] for r in c.execute("SELECT DISTINCT chat_id FROM users WHERE chat_id<0").fetchall()]
            for chat_id in chats:
                try:
                    row = c.execute("SELECT last_ts FROM wealth_tax WHERE chat_id=?", (chat_id,)).fetchone()
                    if not row:  # اولین بار که گروه دیده می‌شه، تایمر ۲۴ ساعته از همین‌جا شروع می‌شه
                        c.execute("INSERT INTO wealth_tax(chat_id,last_ts) VALUES(?,?)", (chat_id, now))
                        db.commit()
                        continue
                    if now - row[0] >= WEALTH_TAX_INTERVAL:
                        c.execute("UPDATE wealth_tax SET last_ts=? WHERE chat_id=?", (now, chat_id))
                        db.commit()
                        await apply_wealth_tax(bot, chat_id)
                except Exception:
                    logger.exception("wealth tax failed for chat %s", chat_id)
        except Exception:
            logger.exception("wealth_tax_loop error")
        await asyncio.sleep(300)

@dp.message(Command("tax"))
async def tax_info(m: Message):
    if m.chat.type == "private":
        return await m.reply("❌ این دستور رو باید تو گروه بزنی.")
    chat_id = m.chat.id
    row = c.execute("SELECT last_ts FROM wealth_tax WHERE chat_id=?", (chat_id,)).fetchone()
    if row:
        left = WEALTH_TAX_INTERVAL - (int(time.time()) - row[0])
        when = f"{fmt_time(left)} دیگه" if left > 0 else "تا چند دقیقه‌ی دیگه"
    else:
        when = "تایمرش هنوز شروع نشده (تا چند دقیقه‌ی دیگه شروع می‌شه)"
    rich = get_richest(chat_id)
    if rich and rich[1] > 0:
        rich_txt = f"👑 الان پولدارترین: {get_name(chat_id, rich[0])} (ثروت {rich[1]} سانت، با احتساب اسپرم و کوین) → مالیاتش: {wealth_tax_amount(rich[1])} سانت"
        active = top_active(chat_id, rich[0])
    else:
        rich_txt = "👑 هنوز کسی سایز نداره."
        active = top_active(chat_id, 0)
    if active:
        act_txt = "🏆 فعال‌ترین‌ها (گیرنده‌ی مالیات): " + "، ".join(f"{get_name(chat_id, u)} ({n} پیام)" for u, n in active)
    else:
        act_txt = "🏆 هنوز فعالی ثبت نشده (فعالیت از وقتی ربات آپدیت شد شمرده می‌شه)."
    await m.reply(
        "🏛 مالیات\n\n"
        f"💰 مالیات ثروت: هر {WEALTH_TAX_INTERVAL//3600} ساعت {int(WEALTH_TAX_PCT*100)}٪ ثروت پولدارترین فرد گروه کم می‌شه و بین {TAX_RECIPIENTS} فعال‌ترین بازیکن پخش می‌شه.\n"
        f"🧬 ثروت = سایز + اسپرم + کوین (هر {SPERM_RATE} اسپرم = ۱ سانت؛ اسپرم بورس باز و ارزش کوین‌ها با اسلیپیج فروش هم حساب می‌شه). نگه داشتن اسپرم یا کوین راه فرار نیست؛ اگه سانت و اسپرم کافی نباشه کوین‌ها اجباری فروخته می‌شن!\n"
        f"{rich_txt}\n"
        f"{act_txt}\n"
        f"⏳ مالیات بعدی: {when}\n\n"
        f"🌾 مالیات مزرعه: از صفحه‌ی {FARM_TAX_FROM_PAGE} پنل به بعد هر بار کاشتن {FARM_PLANT_TAX} سانت مالیات داره (برای همه قطعیه و معافیت نداره؛ اون هم بین فعال‌ترین‌ها پخش می‌شه).\n"
        f"⚔️ پولدارترین فرد گروه حداقل شرط دوئلش {RICHEST_MIN_DUEL_PCT*100:g}٪ سایزشه.\n"
        f"📊 «فعال» یعنی بیشترین پیام تو گروه تو {ACTIVITY_WINDOW_DAYS} روز اخیر.\n\n"
        f"{evade_status_text(chat_id, m.from_user.id)}"
    )

# ===== بازار کریپتو 🪙 (هسته‌ی محاسبات) =====
# - واحد همه‌چیز سانته: قیمت کوین، کارمزد و مالیات
# - هر کوین «پول رسمی» یه حزبه (BTK بیتکیر، ETK اترکص، BGT بیگتیت). صاحب هر شرکتِ بورس خودش یکی از این حزب‌ها رو انتخاب می‌کنه (/joinparty).
# - بدون تیک رندوم، ولی قیمت خودش حرکت می‌کنه: هر ۱۰ دقیقه «ربات‌های بازارساز» (یکی ارزش‌گرا، یکی روندگرا) با سرمایه‌ی محدود
#   قیمت رو به‌سمت «ارزش واقعی» می‌برن. ارزش واقعی = قیمت پایه × سیکل بازار × حال‌وهوا (اخبار و معامله‌های بزرگ) × قدرت حزب
# - قدرت حزب = جمع ارزش (اسپرم) شرکت‌هایی که ازش حمایت می‌کنن، نسبت به میانگین حزب‌ها (با کف و سقف)؛ هرچی شرکت‌ها موفق‌تر، کوین بهتر
# - هر کوین یه استخر نقدینگی (x*y=k) داره و قیمت = سانتِ استخر ÷ کوینِ استخر.
#   خرید قیمت رو بالا می‌بره، فروش پایین میاره، و تزریق (سانت بی‌کوین به استخر) قیمت رو هل می‌ده.
# - اخبار از اتفاق‌های واقعی بازار ساخته می‌شن (معامله‌ی سنگین، تزریق، ورود شرکت به حزب، نقد کردن شرکت، فروش اجباری مالیات)
# - کارمزد معامله‌ها بین فعال‌ترین بازیکنا پخش می‌شه (مثل مالیات)
# - ارزش کوین‌ها تو ثروتِ مالیات ۵٪ حساب می‌شه؛ اگه سانت و اسپرم برای مالیات کافی نباشه کوین‌ها اجباری فروخته می‌شن
COINS = {
    "BTK": {"emoji": "🟠", "name": "بیتکیر", "party": "حزب بیتکیر", "price": 200.0, "depth": 40000.0, "cycle": (0.10, 9.0, 0.04, 2.7)},
    "ETK": {"emoji": "🔷", "name": "اترکص",  "party": "حزب اترکص",  "price": 50.0,  "depth": 10000.0, "cycle": (0.18, 6.0, 0.07, 1.9)},
    "BGT": {"emoji": "🍈", "name": "بیگتیت", "party": "حزب بیگتیت", "price": 5.0,   "depth": 2000.0,  "cycle": (0.30, 4.0, 0.12, 1.3)},
}
COIN_ALIASES = {"بیتکیر": "BTK", "اترکص": "ETK", "بیگتیت": "BGT"}   # اسم فارسی هم تو دستورها قبول می‌شه
OLD_COIN_NAMES = {"USD": "BTK", "SPM": "ETK", "MOON": "BGT"}      # برای مهاجرت دیتابیس قدیمی
PARTY_SMOOTH = 50          # هرچی بیشتر، قدرت حزب‌ها تو شروع بازی کمتر از هم فاصله می‌گیره
PARTY_EXPONENT = 0.6       # شدت اثر قدرت حزب روی ارزش واقعی کوین (۰ = بی‌اثر)
PARTY_FACTOR_MIN = 0.6     # کف ضریب (حزب بدون شرکت)
PARTY_FACTOR_MAX = 1.8     # سقف ضریب
PARTY_NEWS_KICK = 0.10     # فشار فوریِ «حال‌وهوا» وقتی شرکت به حزب می‌پیونده، ازش می‌ره یا نقد می‌شه
PARTY_SWITCH_COOLDOWN = 24 * 3600  # بعد از انتخاب حزب، تا این مدت نمی‌شه عوضش کرد (اولین انتخاب آزاده)
CRYPTO_NEWS_MOVE_PCT = 0.08      # معامله‌ای که قیمت رو این‌قدر جابه‌جا کنه خبر می‌شه
CRYPTO_SNAPSHOT_INTERVAL = 600   # هر ۱۰ دقیقه: یه قدم حرکت بازار + یه نمودار خودکار تو گروه
CRYPTO_NPC_FRACTION = 0.12       # سرمایه‌ی ربات‌های بازارساز نسبت به استخر (یه‌بار تو شروع)
CRYPTO_NPC_SPEED = 0.30          # هر قدم، ربات «ارزش‌گرا» چند درصد از فاصله‌ی قیمت تا ارزش واقعی رو پر می‌کنه
CRYPTO_NPC_MOMENTUM = 0.35       # ربات «روندگرا» چند درصد از حرکت قبلی رو ادامه می‌ده
CRYPTO_NPC_MAX_MOVE = 0.05       # حداکثر حرکت ربات‌ها تو هر قدم (۱۰ دقیقه)
CRYPTO_SENT_HALFLIFE = 3 * 3600  # نیمه‌عمر اثر اخبار و معامله‌های بزرگ روی «حال‌وهوای بازار»
CRYPTO_NEWS_STEP_PCT = 0.05      # حرکت ۱۰ دقیقه‌ای بیشتر از این = خبر «موج خرید/فروش»
CRYPTO_CHART_HOURS = 6           # نمودار خودکار چند ساعت اخیر رو نشون بده

c.execute("""CREATE TABLE IF NOT EXISTS crypto_pools(
    chat_id INTEGER, coin TEXT, cm REAL, qty REAL,
    PRIMARY KEY(chat_id, coin))""")
c.execute("""CREATE TABLE IF NOT EXISTS crypto_wallet(
    chat_id INTEGER, user_id INTEGER, coin TEXT, qty REAL DEFAULT 0,
    PRIMARY KEY(chat_id, user_id, coin))""")
c.execute("""CREATE TABLE IF NOT EXISTS crypto_prices(
    chat_id INTEGER, coin TEXT, ts INTEGER, price REAL)""")
c.execute("CREATE INDEX IF NOT EXISTS idx_crypto_prices ON crypto_prices(chat_id, coin, ts)")
c.execute("""CREATE TABLE IF NOT EXISTS crypto_news(
    chat_id INTEGER, ts INTEGER, text TEXT)""")
c.execute("""CREATE TABLE IF NOT EXISTS crypto_npc(
    chat_id INTEGER, coin TEXT, cm REAL, qty REAL, sentiment REAL DEFAULT 0, last_price REAL DEFAULT 0, last_step INTEGER DEFAULT 0,
    PRIMARY KEY(chat_id, coin))""")
c.execute("""CREATE TABLE IF NOT EXISTS crypto_settings(
    chat_id INTEGER PRIMARY KEY, auto_chart INTEGER DEFAULT 1)""")
db.commit()

# ---- مهاجرت دیتابیس قدیمی: اسم جدید کوین‌ها + ستون حزب برای شرکت‌ها ----
for _old, _new in OLD_COIN_NAMES.items():
    for _tbl in ("crypto_pools", "crypto_wallet", "crypto_prices", "crypto_npc"):
        c.execute(f"UPDATE OR IGNORE {_tbl} SET coin=? WHERE coin=?", (_new, _old))
for _col in ("party TEXT", "party_changed INTEGER DEFAULT 0"):  # حزب هر شرکت (خالی = بدون حزب) و زمان آخرین انتخاب
    try:
        c.execute(f"ALTER TABLE owned_companies ADD COLUMN {_col}")
    except sqlite3.OperationalError:
        pass
db.commit()

def fmt_price(x):
    return f"{x:,.2f}" if x < 1000 else f"{x:,.0f}"

def fmt_qty(x):
    return f"{x:,.4f}".rstrip("0").rstrip(".") or "0"

def crypto_init(chat_id):
    """استخرها، سرمایه‌ی ربات‌های بازارساز و تنظیمات این گروه رو (اگه نبودن) می‌سازه."""
    now = int(time.time())
    for sym, cfg in COINS.items():
        if not c.execute("SELECT 1 FROM crypto_pools WHERE chat_id=? AND coin=?", (chat_id, sym)).fetchone():
            cm = cfg["depth"]
            c.execute("INSERT INTO crypto_pools(chat_id,coin,cm,qty) VALUES(?,?,?,?)", (chat_id, sym, cm, cm / cfg["price"]))
            c.execute("INSERT INTO crypto_prices(chat_id,coin,ts,price) VALUES(?,?,?,?)", (chat_id, sym, now, cfg["price"]))
        cm, q = pool_get(chat_id, sym)
        c.execute(
            "INSERT OR IGNORE INTO crypto_npc(chat_id,coin,cm,qty,sentiment,last_price,last_step) VALUES(?,?,?,?,0,?,?)",
            (chat_id, sym, cm * CRYPTO_NPC_FRACTION, q * CRYPTO_NPC_FRACTION, cm / q, now)
        )
    c.execute("INSERT OR IGNORE INTO crypto_settings(chat_id,auto_chart) VALUES(?,1)", (chat_id,))
    db.commit()

def pool_get(chat_id, sym):
    return c.execute("SELECT cm,qty FROM crypto_pools WHERE chat_id=? AND coin=?", (chat_id, sym)).fetchone()

def pool_price(chat_id, sym):
    row = pool_get(chat_id, sym)
    return row[0] / row[1] if row and row[1] > 0 else 0.0

def pool_set(chat_id, sym, cm, qty):
    c.execute("UPDATE crypto_pools SET cm=?, qty=? WHERE chat_id=? AND coin=?", (cm, qty, chat_id, sym))
    c.execute("INSERT INTO crypto_prices(chat_id,coin,ts,price) VALUES(?,?,?,?)", (chat_id, sym, int(time.time()), cm / qty))

def add_sentiment(chat_id, sym, delta):
    """اخبار و معامله‌های بزرگ حال‌وهوای بازار رو عوض می‌کنن (به‌مرور محو می‌شه)."""
    c.execute(
        "UPDATE crypto_npc SET sentiment=MAX(-0.5, MIN(0.8, sentiment+?)) WHERE chat_id=? AND coin=?",
        (delta, chat_id, sym)
    )

def cycle_factor(chat_id, sym, t):
    """سیکل بازار: دو موج با دوره‌ی متفاوت (قطعی، نه رندوم). هر گروه فاز خودش رو داره."""
    a1, p1, a2, p2 = COINS[sym]["cycle"]
    h = t / 3600.0
    ph = (abs(chat_id) % 97) / 97 * 2 * math.pi
    return 1 + a1 * math.sin(2 * math.pi * h / p1 + ph) + a2 * math.sin(2 * math.pi * h / p2 + 1.3 + ph)

def fair_value(chat_id, sym, t, sentiment=0.0):
    """ارزش واقعی کوین (سانت) = قیمت پایه × سیکل × حال‌وهوا × قدرت حزب (هرچی شرکت‌های حزب موفق‌تر، ارزش بیشتر)."""
    cfg = COINS[sym]
    return cfg["price"] * cycle_factor(chat_id, sym, t) * (1 + sentiment) * party_factor(chat_id, sym)

def market_step(chat_id):
    """یه قدم حرکت بازار (هر ۱۰ دقیقه): ربات‌های بازارساز قیمت رو به‌سمت ارزش واقعی می‌برن.
    ربات ارزش‌گرا فاصله‌ی قیمت تا ارزش واقعی رو کم می‌کنه؛ ربات روندگرا حرکت قبلی (از جمله حرکت بازیکنا) رو ادامه می‌ده.
    ربات‌ها سرمایه‌ی محدود دارن (سانت و کوین)، پس نمی‌تونن قیمت رو بی‌نهایت هل بدن.
    خروجی: لیست خبرهای این قدم."""
    now = int(time.time())
    news = []
    for sym, cfg in COINS.items():
        pool = pool_get(chat_id, sym)
        npc = c.execute(
            "SELECT cm,qty,sentiment,last_price,last_step FROM crypto_npc WHERE chat_id=? AND coin=?", (chat_id, sym)
        ).fetchone()
        if not pool or not npc:
            continue
        cm, q = pool
        ncm, nq, sent, last_p, last_t = npc
        sent *= 0.5 ** (max(0, now - last_t) / CRYPTO_SENT_HALFLIFE)
        p = cm / q
        fair = fair_value(chat_id, sym, now, sent)
        mom = (p / last_p - 1) if last_p > 0 else 0.0
        target = p + CRYPTO_NPC_SPEED * (fair - p) + CRYPTO_NPC_MOMENTUM * mom * p
        target = min(p * (1 + CRYPTO_NPC_MAX_MOVE), max(p * (1 - CRYPTO_NPC_MAX_MOVE), target))
        k = cm * q
        new_cm = math.sqrt(k * target)
        cm2, q2 = cm, q
        if new_cm > cm:  # ربات‌ها می‌خرن
            need = min(new_cm - cm, ncm)
            if need > 0.01:
                coin_out = q - k / (cm + need)
                cm2, q2 = cm + need, q - coin_out
                ncm -= need
                nq += coin_out
        else:  # ربات‌ها می‌فروشن
            qty_in = min(k / new_cm - q, nq)
            if qty_in > 1e-9:
                cm_out = cm - k / (q + qty_in)
                cm2, q2 = cm - cm_out, q + qty_in
                ncm += cm_out
                nq -= qty_in
        pool_set(chat_id, sym, cm2, q2)
        p_new = cm2 / q2
        c.execute(
            "UPDATE crypto_npc SET cm=?, qty=?, sentiment=?, last_price=?, last_step=? WHERE chat_id=? AND coin=?",
            (ncm, nq, sent, p_new, now, chat_id, sym)
        )
        mv = (p_new / last_p - 1) if last_p > 0 else 0.0
        if abs(mv) >= CRYPTO_NEWS_STEP_PCT and not c.execute(
            "SELECT 1 FROM crypto_news WHERE chat_id=? AND ts>? AND text LIKE ?", (chat_id, now - 3600, f"%موج%{sym}%")
        ).fetchone():
            txt = (f"📈 موج خرید روی {cfg['emoji']} {sym}! قیمت تو ۱۰ دقیقه‌ی گذشته {mv*100:+.1f}٪ بالا رفت (الان {fmt_price(p_new)})"
                   if mv > 0 else
                   f"📉 موج فروش روی {cfg['emoji']} {sym}! قیمت تو ۱۰ دقیقه‌ی گذشته {mv*100:+.1f}٪ افت کرد (الان {fmt_price(p_new)})")
            add_news(chat_id, txt)
            news.append(txt)
    db.commit()
    return news

def wallet_get(chat_id, uid, sym):
    row = c.execute("SELECT qty FROM crypto_wallet WHERE chat_id=? AND user_id=? AND coin=?", (chat_id, uid, sym)).fetchone()
    return row[0] if row else 0.0

def wallet_add(chat_id, uid, sym, delta):
    if delta >= 0:
        c.execute(
            "INSERT INTO crypto_wallet(chat_id,user_id,coin,qty) VALUES(?,?,?,?) "
            "ON CONFLICT(chat_id,user_id,coin) DO UPDATE SET qty=qty+excluded.qty",
            (chat_id, uid, sym, delta)
        )
    else:
        c.execute(
            "UPDATE crypto_wallet SET qty=MAX(0, qty+?) WHERE chat_id=? AND user_id=? AND coin=?",
            (delta, chat_id, uid, sym)
        )

def add_news(chat_id, text):
    c.execute("INSERT INTO crypto_news(chat_id,ts,text) VALUES(?,?,?)", (chat_id, int(time.time()), text))

def change_24h(chat_id, sym):
    now = int(time.time())
    row = c.execute(
        "SELECT price FROM crypto_prices WHERE chat_id=? AND coin=? AND ts<=? ORDER BY ts DESC LIMIT 1",
        (chat_id, sym, now - 86400)
    ).fetchone() or c.execute(
        "SELECT price FROM crypto_prices WHERE chat_id=? AND coin=? ORDER BY ts ASC LIMIT 1", (chat_id, sym)
    ).fetchone()
    cur = pool_price(chat_id, sym)
    return (cur / row[0] - 1) if row and row[0] > 0 else 0.0

def sell_value(chat_id, sym, qty):
    """سانتی که با فروش qty کوین (با اسلیپیج، قبل از کارمزد) به‌دست میاد."""
    row = pool_get(chat_id, sym)
    if not row or qty <= 0:
        return 0
    cm, q = row
    return int(cm - (cm * q) / (q + qty))

def crypto_values(chat_id):
    """ارزش کوین‌های هر بازیکن (به سانت، با اسلیپیج فروش) → {user_id: سانت}"""
    out = {}
    for uid, sym, qty in c.execute("SELECT user_id,coin,qty FROM crypto_wallet WHERE chat_id=? AND qty>0", (chat_id,)).fetchall():
        out[uid] = out.get(uid, 0) + sell_value(chat_id, sym, qty)
    return out

def crypto_value_of(chat_id, uid):
    total = 0
    for sym, qty in c.execute("SELECT coin,qty FROM crypto_wallet WHERE chat_id=? AND user_id=? AND qty>0", (chat_id, uid)).fetchall():
        total += sell_value(chat_id, sym, qty)
    return total

def crypto_buy(chat_id, uid, name, sym, spend):
    """خرید با spend سانت. خروجی: (True, dict) یا (False, پیام خطا)"""
    cfg = COINS[sym]
    size = get_size(chat_id, uid)
    if spend < CRYPTO_MIN_TRADE:
        return False, f"❌ حداقل معامله {CRYPTO_MIN_TRADE} سانته."
    if spend > size:
        return False, "❌ سانت کافی نداری."
    max_spend = max(CRYPTO_MIN_TRADE, int(size * CRYPTO_MAX_TRADE_PCT))
    if spend > max_spend:
        return False, f"❌ تو هر خرید حداکثر {int(CRYPTO_MAX_TRADE_PCT*100)}٪ سایزت ({max_spend} سانت) رو می‌تونی خرج کنی."
    cm, q = pool_get(chat_id, sym)
    fee = max(1, math.ceil(spend * CRYPTO_FEE_PCT))
    net = spend - fee
    p0 = cm / q
    coin_out = q - (cm * q) / (cm + net)
    pool_set(chat_id, sym, cm + net, q - coin_out)
    p1 = (cm + net) / (q - coin_out)
    add_sentiment(chat_id, sym, 0.5 * (p1 / p0 - 1))
    c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?", (spend, chat_id, uid))
    wallet_add(chat_id, uid, sym, coin_out)
    distribute_tax(chat_id, uid, fee)
    news = None
    if p1 / p0 - 1 >= CRYPTO_NEWS_MOVE_PCT:
        news = f"🐋 خرید نهنگی! {name} با {spend} سانت {cfg['emoji']} {sym} خرید و قیمت از {fmt_price(p0)} به {fmt_price(p1)} رسید ({(p1/p0-1)*100:+.1f}٪)"
        add_news(chat_id, news)
    db.commit()
    return True, {"coin_out": coin_out, "p0": p0, "p1": p1, "fee": fee, "spend": spend, "news": news}

def crypto_sell(chat_id, uid, name, sym, qty=None):
    """فروش qty کوین (None = همه). خروجی: (True, dict) یا (False, پیام خطا)"""
    cfg = COINS[sym]
    held = wallet_get(chat_id, uid, sym)
    if held <= 0:
        return False, f"❌ از {sym} چیزی نداری."
    if qty is None or qty > held:
        qty = held
    if qty <= 0:
        return False, "❌ مقدار نامعتبره."
    cm, q = pool_get(chat_id, sym)
    gross = int(cm - (cm * q) / (q + qty))
    if gross < CRYPTO_MIN_TRADE:
        return False, f"❌ این مقدار به {gross} سانت می‌رسه؛ حداقل معامله {CRYPTO_MIN_TRADE} سانته."
    fee = max(1, math.ceil(gross * CRYPTO_FEE_PCT))
    net = gross - fee
    p0 = cm / q
    pool_set(chat_id, sym, cm - gross, q + qty)
    p1 = (cm - gross) / (q + qty)
    add_sentiment(chat_id, sym, 0.5 * (p1 / p0 - 1))
    wallet_add(chat_id, uid, sym, -qty)
    c.execute("UPDATE users SET size=size+? WHERE chat_id=? AND user_id=?", (net, chat_id, uid))
    distribute_tax(chat_id, uid, fee)
    news = None
    if p1 / p0 - 1 <= -CRYPTO_NEWS_MOVE_PCT:
        news = f"📉 فروش سنگین! {name} {fmt_qty(qty)} {cfg['emoji']} {sym} فروخت و قیمت از {fmt_price(p0)} به {fmt_price(p1)} افتاد ({(p1/p0-1)*100:+.1f}٪)"
        add_news(chat_id, news)
    db.commit()
    return True, {"qty": qty, "gross": gross, "net": net, "fee": fee, "p0": p0, "p1": p1, "news": news}

def crypto_inject(chat_id, uid, name, sym, amount):
    """تزریق سانت به استخر (بدون گرفتن کوین): قیمت بالا می‌ره و سانت برای همیشه تو استخر می‌مونه."""
    cfg = COINS[sym]
    size = get_size(chat_id, uid)
    if amount < CRYPTO_INJECT_MIN:
        return False, f"❌ حداقل تزریق {CRYPTO_INJECT_MIN} سانته."
    if amount > size:
        return False, "❌ سانت کافی نداری."
    max_amt = max(CRYPTO_INJECT_MIN, int(size * CRYPTO_MAX_TRADE_PCT))
    if amount > max_amt:
        return False, f"❌ تو هر تزریق حداکثر {int(CRYPTO_MAX_TRADE_PCT*100)}٪ سایزت ({max_amt} سانت) رو می‌تونی خرج کنی."
    cm, q = pool_get(chat_id, sym)
    p0 = cm / q
    pool_set(chat_id, sym, cm + amount, q)
    p1 = (cm + amount) / q
    add_sentiment(chat_id, sym, 0.6 * (p1 / p0 - 1))
    c.execute("UPDATE users SET size=size-? WHERE chat_id=? AND user_id=?", (amount, chat_id, uid))
    news = f"💉 تزریق به بازار! {name} {amount} سانت به استخر {cfg['emoji']} {sym} تزریق کرد؛ قیمت از {fmt_price(p0)} به {fmt_price(p1)} رسید ({(p1/p0-1)*100:+.1f}٪)"
    add_news(chat_id, news)
    db.commit()
    return True, {"p0": p0, "p1": p1, "news": news}

# ---------- حزب‌ها ----------
def party_tag(sym):
    """برچسب کوتاه حزب برای نمایش کنار اسم شرکت."""
    cfg = COINS.get(sym)
    return f" — {cfg['emoji']} {cfg['party']} (پول رسمی: {cfg['name']})" if cfg else " — 🏳️ بدون حزب (/joinparty)"

def party_econ(chat_id):
    """قدرت اقتصادی هر حزب = جمع ارزش (اسپرم) شرکت‌هایی که ازش حمایت می‌کنن → {sym: ارزش}"""
    out = {sym: 0 for sym in COINS}
    for sym, total in c.execute(
        "SELECT party, COALESCE(SUM(value),0) FROM owned_companies WHERE chat_id=? AND value>0 GROUP BY party", (chat_id,)
    ).fetchall():
        if sym in out:
            out[sym] = total
    return out

def party_factor(chat_id, sym, econ=None):
    """ضریب قدرت حزب روی ارزش واقعی کوین: ۱ = حزب متوسط؛ بالاتر = شرکت‌های موفق‌تر از میانگین؛ پایین‌تر = ضعیف‌تر."""
    if econ is None:
        econ = party_econ(chat_id)
    mean = sum(econ.values()) / len(econ)
    f = ((econ[sym] + PARTY_SMOOTH) / (mean + PARTY_SMOOTH)) ** PARTY_EXPONENT
    return max(PARTY_FACTOR_MIN, min(PARTY_FACTOR_MAX, f))

def party_company_event(chat_id, sym, company_name, value, joined, kind="cashout"):
    """حال‌وهوای بازارِ کوینِ یه حزب فوراً تکون می‌خوره و خبرش ثبت می‌شه (قدرت حزب هم خودش از ارزش شرکت‌ها عوض می‌شه).
    joined=True: شرکت پیوست | joined=False: kind="leave" شرکت رفت، kind="cashout" بخشی از ارزش نقد شد."""
    crypto_init(chat_id)
    cfg = COINS[sym]
    kick = PARTY_NEWS_KICK * value / (value + PARTY_SMOOTH * 2)
    add_sentiment(chat_id, sym, kick if joined else -kick)
    if joined:
        txt = (f"🏛 شرکت «{company_name}» ({value} اسپرم) پشت {cfg['party']} وایستاد؛ "
               f"قدرت اقتصادی حزب بالا رفت و بازار به {cfg['emoji']} {cfg['name']} خوش‌بین شد")
    elif kind == "leave":
        txt = (f"🚪 شرکت «{company_name}» ({value} اسپرم) از {cfg['party']} جدا شد؛ "
               f"حزب ضعیف‌تر شد و {cfg['emoji']} {cfg['name']} تحت فشار فروش قرار گرفت")
    else:
        txt = (f"🏚 «{company_name}» {value} اسپرم از ارزشش رو نقد کرد؛ "
               f"{cfg['party']} ضعیف‌تر شد و {cfg['emoji']} {cfg['name']} تحت فشار فروش قرار گرفت")
    add_news(chat_id, txt)
    db.commit()
    return txt

def parties_txt():
    """معرفی حزب‌ها و پول رسمی‌شون."""
    return "\n".join(f"{cfg['emoji']} {cfg['party']} — پول رسمی: {cfg['name']} ({sym})" for sym, cfg in COINS.items())

def party_join(chat_id, uid, cid, sym):
    """صاحب شرکت حزب شرکتش رو انتخاب یا عوض می‌کنه. خروجی: (True, پیام) یا (False, پیام خطا)"""
    row = c.execute(
        "SELECT owner_id,name,value,party,party_changed FROM owned_companies WHERE id=? AND chat_id=?", (cid, chat_id)
    ).fetchone()
    if not row:
        return False, "❌ همچین شرکتی پیدا نشد."
    owner_id, name, value, old, changed = row
    if owner_id != uid:
        return False, "❌ این شرکت مال تو نیست!"
    if value <= 0:
        return False, "❌ ارزش این شرکت صفره؛ هیچ حزبی ازش قدرت نمی‌گیره."
    if old == sym:
        return False, f"❌ «{name}» همین الان پشت {COINS[sym]['party']} هست."
    now = int(time.time())
    left = (changed or 0) + PARTY_SWITCH_COOLDOWN - now
    if old in COINS and left > 0:
        return False, f"⏳ حزب این شرکت رو تازه عوض کردی؛ {left // 3600} ساعت و {(left % 3600) // 60} دقیقه‌ی دیگه می‌تونی دوباره عوضش کنی."
    c.execute("UPDATE owned_companies SET party=?, party_changed=? WHERE id=?", (sym, now, cid))
    db.commit()
    if old in COINS:
        party_company_event(chat_id, old, name, value, False, kind="leave")
    party_company_event(chat_id, sym, name, value, True)
    cfg = COINS[sym]
    return True, (f"🏛 «{name}» حالا پشت {cfg['party']} وایستاده!\\n"
                  f"💱 پول رسمی‌ش: {cfg['emoji']} {cfg['name']} ({sym})\\n"
                  f"💪 ارزش شرکت ({value} اسپرم) به قدرت اقتصادی این حزب اضافه شد.")

# ---------- فروش اجباری برای مالیات ----------
def liquidate_for_tax(chat_id, uid, need):
    """برای پرداخت مالیات به اندازه‌ی need سانت از کوین‌های بازیکن (ارزشمندترین اول) می‌فروشه.
    خروجی: (سانت به‌دست‌اومده، [(sym, qty, سانت)])"""
    holds = c.execute("SELECT coin,qty FROM crypto_wallet WHERE chat_id=? AND user_id=? AND qty>0", (chat_id, uid)).fetchall()
    holds.sort(key=lambda r: -sell_value(chat_id, r[0], r[1]))
    got, sold = 0, []
    for sym, held in holds:
        remaining = need - got
        if remaining <= 0:
            break
        cm, q = pool_get(chat_id, sym)
        gross_all = sell_value(chat_id, sym, held)
        if gross_all <= 0:
            continue
        if gross_all <= remaining:
            qty_in, gross = held, gross_all
        else:
            qty_in = (cm * q) / (cm - remaining) - q
            qty_in = min(held, qty_in)
            gross = int(cm - (cm * q) / (q + qty_in))
            while gross < remaining and qty_in < held:
                qty_in = min(held, qty_in * 1.001 + 1e-9)
                gross = int(cm - (cm * q) / (q + qty_in))
        pool_set(chat_id, sym, cm - gross, q + qty_in)
        wallet_add(chat_id, uid, sym, -qty_in)
        got += gross
        sold.append((sym, qty_in, gross))
    db.commit()
    return got, sold

# ===== دستورهای بازار کریپتو =====
CRYPTO_CD = {}  # (chat_id, user_id) -> آخرین معامله

def parse_coin(arg):
    arg = (arg or "").strip()
    sym = COIN_ALIASES.get(arg) or arg.upper()
    return sym if sym in COINS else None

def coins_txt():
    return "، ".join(f"{cfg['emoji']} {sym} ({cfg['name']})" for sym, cfg in COINS.items())

def crypto_cd_left(chat_id, uid):
    return int(CRYPTO_CD.get((chat_id, uid), 0) + CRYPTO_COOLDOWN - time.time())

def crypto_sparkline(prices):
    blocks = "▁▂▃▄▅▆▇█"
    lo, hi = min(prices), max(prices)
    if hi - lo < 1e-9:
        return blocks[0] * len(prices)
    return "".join(blocks[int((p - lo) / (hi - lo) * (len(blocks) - 1))] for p in prices)

def crypto_chart_png(sym, rows):
    """رندر چارت (تابع خالص؛ بدون دسترسی به دیتابیس تا بشه تو ترد جدا اجراش کرد). خروجی: bytes یا None"""
    try:
        import io
        from datetime import datetime
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        xs = [datetime.fromtimestamp(r[0]) for r in rows]
        ys = [r[1] for r in rows]
        color = "#2ecc71" if ys[-1] >= ys[0] else "#e74c3c"
        fig, ax = plt.subplots(figsize=(8, 4), dpi=110)
        ax.plot(xs, ys, color=color, linewidth=2, drawstyle="steps-post")
        ax.fill_between(xs, ys, min(ys), color=color, alpha=0.12, step="post")
        ax.set_title(f"{sym} / cm   last: {ys[-1]:,.2f}")
        ax.grid(alpha=0.25)
        fig.autofmt_xdate()
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        return buf.getvalue()
    except Exception:
        logger.exception("chart render failed")
        return None

TRADE_GROUP = {}               # user_id -> (chat_id گروهِ انتخاب‌شده برای معامله، زمان آخرین استفاده)
TRADE_GROUP_TTL = 6 * 3600     # انتخاب گروه بعد از این مدت بی‌استفاده بودن پاک می‌شه

def user_trade_groups(uid):
    """گروه‌هایی که این کاربر توشون بازی کرده (چت خصوصی‌ها حساب نمی‌شن)."""
    return [r[0] for r in c.execute("SELECT DISTINCT chat_id FROM users WHERE user_id=? AND chat_id<0", (uid,)).fetchall()]

async def group_title(bot, chat_id):
    try:
        return (await bot.get_chat(chat_id)).title or f"گروه {chat_id}"
    except Exception:
        return f"گروه {chat_id}"

async def send_group_picker(m: Message, groups):
    rows = [[InlineKeyboardButton(text=await group_title(m.bot, g), callback_data=f"tgroup:{g}")] for g in groups[:10]]
    await m.reply("🏛 معامله‌ات برای کدوم گروه باشه؟", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

async def resolve_trade_group(m: Message):
    """تو پیوی: گروهِ معامله‌ی این کاربر رو پیدا می‌کنه. اگه چندتا گروه داره و هنوز انتخاب نکرده، دکمه‌ی انتخاب می‌فرسته و None برمی‌گردونه."""
    uid = m.from_user.id
    now = time.time()
    sel = TRADE_GROUP.get(uid)
    if sel and now - sel[1] < TRADE_GROUP_TTL:
        TRADE_GROUP[uid] = (sel[0], now)
        return sel[0]
    groups = user_trade_groups(uid)
    if not groups:
        await m.reply("❌ هنوز تو هیچ گروهی بازی نکردی. اول تو گروه /grow بزن، بعد بیا پیوی.")
        return None
    if len(groups) == 1:
        TRADE_GROUP[uid] = (groups[0], now)
        return groups[0]
    await send_group_picker(m, groups)
    return None

async def crypto_precheck(m: Message, group_ok=True):
    """ساخته شدن استخرها + ثبت کاربر. خروجی: (chat_id گروه، uid) یا None.
    تو پیوی: گروه از انتخاب کاربر میاد. تو گروه: اگه group_ok=False (دستورهای معامله) کاربر رو می‌فرسته پیوی."""
    uid = m.from_user.id
    if m.chat.type == "private":
        chat_id = await resolve_trade_group(m)
        if chat_id is None:
            return None
    else:
        chat_id = m.chat.id
        if not group_ok:
            user(chat_id, uid, m.from_user.full_name)
            TRADE_GROUP[uid] = (chat_id, time.time())
            title = m.chat.title or "این گروه"
            try:
                await m.bot.send_message(
                    uid,
                    f"🔒 معامله‌ی کریپتو اینجا انجام می‌شه تا کسی نفهمه چی می‌خری و می‌فروشی.\n\n🏛 گروه: «{title}»\n\n"
                    "🛒 /cbuy [کوین] [سانت]\n💰 /csell [کوین] [مقدار یا all]\n💉 /cinject [کوین] [سانت]\n"
                    "👛 /cwallet | 🪙 /crypto\n\nمثلاً: /cbuy BTK 100\nگروه دیگه‌ای می‌خوای؟ /tgroup"
                )
            except (TelegramForbiddenError, TelegramBadRequest):
                await m.reply("❌ معامله‌ی کریپتو فقط تو پیوی ربات انجام می‌شه؛ اول ربات رو توی پیوی استارت کن، بعد دوباره اینجا بزن.")
                return None
            await m.reply("🔒 معامله‌ی کریپتو فقط تو پیوی ربات انجام می‌شه. 📩 برات پیام خصوصی فرستادم!")
            return None
    user(chat_id, uid, m.from_user.full_name)
    crypto_init(chat_id)
    return chat_id, uid

@dp.callback_query(F.data.startswith("tgroup:"))
async def trade_group_pick(q: CallbackQuery):
    chat_id = int(q.data.split(":")[1])
    uid = q.from_user.id
    if chat_id not in user_trade_groups(uid):
        return await q.answer("❌ تو این گروه بازی نکردی.", show_alert=True)
    TRADE_GROUP[uid] = (chat_id, time.time())
    title = await group_title(q.bot, chat_id)
    await q.message.edit_text(f"✅ گروه معامله: «{title}»\n\nحالا دستورت رو بزن؛ مثلاً /cbuy BTK 100 یا /crypto")
    await q.answer()

@dp.message(Command("tgroup"))
async def trade_group_cmd(m: Message):
    """عوض کردن گروهِ معامله (تو پیوی)."""
    if m.chat.type != "private":
        return await m.reply("❌ این دستور رو تو پیوی ربات بزن.")
    groups = user_trade_groups(m.from_user.id)
    if not groups:
        return await m.reply("❌ هنوز تو هیچ گروهی بازی نکردی. اول تو گروه /grow بزن.")
    TRADE_GROUP.pop(m.from_user.id, None)
    await send_group_picker(m, groups)

@dp.message(Command("crypto"))
async def crypto_overview(m: Message):
    ids = await crypto_precheck(m)
    if not ids:
        return
    chat_id, uid = ids
    lines = []
    for sym, cfg in COINS.items():
        cm, q = pool_get(chat_id, sym)
        ch = change_24h(chat_id, sym)
        arrow = "🟢▲" if ch >= 0.0005 else ("🔴▼" if ch <= -0.0005 else "⚪️▬")
        lines.append(
            f"{cfg['emoji']} {sym} {cfg['name']} — {fmt_price(cm / q)} سانت  {arrow} {ch*100:+.1f}٪\n"
            f"   💧 نقدینگی {int(cm):,} | 🏛 {cfg['party']} | 💪 {party_econ(chat_id)[sym]} اسپرم"
        )
    news = c.execute("SELECT text FROM crypto_news WHERE chat_id=? ORDER BY ts DESC LIMIT 1", (chat_id,)).fetchone()
    txt = (
        "🪙 بازار کریپتو (همه‌چی با سانت)\n\n" + "\n".join(lines) +
        f"\n\n💎 کوین‌های تو: ≈ {crypto_value_of(chat_id, uid)} سانت\n"
        + (f"📰 آخرین خبر: {news[0]}\n" if news else "")
        + "\n🔒 معامله فقط تو پیوی ربات:\n🛒 /cbuy [کوین] [سانت] | 💰 /csell [کوین] [مقدار|all]\n"
        "📈 /cchart [کوین] | 👛 /cwallet | 💉 /cinject [کوین] [سانت]\n"
        "🏛 /party | 📰 /cnews"
    )
    await m.reply(txt)

@dp.message(Command("cbuy"))
async def crypto_buy_cmd(m: Message):
    ids = await crypto_precheck(m, group_ok=False)
    if not ids:
        return
    chat_id, uid = ids
    args = m.text.split()[1:]
    sym = parse_coin(args[0]) if args else None
    if not sym or len(args) < 2 or not args[1].isdigit():
        return await m.reply(f"استفاده: /cbuy [کوین] [مقدار سانت]\nمثلاً: /cbuy BTK 100\nکوین‌ها: {coins_txt()}")
    left = crypto_cd_left(chat_id, uid)
    if left > 0:
        return await m.reply(f"⏳ {left} ثانیه‌ی دیگه می‌تونی معامله کنی.")
    ok, res = crypto_buy(chat_id, uid, "یه نهنگ ناشناس", sym, int(args[1]))
    if not ok:
        return await m.reply(res)
    CRYPTO_CD[(chat_id, uid)] = time.time()
    cfg = COINS[sym]
    await m.reply(
        f"✅ خرید انجام شد!\n\n"
        f"{cfg['emoji']} {fmt_qty(res['coin_out'])} {sym} خریدی\n"
        f"💸 پرداختی: {res['spend']} سانت (کارمزد {res['fee']})\n"
        f"📈 قیمت: {fmt_price(res['p0'])} → {fmt_price(res['p1'])}\n"
        f"📏 سایزت: {get_size(chat_id, uid)}"
    )
    if res["news"]:
        await m.bot.send_message(chat_id, res["news"])

@dp.message(Command("csell"))
async def crypto_sell_cmd(m: Message):
    ids = await crypto_precheck(m, group_ok=False)
    if not ids:
        return
    chat_id, uid = ids
    args = m.text.split()[1:]
    sym = parse_coin(args[0]) if args else None
    qty = None
    if sym and len(args) >= 2 and args[1].lower() != "all":
        try:
            qty = float(args[1].replace(",", "."))
        except ValueError:
            sym = None
    if not sym or (len(args) < 2):
        return await m.reply(f"استفاده: /csell [کوین] [مقدار یا all]\nمثلاً: /csell BTK all\nکوین‌ها: {coins_txt()}")
    left = crypto_cd_left(chat_id, uid)
    if left > 0:
        return await m.reply(f"⏳ {left} ثانیه‌ی دیگه می‌تونی معامله کنی.")
    ok, res = crypto_sell(chat_id, uid, "یه نهنگ ناشناس", sym, qty)
    if not ok:
        return await m.reply(res)
    CRYPTO_CD[(chat_id, uid)] = time.time()
    cfg = COINS[sym]
    await m.reply(
        f"✅ فروش انجام شد!\n\n"
        f"{cfg['emoji']} {fmt_qty(res['qty'])} {sym} فروختی\n"
        f"💰 دریافتی: {res['net']} سانت (کارمزد {res['fee']})\n"
        f"📉 قیمت: {fmt_price(res['p0'])} → {fmt_price(res['p1'])}\n"
        f"📏 سایزت: {get_size(chat_id, uid)}"
    )
    if res["news"]:
        await m.bot.send_message(chat_id, res["news"])

@dp.message(Command("cinject"))
async def crypto_inject_cmd(m: Message):
    ids = await crypto_precheck(m, group_ok=False)
    if not ids:
        return
    chat_id, uid = ids
    args = m.text.split()[1:]
    sym = parse_coin(args[0]) if args else None
    if not sym or len(args) < 2 or not args[1].isdigit():
        return await m.reply(
            f"💉 تزریق به بازار\n\nاستفاده: /cinject [کوین] [مقدار سانت]\nمثلاً: /cinject ETK 100\n\n"
            f"سانتت بدون گرفتن کوین به استخر می‌ره و قیمت بالا می‌ره (برای همه‌ی دارنده‌ها). "
            f"سانت برنمی‌گرده و تزریق تو اخبار اعلام می‌شه. حداقل {CRYPTO_INJECT_MIN} سانت."
        )
    left = crypto_cd_left(chat_id, uid)
    if left > 0:
        return await m.reply(f"⏳ {left} ثانیه‌ی دیگه می‌تونی معامله کنی.")
    ok, res = crypto_inject(chat_id, uid, m.from_user.full_name, sym, int(args[1]))
    if not ok:
        return await m.reply(res)
    CRYPTO_CD[(chat_id, uid)] = time.time()
    await m.reply(f"💉 تزریق انجام شد! قیمت {sym}: {fmt_price(res['p0'])} → {fmt_price(res['p1'])}\n📏 سایزت: {get_size(chat_id, uid)}")
    await m.bot.send_message(chat_id, res["news"])

@dp.message(Command("cchart"))
async def crypto_chart_cmd(m: Message):
    ids = await crypto_precheck(m)
    if not ids:
        return
    chat_id, _uid = ids
    args = m.text.split()[1:]
    sym = parse_coin(args[0]) if args else None
    if not sym:
        return await m.reply(f"استفاده: /cchart [کوین]\nمثلاً: /cchart BTK\nکوین‌ها: {coins_txt()}")
    rows = c.execute(
        "SELECT ts, price FROM crypto_prices WHERE chat_id=? AND coin=? ORDER BY ts DESC LIMIT 150", (chat_id, sym)
    ).fetchall()[::-1]
    cfg = COINS[sym]
    cm, q = pool_get(chat_id, sym)
    prices = [r[1] for r in rows]
    ch = change_24h(chat_id, sym)
    caption = (
        f"{cfg['emoji']} {sym} {cfg['name']}\n"
        f"💰 قیمت: {fmt_price(cm / q)} سانت  ({ch*100:+.1f}٪ در ۲۴ ساعت)\n"
        f"🔺 بیشترین: {fmt_price(max(prices))} | 🔻 کمترین: {fmt_price(min(prices))}\n"
        f"💧 نقدینگی: {int(cm):,} | 🏛 {cfg['party']}: {party_econ(chat_id)[sym]} اسپرم"
    )
    png = await asyncio.to_thread(crypto_chart_png, sym, rows) if len(rows) >= 2 else None
    if png:
        return await m.bot.send_photo(m.chat.id, BufferedInputFile(png, filename=f"{sym}.png"), caption=caption)
    spark = crypto_sparkline(prices[-40:]) if prices else ""
    await m.reply(caption + (f"\n\n{spark}" if spark else "\n\n(هنوز داده‌ی کافی برای چارت نیست.)"))

@dp.message(Command("cwallet"))
async def crypto_wallet_cmd(m: Message):
    ids = await crypto_precheck(m)
    if not ids:
        return
    chat_id, uid = ids
    lines, total = [], 0
    for sym, cfg in COINS.items():
        qty = wallet_get(chat_id, uid, sym)
        if qty > 0:
            val = sell_value(chat_id, sym, qty)
            total += val
            lines.append(f"{cfg['emoji']} {sym}: {fmt_qty(qty)} ≈ {val} سانت")
    await m.reply(
        "👛 کیف پول کریپتو\n\n"
        + ("\n".join(lines) if lines else "کوینی نداری.") +
        f"\n\n💎 ارزش کل (با اسلیپیج فروش): ≈ {total} سانت"
        + f"\n\n📏 سایز: {get_size(chat_id, uid)} | ثروت کل (برای مالیات): {net_worth(chat_id, uid)} سانت"
    )

@dp.message(Command("joinparty"))
async def joinparty_cmd(m: Message):
    ids = await crypto_precheck(m)
    if not ids:
        return
    chat_id, uid = ids
    args = m.text.split()[1:]
    sym = parse_coin(args[1]) if len(args) >= 2 else None
    if len(args) < 2 or not args[0].isdigit() or not sym:
        mine = c.execute("SELECT id,name,value,party FROM owned_companies WHERE chat_id=? AND owner_id=?", (chat_id, uid)).fetchall()
        listing = "\n".join(f"#{cid} {name} ({value} اسپرم){party_tag(p)}" for cid, name, value, p in mine) or "هنوز شرکتی نداری."
        return await m.reply(
            "🏛 انتخاب حزب برای شرکتت\n\nاستفاده: /joinparty [شماره شرکت] [کوین]\nمثلاً: /joinparty 5 BTK\n\n"
            f"حزب‌ها:\n{parties_txt()}\n\n🏢 شرکت‌های تو:\n{listing}\n\n"
            f"بعد از انتخاب، تا {PARTY_SWITCH_COOLDOWN // 3600} ساعت نمی‌تونی حزب شرکت رو عوض کنی."
        )
    ok, msg = party_join(chat_id, uid, int(args[0]), sym)
    await m.reply(msg)
    if ok:
        news = c.execute("SELECT text FROM crypto_news WHERE chat_id=? ORDER BY ts DESC LIMIT 1", (chat_id,)).fetchone()
        if news:
            await m.bot.send_message(chat_id, news[0])

@dp.message(Command("party", "parties"))
async def party_cmd(m: Message):
    ids = await crypto_precheck(m)
    if not ids:
        return
    chat_id, _uid = ids
    econ = party_econ(chat_id)
    total = sum(econ.values())
    rows = c.execute(
        "SELECT party,name,value,owner_id FROM owned_companies WHERE chat_id=? AND value>0 ORDER BY value DESC", (chat_id,)
    ).fetchall()
    blocks = []
    for sym in sorted(COINS, key=lambda s: -econ[s]):
        cfg = COINS[sym]
        share = econ[sym] / total * 100 if total else 0
        mine = [r for r in rows if r[0] == sym]
        block = (
            f"{cfg['emoji']} {cfg['party']} — 💱 پول رسمی: {cfg['name']} ({sym}) = {fmt_price(pool_price(chat_id, sym))} سانت ({change_24h(chat_id, sym)*100:+.1f}٪)\n"
            f"   🏢 {len(mine)} شرکت | 💪 قدرت اقتصادی {econ[sym]} اسپرم ({share:.0f}٪) | ⚖️ اثر روی ارزش واقعی کوین: ×{party_factor(chat_id, sym, econ):.2f}"
        )
        for _p, name, value, owner in mine[:3]:
            block += f"\n   • {name} — {value} اسپرم (👤 {get_name(chat_id, owner)})"
        blocks.append(block)
    free = c.execute("SELECT COUNT(*) FROM owned_companies WHERE chat_id=? AND value>0 AND (party IS NULL OR party='')", (chat_id,)).fetchone()[0]
    await m.reply(
        "🏛 حزب‌ها و پول رسمی‌شون\n\n" + "\n\n".join(blocks) +
        (f"\n\n🏳️ {free} شرکت هنوز حزب انتخاب نکردن و به هیچ کوینی کمک نمی‌کنن." if free else "") +
        "\n\nصاحب هر شرکت خودش انتخاب می‌کنه پشت کدوم حزب وایسته: /joinparty [شماره شرکت] [کوین] "
        "(شماره‌ها تو /mycompanies). هرچی شرکت‌های یه حزب با ارزش‌تر باشن، پول رسمی‌ش ارزشمندتر می‌شه."
    )

@dp.message(Command("cnews"))
async def crypto_news_cmd(m: Message):
    ids = await crypto_precheck(m)
    if not ids:
        return
    chat_id, _uid = ids
    rows = c.execute("SELECT ts, text FROM crypto_news WHERE chat_id=? ORDER BY ts DESC LIMIT 8", (chat_id,)).fetchall()
    if not rows:
        return await m.reply("📰 هنوز خبری نیست. خبرها از معامله‌های سنگین، تزریق و ورود یا نقد شدن شرکت‌های حزب‌ها ساخته می‌شن.")
    now = int(time.time())
    def ago(ts):
        d = now - ts
        return f"{d // 3600} ساعت پیش" if d >= 3600 else f"{max(1, d // 60)} دقیقه پیش"
    await m.reply("📰 اخبار بازار\n\n" + "\n\n".join(f"• {t}\n  ({ago(ts)})" for ts, t in rows))

def crypto_multi_chart_png(series, hours):
    """چارت یه‌تکه‌ی هر ۳ کوین (پنل جدا برای هرکدوم). series = {sym: [(ts, price), ...]}.
    تابع خالص (بدون دسترسی به دیتابیس) تا تو ترد جدا اجرا بشه. خروجی: bytes یا None"""
    try:
        import io
        from datetime import datetime
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        syms = [s for s in COINS if len(series.get(s, [])) >= 2]
        if not syms:
            return None
        fig, axes = plt.subplots(len(syms), 1, figsize=(8, 2.6 * len(syms)), dpi=110, sharex=True)
        fig.patch.set_facecolor("#14161a")
        if len(syms) == 1:
            axes = [axes]
        for ax, sym in zip(axes, syms):
            rows = series[sym]
            xs = [datetime.fromtimestamp(r[0]) for r in rows]
            ys = [r[1] for r in rows]
            ch = (ys[-1] / ys[0] - 1) * 100 if ys[0] > 0 else 0.0
            color = "#2ecc71" if ys[-1] >= ys[0] else "#e74c3c"
            ax.set_facecolor("#1c1f24")
            ax.plot(xs, ys, color=color, linewidth=2, drawstyle="steps-post")
            ax.fill_between(xs, ys, min(ys), color=color, alpha=0.12, step="post")
            ax.set_title(f"{sym}   {ys[-1]:,.2f} cm   ({ch:+.1f}% / {hours}h)", color="white", fontsize=11, loc="left")
            ax.grid(alpha=0.15)
            ax.tick_params(colors="#aaaaaa", labelsize=8)
            for sp in ax.spines.values():
                sp.set_color("#333842")
        fig.autofmt_xdate()
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
        plt.close(fig)
        return buf.getvalue()
    except Exception:
        logger.exception("multi chart render failed")
        return None

def crypto_chart_caption(chat_id):
    lines = []
    for sym, cfg in COINS.items():
        cm, q = pool_get(chat_id, sym)
        ch = change_24h(chat_id, sym)
        arrow = "🟢▲" if ch >= 0.0005 else ("🔴▼" if ch <= -0.0005 else "⚪️▬")
        lines.append(f"{cfg['emoji']} {sym}: {fmt_price(cm / q)} سانت {arrow} {ch*100:+.1f}٪ (۲۴ ساعت) | 💪 {party_econ(chat_id)[sym]}")
    return "📊 آپدیت ۱۰ دقیقه‌ای بازار\n\n" + "\n".join(lines)

async def crypto_market_loop(bot):
    """هر CRYPTO_SNAPSHOT_INTERVAL ثانیه (۱۰ دقیقه) برای هر گروه:
    ۱) یه قدم حرکت بازار (ربات‌های بازارساز قیمت رو به‌سمت ارزش واقعی می‌برن؛ اثر قدرت حزب‌ها، سیکل و معامله‌های بازیکنا اینجا اعمال می‌شه)
    ۲) خبرهای تولیدشده رو تو گروه می‌فرسته
    ۳) اگه auto_chart روشن باشه، چارت عکسی ۳ کوین رو می‌فرسته"""
    while True:
        await asyncio.sleep(CRYPTO_SNAPSHOT_INTERVAL)
        try:
            now = int(time.time())
            chats = [r[0] for r in c.execute("SELECT DISTINCT chat_id FROM crypto_pools").fetchall()]
            for chat_id in chats:
                try:
                    news = market_step(chat_id)
                    auto = c.execute("SELECT auto_chart FROM crypto_settings WHERE chat_id=?", (chat_id,)).fetchone()
                    series = {}
                    for sym in COINS:
                        series[sym] = c.execute(
                            "SELECT ts, price FROM crypto_prices WHERE chat_id=? AND coin=? AND ts>=? ORDER BY ts",
                            (chat_id, sym, now - CRYPTO_CHART_HOURS * 3600)
                        ).fetchall()
                    for txt in news:
                        try:
                            await bot.send_message(chat_id, txt)
                        except (TelegramForbiddenError, TelegramBadRequest):
                            break
                    if auto is None or auto[0]:
                        png = await asyncio.to_thread(crypto_multi_chart_png, series, CRYPTO_CHART_HOURS)
                        if png:
                            await bot.send_photo(
                                chat_id, BufferedInputFile(png, filename="market.png"),
                                caption=crypto_chart_caption(chat_id)
                            )
                except (TelegramForbiddenError, TelegramBadRequest):
                    logger.warning("crypto loop: can't post to chat %s", chat_id)
                except Exception:
                    logger.exception("crypto_market_loop chat %s error", chat_id)
            c.execute("DELETE FROM crypto_prices WHERE ts<?", (now - 3 * 86400,))
            c.execute("DELETE FROM crypto_news WHERE ts<?", (now - 14 * 86400,))
            db.commit()
        except Exception:
            logger.exception("crypto_market_loop error")

@dp.message(Command("cauto"))
async def crypto_auto_cmd(m: Message):
    """روشن/خاموش کردن چارت خودکار ۱۰ دقیقه‌ای (ادمین بازی یا ادمین گروه)."""
    ids = await crypto_precheck(m)
    if not ids:
        return
    chat_id, uid = ids
    is_admin = uid in ADMIN_IDS
    if not is_admin:
        try:
            mem = await m.bot.get_chat_member(chat_id, uid)
            is_admin = mem.status in ("administrator", "creator")
        except Exception:
            is_admin = False
    if not is_admin:
        return await m.reply("❌ فقط ادمین می‌تونه چارت خودکار رو عوض کنه.")
    args = m.text.split()[1:]
    cur = c.execute("SELECT auto_chart FROM crypto_settings WHERE chat_id=?", (chat_id,)).fetchone()
    cur = cur[0] if cur else 1
    if not args or args[0].lower() not in ("on", "off"):
        return await m.reply(f"📊 چارت خودکار الان {'روشنه ✅' if cur else 'خاموشه ⛔️'}\nاستفاده: /cauto on  یا  /cauto off")
    val = 1 if args[0].lower() == "on" else 0
    c.execute("UPDATE crypto_settings SET auto_chart=? WHERE chat_id=?", (val, chat_id))
    db.commit()
    await m.reply("✅ چارت خودکار روشن شد." if val else "⛔️ چارت خودکار خاموش شد (قیمت‌ها همچنان هر ۱۰ دقیقه آپدیت می‌شن).")

async def main():
    bot=Bot(TOKEN)
    from aiogram.types import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeDefault
    commands = [
        BotCommand(command="help", description="📖 راهنمای کامل بازی"),
        BotCommand(command="grow", description="🌱 رشد کن"),
        BotCommand(command="size", description="📊 اندازه و پروفایل"),
        BotCommand(command="rank", description="🏅 رنک و پیشرفت روزانه"),
        BotCommand(command="ranktop", description="🏆 برترین‌های رنک گروه"),
        BotCommand(command="farm", description="🌾 پنل مزرعه‌ی اسپرم"),
        BotCommand(command="farmrank", description="🌾 رنک مزرعه‌ی من (زنده)"),
        BotCommand(command="farmleader", description="📊 جدول رنک مزرعه‌ی گروه"),
        BotCommand(command="tosperm", description="🧬 تبدیل سانت به اسپرم"),
        BotCommand(command="tocent", description="💰 تبدیل اسپرم به سانت"),
        BotCommand(command="top", description="🏆 جدول بزرگان"),
        BotCommand(command="tax", description="🏛 مالیات پولدارترین فرد و مزرعه"),
        BotCommand(command="crypto", description="🪙 بازار کریپتو"),
        BotCommand(command="cbuy", description="🛒 خرید کوین"),
        BotCommand(command="csell", description="💰 فروش کوین"),
        BotCommand(command="cchart", description="📈 چارت قیمت کوین"),
        BotCommand(command="cwallet", description="👛 کیف پول کریپتو"),
        BotCommand(command="cinject", description="💉 تزریق به بازار"),
        BotCommand(command="party", description="🏛 حزب‌ها، شرکت‌ها و پول رسمی‌شون"),
        BotCommand(command="joinparty", description="🏛 انتخاب حزب برای شرکتت"),
        BotCommand(command="tgroup", description="🔒 انتخاب گروه معامله (تو پیوی)"),
        BotCommand(command="cnews", description="📰 اخبار بازار کریپتو"),
        BotCommand(command="cauto", description="📊 روشن/خاموش چارت خودکار ۱۰ دقیقه‌ای (ادمین)"),
        BotCommand(command="token", description="🎟 توکن‌های من و قیمت توکن"),
        BotCommand(command="buytoken", description="🛒 خرید توکن بازی"),
        BotCommand(command="box", description="🎁 مینی‌گیم جعبه‌ی شانس (۱ توکن)"),
        BotCommand(command="climb", description="🪜 مینی‌گیم نردبان (۱ توکن)"),
        BotCommand(command="bj", description="🃏 بلک‌جک ۲۱ (۱ توکن)"),
        BotCommand(command="market", description="🛒 بازار سلبریتی"),
        BotCommand(command="collection", description="📚 کالکشن من"),
        BotCommand(command="spin", description="🎰 اسپین سلبریتی"),
        BotCommand(command="buy", description="🛍 خرید سلبریتی"),
        BotCommand(command="sell", description="💸 فروش سلبریتی"),
        BotCommand(command="list", description="🏪 فروش به دیگران"),
        BotCommand(command="lock", description="🔒 قفل کردن سلبریتی"),
        BotCommand(command="pvp", description="⚔️ دوئل"),
        BotCommand(command="mafia", description="🔫 جنگ مافیا تیمی"),
        BotCommand(command="mafia2", description="🔫 مافیا (فاش‌شدن تیم‌ها در پایان)"),
        BotCommand(command="loan", description="💰 وام دادن"),
        BotCommand(command="repay", description="✅ پرداخت بدهی"),
        BotCommand(command="collectors", description="🏆 بهترین کلکسیونرها"),
        BotCommand(command="gloan", description="🏦 وام گرفتن از بازی"),
        BotCommand(command="gpay", description="✅ پرداخت وام بازی"),
        BotCommand(command="copen", description="📈 باز کردن بازار کمپانی (ادمین)"),
        BotCommand(command="invest", description="💰 سرمایه‌گذاری روی یه کمپانی"),
        BotCommand(command="cclose", description="📉 بستن بازار و اعلام برنده (ادمین)"),
        BotCommand(command="mycompanies", description="🏢 کمپانی‌های من"),
        BotCommand(command="bourseleader", description="📊 جدول رنک بورس گروه"),
        BotCommand(command="hire", description="🔫 خرید یار برای کمپانی"),
        BotCommand(command="useyar", description="🕵️ فرستادن یار به نبرد مافیای فعلیت"),
        BotCommand(command="cashout", description="💸 نقد کردن نصف ارزش کمپانی"),
        BotCommand(command="addcm", description="➕ افزودن سانت به کاربر (ادمین)"),
        BotCommand(command="luckydrop", description="🎉 دادن سانت به یه بازیکن رندوم (ادمین)"),
        BotCommand(command="bid", description="🔨 پیشنهاد دادن تو مزایده"),
        BotCommand(command="auctionstatus", description="📋 وضعیت مزایده‌های فعال"),
        BotCommand(command="aucol", description="🗂 کالکشن مزایده‌های فعال"),
        BotCommand(command="bidcol", description="🖼 کالکشن مزایده‌ی من (بالاترین پیشنهادها)"),
        BotCommand(command="cancelbid", description="❌ لغو پیشنهاد من تو مزایده"),
        BotCommand(command="auction", description="🔨 شروع مزایده (ادمین)"),
        BotCommand(command="aulist", description="🔨 لیست سلبریتی‌های تیر مزایده"),
        BotCommand(command="addau", description="➕ افزودن سلبریتی به تیر مزایده (ادمین)"),
        BotCommand(command="giveau", description="🎁 دادن سلبریتی تیر مزایده به کاربر (ادمین)"),
        BotCommand(command="endauction", description="🏁 پایان مزایده (ادمین)"),
        BotCommand(command="resetgroup", description="⚠️ پاک کردن کامل داده‌های این گروه (ادمین)"),
        BotCommand(command="addsperm", description="➕ افزودن اسپرم به کاربر (ادمین)"),
        BotCommand(command="addspermall", description="➕ افزودن اسپرم به همه (ادمین)"),
        BotCommand(command="addcb", description="👑 دادن/گرفتن سلبریتی از کاربر (ادمین)"),
        BotCommand(command="getfileid", description="🆔 گرفتن file_id عکس (ادمین)"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    await bot.set_my_commands(commands, scope=BotCommandScopeAllGroupChats())
    asyncio.create_task(check_loans(bot))
    asyncio.create_task(company_dividend_loop(bot))
    asyncio.create_task(auction_loop(bot))
    asyncio.create_task(wealth_tax_loop(bot))
    asyncio.create_task(crypto_market_loop(bot))
    await dp.start_polling(bot)

if __name__=="__main__":
    import asyncio
    asyncio.run(main())
