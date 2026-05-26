import logging
from datetime import datetime, timedelta

from pytz import timezone
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from bot.db import add_subscriber, remove_subscriber, is_subscribed
from bot.esios import fetch_pvpc_prices
from bot.formatter import format_message

logger = logging.getLogger("bot.handlers")

MADRID_TZ = timezone("Europe/Madrid")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    username = update.effective_user.username

    await add_subscriber(chat_id, username)
    await update.message.reply_text(
        "✅ Te has suscrito a las notificaciones diarias del precio de la luz.\n"
        "Recibirás los precios del día siguiente cada día a las 20:15h.\n"
        "Usa /stop para darte de baja o /precio para consultar ahora."
    )
    logger.info("New subscriber: chat_id=%s username=%s", chat_id, username)


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    await remove_subscriber(chat_id)
    await update.message.reply_text("❌ Te has dado de baja. Ya no recibirás notificaciones diarias.")
    logger.info("Unsubscribed: chat_id=%s", chat_id)


async def precio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    now = datetime.now(MADRID_TZ)

    if now.hour >= 20:
        target_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        label = "mañana"
    else:
        target_date = now.strftime("%Y-%m-%d")
        label = "hoy"

    await update.message.reply_text(f"Consultando precios de {label}...")

    prices = await fetch_pvpc_prices(target_date)

    if not prices:
        if now.hour >= 20:
            await update.message.reply_text(
                "Los precios de mañana aún no están publicados, prueba en unos minutos."
            )
        else:
            await update.message.reply_text(
                "No he podido obtener los precios ahora. Inténtalo de nuevo más tarde."
            )
        return

    message = format_message(prices, target_date)
    await update.message.reply_text(message)


async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚡ *PrecioLuz Bot — Comandos*\n\n"
        "/start — Suscribirse a notificaciones diarias\n"
        "/stop — Darse de baja\n"
        "/precio — Consultar precio de hoy o mañana\n"
        "/ayuda — Mostrar esta ayuda\n\n"
        "Los precios se obtienen de la API oficial ESIOS de REE.",
        parse_mode="Markdown",
    )


def register_handlers(app: Application):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("precio", precio))
    app.add_handler(CommandHandler("ayuda", ayuda))
