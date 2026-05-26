import logging
import os
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pytz import timezone

from bot.esios import fetch_pvpc_prices
from bot.formatter import format_message
from bot.db import get_all_subscribers

logger = logging.getLogger("bot.scheduler")

MADRID_TZ = timezone("Europe/Madrid")


async def _notify_job(app):
    now = datetime.now(MADRID_TZ)
    target_date = now.strftime("%Y-%m-%d")

    if now.hour >= 20:
        from datetime import timedelta
        target_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        prices = await fetch_pvpc_prices(target_date)
    except Exception:
        logger.exception("Failed to fetch prices for %s", target_date)
        try:
            subscribers = await get_all_subscribers()
            for chat_id, _ in subscribers:
                await app.bot.send_message(
                    chat_id=chat_id,
                    text="No he podido obtener los precios de la luz ahora. Reintentaré en unos minutos.",
                )
        except Exception:
            logger.exception("Failed to send retry notice")
        _schedule_retry(app, minutes=30)
        return

    if not prices:
        logger.warning("No prices available yet for %s", target_date)
        try:
            subscribers = await get_all_subscribers()
            for chat_id, _ in subscribers:
                await app.bot.send_message(
                    chat_id=chat_id,
                    text="Los precios de mañana aún no están publicados, probaré de nuevo en unos minutos.",
                )
        except Exception:
            logger.exception("Failed to send no-prices notice")
        _schedule_retry(app, minutes=30)
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


def _schedule_retry(app, minutes=30):
    now = datetime.now(MADRID_TZ)
    retry_time = now.replace(minute=0, second=0, microsecond=0)
    retry_time = retry_time.replace(hour=now.hour, minute=now.minute + minutes if now.minute + minutes < 60 else 0)
    scheduler = _get_scheduler()
    if scheduler:
        run_date = now.__class__.fromtimestamp(now.timestamp() + minutes * 60, tz=MADRID_TZ)
        scheduler.add_job(_notify_job, "date", run_date=run_date, args=[app], id="retry_notify")
        logger.info("Retry scheduled at %s", run_date)


_scheduler_instance: AsyncIOScheduler | None = None


def _get_scheduler():
    return _scheduler_instance


def setup_scheduler(app) -> AsyncIOScheduler:
    global _scheduler_instance

    hour = int(os.getenv("NOTIFY_HOUR", "20"))
    minute = int(os.getenv("NOTIFY_MINUTE", "15"))

    scheduler = AsyncIOScheduler(timezone=MADRID_TZ)
    scheduler.add_job(
        _notify_job,
        "cron",
        hour=hour,
        minute=minute,
        args=[app],
        id="daily_notify",
    )

    _scheduler_instance = scheduler
    return scheduler
