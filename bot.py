import os
import json
import base64
import hashlib
import hmac
import logging
import re
import sqlite3
import threading
import asyncio
from datetime import datetime, timedelta
from urllib.parse import parse_qsl

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from openai import OpenAI

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DB_PATH = os.environ.get("DB_PATH", "finances.db")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
VISION_MODEL = os.environ.get("VISION_MODEL", "gpt-5-mini")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "")
WEB_HOST = os.environ.get("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.environ.get("PORT", "8080"))
MAX_IMPORT_IMAGES = int(os.environ.get("MAX_IMPORT_IMAGES", "10"))

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

(EXP_CATEGORY, EXP_AMOUNT, EXP_NOTE, EXP_SHARE,
 INC_SOURCE, INC_UBER_AMOUNT,
 INC_HOURS, INC_RATE, INC_OFFICIAL_HOURS, INC_ZUS, INC_TAXPCT,
 IMPORT_PHOTOS, IMPORT_CONFIRM) = range(13)

app_web = FastAPI(title="FinanceBot Mini App")
app_web.mount("/static", StaticFiles(directory="web"), name="static")


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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS merchant_categories (
            user_id INTEGER NOT NULL,
            merchant TEXT NOT NULL,
            category TEXT NOT NULL,
            PRIMARY KEY (user_id, merchant)
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
        end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    elif period == "year":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(year=start.year + 1)
    else:
        start = datetime(2000, 1, 1)
        end = datetime(2100, 1, 1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def main_menu_keyboard():
    rows = [
        ["➕ Расход", "➕ Доход"],
        ["📥 Импорт", "📊 Баланс"],
        ["📈 Статистика", "🗒 Последние записи"],
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Привет! Я твой финансовый трекер.\n\n"
        "Теперь умею не только считать баланс, но и импортировать расходы со скриншотов банковского приложения. 📸\n\n"
        "Выбери действие ниже 👇"
    )
    if WEBAPP_URL:
        text += "\n\n📊 Для красивой аналитики открой Mini App кнопкой «📈 Статистика»."
    await update.message.reply_text(text, reply_markup=main_menu_keyboard())


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
    await update.message.reply_text("Какая доля суммы твоя? (если делите с кем-то расходы)", reply_markup=InlineKeyboardMarkup(buttons))
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
    await query.edit_message_text(f"✅ Добавлено: {EXPENSE_CATEGORIES[d['category']]} — {fmt(d['amount'])} ({pct:.0f}% → {fmt(counted)})")
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
    conn.execute("INSERT INTO income (user_id, date, source, amount) VALUES (?,?,?,?)", (update.effective_user.id, datetime.now().strftime("%Y-%m-%d"), "uber", amount))
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
    return (await _ask_float(update, context, "hours", INC_RATE, "Ставка, zł/час (brutto)?")) or INC_HOURS


async def income_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return (await _ask_float(update, context, "rate", INC_OFFICIAL_HOURS, "Сколько из них официальных часов?")) or INC_RATE


async def income_official_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return (await _ask_float(update, context, "official_hours", INC_ZUS, "Сумма ZUS за этот период, zł?")) or INC_OFFICIAL_HOURS


async def income_zus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return (await _ask_float(update, context, "zus", INC_TAXPCT, "Налог с наличных, %? (обычно 10)")) or INC_ZUS


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
    conn.execute("""INSERT INTO income (user_id, date, source, amount, gross, hours, rate, official_hours, zus, cash_tax_pct)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""", (update.effective_user.id, datetime.now().strftime("%Y-%m-%d"), "stroika", net, gross, hours, rate, off_hours, zus, tax_pct))
    conn.commit()
    conn.close()
    await update.message.reply_text(
        f"✅ Стройка добавлена\n\nBrutto: {fmt(gross)}\n− ZUS: {fmt(zus)}\n− налог с наличных ({tax_pct:.0f}%): {fmt(cash_tax)}\n— — — — —\nNetto на руки: {fmt(net)}",
        reply_markup=main_menu_keyboard(),
    )
    context.user_data.clear()
    return ConversationHandler.END


# ---------- BALANCE ----------
async def balance_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [[InlineKeyboardButton("День", callback_data="bal:day"), InlineKeyboardButton("Неделя", callback_data="bal:week"), InlineKeyboardButton("Месяц", callback_data="bal:month")],
               [InlineKeyboardButton("Год", callback_data="bal:year"), InlineKeyboardButton("Всё время", callback_data="bal:all")]]
    await update.message.reply_text("За какой период показать баланс?", reply_markup=InlineKeyboardMarkup(buttons))


PERIOD_LABELS = {"day": "день", "week": "неделю", "month": "месяц", "year": "год", "all": "всё время"}


async def balance_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    period = query.data.split(":")[1]
    start, end = period_bounds(period)
    user_id = update.effective_user.id
    conn = db()
    exp_rows = conn.execute("SELECT category, SUM(amount * share_pct / 100.0) as total FROM expenses WHERE user_id=? AND date>=? AND date<? GROUP BY category ORDER BY total DESC", (user_id, start, end)).fetchall()
    inc_rows = conn.execute("SELECT source, SUM(amount) as total FROM income WHERE user_id=? AND date>=? AND date<? GROUP BY source ORDER BY total DESC", (user_id, start, end)).fetchall()
    conn.close()
    total_exp = sum(r["total"] for r in exp_rows) if exp_rows else 0
    total_inc = sum(r["total"] for r in inc_rows) if inc_rows else 0
    net = total_inc - total_exp
    lines = [f"📊 Баланс за {PERIOD_LABELS[period]}\n", f"Доходы: {fmt(total_inc)}"]
    lines += [f"  {INCOME_SOURCES.get(r['source'], r['source'])}: {fmt(r['total'])}" for r in inc_rows]
    lines.append(f"\nРасходы: {fmt(total_exp)}")
    lines += [f"  {EXPENSE_CATEGORIES.get(r['category'], r['category'])}: {fmt(r['total'])} ({(r['total'] / total_exp * 100) if total_exp else 0:.0f}%)" for r in exp_rows]
    lines.append(f"\n💰 Итого: {'−' if net < 0 else ''}{fmt(abs(net))}")
    await query.edit_message_text("\n".join(lines))


# ---------- RECENT ----------
async def recent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = db()
    exp_rows = conn.execute("SELECT date, category, amount, note, share_pct FROM expenses WHERE user_id=? ORDER BY id DESC LIMIT 8", (user_id,)).fetchall()
    inc_rows = conn.execute("SELECT date, source, amount FROM income WHERE user_id=? ORDER BY id DESC LIMIT 8", (user_id,)).fetchall()
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


# ---------- IMPORT / OCR ----------
def import_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 Распознать", callback_data="import:process")],
        [InlineKeyboardButton("❌ Отмена", callback_data="import:cancel")],
    ])


def import_preview_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Добавить всё", callback_data="import:confirm")],
        [InlineKeyboardButton("❌ Отмена", callback_data="import:cancel")],
    ])


