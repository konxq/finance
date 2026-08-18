import os
import sqlite3
import logging
import asyncio
import hashlib
import hmac
import json
import threading
from collections import defaultdict
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton, WebAppInfo
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DB_PATH = os.environ.get("DB_PATH", "finances.db")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "")

EXPENSE_CATEGORIES = {
    "food": "🍎 Еда",
    "transport": "⛽ Транспорт",
    "tools": "🔧 Инструменты",
    "housing": "🏠 Жильё",
    "services": "📱 Связь",
    "other": "🛍 Прочее",
}

INCOME_SOURCES = {
    "uber": "🛵 Uber",
    "stroika": "🏗 Стройка",
}

# ---------- conversation states ----------
(EXP_CATEGORY, EXP_AMOUNT, EXP_NOTE, EXP_SHARE,
 INC_SOURCE, INC_UBER_AMOUNT,
 INC_HOURS, INC_RATE, INC_OFFICIAL_HOURS, INC_ZUS, INC_TAXPCT) = range(11)


# ---------- database ----------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            note TEXT,
            share_pct REAL NOT NULL DEFAULT 100
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS income (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            source TEXT NOT NULL,
            amount REAL NOT NULL,
            gross REAL,
            hours REAL,
            rate REAL,
            official_hours REAL,
            zus REAL,
            cash_tax_pct REAL
        )
    """)
    conn.commit()
    conn.close()


def fmt(n):
    return f"{n:,.2f}".replace(",", " ").replace(".", ",") + " zł"


def period_bounds(period: str):
    now = datetime.now()
    if period == "day":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
    elif period == "week":
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7)
    elif period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
    elif period == "year":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(year=start.year + 1)
    else:  # all time
        start = datetime(2000, 1, 1)
        end = datetime(2100, 1, 1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


# ---------- main menu ----------
def main_menu_keyboard():
    rows = [["➕ Расход", "➕ Доход"], ["📊 Баланс", "🗒 Последние записи"]]
    if WEBAPP_URL:
        rows.append([KeyboardButton("📊 Открыть приложение", web_app=WebAppInfo(url=WEBAPP_URL))])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я твой финансовый трекер.\n\n"
        "Помогу вести доходы (стройка + Uber) и расходы по категориям.\n"
        "Выбери действие на клавиатуре ниже 👇",
        reply_markup=main_menu_keyboard(),
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Отменено.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


# ---------- ADD EXPENSE ----------
async def expense_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    buttons = [[InlineKeyboardButton(v, callback_data=f"cat:{k}")] for k, v in EXPENSE_CATEGORIES.items()]
    await update.message.reply_text("Выбери категорию расхода:", reply_markup=InlineKeyboardMarkup(buttons))
    return EXP_CATEGORY


async def expense_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["category"] = query.data.split(":")[1]
    await query.edit_message_text(f"Категория: {EXPENSE_CATEGORIES[context.user_data['category']]}\n\nВведи сумму, zł:")
    return EXP_AMOUNT


async def expense_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.replace(",", "."))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Не понял сумму. Введи число, например 45.50")
        return EXP_AMOUNT
    context.user_data["amount"] = amount
    await update.message.reply_text("Заметка (например, магазин)? Или отправь «-», если не нужна.")
    return EXP_NOTE


async def expense_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    note = update.message.text.strip()
    context.user_data["note"] = "" if note == "-" else note
    buttons = [[
        InlineKeyboardButton("100%", callback_data="share:100"),
        InlineKeyboardButton("75%", callback_data="share:75"),
        InlineKeyboardButton("50%", callback_data="share:50"),
        InlineKeyboardButton("25%", callback_data="share:25"),
    ]]
    await update.message.reply_text(
        "Какая доля суммы твоя? (если делите с кем-то расходы)",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return EXP_SHARE


async def expense_share(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pct = float(query.data.split(":")[1])
    d = context.user_data
    conn = db()
    conn.execute(
        "INSERT INTO expenses (user_id, date, category, amount, note, share_pct) VALUES (?,?,?,?,?,?)",
        (update.effective_user.id, datetime.now().strftime("%Y-%m-%d"), d["category"], d["amount"], d["note"], pct),
    )
    conn.commit()
    conn.close()
    counted = d["amount"] * pct / 100
    await query.edit_message_text(
        f"✅ Добавлено: {EXPENSE_CATEGORIES[d['category']]} — {fmt(d['amount'])} "
        f"({pct:.0f}% → {fmt(counted)})"
    )
    context.user_data.clear()
    return ConversationHandler.END


# ---------- ADD INCOME ----------
async def income_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    buttons = [[InlineKeyboardButton(v, callback_data=f"src:{k}")] for k, v in INCOME_SOURCES.items()]
    await update.message.reply_text("Выбери источник дохода:", reply_markup=InlineKeyboardMarkup(buttons))
    return INC_SOURCE


async def income_source(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    source = query.data.split(":")[1]
    context.user_data["source"] = source
    if source == "uber":
        await query.edit_message_text("Сумма на руки (netto), zł:")
        return INC_UBER_AMOUNT
    else:
        await query.edit_message_text("Сколько часов отработано?")
        return INC_HOURS


async def income_uber_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.replace(",", "."))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Не понял сумму. Введи число.")
        return INC_UBER_AMOUNT
    conn = db()
    conn.execute(
        "INSERT INTO income (user_id, date, source, amount) VALUES (?,?,?,?)",
        (update.effective_user.id, datetime.now().strftime("%Y-%m-%d"), "uber", amount),
    )
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ Доход Uber: {fmt(amount)}", reply_markup=main_menu_keyboard())
    context.user_data.clear()
    return ConversationHandler.END


async def _ask_float(update, context, key, next_state, prompt):
    try:
        val = float(update.message.text.replace(",", "."))
        if val < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Не понял число, попробуй ещё раз.")
        return None
    context.user_data[key] = val
    await update.message.reply_text(prompt)
    return next_state


async def income_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nxt = await _ask_float(update, context, "hours", INC_RATE, "Ставка, zł/час (brutto)?")
    return nxt if nxt else INC_HOURS


async def income_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nxt = await _ask_float(update, context, "rate", INC_OFFICIAL_HOURS, "Сколько из них официальных часов?")
    return nxt if nxt else INC_RATE


async def income_official_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nxt = await _ask_float(update, context, "official_hours", INC_ZUS, "Сумма ZUS за этот период, zł?")
    return nxt if nxt else INC_OFFICIAL_HOURS


async def income_zus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nxt = await _ask_float(update, context, "zus", INC_TAXPCT, "Налог с наличных, %? (обычно 10)")
    return nxt if nxt else INC_ZUS


async def income_taxpct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        tax_pct = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("Не понял число, попробуй ещё раз.")
        return INC_TAXPCT

    d = context.user_data
    hours, rate, off_hours, zus = d["hours"], d["rate"], d["official_hours"], d["zus"]
    gross = hours * rate
    official_amount = min(off_hours, hours) * rate
    cash_amount = max(gross - official_amount, 0)
    cash_tax = cash_amount * tax_pct / 100
    net = (official_amount - zus) + (cash_amount - cash_tax)

    conn = db()
    conn.execute(
        """INSERT INTO income (user_id, date, source, amount, gross, hours, rate, official_hours, zus, cash_tax_pct)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (update.effective_user.id, datetime.now().strftime("%Y-%m-%d"), "stroika", net,
         gross, hours, rate, off_hours, zus, tax_pct),
    )
    conn.commit()
    conn.close()

    text = (
        f"✅ Стройка добавлена\n\n"
        f"Brutto: {fmt(gross)}\n"
        f"− ZUS: {fmt(zus)}\n"
        f"− налог с наличных ({tax_pct:.0f}%): {fmt(cash_tax)}\n"
        f"— — — — —\n"
        f"Netto на руки: {fmt(net)}"
    )
    await update.message.reply_text(text, reply_markup=main_menu_keyboard())
    context.user_data.clear()
    return ConversationHandler.END


