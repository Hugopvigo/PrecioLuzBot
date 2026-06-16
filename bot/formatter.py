"""Rich Markdown formatter for Telegram Bot API 10.1.

Generates Markdown content for sendRichMessage with tables, headings,
expandable details, and structured layouts.
"""

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

_TRAMO_EMOJI = {
    "cheap": "🟢",
    "affordable": "🟡",
    "medium": "🟠",
    "dear": "🔴",
}


def _build_notification_keyboard() -> dict:
    """Build inline keyboard for notification messages."""
    return {
        "inline_keyboard": [
            [
                {"text": "📈 Ver gráfico", "callback_data": "cmd_grafico"},
                {"text": "📅 Precio hoy", "callback_data": "cmd_precio_hoy"},
            ],
            [
                {"text": "🔮 Precio mañana", "callback_data": "cmd_precio_manana"},
                {"text": "❓ Ayuda", "callback_data": "cmd_ayuda"},
            ],
        ]
    }


def format_rich_message(
    prices: list[dict],
    date_str: str,
    yesterday_avg: float | None = None,
) -> str:
    """Build a full rich markdown message with prices."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    day_name = DAY_NAMES[dt.weekday()]
    month_name = MONTH_NAMES[dt.month]

    sorted_by_price = sorted(prices, key=lambda p: p["price_kwh"])
    cheapest_set = {p["hour"] for p in sorted_by_price[:3]}
    dearest_set = {p["hour"] for p in sorted_by_price[-3:]}

    avg_price = sum(p["price_kwh"] for p in prices) / len(prices)

    n = len(prices)
    t1 = sorted_by_price[n // 4]["price_kwh"]
    t2 = sorted_by_price[n // 2]["price_kwh"]
    t3 = sorted_by_price[3 * n // 4]["price_kwh"]

    min_price = sorted_by_price[0]["price_kwh"]
    max_price = sorted_by_price[-1]["price_kwh"]
    cheapest = sorted_by_price[0]
    dearest = sorted_by_price[-1]

    lines = []

    # ── Header ──
    lines.append(f"## ⚡ Precio de la luz — {day_name} {dt.day} {month_name}")
    lines.append("")

    # ── Resumen ──
    lines.append("### 📊 Resumen del día")
    lines.append("")
    lines.append(f"- **Más barata:** `{cheapest['hour']:02d}:00h` → **`{_fmt(cheapest['price_kwh'])} €/kWh`** 🟢💰")
    lines.append(f"- **Más cara:** `{dearest['hour']:02d}:00h` → **`{_fmt(dearest['price_kwh'])} €/kWh`** 🔴💀")

    trend_str = ""
    if yesterday_avg is not None and yesterday_avg > 0:
        diff_pct = ((avg_price - yesterday_avg) / yesterday_avg) * 100
        if diff_pct < 0:
            trend_str = f" (↓ {abs(diff_pct):.0f}% vs ayer)"
        elif diff_pct > 0:
            trend_str = f" (↑ {diff_pct:.0f}% vs ayer)"
        else:
            trend_str = " (igual que ayer)"

    lines.append(f"- **Media del día:** **`{_fmt(avg_price)} €/kWh`**{trend_str}")
    lines.append("")

    # ── Divider ──
    lines.append("---")
    lines.append("")

    # ── Tabla horaria ──
    lines.append("### 🕐 Desglose horario")
    lines.append("")
    lines.append("| Hora | Precio (€/kWh) | Nivel | |")
    lines.append("|:-----|---------------:|:------|:---|")

    for p in sorted(prices, key=lambda x: x["hour"]):
        hour = p["hour"]
        price = p["price_kwh"]

        if price <= t1:
            tramo = "cheap"
        elif price <= t2:
            tramo = "affordable"
        elif price <= t3:
            tramo = "medium"
        else:
            tramo = "dear"

        emoji = _TRAMO_EMOJI[tramo]

        if hour in cheapest_set:
            marker = " 💰"
        elif hour in dearest_set:
            marker = " 💀"
        else:
            marker = ""

        lines.append(f"| **{hour:02d}** | `{_fmt(price)}` | {emoji} |{marker}|")

    lines.append("")

    # ── Divider ──
    lines.append("---")
    lines.append("")

    # ── Top 3 baratas (details expandible) ──
    cheapest_3 = sorted_by_price[:3]
    lines.append("<details>")
    lines.append("<summary>💰 Top 3 horas más baratas</summary>")
    lines.append("")
    for i, p in enumerate(cheapest_3, 1):
        bar = _build_bar_visual(p["price_kwh"], max_price, min_price)
        lines.append(f"{i}. `{p['hour']:02d}:00h` → **`{_fmt(p['price_kwh'])} €/kWh`** {bar}")
    lines.append("")
    lines.append("</details>")
    lines.append("")

    # ── Top 3 caras (details expandible) ──
    dearest_3 = sorted_by_price[-3:]
    lines.append("<details>")
    lines.append("<summary>💀 Top 3 horas más caras</summary>")
    lines.append("")
    for i, p in enumerate(dearest_3, 1):
        bar = _build_bar_visual(p["price_kwh"], max_price, min_price)
        lines.append(f"{i}. `{p['hour']:02d}:00h` → **`{_fmt(p['price_kwh'])} €/kWh`** {bar}")
    lines.append("")
    lines.append("</details>")
    lines.append("")

    # ── Footer ──
    lines.append("---")
    lines.append("<footer>Datos: REE ESIOS · /ayuda · /grafico · by HPVF</footer>")

    return "\n".join(lines)


def format_rich_grafico(prices: list[dict], date_str: str) -> str:
    """Build a ranking/chart view sorted by price, cheapest first."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    day_name = DAY_NAMES[dt.weekday()]
    month_name = MONTH_NAMES[dt.month]

    sorted_by_price = sorted(prices, key=lambda p: p["price_kwh"])
    min_price = sorted_by_price[0]["price_kwh"]
    max_price = sorted_by_price[-1]["price_kwh"]

    avg_price = sum(p["price_kwh"] for p in prices) / len(prices)

    lines = []

    lines.append(f"## 📈 Gráfico de precios — {day_name} {dt.day} {month_name}")
    lines.append("")
    lines.append(f"> **Media del día:** `{_fmt(avg_price)} €/kWh` · Rango: `{_fmt(min_price)}` → `{_fmt(max_price)} €/kWh`")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Tabla ordenada ──
    lines.append("### De más barata a más cara")
    lines.append("")
    lines.append("| # | Hora | Precio | Distribución |")
    lines.append("|--:|:-----|-------:|:-------------|")

    for rank, p in enumerate(sorted_by_price, 1):
        bar = _build_bar_visual(p["price_kwh"], max_price, min_price)

        if rank <= 3:
            marker = " 💰"
        elif rank >= len(sorted_by_price) - 2:
            marker = " 💀"
        else:
            marker = ""

        lines.append(f"| {rank} | **{p['hour']:02d}h** | `{_fmt(p['price_kwh'])}` | {bar}{marker} |")

    lines.append("")

    # ── Distribución por tramos ──
    n = len(prices)
    t1 = sorted_by_price[n // 4]["price_kwh"]
    t2 = sorted_by_price[n // 2]["price_kwh"]
    t3 = sorted_by_price[3 * n // 4]["price_kwh"]

    cheap_count = sum(1 for p in prices if p["price_kwh"] <= t1)
    affordable_count = sum(1 for p in prices if t1 < p["price_kwh"] <= t2)
    medium_count = sum(1 for p in prices if t2 < p["price_kwh"] <= t3)
    dear_count = sum(1 for p in prices if p["price_kwh"] > t3)

    lines.append("---")
    lines.append("")
    lines.append("### 🎯 Distribución por tramos")
    lines.append("")
    lines.append(f"- 🟢 **Barato** (≤ `{_fmt(t1)}`): **{cheap_count}h**")
    lines.append(f"- 🟡 **Asequible** ({_fmt(t1)} - {_fmt(t2)}): **{affordable_count}h**")
    lines.append(f"- 🟠 **Medio** ({_fmt(t2)} - {_fmt(t3)}): **{medium_count}h**")
    lines.append(f"- 🔴 **Caro** (> `{_fmt(t3)}`): **{dear_count}h**")
    lines.append("")

    # ── Footer ──
    lines.append("---")
    lines.append("<footer>Datos: REE ESIOS · /precio · /ayuda · by HPVF</footer>")

    return "\n".join(lines)


def format_rich_start() -> str:
    """Rich welcome message for /start."""
    lines = [
        "## ⚡ Bienvenido a PrecioLuz Bot",
        "",
        "Ahora recibirás **cada día a las 20:15h** los precios de la luz del día siguiente.",
        "",
        "### 📋 Comandos disponibles",
        "",
        "| Comando | Descripción |",
        "|:--------|:------------|",
        "| `/precio` | Consultar precio de hoy o mañana |",
        "| `/grafico` | Ver gráfico de precios ordenados |",
        "| `/ayuda` | Ver ayuda completa |",
        "| `/stop` | Darse de baja |",
        "",
        "---",
        "",
        "<footer>Fuente: REE ESIOS · by HPVF</footer>",
    ]
    return "\n".join(lines)


def format_rich_stop() -> str:
    """Rich message for /stop."""
    lines = [
        "## ❌ Baja completada",
        "",
        "Ya **no recibirás** notificaciones diarias.",
        "",
        "Si cambias de opinión, usa `/start` para volver a suscribirte.",
    ]
    return "\n".join(lines)


def format_rich_ayuda() -> str:
    """Rich help message for /ayuda."""
    lines = [
        "## ⚡ PrecioLuz Bot — Ayuda",
        "",
        "### 📋 Comandos",
        "",
        "| Comando | Qué hace |",
        "|:--------|:---------|",
        "| `/start` | Suscribirse a notificaciones diarias |",
        "| `/stop` | Darse de baja |",
        "| `/precio` | Consultar precio de hoy (o mañana después de las 20h) |",
        "| `/grafico` | Gráfico visual de precios ordenados |",
        "| `/ayuda` | Mostrar esta ayuda |",
        "",
        "### 📊 Cómo funciona",
        "",
        "- Los precios se obtienen de la **API oficial ESIOS** de Red Eléctrica Española.",
        "- Cada día a las **20:15h** recibirás los precios del día siguiente.",
        "- Si los precios no están listos, se reintenta automáticamente.",
        "",
        "### 🎨 Colores",
        "",
        "- 🟢 **Verde**: precio barato (cuartil 1)",
        "- 🟡 **Amarillo**: precio asequible (cuartil 2)",
        "- 🟠 **Naranja**: precio medio (cuartil 3)",
        "- 🔴 **Rojo**: precio caro (cuartil 4)",
        "- 💰 Las 3 horas **más baratas** del día",
        "- 💀 Las 3 horas **más caras** del día",
        "",
        "---",
        "",
        "<footer>by HPVF · Fuente: REE ESIOS</footer>",
    ]
    return "\n".join(lines)


def format_thinking(message: str = "Analizando datos de ESIOS...") -> str:
    """Draft message with thinking block for streaming."""
    return f"## ⚡ Consultando precios\n\n<tg-thinking>{message}</tg-thinking>"


def format_draft_partial(prices: list[dict], date_str: str) -> str:
    """Partial draft: header + summary only (before full table)."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    day_name = DAY_NAMES[dt.weekday()]
    month_name = MONTH_NAMES[dt.month]

    sorted_by_price = sorted(prices, key=lambda p: p["price_kwh"])
    avg_price = sum(p["price_kwh"] for p in prices) / len(prices)
    cheapest = sorted_by_price[0]
    dearest = sorted_by_price[-1]

    lines = [
        f"## ⚡ Precio de la luz — {day_name} {dt.day} {month_name}",
        "",
        "### 📊 Resumen del día",
        "",
        f"- **Más barata:** `{cheapest['hour']:02d}:00h` → **`{_fmt(cheapest['price_kwh'])} €/kWh`** 🟢💰",
        f"- **Más cara:** `{dearest['hour']:02d}:00h` → **`{_fmt(dearest['price_kwh'])} €/kWh`** 🔴💀",
        f"- **Media del día:** **`{_fmt(avg_price)} €/kWh`**",
        "",
        "---",
        "",
        "### 🕐 Desglose horario",
        "",
        "<tg-thinking>Cargando tabla de precios...</tg-thinking>",
    ]
    return "\n".join(lines)


def _fmt(price: float) -> str:
    """Format price with 4 decimals, comma as decimal separator."""
    return f"{price:.4f}".replace(".", ",")


def _build_bar_visual(price: float, max_price: float, min_price: float, max_len: int = 8) -> str:
    """Build a proportional bar using block characters."""
    if max_price == min_price:
        return "▓" * max_len

    ratio = (price - min_price) / (max_price - min_price)
    filled = max(1, min(round(ratio * max_len), max_len))
    empty = max_len - filled

    return "█" * filled + "░" * empty
