import asyncio
import logging
import os
from datetime import datetime, timezone

import aiohttp
from pytz import timezone as pytz_timezone

from bot.cache import get_cached, set_cached
from bot.db import get_prices, save_prices

logger = logging.getLogger("bot.esios")

ESIOS_BASE_URL = "https://api.esios.ree.es/indicators/1001"
MADRID_TZ = pytz_timezone("Europe/Madrid")
MAX_RETRIES = 3
RETRY_DELAY = 5


async def fetch_pvpc_prices(date: str) -> list[dict] | None:
    cache_key = f"precios:{date}"

    # 1. Caché en memoria (evita DB para consultas repetidas en la misma sesión)
    cached = get_cached(cache_key)
    if cached is not None:
        logger.debug("Cache hit (memory) for %s", cache_key)
        return cached

    # 2. Base de datos local (cumplimiento REE: una sola llamada por día)
    stored = await get_prices(date)
    if stored:
        logger.debug("Cache hit (db) for %s", cache_key)
        set_cached(cache_key, stored)
        return stored

    token = os.getenv("ESIOS_API_TOKEN")
    if not token:
        logger.critical("ESIOS_API_TOKEN not set")
        return None

    # Construir fechas con offset Madrid para que la API devuelva
    # exactamente las 24 horas del día local (00:00-23:59 hora española)
    local_start = MADRID_TZ.localize(
        datetime.strptime(date, "%Y-%m-%d").replace(hour=0, minute=0, second=0)
    )
    local_end = local_start.replace(hour=23, minute=59, second=59)

    headers = {
        "x-api-key": token,
        "Accept": "application/json",
    }
    params = {
        "start_date": local_start.isoformat(),
        "end_date": local_end.isoformat(),
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
                            await save_prices(date, prices)
                        return prices
                    logger.warning("ESIOS returned status %d (attempt %d/%d)", resp.status, attempt, MAX_RETRIES)
        except Exception:
            logger.exception("Error fetching ESIOS (attempt %d/%d)", attempt, MAX_RETRIES)

        if attempt < MAX_RETRIES:
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
            # geo_id 3 = Peninsular España; ignorar Canarias, Baleares, Ceuta, Melilla
            if v.get("geo_id") != 3:
                continue

            price_mwh = v["value"]
            price_kwh = round(price_mwh / 1000, 4)

            # Convertir a hora local Madrid para mostrar la hora correcta
            hour_str = v.get("time_interval", {}).get("start", "")
            if hour_str:
                dt_local = datetime.fromisoformat(hour_str).astimezone(MADRID_TZ)
                hour_num = dt_local.hour
            else:
                dt_local = datetime.fromisoformat(v["datetime"]).astimezone(MADRID_TZ)
                hour_num = dt_local.hour

            prices.append({
                "hour": hour_num,
                "price_kwh": price_kwh,
                "price_mwh": price_mwh,
            })
        except (KeyError, TypeError, ValueError):
            continue

    prices.sort(key=lambda p: p["hour"])
    return prices