def normalize_merchant(name):
    name = (name or "").strip().lower()
    name = re.sub(r"[^a-zа-я0-9]+", " ", name, flags=re.I)
    return re.sub(r"\s+", " ", name).strip()


def get_saved_categories(user_id):
    conn = db()
    rows = conn.execute("SELECT merchant, category FROM merchant_categories WHERE user_id=?", (user_id,)).fetchall()
    conn.close()
    return {r["merchant"]: r["category"] for r in rows}


def save_merchant_category(user_id, merchant, category):
    key = normalize_merchant(merchant)
    if not key or category not in EXPENSE_CATEGORIES:
        return
    conn = db()
    conn.execute("INSERT OR REPLACE INTO merchant_categories (user_id, merchant, category) VALUES (?,?,?)", (user_id, key, category))
    conn.commit()
    conn.close()


def parse_json_from_model(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}|\[.*\]", text, flags=re.S)
    if not match:
        raise ValueError("Модель не вернула JSON")
    return json.loads(match.group(0))


def image_to_data_url(data: bytes, mime="image/jpeg"):
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def extract_transactions_from_images(images, saved_categories):
    if not OPENAI_API_KEY:
        raise RuntimeError("Не задан OPENAI_API_KEY")
    client = OpenAI(api_key=OPENAI_API_KEY)
    content = [{
        "type": "input_text",
        "text": (
            "Ты распознаёшь банковские операции с изображений. Верни ТОЛЬКО JSON без markdown. "
            "Нужно найти ВСЕ видимые операции, не пропуская строки и не придумывая данные. "
            "Для каждой операции: date (YYYY-MM-DD или пусто), merchant, amount (положительное число), "
            "currency, direction (expense/income), category (food/transport/tools/housing/services/other), "
            "note. Если дата на скриншоте указана без года, используй текущий год. "
            "Если сумма относится к возврату/зачислению, direction=income. "
            "Категорию выбирай по смыслу. Список уже известных магазинов и категорий: "
            + json.dumps(saved_categories, ensure_ascii=False)
            + ". Если магазин есть в этом списке, обязательно используй сохранённую категорию. "
            "Формат: {\"transactions\":[{...}]}. Не включай баланс счёта, комиссии, заголовки или дубликаты."
        ),
    }]
    for data, mime in images:
        content.append({"type": "input_image", "image_url": image_to_data_url(data, mime), "detail": "high"})
    response = client.responses.create(model=VISION_MODEL, input=[{"role": "user", "content": content}], store=False)
    parsed = parse_json_from_model(response.output_text)
    transactions = parsed.get("transactions", parsed if isinstance(parsed, list) else [])
    if not isinstance(transactions, list):
        raise ValueError("Некорректный формат ответа OCR")
    cleaned = []
    seen = set()
    current_year = datetime.now().year
    for t in transactions:
        if not isinstance(t, dict):
            continue
        try:
            amount = float(str(t.get("amount", "")).replace(",", "."))
        except Exception:
            continue
        if amount <= 0:
            continue
        date = str(t.get("date") or "")[:10]
        if re.fullmatch(r"\d{2}\.\d{2}", date):
            date = f"{current_year}-{date[3:5]}-{date[0:2]}"
        merchant = str(t.get("merchant") or "Неизвестно").strip()[:120]
        direction = "income" if t.get("direction") == "income" else "expense"
        category = t.get("category") if t.get("category") in EXPENSE_CATEGORIES else "other"
        saved = saved_categories.get(normalize_merchant(merchant))
        if saved:
            category = saved
        key = (date, normalize_merchant(merchant), round(amount, 2), direction)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append({
            "date": date or datetime.now().strftime("%Y-%m-%d"),
            "merchant": merchant,
            "amount": round(amount, 2),
            "currency": str(t.get("currency") or "PLN"),
            "direction": direction,
            "category": category,
            "note": str(t.get("note") or "")[:200],
        })
    return cleaned