# ---------- BALANCE ----------
async def balance_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [[
        InlineKeyboardButton("День", callback_data="bal:day"),
        InlineKeyboardButton("Неделя", callback_data="bal:week"),
        InlineKeyboardButton("Месяц", callback_data="bal:month"),
    ], [
        InlineKeyboardButton("Год", callback_data="bal:year"),
        InlineKeyboardButton("Всё время", callback_data="bal:all"),
    ]]
    await update.message.reply_text("За какой период показать баланс?", reply_markup=InlineKeyboardMarkup(buttons))


PERIOD_LABELS = {"day": "день", "week": "неделю", "month": "месяц", "year": "год", "all": "всё время"}


async def balance_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    period = query.data.split(":")[1]
    start, end = period_bounds(period)
    user_id = update.effective_user.id

    conn = db()
    exp_rows = conn.execute(
        "SELECT category, SUM(amount * share_pct / 100.0) as total FROM expenses "
        "WHERE user_id=? AND date>=? AND date<? GROUP BY category ORDER BY total DESC",
        (user_id, start, end),
    ).fetchall()
    inc_rows = conn.execute(
        "SELECT source, SUM(amount) as total FROM income "
        "WHERE user_id=? AND date>=? AND date<? GROUP BY source ORDER BY total DESC",
        (user_id, start, end),
    ).fetchall()
    conn.close()

    total_exp = sum(r["total"] for r in exp_rows) if exp_rows else 0
    total_inc = sum(r["total"] for r in inc_rows) if inc_rows else 0
    net = total_inc - total_exp

    lines = [f"📊 Баланс за {PERIOD_LABELS[period]}\n"]
    lines.append(f"Доходы: {fmt(total_inc)}")
    for r in inc_rows:
        lines.append(f"  {INCOME_SOURCES.get(r['source'], r['source'])}: {fmt(r['total'])}")
    lines.append(f"\nРасходы: {fmt(total_exp)}")
    for r in exp_rows:
        pct = (r["total"] / total_exp * 100) if total_exp else 0
        lines.append(f"  {EXPENSE_CATEGORIES.get(r['category'], r['category'])}: {fmt(r['total'])} ({pct:.0f}%)")
    lines.append(f"\n💰 Итого: {'−' if net < 0 else ''}{fmt(abs(net))}")

    await query.edit_message_text("\n".join(lines))


