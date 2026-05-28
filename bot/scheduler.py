import logging
import os
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pytz import timezone

from bot.esios import fetch_pvpc_prices
from bot.formatter import format_message
from bot.db import get_all_subscribers

logger = logging.getLogger("bot.scheduler")

MADRID_TZ = timezone("Europe/Madrid")

# Minutos entre reintentos: intento 1→2: 60 min, intento 2→3: 30 min
RETRY_DELAYS = {1: 60, 2: 30}
MAX_ATTEMPTS = 3

_scheduler_instance: AsyncIOScheduler | None = None


async def _notify_job(app, attempt: int = 1):
    now = datetime.now(MADRID_TZ)
    target_date = now.strftime("%Y-%m-%d")

    if now.hour >= 20:
        target_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        prices = await fetch_pvpc_prices(target_date)
    except Exception:
        logger.exception("Failed to fetch prices for %s (attempt %d)", target_date, attempt)
        await _handle_no_prices(app, attempt)
        return

    if not prices:
        logger.warning("No prices available yet for %s (attempt %d)", target_date, attempt)
        await _handle_no_prices(app, attempt)
        return

    message = format_message(prices, target_date)
    subscribers = await get_all_subscribers()
    for chat_id, _ in subscribers:
        try:
            await app.bot.send_message(chat_id=chat_id, text=message)
        except Exception as exc:
            error_msg = str(exc).lower()
            if "blocked" in error_msg or "deactivated" in error_msg:
                logger.info("Removing blocked subscriber %s", chat_id)
                from bot.db import remove_subscriber
                await remove_subscriber(chat_id)
            else:
                logger.exception("Failed to send to %s", chat_id)


async def _handle_no_prices(app, attempt: int):
    if attempt >= MAX_ATTEMPTS:
        logger.error("All %d attempts failed, notifying subscribers", MAX_ATTEMPTS)
        await _broadcast(
            app,
            "⚠️ Los precios de mañana no están disponibles tras varios intentos. "
            "Por favor, consúltalos manualmente mañana.",
        )
        return

    delay = RETRY_DELAYS[attempt]
    next_attempt = attempt + 1

    if attempt == 2:
        # Antes del último intento, avisamos
        await _broadcast(
            app,
            f"Los precios de mañana aún no están publicados. "
            f"Haré un último intento en {delay} minutos.",
        )

    _schedule_retry(app, attempt=next_attempt, minutes=delay)
    logger.info("Retry #%d scheduled in %d min", next_attempt, delay)


async def _broadcast(app, text: str):
    try:
        subscribers = await get_all_subscribers()
        for chat_id, _ in subscribers:
            await app.bot.send_message(chat_id=chat_id, text=text)
    except Exception:
        logger.exception("Failed to broadcast message")


def _schedule_retry(app, attempt: int, minutes: int):
    scheduler = _get_scheduler()
    if not scheduler:
        return
    run_date = datetime.now(MADRID_TZ) + timedelta(minutes=minutes)
    job_id = f"retry_notify_{attempt}"
    # Evitar duplicados si ya existe ese job
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    scheduler.add_job(
        _notify_job,
        "date",
        run_date=run_date,
        args=[app, attempt],
        id=job_id,
    )
    logger.info("Retry #%d scheduled at %s", attempt, run_date.strftime("%H:%M"))


def _get_scheduler() -> AsyncIOScheduler | None:
    return _scheduler_instance


def setup_scheduler(app) -> AsyncIOScheduler:
    global _scheduler_instance

    hour = int(os.getenv("NOTIFY_HOUR", "20"))
    minute = int(os.getenv("NOTIFY_MINUTE", "30"))

    scheduler = AsyncIOScheduler(timezone=MADRID_TZ)
    scheduler.add_job(
        _notify_job,
        "cron",
        hour=hour,
        minute=minute,
        args=[app, 1],
        id="daily_notify",
    )

    _scheduler_instance = scheduler
    return scheduler
