import logging
import random
from datetime import datetime, timedelta

from pytz import timezone
from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from bot.db import add_subscriber, remove_subscriber, is_subscribed, get_daily_avg, save_daily_avg
from bot.esios import fetch_pvpc_prices
from bot.formatter import (
    format_rich_message,
    format_rich_grafico,
    format_rich_start,
    format_rich_stop,
    format_rich_ayuda,
    format_thinking,
    format_draft_partial,
    _build_notification_keyboard,
)
from bot.rich import send_rich_message, send_rich_draft, send_photo
from bot.chart import generate_price_chart

logger = logging.getLogger("bot.handlers")

MADRID_TZ = timezone("Europe/Madrid")


def _resolve_target_date(now) -> tuple[str, str]:
    """Return (target_date, label) based on current hour."""
    if now.hour >= 20:
        target_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        label = "mañana"
    else:
        target_date = now.strftime("%Y-%m-%d")
        label = "hoy"
    return target_date, label


def _yesterday_date(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return (dt - timedelta(days=1)).strftime("%Y-%m-%d")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    username = update.effective_user.username

    await add_subscriber(chat_id, username)
    markdown = format_rich_start()
    await send_rich_message(chat_id, markdown)
    logger.info("New subscriber: chat_id=%s username=%s", chat_id, username)


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    await remove_subscriber(chat_id)
    markdown = format_rich_stop()
    await send_rich_message(chat_id, markdown)
    logger.info("Unsubscribed: chat_id=%s", chat_id)


async def precio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    now = datetime.now(MADRID_TZ)
    target_date, label = _resolve_target_date(now)

    # ── Step 1: Send thinking draft ──
    draft_id = random.randint(1, 2_147_483_647)
    thinking_md = format_thinking(f"Consultando precios de {label}...")
    await send_rich_draft(chat_id, draft_id, thinking_md)

    # ── Step 2: Fetch prices ──
    prices = await fetch_pvpc_prices(target_date)

    if not prices:
        if now.hour >= 20:
            msg = (
                "## ⚡ Precios no disponibles\n\n"
                "Los precios de **mañana** aún no están publicados.\n\n"
                "Prueba en unos minutos con `/precio`."
            )
        else:
            msg = (
                "## ⚡ Error de conexión\n\n"
                "No he podido obtener los precios ahora.\n\n"
                "Inténtalo de nuevo con `/precio` más tarde."
            )
        await send_rich_message(chat_id, msg)
        return

    # ── Step 3: Stream partial then final ──
    partial_md = format_draft_partial(prices, target_date)
    await send_rich_draft(chat_id, draft_id, partial_md)

    yesterday_avg = await get_daily_avg(_yesterday_date(target_date))
    full_md = format_rich_message(prices, target_date, yesterday_avg=yesterday_avg)

    # ── Step 4: Send chart image + text ──
    chart_buf = generate_price_chart(prices, target_date)
    keyboard = _build_notification_keyboard()
    await send_photo(chat_id, chart_buf, caption=full_md, reply_markup=keyboard)


async def grafico(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    now = datetime.now(MADRID_TZ)
    target_date, label = _resolve_target_date(now)

    # ── Thinking draft ──
    draft_id = random.randint(1, 2_147_483_647)
    thinking_md = format_thinking(f"Generando gráfico de {label}...")
    await send_rich_draft(chat_id, draft_id, thinking_md)

    # ── Fetch ──
    prices = await fetch_pvpc_prices(target_date)

    if not prices:
        if now.hour >= 20:
            msg = (
                "## ⚡ Precios no disponibles\n\n"
                "Los precios de **mañana** aún no están publicados."
            )
        else:
            msg = (
                "## ⚡ Error de conexión\n\n"
                "No he podido obtener los precios ahora."
            )
        await send_rich_message(chat_id, msg)
        return

    # ── Stream partial then final ──
    partial_md = format_draft_partial(prices, target_date)
    await send_rich_draft(chat_id, draft_id, partial_md)

    full_md = format_rich_grafico(prices, target_date)
    await send_rich_message(chat_id, full_md)


async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    markdown = format_rich_ayuda()
    await send_rich_message(chat_id, markdown)


async def _handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses."""
    query = update.callback_query
    await query.answer()

    data = query.data
    chat_id = query.message.chat.id

    if data == "cmd_grafico":
        now = datetime.now(MADRID_TZ)
        target_date, label = _resolve_target_date(now)
        prices = await fetch_pvpc_prices(target_date)
        if prices:
            full_md = format_rich_grafico(prices, target_date)
            await send_rich_message(chat_id, full_md)
        else:
            await send_rich_message(chat_id, "## ⚡ Precios no disponibles")

    elif data == "cmd_precio_hoy":
        target_date = datetime.now(MADRID_TZ).strftime("%Y-%m-%d")
        prices = await fetch_pvpc_prices(target_date)
        if prices:
            yesterday_avg = await get_daily_avg(_yesterday_date(target_date))
            full_md = format_rich_message(prices, target_date, yesterday_avg=yesterday_avg)
            chart_buf = generate_price_chart(prices, target_date)
            keyboard = _build_notification_keyboard()
            await send_photo(chat_id, chart_buf, caption=full_md, reply_markup=keyboard)
        else:
            await send_rich_message(chat_id, "## ⚡ Precios de hoy no disponibles")

    elif data == "cmd_precio_manana":
        target_date = (datetime.now(MADRID_TZ) + timedelta(days=1)).strftime("%Y-%m-%d")
        prices = await fetch_pvpc_prices(target_date)
        if prices:
            yesterday_avg = await get_daily_avg(_yesterday_date(target_date))
            full_md = format_rich_message(prices, target_date, yesterday_avg=yesterday_avg)
            chart_buf = generate_price_chart(prices, target_date)
            keyboard = _build_notification_keyboard()
            await send_photo(chat_id, chart_buf, caption=full_md, reply_markup=keyboard)
        else:
            await send_rich_message(
                chat_id,
                "## ⚡ Precios de mañana no disponibles\n\n"
                "Aún no se han publicado. Prueba después de las 20h.",
            )

    elif data == "cmd_ayuda":
        markdown = format_rich_ayuda()
        await send_rich_message(chat_id, markdown)


def register_handlers(app: Application):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("precio", precio))
    app.add_handler(CommandHandler("grafico", grafico))
    app.add_handler(CommandHandler("ayuda", ayuda))
    app.add_handler(CallbackQueryHandler(_handle_callback))