async def import_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["import_images"] = []
    await update.message.reply_text(
        "📥 Импорт расходов\n\n"
        "Отправляй скриншоты операций из банковского приложения. Можно несколько подряд.\n"
        f"Максимум за один импорт: {MAX_IMPORT_IMAGES} изображений.\n\n"
        "Когда закончишь, нажми «🔎 Распознать».",
        reply_markup=import_keyboard(),
    )
    return IMPORT_PHOTOS


async def import_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    images = context.user_data.setdefault("import_images", [])
    if len(images) >= MAX_IMPORT_IMAGES:
        await update.message.reply_text(f"Достигнут лимит {MAX_IMPORT_IMAGES} изображений. Нажми «🔎 Распознать».", reply_markup=import_keyboard())
        return IMPORT_PHOTOS
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    data = bytes(await file.download_as_bytearray())
    images.append((data, "image/jpeg"))
    await update.message.reply_text(f"📸 Скриншот {len(images)}/{MAX_IMPORT_IMAGES} получен. Можешь отправить следующий или нажать «🔎 Распознать».", reply_markup=import_keyboard())
    return IMPORT_PHOTOS


async def import_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    images = context.user_data.get("import_images", [])
    if not images:
        await query.edit_message_text("Сначала отправь хотя бы один скриншот.", reply_markup=import_keyboard())
        return IMPORT_PHOTOS
    if not OPENAI_API_KEY:
        await query.edit_message_text("⚠️ Для распознавания нужен OPENAI_API_KEY в Railway → Variables.")
        return IMPORT_PHOTOS
    await query.edit_message_text(f"🔎 Распознаю {len(images)} скриншот(а)... Это может занять немного времени.")
    try:
        saved = get_saved_categories(update.effective_user.id)
        transactions = await asyncio.to_thread(extract_transactions_from_images, images, saved)
    except Exception as e:
        logger.exception("OCR import failed")
        await query.message.reply_text(f"❌ Не получилось распознать скриншоты.\n\nОшибка: {str(e)[:500]}", reply_markup=main_menu_keyboard())
        context.user_data.clear()
        return ConversationHandler.END
    if not transactions:
        await query.message.reply_text("Не нашёл операций. Попробуй отправить более чёткие скриншоты со списком операций.", reply_markup=main_menu_keyboard())
        context.user_data.clear()
        return ConversationHandler.END
    context.user_data["import_transactions"] = transactions
    lines = [f"🔎 Найдено операций: {len(transactions)}\n"]
    total_exp = 0
    total_inc = 0
    for i, t in enumerate(transactions, 1):
        cat = EXPENSE_CATEGORIES.get(t["category"], "🛍 Прочее")
        if t["direction"] == "income":
            total_inc += t["amount"]
            lines.append(f"{i}. {t['date']} · 🟢 {t['merchant']} · +{fmt(t['amount'])}")
        else:
            total_exp += t["amount"]
            lines.append(f"{i}. {t['date']} · {cat} · {t['merchant']} · −{fmt(t['amount'])}")
    lines.append(f"\n💸 Расходы: {fmt(total_exp)}")
    if total_inc:
        lines.append(f"💰 Зачисления: {fmt(total_inc)}")
    lines.append("\nПроверь список. Если всё верно, нажми «✅ Добавить всё».")
    # Telegram message limit safeguard
    text = "\n".join(lines)
    if len(text) > 3900:
        text = text[:3900] + "\n…"
    await query.message.reply_text(text, reply_markup=import_preview_keyboard())
    return IMPORT_CONFIRM


