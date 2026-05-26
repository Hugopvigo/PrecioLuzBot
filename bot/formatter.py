import locale
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


def format_message(prices: list[dict], date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    day_name = DAY_NAMES[dt.weekday()]
    month_name = MONTH_NAMES[dt.month]

    sorted_prices = sorted(prices, key=lambda p: p["price_kwh"])
    cheapest = sorted_prices[:3]
    dearest = sorted_prices[-3:]

    cheapest_set = {p["hour"] for p in cheapest}
    dearest_set = {p["hour"] for p in dearest}

    avg_price = sum(p["price_kwh"] for p in prices) / len(prices)
    max_price = max(p["price_kwh"] for p in prices)

    n = len(prices)
    sorted_by_price = sorted(prices, key=lambda p: p["price_kwh"])
    cheap_threshold = sorted_by_price[n // 3]["price_kwh"]
    expensive_threshold = sorted_by_price[2 * n // 3]["price_kwh"]

    min_price = min(p["price_kwh"] for p in prices)
    max_p = max(p["price_kwh"] for p in prices)
    abs_min = min_price

    lines = []
    lines.append(f"⚡ Precio de la luz — {day_name} {dt.day} {month_name}")
    lines.append("")

    cheapest_hour = sorted_prices[0]
    dearest_hour = sorted_prices[-1]
    lines.append(f"🟢 Más barata: {cheapest_hour['hour']:02d}:00h → {format_price(cheapest_hour['price_kwh'])} €/kWh")
    lines.append(f"🔴 Más cara: {dearest_hour['hour']:02d}:00h → {format_price(dearest_hour['price_kwh'])} €/kWh")
    lines.append(f"📊 Media del día: {format_price(avg_price)} €/kWh")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━")

    for p in sorted(prices, key=lambda x: x["hour"]):
        hour = p["hour"]
        price = p["price_kwh"]

        if hour in cheapest_set:
            icon = "🟢💰"
        elif price <= cheap_threshold:
            icon = "🟢  "
        elif price <= expensive_threshold:
            icon = "🟡  "
        elif hour in dearest_set:
            icon = "🔴💀"
        else:
            icon = "🔴  "

        bar = _build_bar(price, max_p, abs_min, max_len=12)

        annotation = ""
        if hour == cheapest_hour["hour"]:
            annotation = " ← más barata"
        elif hour == dearest_hour["hour"]:
            annotation = " ← más cara"

        lines.append(f"{icon} {hour:02d}h {format_price(price)} {bar}{annotation}")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("Datos: REE ESIOS · /ayuda")

    return "\n".join(lines)


def format_price(price: float) -> str:
    return f"{price:.4f}".replace(".", ",")


def _build_bar(price: float, max_price: float, min_price: float, max_len: int = 12) -> str:
    if max_price == min_price:
        return "░" * max_len

    ratio = (price - min_price) / (max_price - min_price)
    filled = round(ratio * max_len)
    filled = max(1, min(filled, max_len))

    return "█" * filled + "░" * (max_len - filled)