# ---------- RECENT ----------
async def recent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = db()
    exp_rows = conn.execute(
        "SELECT date, category, amount, note, share_pct FROM expenses WHERE user_id=? ORDER BY id DESC LIMIT 8",
        (user_id,),
    ).fetchall()
    inc_rows = conn.execute(
        "SELECT date, source, amount FROM income WHERE user_id=? ORDER BY id DESC LIMIT 8",
        (user_id,),
    ).fetchall()
    conn.close()

    lines = ["🗒 Последние расходы:"]
    if not exp_rows:
        lines.append("  пока нет записей")
    for r in exp_rows:
        counted = r["amount"] * r["share_pct"] / 100
        share_note = f" ({r['share_pct']:.0f}%)" if r["share_pct"] != 100 else ""
        lines.append(f"  {r['date']} · {EXPENSE_CATEGORIES.get(r['category'], r['category'])} · {fmt(counted)}{share_note} · {r['note'] or ''}")

    lines.append("\n🗒 Последние доходы:")
    if not inc_rows:
        lines.append("  пока нет записей")
    for r in inc_rows:
        lines.append(f"  {r['date']} · {INCOME_SOURCES.get(r['source'], r['source'])} · {fmt(r['amount'])}")

    await update.message.reply_text("\n".join(lines))


# ---------- Mini App API ----------
def _telegram_user_id(init_data: str):
    if not init_data or not BOT_TOKEN:
        return None
    try:
        from urllib.parse import parse_qsl
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = pairs.pop("hash", None)
        if not received_hash:
            return None
        data_check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, received_hash):
            return None
        user = json.loads(pairs.get("user", "{}"))
        return int(user.get("id")) if user.get("id") else None
    except Exception:
        return None