async def import_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    transactions = context.user_data.get("import_transactions", [])
    user_id = update.effective_user.id
    conn = db()
    added_exp = added_inc = 0
    for t in transactions:
        if t["direction"] == "expense":
            conn.execute("INSERT INTO expenses (user_id,date,category,amount,note,share_pct) VALUES (?,?,?,?,?,100)", (user_id, t["date"], t["category"], t["amount"], t["merchant"], 100))
            added_exp += 1
            save_key = normalize_merchant(t["merchant"])
            if save_key and t["category"] in EXPENSE_CATEGORIES:
                conn.execute("INSERT OR REPLACE INTO merchant_categories (user_id,merchant,category) VALUES (?,?,?)", (user_id, save_key, t["category"]))
        else:
            conn.execute("INSERT INTO income (user_id,date,source,amount) VALUES (?,?,?,?)", (user_id, t["date"], "bank_import", t["amount"]))
            added_inc += 1
    conn.commit()
    conn.close()
    context.user_data.clear()
    await query.edit_message_text(f"✅ Импорт завершён!\n\nДобавлено расходов: {added_exp}\nДобавлено зачислений: {added_inc}")
    return ConversationHandler.END


async def import_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text("Импорт отменён.")
    return ConversationHandler.END


# ---------- MINI APP API ----------
def validate_telegram_init_data(init_data: str):
    if not BOT_TOKEN or not init_data:
        return None
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = pairs.pop("hash", None)
        if not received_hash:
            return None
        data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, received_hash):
            return None
        return pairs
    except Exception:
        return None


def api_user(request: Request):
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    validated = validate_telegram_init_data(init_data)
    if not validated:
        raise HTTPException(status_code=401, detail="Invalid Telegram initData")
    try:
        user = json.loads(validated.get("user", "{}"))
        return int(user["id"])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Telegram user")


