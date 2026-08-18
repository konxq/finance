import os
import sqlite3
import logging
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
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DB_PATH = os.environ.get("DB_PATH", "finances.db")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "")


# =========================================================
# КАТЕГОРИИ
# =========================================================

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


# =========================================================
# СОСТОЯНИЯ ДИАЛОГОВ
# =========================================================

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


# =========================================================
# DATABASE
# =========================================================

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


# =========================================================
# ПЕРИОДЫ
# =========================================================

def period_bounds(period: str):
    now = datetime.now()

    if period == "day":
        start = now.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )
        end = start + timedelta(days=1)

    elif period == "week":
        start = (
            now - timedelta(days=now.weekday())
        ).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )
        end = start + timedelta(days=7)

    elif period == "month":
        start = now.replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )

        if start.month == 12:
            end = start.replace(
                year=start.year + 1,
                month=1
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
            microsecond=0
        )
        end = start.replace(year=start.year + 1)

    else:
        start = datetime(2000, 1, 1)
        end = datetime(2100, 1, 1)

    return (
        start.strftime("%Y-%m-%d"),
        end.strftime("%Y-%m-%d")
    )


PERIOD_LABELS = {
    "day": "день",
    "week": "неделю",
    "month": "месяц",
    "year": "год",
    "all": "всё время",
}


# =========================================================
# ГЛАВНОЕ МЕНЮ
# =========================================================

def main_menu():
    rows = [
        [
            InlineKeyboardButton(
                "➕ Расход",
                callback_data="menu:expense"
            ),
            InlineKeyboardButton(
                "➕ Доход",
                callback_data="menu:income"
            ),
        ],
        [
            InlineKeyboardButton(
                "📊 Баланс",
                callback_data="menu:balance"
            ),
            InlineKeyboardButton(
                "🗒 Последние записи",
                callback_data="menu:recent"
            ),
        ],
        [
            InlineKeyboardButton(
                "🗑 Удалить запись",
                callback_data="menu:delete"
            ),
        ],
    ]

    if WEBAPP_URL:
        rows.append([
            InlineKeyboardButton(
                "📱 Открыть приложение",
                web_app=WebAppInfo(url=WEBAPP_URL)
            )
        ])

    return InlineKeyboardMarkup(rows)


def cancel_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "❌ Отмена",
                callback_data="menu:cancel"
            )
        ]
    ])


async def show_menu_message(update, text="Выбери действие:"):
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            text,
            reply_markup=main_menu()
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=main_menu()
        )


# =========================================================
# START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    user = update.effective_user
    name = user.first_name or "друг"

    text = (
        f"Привет, {name}! 👋\n\n"
        "💰 <b>Financebot</b>\n"
        "Твой личный финансовый трекер.\n\n"
        "Здесь можно записывать доходы и расходы, "
        "смотреть баланс и открывать аналитику.\n\n"
        "Выбери действие:"
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu()
    )


# =========================================================
# ГЛАВНОЕ МЕНЮ CALLBACK
# =========================================================