def _dashboard(user_id: int, period: str):
    start, end = period_bounds(period)
    conn = db()
    inc = conn.execute("SELECT COALESCE(SUM(amount),0) FROM income WHERE user_id=? AND date>=? AND date<?", (user_id,start,end)).fetchone()[0]
    exp = conn.execute("SELECT COALESCE(SUM(amount * share_pct / 100.0),0) FROM expenses WHERE user_id=? AND date>=? AND date<?", (user_id,start,end)).fetchone()[0]
    inc_src = conn.execute("SELECT source, SUM(amount) total FROM income WHERE user_id=? AND date>=? AND date<? GROUP BY source ORDER BY total DESC", (user_id,start,end)).fetchall()
    exp_cat = conn.execute("SELECT category, SUM(amount * share_pct / 100.0) total FROM expenses WHERE user_id=? AND date>=? AND date<? GROUP BY category ORDER BY total DESC", (user_id,start,end)).fetchall()
    recent_exp = conn.execute("SELECT date, category label, amount * share_pct / 100.0 amount, note FROM expenses WHERE user_id=? ORDER BY id DESC LIMIT 6", (user_id,)).fetchall()
    recent_inc = conn.execute("SELECT date, source label, amount, '' note FROM income WHERE user_id=? ORDER BY id DESC LIMIT 6", (user_id,)).fetchall()
    conn.close()
    daily = defaultdict(lambda: [0.0,0.0])
    conn = db()
    for r in conn.execute("SELECT date, SUM(amount) total FROM income WHERE user_id=? AND date>=? AND date<? GROUP BY date", (user_id,start,end)):
        daily[r['date']][0] = r['total']
    for r in conn.execute("SELECT date, SUM(amount * share_pct / 100.0) total FROM expenses WHERE user_id=? AND date>=? AND date<? GROUP BY date", (user_id,start,end)):
        daily[r['date']][1] = r['total']
    conn.close()
    dates = sorted(daily)
    recent=[]
    for r in recent_inc:
        recent.append({'date':r['date'],'label':INCOME_SOURCES.get(r['label'],r['label']),'amount':float(r['amount']),'note':r['note'],'kind':'income'})
    for r in recent_exp:
        recent.append({'date':r['date'],'label':EXPENSE_CATEGORIES.get(r['label'],r['label']),'amount':float(r['amount']),'note':r['note'],'kind':'expense'})
    recent.sort(key=lambda x:x['date'], reverse=True)
    return {
        'income':float(inc),'expenses':float(exp),'net':float(inc-exp),
        'income_by_source':[{'label':INCOME_SOURCES.get(r['source'],r['source']),'value':float(r['total'])} for r in inc_src],
        'expenses_by_category':[{'label':EXPENSE_CATEGORIES.get(r['category'],r['category']),'value':float(r['total'])} for r in exp_cat],
        'daily':[{'date':d,'income':daily[d][0],'expenses':daily[d][1]} for d in dates],
        'recent':recent[:10]
    }

def run_web_server():
    from fastapi import FastAPI, Header, HTTPException
    from fastapi.responses import FileResponse
    import uvicorn
    api = FastAPI()
    @api.get("/")
    def index():
        return FileResponse(os.path.join(os.path.dirname(__file__), "web", "index.html"))
    @api.get("/api/dashboard")
    def dashboard(period: str = "month", x_telegram_init_data: str = Header(default="")):
        user_id = _telegram_user_id(x_telegram_init_data)
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid Telegram init data")
        if period not in {"day","week","month","year","all"}:
            period = "month"
        return _dashboard(user_id, period)
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(api, host="0.0.0.0", port=port, log_level="info")


def main():
    if not BOT_TOKEN:
        raise SystemExit("Переменная окружения BOT_TOKEN не задана")

    init_db()
    if WEBAPP_URL:
        logger.info("Mini App URL configured: %s", WEBAPP_URL)
    threading.Thread(target=run_web_server, daemon=True).start()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("^📊 Баланс$"), balance_start))
    app.add_handler(CallbackQueryHandler(balance_show, pattern="^bal:"))
    app.add_handler(MessageHandler(filters.Regex("^🗒 Последние записи$"), recent))

    expense_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ Расход$"), expense_start)],
        states={
            EXP_CATEGORY: [CallbackQueryHandler(expense_category, pattern="^cat:")],
            EXP_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, expense_amount)],
            EXP_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, expense_note)],
            EXP_SHARE: [CallbackQueryHandler(expense_share, pattern="^share:")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(expense_conv)

    income_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ Доход$"), income_start)],
        states={
            INC_SOURCE: [CallbackQueryHandler(income_source, pattern="^src:")],
            INC_UBER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, income_uber_amount)],
            INC_HOURS: [MessageHandler(filters.TEXT & ~filters.COMMAND, income_hours)],
            INC_RATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, income_rate)],
            INC_OFFICIAL_HOURS: [MessageHandler(filters.TEXT & ~filters.COMMAND, income_official_hours)],
            INC_ZUS: [MessageHandler(filters.TEXT & ~filters.COMMAND, income_zus)],
            INC_TAXPCT: [MessageHandler(filters.TEXT & ~filters.COMMAND, income_taxpct)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(income_conv)

    logger.info("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
