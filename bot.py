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

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
    WebAppInfo,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


BOT_TOKEN = os.environ.get("BOT_TOKEN")
DB_PATH = os.environ.get("DB_PATH", "finances.db")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "")


# ============================================================
# CATEGORIES
# ============================================================

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


# ============================================================
# CONVERSATION STATES
# ============================================================

(
    EXP_CATEGORY,
    EXP_AMOUNT,
    EXP_NOTE,
    EXP_SHARE,

    INC_SOURCE,
    INC_UBER_AMOUNT,
    INC_HOURS,
    INC_RATE,
    INC_OFFICIAL_HOURS,
    INC_ZUS,
    INC_TAXPCT,
) = range(11)


# ============================================================
# DATABASE
# ============================================================

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
    return (
        f"{n:,.2f}"
        .replace(",", " ")
        .replace(".", ",")
        + " zł"
    )


def period_bounds(period: str):

    now = datetime.now()

    if period == "day":

        start = now.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        end = start + timedelta(days=1)

    elif period == "week":

        start = (
            now - timedelta(days=now.weekday())
        ).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        end = start + timedelta(days=7)

    elif period == "month":

        start = now.replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        if start.month == 12:

            end = start.replace(
                year=start.year + 1,
                month=1,
            )

        else:

            end = start.replace(
                month=start.month + 1
            )

    elif period == "year":

        start = now.replace(
            month=1,
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        end = start.replace(
            year=start.year + 1
        )

    else:

        start = datetime(2000, 1, 1)
        end = datetime(2100, 1, 1)

    return (
        start.strftime("%Y-%m-%d"),
        end.strftime("%Y-%m-%d"),
    )


# ============================================================
# MAIN MENU
# ============================================================

def main_menu_keyboard():

    rows = [
        ["➕ Расход", "➕ Доход"],
        ["📊 Баланс", "🗒 Последние записи"],
        ["🗑 Удалить запись"],
    ]

    if WEBAPP_URL:

        rows.append([
            KeyboardButton(
                "📊 Открыть приложение",
                web_app=WebAppInfo(url=WEBAPP_URL),
            )
        ])

    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
    )


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await update.message.reply_text(
        "Привет! Я твой финансовый трекер.\n\n"
        "Помогу вести доходы (стройка + Uber) "
        "и расходы по категориям.\n\n"
        "Выбери действие на клавиатуре ниже 👇",
        reply_markup=main_menu_keyboard(),
    )


async def cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    context.user_data.clear()

    await update.message.reply_text(
        "Отменено.",
        reply_markup=main_menu_keyboard(),
    )

    return ConversationHandler.END


# ============================================================
# ADD EXPENSE
# ============================================================