async def menu_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data.clear()

    buttons = [
        [
            InlineKeyboardButton(
                value,
                callback_data=f"cat:{key}"
            )
        ]
        for key, value in EXPENSE_CATEGORIES.items()
    ]

    buttons.append([
        InlineKeyboardButton(
            "❌ Отмена",
            callback_data="menu:cancel"
        )
    ])

    await query.edit_message_text(
        "💸 <b>Добавление расхода</b>\n\n"
        "Выбери категорию:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

    return EXP_CATEGORY


async def menu_income(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data.clear()

    buttons = [
        [
            InlineKeyboardButton(
                value,
                callback_data=f"src:{key}"
            )
        ]
        for key, value in INCOME_SOURCES.items()
    ]

    buttons.append([
        InlineKeyboardButton(
            "❌ Отмена",
            callback_data="menu:cancel"
        )
    ])

    await query.edit_message_text(
        "💰 <b>Добавление дохода</b>\n\n"
        "Выбери источник:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

    return INC_SOURCE


async def menu_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    buttons = [
        [
            InlineKeyboardButton(
                "Сегодня",
                callback_data="bal:day"
            ),
            InlineKeyboardButton(
                "Неделя",
                callback_data="bal:week"
            ),
        ],
        [
            InlineKeyboardButton(
                "Месяц",
                callback_data="bal:month"
            ),
            InlineKeyboardButton(
                "Год",
                callback_data="bal:year"
            ),
        ],
        [
            InlineKeyboardButton(
                "Всё время",
                callback_data="bal:all"
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ Назад",
                callback_data="menu:home"
            )
        ],
    ]

    await query.edit_message_text(
        "📊 <b>Баланс</b>\n\n"
        "За какой период показать статистику?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def menu_recent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    conn = db()

    exp_rows = conn.execute(
        """
        SELECT date, category, amount, note, share_pct
        FROM expenses
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 8
        """,
        (user_id,)
    ).fetchall()

    inc_rows = conn.execute(
        """
        SELECT date, source, amount
        FROM income
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 8
        """,
        (user_id,)
    ).fetchall()

    conn.close()

    lines = ["🗒 <b>Последние записи</b>\n"]

    if exp_rows:
        lines.append("💸 <b>Расходы:</b>")

        for r in exp_rows:
            counted = r["amount"] * r["share_pct"] / 100

            share_note = (
                f" ({r['share_pct']:.0f}%)"
                if r["share_pct"] != 100
                else ""
            )

            note = (
                f" · {r['note']}"
                if r["note"]
                else ""
            )

            lines.append(
                f"{r['date']} · "
                f"{EXPENSE_CATEGORIES.get(r['category'], r['category'])} · "
                f"{fmt(counted)}"
                f"{share_note}"
                f"{note}"
            )
    else:
        lines.append("💸 Расходов пока нет.")

    lines.append("")

    if inc_rows:
        lines.append("💰 <b>Доходы:</b>")

        for r in inc_rows:
            lines.append(
                f"{r['date']} · "
                f"{INCOME_SOURCES.get(r['source'], r['source'])} · "
                f"{fmt(r['amount'])}"
            )
    else:
        lines.append("💰 Доходов пока нет.")

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "⬅️ Назад",
                    callback_data="menu:home"
                )
            ]
        ])
    )


async def menu_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await show_menu_message(update)


async def menu_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "❌ Действие отменено.\n\nВыбери действие:",
        reply_markup=main_menu()
    )

    return ConversationHandler.END


# =========================================================
# УДАЛЕНИЕ ЗАПИСИ
# =========================================================

