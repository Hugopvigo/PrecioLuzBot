from datetime import datetime

from pytz import timezone

MADRID_TZ = timezone("Europe/Madrid")

DAY_NAMES = {
    0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves",
    4: "Viernes", 5: "Sábado", 6: "Domingo",
}

MONTH_NAMES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}

_TRAMO_FILL = {
    "cheap":  "🟩",
    "medium": "🟨",
    "dear":   "🟥",
}

_TRAMO_ICON = {
    "cheap":  "🟢",
    "medium": "🟡",
    "dear":   "🔴",
}


def format_message(prices: list[dict], date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    day_name = DAY_NAMES[dt.weekday()]
    month_name = MONTH_NAMES[dt.month]

    sorted_prices = sorted(prices, key=lambda p: p["price_kwh"])
    cheapest_set = {p["hour"] for p in sorted_prices[:3]}
    dearest_set = {p["hour"] for p in sorted_prices[-3:]}

    avg_price = sum(p["price_kwh"] for p in prices) / len(prices)

    n = len(prices)
    cheap_threshold = sorted_prices[n // 3]["price_kwh"]
    expensive_threshold = sorted_prices[2 * n // 3]["price_kwh"]

    min_price = sorted_prices[0]["price_kwh"]
    max_price = sorted_prices[-1]["price_kwh"]
    cheapest_hour = sorted_prices[0]
    dearest_hour = sorted_prices[-1]

    lines = []
    lines.append(f"⚡ Precio de la luz — {day_name} {dt.day} {month_name}")
    lines.append("")
    lines.append(f"🟢 Más barata: {cheapest_hour['hour']:02d}:00h → {format_price(cheapest_hour['price_kwh'])} €/kWh")
    lines.append(f"🔴 Más cara: {dearest_hour['hour']:02d}:00h → {format_price(dearest_hour['price_kwh'])} €/kWh")
    lines.append(f"📊 Media del día: {format_price(avg_price)} €/kWh")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━")

    for p in sorted(prices, key=lambda x: x["hour"]):
        hour = p["hour"]
        price = p["price_kwh"]

        if price <= cheap_threshold:
            tramo = "cheap"
        elif price <= expensive_threshold:
            tramo = "medium"
        else:
            tramo = "dear"

        color_icon = _TRAMO_ICON[tramo]
        bar = _build_bar(price, max_price, min_price, _TRAMO_FILL[tramo])

        if hour in cheapest_set:
            special = " 💰"
        elif hour in dearest_set:
            special = " 💀"
        else:
            special = ""

        lines.append(f"{color_icon} {hour:02d}h {format_price(price)}€ {bar}{special}")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("Datos: REE ESIOS · /ayuda · by HPVF")

    return "\n".join(lines)


def format_price(price: float) -> str:
    return f"{price:.4f}".replace(".", ",")


def _build_bar(price: float, max_price: float, min_price: float, fill_emoji: str, max_len: int = 6) -> str:
    if max_price == min_price:
        return "⬜" * max_len

    ratio = (price - min_price) / (max_price - min_price)
    filled = max(1, min(round(ratio * max_len), max_len))
    return fill_emoji * filled + "⬜" * (max_len - filled)