async def expense_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    context.user_data.clear()

    buttons = [
        [
            InlineKeyboardButton(
                value,
                callback_data=f"cat:{key}",
            )
        ]
        for key, value in EXPENSE_CATEGORIES.items()
    ]

    await update.message.reply_text(
        "Выбери категорию расхода:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

    return EXP_CATEGORY


async def expense_category(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    category = query.data.split(":")[1]

    context.user_data["category"] = category

    await query.edit_message_text(
        f"Категория: "
        f"{EXPENSE_CATEGORIES[category]}\n\n"
        f"Введи сумму, zł:"
    )

    return EXP_AMOUNT


async def expense_amount(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    try:

        amount = float(
            update.message.text.replace(",", ".")
        )

        if amount <= 0:
            raise ValueError

    except ValueError:

        await update.message.reply_text(
            "Не понял сумму. "
            "Введи число, например 45.50"
        )

        return EXP_AMOUNT

    context.user_data["amount"] = amount

    await update.message.reply_text(
        "Заметка (например, магазин)? "
        "Или отправь «-», если не нужна."
    )

    return EXP_NOTE


async def expense_note(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    note = update.message.text.strip()

    context.user_data["note"] = (
        ""
        if note == "-"
        else note
    )

    buttons = [[
        InlineKeyboardButton(
            "100%",
            callback_data="share:100",
        ),
        InlineKeyboardButton(
            "75%",
            callback_data="share:75",
        ),
        InlineKeyboardButton(
            "50%",
            callback_data="share:50",
        ),
        InlineKeyboardButton(
            "25%",
            callback_data="share:25",
        ),
    ]]

    await update.message.reply_text(
        "Какая доля суммы твоя? "
        "(если делите с кем-то расходы)",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

    return EXP_SHARE


async def expense_share(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    pct = float(
        query.data.split(":")[1]
    )

    data = context.user_data

    conn = db()

    conn.execute(
        """
        INSERT INTO expenses
        (
            user_id,
            date,
            category,
            amount,
            note,
            share_pct
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            update.effective_user.id,
            datetime.now().strftime("%Y-%m-%d"),
            data["category"],
            data["amount"],
            data["note"],
            pct,
        ),
    )

    conn.commit()
    conn.close()

    counted = (
        data["amount"] * pct / 100
    )

    await query.edit_message_text(
        f"✅ Добавлено: "
        f"{EXPENSE_CATEGORIES[data['category']]} "
        f"— {fmt(data['amount'])} "
        f"({pct:.0f}% → {fmt(counted)})"
    )

    context.user_data.clear()

    return ConversationHandler.END


# ============================================================
# ADD INCOME
# ============================================================

async def income_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    context.user_data.clear()

    buttons = [
        [
            InlineKeyboardButton(
                value,
                callback_data=f"src:{key}",
            )
        ]
        for key, value in INCOME_SOURCES.items()
    ]

    await update.message.reply_text(
        "Выбери источник дохода:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

    return INC_SOURCE


async def income_source(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    source = query.data.split(":")[1]

    context.user_data["source"] = source

    if source == "uber":

        await query.edit_message_text(
            "Сумма на руки (netto), zł:"
        )

        return INC_UBER_AMOUNT

    await query.edit_message_text(
        "Сколько часов отработано?"
    )

    return INC_HOURS


async def income_uber_amount(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    try:

        amount = float(
            update.message.text.replace(",", ".")
        )

        if amount <= 0:
            raise ValueError

    except ValueError:

        await update.message.reply_text(
            "Не понял сумму. Введи число."
        )

        return INC_UBER_AMOUNT

    conn = db()

    conn.execute(
        """
        INSERT INTO income
        (
            user_id,
            date,
            source,
            amount
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            update.effective_user.id,
            datetime.now().strftime("%Y-%m-%d"),
            "uber",
            amount,
        ),
    )

    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ Доход Uber: {fmt(amount)}",
        reply_markup=main_menu_keyboard(),
    )

    context.user_data.clear()

    return ConversationHandler.END


async def _ask_float(
    update,
    context,
    key,
    next_state,
    prompt,
):

    try:

        value = float(
            update.message.text.replace(",", ".")
        )

        if value < 0:
            raise ValueError

    except ValueError:

        await update.message.reply_text(
            "Не понял число, попробуй ещё раз."
        )

        return None

    context.user_data[key] = value

    await update.message.reply_text(prompt)

    return next_state


async def income_hours(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    result = await _ask_float(
        update,
        context,
        "hours",
        INC_RATE,
        "Ставка, zł/час (brutto)?",
    )

    return result if result else INC_HOURS


async def income_rate(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    result = await _ask_float(
        update,
        context,
        "rate",
        INC_OFFICIAL_HOURS,
        "Сколько из них официальных часов?",
    )

    return result if result else INC_RATE


async def income_official_hours(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    result = await _ask_float(
        update,
        context,
        "official_hours",
        INC_ZUS,
        "Сумма ZUS за этот период, zł?",
    )

    return (
        result
        if result
        else INC_OFFICIAL_HOURS
    )


async def income_zus(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    result = await _ask_float(
        update,
        context,
        "zus",
        INC_TAXPCT,
        "Налог с наличных, %? (обычно 10)",
    )

    return result if result else INC_ZUS


async def income_taxpct(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    try:

        tax_pct = float(
            update.message.text.replace(",", ".")
        )

    except ValueError:

        await update.message.reply_text(
            "Не понял число, попробуй ещё раз."
        )

        return INC_TAXPCT

    data = context.user_data

    hours = data["hours"]
    rate = data["rate"]
    official_hours = data["official_hours"]
    zus = data["zus"]

    gross = hours * rate

    official_amount = (
        min(
            official_hours,
            hours,
        )
        * rate
    )

    cash_amount = max(
        gross - official_amount,
        0,
    )

    cash_tax = (
        cash_amount
        * tax_pct
        / 100
    )

    net = (
        official_amount - zus
    ) + (
        cash_amount - cash_tax
    )

    conn = db()

    conn.execute(
        """
        INSERT INTO income
        (
            user_id,
            date,
            source,
            amount,
            gross,
            hours,
            rate,
            official_hours,
            zus,
            cash_tax_pct
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            update.effective_user.id,
            datetime.now().strftime("%Y-%m-%d"),
            "stroika",
            net,
            gross,
            hours,
            rate,
            official_hours,
            zus,
            tax_pct,
        ),
    )

    conn.commit()
    conn.close()

    text = (
        "✅ Стройка добавлена\n\n"
        f"Brutto: {fmt(gross)}\n"
        f"− ZUS: {fmt(zus)}\n"
        f"− налог с наличных "
        f"({tax_pct:.0f}%): {fmt(cash_tax)}\n"
        "— — — — —\n"
        f"Netto на руки: {fmt(net)}"
    )

    await update.message.reply_text(
        text,
        reply_markup=main_menu_keyboard(),
    )

    context.user_data.clear()

    return ConversationHandler.END


# ============================================================
# BALANCE
# ============================================================

PERIOD_LABELS = {
    "day": "день",
    "week": "неделю",
    "month": "месяц",
    "year": "год",
    "all": "всё время",
}


async def balance_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    buttons = [[
        InlineKeyboardButton(
            "День",
            callback_data="bal:day",
        ),
        InlineKeyboardButton(
            "Неделя",
            callback_data="bal:week",
        ),
        InlineKeyboardButton(
            "Месяц",
            callback_data="bal:month",
        ),
    ], [
        InlineKeyboardButton(
            "Год",
            callback_data="bal:year",
        ),
        InlineKeyboardButton(
            "Всё время",
            callback_data="bal:all",
        ),
    ]]

    await update.message.reply_text(
        "За какой период показать баланс?",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def balance_show(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    period = query.data.split(":")[1]

    start, end = period_bounds(period)

    user_id = update.effective_user.id

    conn = db()

    exp_rows = conn.execute(
        """
        SELECT
            category,
            SUM(
                amount * share_pct / 100.0
            ) AS total
        FROM expenses
        WHERE
            user_id=?
            AND date>=?
            AND date<?
        GROUP BY category
        ORDER BY total DESC
        """,
        (
            user_id,
            start,
            end,
        ),
    ).fetchall()

    inc_rows = conn.execute(
        """
        SELECT
            source,
            SUM(amount) AS total
        FROM income
        WHERE
            user_id=?
            AND date>=?
            AND date<?
        GROUP BY source
        ORDER BY total DESC
        """,
        (
            user_id,
            start,
            end,
        ),
    ).fetchall()

    conn.close()

    total_exp = (
        sum(r["total"] for r in exp_rows)
        if exp_rows
        else 0
    )

    total_inc = (
        sum(r["total"] for r in inc_rows)
        if inc_rows
        else 0
    )

    net = total_inc - total_exp

    lines = [
        f"📊 Баланс за "
        f"{PERIOD_LABELS[period]}\n"
    ]

    lines.append(
        f"Доходы: {fmt(total_inc)}"
    )

    for row in inc_rows:

        lines.append(
            f"  "
            f"{INCOME_SOURCES.get(row['source'], row['source'])}: "
            f"{fmt(row['total'])}"
        )

    lines.append(
        f"\nРасходы: {fmt(total_exp)}"
    )

    for row in exp_rows:

        pct = (
            row["total"]
            / total_exp
            * 100
            if total_exp
            else 0
        )

        lines.append(
            f"  "
            f"{EXPENSE_CATEGORIES.get(row['category'], row['category'])}: "
            f"{fmt(row['total'])} "
            f"({pct:.0f}%)"
        )

    lines.append(
        f"\n💰 Итого: "
        f"{'−' if net < 0 else ''}"
        f"{fmt(abs(net))}"
    )

    await query.edit_message_text(
        "\n".join(lines)
    )


# ============================================================
# RECENT OPERATIONS
# ============================================================

async def recent(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user_id = update.effective_user.id

    conn = db()

    exp_rows = conn.execute(
        """
        SELECT
            date,
            category,
            amount,
            note,
            share_pct
        FROM expenses
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 8
        """,
        (user_id,),
    ).fetchall()

    inc_rows = conn.execute(
        """
        SELECT
            date,
            source,
            amount
        FROM income
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 8
        """,
        (user_id,),
    ).fetchall()

    conn.close()

    lines = [
        "🗒 Последние расходы:"
    ]

    if not exp_rows:

        lines.append(
            "  пока нет записей"
        )

    for row in exp_rows:

        counted = (
            row["amount"]
            * row["share_pct"]
            / 100
        )

        share_note = (
            f" ({row['share_pct']:.0f}%)"
            if row["share_pct"] != 100
            else ""
        )

        lines.append(
            f"  "
            f"{row['date']} · "
            f"{EXPENSE_CATEGORIES.get(row['category'], row['category'])} · "
            f"{fmt(counted)}"
            f"{share_note} · "
            f"{row['note'] or ''}"
        )

    lines.append(
        "\n🗒 Последние доходы:"
    )

    if not inc_rows:

        lines.append(
            "  пока нет записей"
        )

    for row in inc_rows:

        lines.append(
            f"  "
            f"{row['date']} · "
            f"{INCOME_SOURCES.get(row['source'], row['source'])} · "
            f"{fmt(row['amount'])}"
        )

    await update.message.reply_text(
        "\n".join(lines)
    )


# ============================================================
# DELETE OPERATION
# ============================================================

async def delete_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user_id = update.effective_user.id

    conn = db()

    expenses = conn.execute(
        """
        SELECT
            id,
            date,
            category,
            amount,
            note,
            share_pct
        FROM expenses
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 8
        """,
        (user_id,),
    ).fetchall()

    incomes = conn.execute(
        """
        SELECT
            id,
            date,
            source,
            amount
        FROM income
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 8
        """,
        (user_id,),
    ).fetchall()

    conn.close()

    operations = []

    for row in expenses:

        counted = (
            row["amount"]
            * row["share_pct"]
            / 100
        )

        operations.append({
            "id": row["id"],
            "type": "expense",
            "date": row["date"],
            "label": EXPENSE_CATEGORIES.get(
                row["category"],
                row["category"],
            ),
            "amount": counted,
            "note": row["note"] or "",
        })

    for row in incomes:

        operations.append({
            "id": row["id"],
            "type": "income",
            "date": row["date"],
            "label": INCOME_SOURCES.get(
                row["source"],
                row["source"],
            ),
            "amount": row["amount"],
            "note": "",
        })

    operations.sort(
        key=lambda item: item["date"],
        reverse=True,
    )

    operations = operations[:10]

    if not operations:

        await update.message.reply_text(
            "🗑 Удалять пока нечего.",
            reply_markup=main_menu_keyboard(),
        )

        return

    buttons = []

    for operation in operations:

        sign = (
            "+"
            if operation["type"] == "income"
            else "−"
        )

        text = (
            f"{sign} "
            f"{operation['label']} · "
            f"{fmt(operation['amount'])}"
        )

        buttons.append([
            InlineKeyboardButton(
                text,
                callback_data=(
                    f"del:"
                    f"{operation['type']}:"
                    f"{operation['id']}"
                ),
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "✖️ Отмена",
            callback_data="del:cancel",
        )
    ])

    await update.message.reply_text(
        "🗑 Выбери операцию, "
        "которую хочешь удалить:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def delete_select(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    if query.data == "del:cancel":

        await query.edit_message_text(
            "Удаление отменено."
        )

        return

    parts = query.data.split(":")

    if len(parts) != 3:

        await query.edit_message_text(
            "❌ Не удалось определить операцию."
        )

        return

    operation_type = parts[1]

    try:
        operation_id = int(parts[2])
    except ValueError:

        await query.edit_message_text(
            "❌ Некорректный ID операции."
        )

        return

    if operation_type not in {
        "expense",
        "income",
    }:

        await query.edit_message_text(
            "❌ Неизвестный тип операции."
        )

        return

    user_id = update.effective_user.id

    conn = db()

    if operation_type == "expense":

        row = conn.execute(
            """
            SELECT
                id,
                date,
                category,
                amount,
                note,
                share_pct
            FROM expenses
            WHERE
                id=?
                AND user_id=?
            """,
            (
                operation_id,
                user_id,
            ),
        ).fetchone()

        if not row:

            conn.close()

            await query.edit_message_text(
                "❌ Операция не найдена."
            )

            return

        counted = (
            row["amount"]
            * row["share_pct"]
            / 100
        )

        label = EXPENSE_CATEGORIES.get(
            row["category"],
            row["category"],
        )

        description = (
            f"💸 {label}\n"
            f"Сумма: {fmt(counted)}\n"
            f"Дата: {row['date']}"
        )

    else:

        row = conn.execute(
            """
            SELECT
                id,
                date,
                source,
                amount
            FROM income
            WHERE
                id=?
                AND user_id=?
            """,
            (
                operation_id,
                user_id,
            ),
        ).fetchone()

        if not row:

            conn.close()

            await query.edit_message_text(
                "❌ Операция не найдена."
            )

            return

        label = INCOME_SOURCES.get(
            row["source"],
            row["source"],
        )

        description = (
            f"💰 {label}\n"
            f"Сумма: {fmt(row['amount'])}\n"
            f"Дата: {row['date']}"
        )

    conn.close()

    context.user_data["delete_type"] = (
        operation_type
    )

    context.user_data["delete_id"] = (
        operation_id
    )

    buttons = [[
        InlineKeyboardButton(
            "🗑 Да, удалить",
            callback_data="del_confirm",
        )
    ], [
        InlineKeyboardButton(
            "✖️ Отмена",
            callback_data="del_cancel",
        )
    ]]

    await query.edit_message_text(
        "⚠️ Удалить эту операцию?\n\n"
        f"{description}",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def delete_confirm(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    operation_type = context.user_data.get(
        "delete_type"
    )

    operation_id = context.user_data.get(
        "delete_id"
    )

    if not operation_type or not operation_id:

        await query.edit_message_text(
            "❌ Операция больше недоступна."
        )

        return

    user_id = update.effective_user.id

    conn = db()

    if operation_type == "expense":

        cursor = conn.execute(
            """
            DELETE FROM expenses
            WHERE
                id=?
                AND user_id=?
            """,
            (
                operation_id,
                user_id,
            ),
        )

    else:

        cursor = conn.execute(
            """
            DELETE FROM income
            WHERE
                id=?
                AND user_id=?
            """,
            (
                operation_id,
                user_id,
            ),
        )

    conn.commit()

    deleted = cursor.rowcount

    conn.close()

    context.user_data.pop(
        "delete_type",
        None,
    )

    context.user_data.pop(
        "delete_id",
        None,
    )

    if deleted:

        await query.edit_message_text(
            "✅ Операция удалена."
        )

    else:

        await query.edit_message_text(
            "❌ Операция уже была удалена "
            "или не найдена."
        )


async def delete_cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    context.user_data.pop(
        "delete_type",
        None,
    )

    context.user_data.pop(
        "delete_id",
        None,
    )

    await query.edit_message_text(
        "Удаление отменено."
    )


# ============================================================
# MINI APP API
# ============================================================

def _telegram_user_id(init_data: str):

    if not init_data or not BOT_TOKEN:
        return None

    try:

        from urllib.parse import parse_qsl

        pairs = dict(
            parse_qsl(
                init_data,
                keep_blank_values=True,
            )
        )

        received_hash = pairs.pop(
            "hash",
            None,
        )

        if not received_hash:
            return None

        data_check = "\n".join(
            f"{key}={pairs[key]}"
            for key in sorted(pairs)
        )

        secret = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode(),
            hashlib.sha256,
        ).digest()

        calculated_hash = hmac.new(
            secret,
            data_check.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(
            calculated_hash,
            received_hash,
        ):
            return None

        user = json.loads(
            pairs.get(
                "user",
                "{}",
            )
        )

        return (
            int(user.get("id"))
            if user.get("id")
            else None
        )

    except Exception:

        return None


def _dashboard(
    user_id: int,
    period: str,
):

    start, end = period_bounds(period)

    conn = db()

    income = conn.execute(
        """
        SELECT
            COALESCE(SUM(amount), 0)
        FROM income
        WHERE
            user_id=?
            AND date>=?
            AND date<?
        """,
        (
            user_id,
            start,
            end,
        ),
    ).fetchone()[0]

    expenses = conn.execute(
        """
        SELECT
            COALESCE(
                SUM(
                    amount
                    * share_pct
                    / 100.0
                ),
                0
            )
        FROM expenses
        WHERE
            user_id=?
            AND date>=?
            AND date<?
        """,
        (
            user_id,
            start,
            end,
        ),
    ).fetchone()[0]

    income_sources = conn.execute(
        """
        SELECT
            source,
            SUM(amount) AS total
        FROM income
        WHERE
            user_id=?
            AND date>=?
            AND date<?
        GROUP BY source
        ORDER BY total DESC
        """,
        (
            user_id,
            start,
            end,
        ),
    ).fetchall()

    expense_categories = conn.execute(
        """
        SELECT
            category,
            SUM(
                amount
                * share_pct
                / 100.0
            ) AS total
        FROM expenses
        WHERE
            user_id=?
            AND date>=?
            AND date<?
        GROUP BY category
        ORDER BY total DESC
        """,
        (
            user_id,
            start,
            end,
        ),
    ).fetchall()

    recent_expenses = conn.execute(
        """
        SELECT
            date,
            category AS label,
            amount * share_pct / 100.0 AS amount,
            note
        FROM expenses
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 6
        """,
        (user_id,),
    ).fetchall()

    recent_income = conn.execute(
        """
        SELECT
            date,
            source AS label,
            amount,
            '' AS note
        FROM income
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 6
        """,
        (user_id,),
    ).fetchall()

    conn.close()

    daily = defaultdict(
        lambda: [0.0, 0.0]
    )

    conn = db()

    income_daily = conn.execute(
        """
        SELECT
            date,
            SUM(amount) AS total
        FROM income
        WHERE
            user_id=?
            AND date>=?
            AND date<?
        GROUP BY date
        """,
        (
            user_id,
            start,
            end,
        ),
    )

    for row in income_daily:

        daily[row["date"]][0] = (
            row["total"]
        )

    expense_daily = conn.execute(
        """
        SELECT
            date,
            SUM(
                amount
                * share_pct
                / 100.0
            ) AS total
        FROM expenses
        WHERE
            user_id=?
            AND date>=?
            AND date<?
        GROUP BY date
        """,
        (
            user_id,
            start,
            end,
        ),
    )

    for row in expense_daily:

        daily[row["date"]][1] = (
            row["total"]
        )

    conn.close()

    dates = sorted(daily)

    recent = []

    for row in recent_income:

        recent.append({
            "date": row["date"],
            "label": INCOME_SOURCES.get(
                row["label"],
                row["label"],
            ),
            "amount": float(
                row["amount"]
            ),
            "note": row["note"],
            "kind": "income",
        })

    for row in recent_expenses:

        recent.append({
            "date": row["date"],
            "label": EXPENSE_CATEGORIES.get(
                row["label"],
                row["label"],
            ),
            "amount": float(
                row["amount"]
            ),
            "note": row["note"],
            "kind": "expense",
        })

    recent.sort(
        key=lambda item: item["date"],
        reverse=True,
    )

    return {
        "income": float(income),
        "expenses": float(expenses),
        "net": float(
            income - expenses
        ),

        "income_by_source": [
            {
                "label": INCOME_SOURCES.get(
                    row["source"],
                    row["source"],
                ),
                "value": float(
                    row["total"]
                ),
            }
            for row in income_sources
        ],

        "expenses_by_category": [
            {
                "label": EXPENSE_CATEGORIES.get(
                    row["category"],
                    row["category"],
                ),
                "value": float(
                    row["total"]
                ),
            }
            for row in expense_categories
        ],

        "daily": [
            {
                "date": date,
                "income": daily[date][0],
                "expenses": daily[date][1],
            }
            for date in dates
        ],

        "recent": recent[:10],
    }


def run_web_server():

    from fastapi import (
        FastAPI,
        Header,
        HTTPException,
    )

    from fastapi.responses import FileResponse

    import uvicorn

    api = FastAPI()

    @api.get("/")
    def index():

        return FileResponse(
            os.path.join(
                os.path.dirname(__file__),
                "web",
                "index.html",
            )
        )

    @api.get("/api/dashboard")
    def dashboard(
        period: str = "month",
        x_telegram_init_data: str = Header(
            default=""
        ),
    ):

        user_id = _telegram_user_id(
            x_telegram_init_data
        )

        if not user_id:

            raise HTTPException(
                status_code=401,
                detail="Invalid Telegram init data",
            )

        if period not in {
            "day",
            "week",
            "month",
            "year",
            "all",
        }:

            period = "month"

        return _dashboard(
            user_id,
            period,
        )

    port = int(
        os.environ.get(
            "PORT",
            "8080",
        )
    )

    uvicorn.run(
        api,
        host="0.0.0.0",
        port=port,
        log_level="info",
    )


# ============================================================
# MAIN
# ============================================================

def main():

    if not BOT_TOKEN:

        raise SystemExit(
            "Переменная окружения BOT_TOKEN не задана"
        )

    init_db()

    if WEBAPP_URL:

        logger.info(
            "Mini App URL configured: %s",
            WEBAPP_URL,
        )

    threading.Thread(
        target=run_web_server,
        daemon=True,
    ).start()

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )


    # --------------------------------------------------------
    # BASIC COMMANDS
    # --------------------------------------------------------

    app.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    app.add_handler(
        MessageHandler(
            filters.Regex("^📊 Баланс$"),
            balance_start,
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            balance_show,
            pattern="^bal:",
        )
    )

    app.add_handler(
        MessageHandler(
            filters.Regex("^🗒 Последние записи$"),
            recent,
        )
    )


    # --------------------------------------------------------
    # DELETE
    # --------------------------------------------------------

    app.add_handler(
        MessageHandler(
            filters.Regex("^🗑 Удалить запись$"),
            delete_start,
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            delete_select,
            pattern=r"^del:(expense|income):\d+$|^del:cancel$",
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            delete_confirm,
            pattern=r"^del_confirm$",
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            delete_cancel,
            pattern=r"^del_cancel$",
        )
    )


    # --------------------------------------------------------
    # EXPENSE CONVERSATION
    # --------------------------------------------------------

    expense_conv = ConversationHandler(

        entry_points=[
            MessageHandler(
                filters.Regex("^➕ Расход$"),
                expense_start,
            )
        ],

        states={

            EXP_CATEGORY: [
                CallbackQueryHandler(
                    expense_category,
                    pattern="^cat:",
                )
            ],

            EXP_AMOUNT: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    expense_amount,
                )
            ],

            EXP_NOTE: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    expense_note,
                )
            ],

            EXP_SHARE: [
                CallbackQueryHandler(
                    expense_share,
                    pattern="^share:",
                )
            ],
        },

        fallbacks=[
            CommandHandler(
                "cancel",
                cancel,
            )
        ],
    )

    app.add_handler(
        expense_conv
    )


    # --------------------------------------------------------
    # INCOME CONVERSATION
    # --------------------------------------------------------

    income_conv = ConversationHandler(

        entry_points=[
            MessageHandler(
                filters.Regex("^➕ Доход$"),
                income_start,
            )
        ],

        states={

            INC_SOURCE: [
                CallbackQueryHandler(
                    income_source,
                    pattern="^src:",
                )
            ],

            INC_UBER_AMOUNT: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    income_uber_amount,
                )
            ],

            INC_HOURS: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    income_hours,
                )
            ],

            INC_RATE: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    income_rate,
                )
            ],

            INC_OFFICIAL_HOURS: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    income_official_hours,
                )
            ],

            INC_ZUS: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    income_zus,
                )
            ],

            INC_TAXPCT: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    income_taxpct,
                )
            ],
        },

        fallbacks=[
            CommandHandler(
                "cancel",
                cancel,
            )
        ],
    )

    app.add_handler(
        income_conv
    )


    logger.info(
        "Bot started"
    )

    app.run_polling()


if __name__ == "__main__":
    main()