async def menu_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

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
        LIMIT 10
        """,
        (user_id,)
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
        LIMIT 10
        """,
        (user_id,)
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
                row["category"]
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
                row["source"]
            ),
            "amount": float(row["amount"]),
            "note": "",
        })

    operations.sort(
        key=lambda x: x["date"],
        reverse=True
    )

    operations = operations[:10]

    if not operations:
        await query.edit_message_text(
            "🗑 <b>Удаление записи</b>\n\n"
            "Пока нет операций для удаления.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Назад",
                        callback_data="menu:home"
                    )
                ]
            ])
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
                )
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "⬅️ Назад",
            callback_data="menu:home"
        )
    ])

    await query.edit_message_text(
        "🗑 <b>Удаление записи</b>\n\n"
        "Выбери операцию, которую нужно удалить:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def delete_select(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")

    if len(parts) != 3:
        await query.edit_message_text(
            "❌ Не удалось определить операцию.",
            reply_markup=main_menu()
        )
        return

    operation_type = parts[1]

    try:
        operation_id = int(parts[2])
    except ValueError:
        await query.edit_message_text(
            "❌ Некорректный номер операции.",
            reply_markup=main_menu()
        )
        return

    if operation_type not in {"expense", "income"}:
        await query.edit_message_text(
            "❌ Неизвестный тип операции.",
            reply_markup=main_menu()
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
            WHERE id=? AND user_id=?
            """,
            (operation_id, user_id)
        ).fetchone()

        if not row:
            conn.close()

            await query.edit_message_text(
                "❌ Операция не найдена.",
                reply_markup=main_menu()
            )
            return

        counted = (
            row["amount"]
            * row["share_pct"]
            / 100
        )

        label = EXPENSE_CATEGORIES.get(
            row["category"],
            row["category"]
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
            WHERE id=? AND user_id=?
            """,
            (operation_id, user_id)
        ).fetchone()

        if not row:
            conn.close()

            await query.edit_message_text(
                "❌ Операция не найдена.",
                reply_markup=main_menu()
            )
            return

        label = INCOME_SOURCES.get(
            row["source"],
            row["source"]
        )

        description = (
            f"💰 {label}\n"
            f"Сумма: {fmt(row['amount'])}\n"
            f"Дата: {row['date']}"
        )

    conn.close()

    context.user_data["delete_type"] = operation_type
    context.user_data["delete_id"] = operation_id

    buttons = [
        [
            InlineKeyboardButton(
                "🗑 Да, удалить",
                callback_data="del_confirm"
            )
        ],
        [
            InlineKeyboardButton(
                "❌ Отмена",
                callback_data="del_cancel"
            )
        ],
    ]

    await query.edit_message_text(
        "⚠️ <b>Удалить эту операцию?</b>\n\n"
        f"{description}\n\n"
        "Это действие нельзя отменить.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def delete_confirm(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
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
            "❌ Операция больше недоступна.",
            reply_markup=main_menu()
        )
        return

    user_id = update.effective_user.id

    conn = db()

    if operation_type == "expense":
        cursor = conn.execute(
            """
            DELETE FROM expenses
            WHERE id=? AND user_id=?
            """,
            (operation_id, user_id)
        )
    else:
        cursor = conn.execute(
            """
            DELETE FROM income
            WHERE id=? AND user_id=?
            """,
            (operation_id, user_id)
        )

    conn.commit()

    deleted = cursor.rowcount

    conn.close()

    context.user_data.pop(
        "delete_type",
        None
    )

    context.user_data.pop(
        "delete_id",
        None
    )

    if deleted:
        await query.edit_message_text(
            "✅ <b>Операция удалена.</b>\n\n"
            "Баланс и статистика будут пересчитаны "
            "при следующем открытии приложения.",
            parse_mode="HTML",
            reply_markup=main_menu()
        )
    else:
        await query.edit_message_text(
            "❌ Операция уже была удалена "
            "или не найдена.",
            reply_markup=main_menu()
        )


async def delete_cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    context.user_data.pop(
        "delete_type",
        None
    )

    context.user_data.pop(
        "delete_id",
        None
    )

    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "Удаление отменено.",
        reply_markup=main_menu()
    )


# =========================================================
# EXPENSE
# =========================================================

