import logging
import os
from datetime import datetime, timezone

import aiohttp

from bot.cache import get_cached, set_cached

logger = logging.getLogger("bot.esios")

ESIOS_BASE_URL = "https://api.esios.ree.es/indicators/1001"
MAX_RETRIES = 3
RETRY_DELAY = 300


async def fetch_pvpc_prices(date: str) -> list[dict] | None:
    cache_key = f"precios:{date}"
    cached = get_cached(cache_key)
    if cached is not None:
        logger.debug("Cache hit for %s", cache_key)
        return cached

    token = os.getenv("ESIOS_API_TOKEN")
    if not token:
        logger.critical("ESIOS_API_TOKEN not set")
        return None

    headers = {
        "Authorization": f"Token token={token}",
        "Accept": "application/json",
    }
    params = {
        "start_date": f"{date}T00:00:00",
        "end_date": f"{date}T23:59:59",
        "time_trunc": "hour",
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(ESIOS_BASE_URL, headers=headers, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        prices = _parse_esios_response(data)
                        if prices:
                            set_cached(cache_key, prices)
                        return prices
                    logger.warning("ESIOS returned status %d (attempt %d/%d)", resp.status, attempt, MAX_RETRIES)
        except Exception:
            logger.exception("Error fetching ESIOS (attempt %d/%d)", attempt, MAX_RETRIES)

        if attempt < MAX_RETRIES:
            import asyncio
            await asyncio.sleep(RETRY_DELAY)

    logger.error("All retries exhausted for date %s", date)
    return None


def _parse_esios_response(data: dict) -> list[dict]:
    try:
        values = data["indicator"]["values"]
    except (KeyError, TypeError):
        logger.error("Unexpected ESIOS response structure")
        return []

    prices = []
    for v in values:
        try:
            price_mwh = v["value"]
            price_kwh = round(price_mwh / 1000, 4)
            dt = datetime.fromisoformat(v["datetime"]).astimezone(timezone.utc)
            hour = v.get("time_interval", {}).get("start", "")
            hour_num = int(hour[11:13]) if len(hour) >= 13 else dt.hour
            prices.append({
                "hour": hour_num,
                "price_kwh": price_kwh,
                "price_mwh": price_mwh,
            })
        except (KeyError, TypeError, ValueError):
            continue

    prices.sort(key=lambda p: p["hour"])
    return prices