def api_stats(user_id, start, end):
    conn = db()
    exp_by_cat = conn.execute("SELECT category, SUM(amount*share_pct/100.0) total FROM expenses WHERE user_id=? AND date>=? AND date<? GROUP BY category ORDER BY total DESC", (user_id, start, end)).fetchall()
    inc_by_src = conn.execute("SELECT source, SUM(amount) total FROM income WHERE user_id=? AND date>=? AND date<? GROUP BY source ORDER BY total DESC", (user_id, start, end)).fetchall()
    daily = conn.execute("""
        SELECT date,
               COALESCE((SELECT SUM(amount*share_pct/100.0) FROM expenses e2 WHERE e2.user_id=? AND e2.date=e.date),0) expenses,
               COALESCE((SELECT SUM(amount) FROM income i2 WHERE i2.user_id=? AND i2.date=e.date),0) income
        FROM (SELECT date FROM expenses WHERE user_id=? AND date>=? AND date<? UNION SELECT date FROM income WHERE user_id=? AND date>=? AND date<?) e
        ORDER BY date
    """, (user_id, user_id, user_id, start, end, user_id, start, end)).fetchall()
    recent_rows = conn.execute("""
        SELECT date, category, amount, note, share_pct, 'expense' kind FROM expenses WHERE user_id=?
        UNION ALL
        SELECT date, source category, amount, '', 100 share_pct, 'income' kind FROM income WHERE user_id=?
        ORDER BY date DESC LIMIT 30
    """, (user_id, user_id)).fetchall()
    conn.close()
    expenses = [{"key": r["category"], "label": EXPENSE_CATEGORIES.get(r["category"], r["category"]), "value": round(r["total"] or 0, 2)} for r in exp_by_cat]
    incomes = [{"key": r["source"], "label": INCOME_SOURCES.get(r["source"], r["source"]), "value": round(r["total"] or 0, 2)} for r in inc_by_src]
    total_exp = sum(x["value"] for x in expenses)
    total_inc = sum(x["value"] for x in incomes)
    return {
        "income": round(total_inc, 2), "expenses": round(total_exp, 2), "net": round(total_inc-total_exp, 2),
        "income_by_source": incomes, "expenses_by_category": expenses,
        "daily": [{"date": r["date"], "income": round(r["income"] or 0, 2), "expenses": round(r["expenses"] or 0, 2)} for r in daily],
        "recent": [
            {"date": r["date"], "label": (EXPENSE_CATEGORIES.get(r["category"], r["category"]) if r["kind"] == "expense" else INCOME_SOURCES.get(r["category"], r["category"])), "amount": round((r["amount"] or 0) * (r["share_pct"] or 100)/100, 2), "kind": r["kind"], "note": r["note"] or ""}
            for r in recent_rows
        ],
    }


@app_web.get("/")
async def web_index():
    return FileResponse("web/index.html")


@app_web.get("/api/dashboard")
async def dashboard(request: Request, period: str = "month"):
    user_id = api_user(request)
    if period not in {"day", "week", "month", "year", "all"}:
        period = "month"
    start, end = period_bounds(period)
    data = api_stats(user_id, start, end)
    data["period"] = period
    return data


@app_web.get("/api/health")
async def health():
    return {"ok": True}


async def run_web_server():
    config = uvicorn.Config(app_web, host=WEB_HOST, port=WEB_PORT, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


def run_web_thread():
    asyncio.run(run_web_server())


def setup_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("^📊 Баланс$"), balance_start))
    app.add_handler(CallbackQueryHandler(balance_show, pattern="^bal:"))
    app.add_handler(MessageHandler(filters.Regex("^📈 Статистика$"), lambda u, c: open_mini_app(u, c)))
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

    import_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📥 Импорт$"), import_start)],
        states={
            IMPORT_PHOTOS: [
                MessageHandler(filters.PHOTO, import_photo),
                CallbackQueryHandler(import_process, pattern="^import:process$"),
                CallbackQueryHandler(import_cancel, pattern="^import:cancel$"),
            ],
            IMPORT_CONFIRM: [
                CallbackQueryHandler(import_confirm, pattern="^import:confirm$"),
                CallbackQueryHandler(import_cancel, pattern="^import:cancel$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(import_conv)


async def open_mini_app(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not WEBAPP_URL:
        await update.message.reply_text("📈 Mini App ещё не настроен. Добавь WEBAPP_URL в Railway после публикации приложения.")
        return
    from telegram import WebAppInfo
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📈 Открыть статистику", web_app=WebAppInfo(url=WEBAPP_URL))]])
    await update.message.reply_text("Открывай финансовую панель 👇", reply_markup=keyboard)


def main():
    if not BOT_TOKEN:
        raise SystemExit("Переменная окружения BOT_TOKEN не задана")
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    setup_handlers(app)
    threading.Thread(target=run_web_thread, daemon=True).start()
    logger.info("Web server started on %s:%s", WEB_HOST, WEB_PORT)
    logger.info("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
