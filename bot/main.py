import asyncio
import logging
import os
import signal
import sys

from telegram.error import NetworkError, TimedOut
from telegram.ext import ApplicationBuilder
from telegram.request import HTTPXRequest

from bot.scheduler import setup_scheduler
from bot.db import init_db
from bot.handlers import register_handlers
from bot.rich import set_my_commands

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)

logger = logging.getLogger("bot.main")


async def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.critical("TELEGRAM_BOT_TOKEN not set")
        sys.exit(1)

    await init_db()

    shutdown_event = asyncio.Event()

    def _signal_handler():
        logger.info("Signal received, initiating graceful shutdown...")
        shutdown_event.set()

    request = HTTPXRequest(connect_timeout=20, read_timeout=20, write_timeout=20)
    app = ApplicationBuilder().token(token).request(request).build()
    register_handlers(app)

    scheduler = setup_scheduler(app)
    scheduler.start()
    logger.info("Scheduler started")

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

    for attempt in range(1, 6):
        try:
            await app.initialize()
            break
        except (NetworkError, TimedOut) as e:
            wait = attempt * 5
            logger.warning("Telegram unreachable (attempt %d/5): %s — retry in %ds", attempt, e, wait)
            if attempt == 5:
                raise
            await asyncio.sleep(wait)

    await app.start()
    await app.updater.start_polling()

    # Register bot commands menu
    await set_my_commands([
        {"command": "start", "description": "🔔 Suscribirse a notificaciones diarias"},
        {"command": "stop", "description": "🛑 Darse de baja"},
        {"command": "precio", "description": "🔍 Consultar precio de hoy o mañana"},
        {"command": "grafico", "description": "📈 Gráfico visual de precios ordenados"},
        {"command": "ayuda", "description": "❓ Ver ayuda completa"},
    ])

    logger.info("PrecioLuz Bot running")

    await shutdown_event.wait()

    logger.info("Shutting down...")
    scheduler.shutdown(wait=False)
    await app.updater.stop()
    await app.stop()
    await app.shutdown()
    logger.info("Goodbye")


if __name__ == "__main__":
    asyncio.run(main())