async def expense_category(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    category = query.data.split(":")[1]

    context.user_data["category"] = category

    await query.edit_message_text(
        f"Категория: {EXPENSE_CATEGORIES[category]}\n\n"
        "💰 Введи сумму расхода, zł:",
        reply_markup=cancel_keyboard()
    )

    return EXP_AMOUNT


async def expense_amount(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    try:
        amount = float(
            update.message.text.replace(",", ".").strip()
        )

        if amount <= 0:
            raise ValueError

    except ValueError:
        await update.message.reply_text(
            "❌ Не понял сумму.\n\n"
            "Введи число, например: <b>45,50</b>",
            parse_mode="HTML",
            reply_markup=cancel_keyboard()
        )
        return EXP_AMOUNT

    context.user_data["amount"] = amount

    await update.message.reply_text(
        "📝 Добавь заметку.\n\n"
        "Например: Biedronka, бензин, инструменты.\n\n"
        "Если заметка не нужна, отправь <b>-</b>.",
        parse_mode="HTML",
        reply_markup=cancel_keyboard()
    )

    return EXP_NOTE


async def expense_note(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    note = update.message.text.strip()

    context.user_data["note"] = (
        ""
        if note == "-"
        else note
    )

    buttons = [
        [
            InlineKeyboardButton(
                "100%",
                callback_data="share:100"
            ),
            InlineKeyboardButton(
                "75%",
                callback_data="share:75"
            ),
        ],
        [
            InlineKeyboardButton(
                "50%",
                callback_data="share:50"
            ),
            InlineKeyboardButton(
                "25%",
                callback_data="share:25"
            ),
        ],
        [
            InlineKeyboardButton(
                "❌ Отмена",
                callback_data="menu:cancel"
            )
        ]
    ]

    await update.message.reply_text(
        "👥 Какая доля суммы твоя?\n\n"
        "Если платил только ты, выбирай <b>100%</b>.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

    return EXP_SHARE


async def expense_share(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
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
        (user_id, date, category, amount, note, share_pct)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            update.effective_user.id,
            datetime.now().strftime("%Y-%m-%d"),
            data["category"],
            data["amount"],
            data["note"],
            pct,
        )
    )

    conn.commit()
    conn.close()

    counted = (
        data["amount"]
        * pct
        / 100
    )

    text = (
        "✅ <b>Расход добавлен</b>\n\n"
        f"{EXPENSE_CATEGORIES[data['category']]}\n"
        f"Сумма: {fmt(data['amount'])}\n"
        f"Твоя доля: {pct:.0f}%\n"
        f"Учтено: <b>{fmt(counted)}</b>"
    )

    context.user_data.clear()

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu()
    )

    return ConversationHandler.END


# =========================================================
# INCOME
# =========================================================

async def income_source(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    source = query.data.split(":")[1]

    context.user_data["source"] = source

    if source == "uber":

        await query.edit_message_text(
            "🛵 <b>Uber</b>\n\n"
            "Введи сумму на руки (netto), zł:",
            parse_mode="HTML",
            reply_markup=cancel_keyboard()
        )

        return INC_UBER_AMOUNT

    await query.edit_message_text(
        "🏗 <b>Стройка</b>\n\n"
        "Сколько часов отработано?",
        parse_mode="HTML",
        reply_markup=cancel_keyboard()
    )

    return INC_HOURS


async def income_uber_amount(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    try:
        amount = float(
            update.message.text.replace(",", ".").strip()
        )

        if amount <= 0:
            raise ValueError

    except ValueError:
        await update.message.reply_text(
            "❌ Не понял сумму.\n\n"
            "Например: <b>150</b>",
            parse_mode="HTML",
            reply_markup=cancel_keyboard()
        )
        return INC_UBER_AMOUNT

    conn = db()

    conn.execute(
        """
        INSERT INTO income
        (user_id, date, source, amount)
        VALUES (?, ?, ?, ?)
        """,
        (
            update.effective_user.id,
            datetime.now().strftime("%Y-%m-%d"),
            "uber",
            amount,
        )
    )

    conn.commit()
    conn.close()

    context.user_data.clear()

    await update.message.reply_text(
        f"✅ <b>Доход Uber добавлен</b>\n\n"
        f"{fmt(amount)}",
        parse_mode="HTML",
        reply_markup=main_menu()
    )

    return ConversationHandler.END


async def ask_float(
    update,
    context,
    key,
    next_state,
    prompt
):
    try:
        value = float(
            update.message.text.replace(",", ".").strip()
        )

        if value < 0:
            raise ValueError

    except ValueError:
        await update.message.reply_text(
            "❌ Не понял число.\n\n"
            "Попробуй ещё раз.",
            reply_markup=cancel_keyboard()
        )
        return None

    context.user_data[key] = value

    await update.message.reply_text(
        prompt,
        reply_markup=cancel_keyboard()
    )

    return next_state


async def income_hours(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    result = await ask_float(
        update,
        context,
        "hours",
        INC_RATE,
        "💰 Какая ставка, zł/час (brutto)?"
    )

    return (
        result
        if result is not None
        else INC_HOURS
    )


async def income_rate(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    result = await ask_float(
        update,
        context,
        "rate",
        INC_OFFICIAL_HOURS,
        "📋 Сколько из этих часов официальные?"
    )

    return (
        result
        if result is not None
        else INC_RATE
    )


async def income_official_hours(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    result = await ask_float(
        update,
        context,
        "official_hours",
        INC_ZUS,
        "💳 Сколько ZUS за этот период, zł?"
    )

    return (
        result
        if result is not None
        else INC_OFFICIAL_HOURS
    )


async def income_zus(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    result = await ask_float(
        update,
        context,
        "zus",
        INC_TAXPCT,
        "💵 Какой налог с наличных, %?\n\n"
        "Например: 10"
    )

    return (
        result
        if result is not None
        else INC_ZUS
    )


async def income_taxpct(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    try:
        tax_pct = float(
            update.message.text.replace(",", ".").strip()
        )

        if tax_pct < 0:
            raise ValueError

    except ValueError:
        await update.message.reply_text(
            "❌ Не понял процент.\n\n"
            "Например: <b>10</b>",
            parse_mode="HTML",
            reply_markup=cancel_keyboard()
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
            hours
        ) * rate
    )

    cash_amount = max(
        gross - official_amount,
        0
    )

    cash_tax = (
        cash_amount
        * tax_pct
        / 100
    )

    net = (
        official_amount
        - zus
        + cash_amount
        - cash_tax
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
        )
    )

    conn.commit()
    conn.close()

    text = (
        "✅ <b>Стройка добавлена</b>\n\n"
        f"Brutto: {fmt(gross)}\n"
        f"− ZUS: {fmt(zus)}\n"
        f"− налог с наличных "
        f"({tax_pct:.0f}%): {fmt(cash_tax)}\n"
        "━━━━━━━━━━━━\n"
        f"💰 Netto на руки: <b>{fmt(net)}</b>"
    )

    context.user_data.clear()

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu()
    )

    return ConversationHandler.END


# =========================================================
# BALANCE
# =========================================================

async def balance_show(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
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
        WHERE user_id=?
          AND date>=?
          AND date<?
        GROUP BY category
        ORDER BY total DESC
        """,
        (user_id, start, end)
    ).fetchall()

    inc_rows = conn.execute(
        """
        SELECT
            source,
            SUM(amount) AS total
        FROM income
        WHERE user_id=?
          AND date>=?
          AND date<?
        GROUP BY source
        ORDER BY total DESC
        """,
        (user_id, start, end)
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
        f"📊 <b>Баланс за {PERIOD_LABELS[period]}</b>\n",
        f"💰 Доходы: <b>{fmt(total_inc)}</b>",
    ]

    for r in inc_rows:
        lines.append(
            f"  "
            f"{INCOME_SOURCES.get(r['source'], r['source'])}: "
            f"{fmt(r['total'])}"
        )

    lines.append(
        f"\n💸 Расходы: <b>{fmt(total_exp)}</b>"
    )

    for r in exp_rows:

        pct = (
            r["total"]
            / total_exp
            * 100
            if total_exp
            else 0
        )

        lines.append(
            f"  "
            f"{EXPENSE_CATEGORIES.get(r['category'], r['category'])}: "
            f"{fmt(r['total'])} "
            f"({pct:.0f}%)"
        )

    if net >= 0:

        lines.append(
            f"\n🟢 <b>Итого: +{fmt(net)}</b>"
        )

    else:

        lines.append(
            f"\n🔴 <b>Итого: −{fmt(abs(net))}</b>"
        )

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "⬅️ Назад",
                    callback_data="menu:balance"
                )
            ],
            [
                InlineKeyboardButton(
                    "🏠 Главное меню",
                    callback_data="menu:home"
                )
            ]
        ])
    )


# =========================================================
# MINI APP API
# =========================================================

def telegram_user_id(init_data: str):

    if not init_data or not BOT_TOKEN:
        return None

    try:

        from urllib.parse import parse_qsl

        pairs = dict(
            parse_qsl(
                init_data,
                keep_blank_values=True
            )
        )

        received_hash = pairs.pop(
            "hash",
            None
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
            hashlib.sha256
        ).digest()

        calculated_hash = hmac.new(
            secret,
            data_check.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(
            calculated_hash,
            received_hash
        ):
            return None

        user = json.loads(
            pairs.get(
                "user",
                "{}"
            )
        )

        if not user.get("id"):
            return None

        return int(
            user["id"]
        )

    except Exception:
        return None


def dashboard_data(
    user_id: int,
    period: str
):

    start, end = period_bounds(
        period
    )

    conn = db()

    income = conn.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM income
        WHERE user_id=?
          AND date>=?
          AND date<?
        """,
        (
            user_id,
            start,
            end
        )
    ).fetchone()[0]

    expenses = conn.execute(
        """
        SELECT COALESCE(
            SUM(
                amount
                * share_pct
                / 100.0
            ),
            0
        )
        FROM expenses
        WHERE user_id=?
          AND date>=?
          AND date<?
        """,
        (
            user_id,
            start,
            end
        )
    ).fetchone()[0]

    income_sources = conn.execute(
        """
        SELECT
            source,
            SUM(amount) AS total
        FROM income
        WHERE user_id=?
          AND date>=?
          AND date<?
        GROUP BY source
        ORDER BY total DESC
        """,
        (
            user_id,
            start,
            end
        )
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
        WHERE user_id=?
          AND date>=?
          AND date<?
        GROUP BY category
        ORDER BY total DESC
        """,
        (
            user_id,
            start,
            end
        )
    ).fetchall()

    recent_expenses = conn.execute(
        """
        SELECT
            date,
            category,
            amount
                * share_pct
                / 100.0 AS amount,
            note
        FROM expenses
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 6
        """,
        (user_id,)
    ).fetchall()

    recent_income = conn.execute(
        """
        SELECT
            date,
            source,
            amount
        FROM income
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 6
        """,
        (user_id,)
    ).fetchall()

    daily_income = conn.execute(
        """
        SELECT
            date,
            SUM(amount) AS total
        FROM income
        WHERE user_id=?
          AND date>=?
          AND date<?
        GROUP BY date
        """,
        (
            user_id,
            start,
            end
        )
    ).fetchall()

    daily_expenses = conn.execute(
        """
        SELECT
            date,
            SUM(
                amount
                * share_pct
                / 100.0
            ) AS total
        FROM expenses
        WHERE user_id=?
          AND date>=?
          AND date<?
        GROUP BY date
        """,
        (
            user_id,
            start,
            end
        )
    ).fetchall()

    conn.close()

    daily = defaultdict(
        lambda: [0.0, 0.0]
    )

    for row in daily_income:
        daily[
            row["date"]
        ][0] = float(
            row["total"]
        )

    for row in daily_expenses:
        daily[
            row["date"]
        ][1] = float(
            row["total"]
        )

    recent = []

    for row in recent_income:
        recent.append({
            "date": row["date"],
            "label": INCOME_SOURCES.get(
                row["source"],
                row["source"]
            ),
            "amount": float(
                row["amount"]
            ),
            "note": "",
            "kind": "income",
        })

    for row in recent_expenses:
        recent.append({
            "date": row["date"],
            "label": EXPENSE_CATEGORIES.get(
                row["category"],
                row["category"]
            ),
            "amount": float(
                row["amount"]
            ),
            "note": row["note"] or "",
            "kind": "expense",
        })

    recent.sort(
        key=lambda x: x["date"],
        reverse=True
    )

    return {
        "income": float(
            income
        ),

        "expenses": float(
            expenses
        ),

        "net": float(
            income - expenses
        ),

        "income_by_source": [
            {
                "label": INCOME_SOURCES.get(
                    row["source"],
                    row["source"]
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
                    row["category"]
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
            for date in sorted(daily)
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
                "index.html"
            )
        )

    @api.get("/api/dashboard")
    def dashboard(
        period: str = "month",
        x_telegram_init_data: str = Header(
            default=""
        )
    ):

        user_id = telegram_user_id(
            x_telegram_init_data
        )

        if not user_id:

            raise HTTPException(
                status_code=401,
                detail="Invalid Telegram init data"
            )

        if period not in {
            "day",
            "week",
            "month",
            "year",
            "all",
        }:

            period = "month"

        return dashboard_data(
            user_id,
            period
        )

    port = int(
        os.environ.get(
            "PORT",
            "8080"
        )
    )

    uvicorn.run(
        api,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )


# =========================================================
# MAIN
# =========================================================

def main():

    if not BOT_TOKEN:

        raise SystemExit(
            "Переменная окружения BOT_TOKEN не задана"
        )

    init_db()

    if WEBAPP_URL:
        logger.info(
            "Mini App URL configured: %s",
            WEBAPP_URL
        )

    threading.Thread(
        target=run_web_server,
        daemon=True
    ).start()

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )


    # -----------------------------------------------------
    # START
    # -----------------------------------------------------

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )


    # -----------------------------------------------------
    # EXPENSE CONVERSATION
    # -----------------------------------------------------

    expense_conv = ConversationHandler(

        entry_points=[
            CallbackQueryHandler(
                menu_expense,
                pattern="^menu:expense$"
            )
        ],

        states={

            EXP_CATEGORY: [
                CallbackQueryHandler(
                    expense_category,
                    pattern="^cat:"
                ),
                CallbackQueryHandler(
                    menu_cancel,
                    pattern="^menu:cancel$"
                ),
            ],

            EXP_AMOUNT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    expense_amount
                ),
            ],

            EXP_NOTE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    expense_note
                ),
            ],

            EXP_SHARE: [
                CallbackQueryHandler(
                    expense_share,
                    pattern="^share:"
                ),
                CallbackQueryHandler(
                    menu_cancel,
                    pattern="^menu:cancel$"
                ),
            ],
        },

        fallbacks=[
            CommandHandler(
                "cancel",
                menu_cancel
            )
        ],
    )

    app.add_handler(
        expense_conv
    )


    # -----------------------------------------------------
    # INCOME CONVERSATION
    # -----------------------------------------------------

    income_conv = ConversationHandler(

        entry_points=[
            CallbackQueryHandler(
                menu_income,
                pattern="^menu:income$"
            )
        ],

        states={

            INC_SOURCE: [
                CallbackQueryHandler(
                    income_source,
                    pattern="^src:"
                ),
                CallbackQueryHandler(
                    menu_cancel,
                    pattern="^menu:cancel$"
                ),
            ],

            INC_UBER_AMOUNT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    income_uber_amount
                ),
            ],

            INC_HOURS: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    income_hours
                ),
            ],

            INC_RATE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    income_rate
                ),
            ],

            INC_OFFICIAL_HOURS: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    income_official_hours
                ),
            ],

            INC_ZUS: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    income_zus
                ),
            ],

            INC_TAXPCT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    income_taxpct
                ),
            ],
        },

        fallbacks=[
            CommandHandler(
                "cancel",
                menu_cancel
            )
        ],
    )

    app.add_handler(
        income_conv
    )


    # -----------------------------------------------------
    # BALANCE
    # -----------------------------------------------------

    app.add_handler(
        CallbackQueryHandler(
            menu_balance,
            pattern="^menu:balance$"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            balance_show,
            pattern="^bal:"
        )
    )


    # -----------------------------------------------------
    # RECENT
    # -----------------------------------------------------

    app.add_handler(
        CallbackQueryHandler(
            menu_recent,
            pattern="^menu:recent$"
        )
    )


    # -----------------------------------------------------
    # DELETE
    # -----------------------------------------------------

    app.add_handler(
        CallbackQueryHandler(
            menu_delete,
            pattern="^menu:delete$"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            delete_select,
            pattern=r"^del:(expense|income):\d+$"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            delete_confirm,
            pattern=r"^del_confirm$"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            delete_cancel,
            pattern=r"^del_cancel$"
        )
    )


    # -----------------------------------------------------
    # HOME
    # -----------------------------------------------------

    app.add_handler(
        CallbackQueryHandler(
            menu_home,
            pattern="^menu:home$"
        )
    )


    # -----------------------------------------------------
    # CANCEL
    # -----------------------------------------------------

    app.add_handler(
        CallbackQueryHandler(
            menu_cancel,
            pattern="^menu:cancel$"
        )
    )


    logger.info(
        "Financebot started successfully"
    )

    app.run_polling()


if __name__ == "__main__":
    main()
