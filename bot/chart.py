"""Chart generation for PrecioLuz Bot.

Generates price charts as PNG images using matplotlib.
"""

import io
import logging

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from pytz import timezone

MADRID_TZ = timezone("Europe/Madrid")

_COLOR_MAP = {
    "cheap": "#22c55e",
    "affordable": "#eab308",
    "medium": "#f97316",
    "dear": "#ef4444",
}


def _get_tramo(price: float, t1: float, t2: float, t3: float) -> str:
    if price <= t1:
        return "cheap"
    elif price <= t2:
        return "affordable"
    elif price <= t3:
        return "medium"
    return "dear"


def generate_price_chart(prices: list[dict], date_str: str) -> io.BytesIO:
    """Generate a bar chart of hourly prices and return as PNG BytesIO."""
    from datetime import datetime
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    day_name = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"][dt.weekday()]

    sorted_by_price = sorted(prices, key=lambda p: p["price_kwh"])
    n = len(prices)
    t1 = sorted_by_price[n // 4]["price_kwh"]
    t2 = sorted_by_price[n // 2]["price_kwh"]
    t3 = sorted_by_price[3 * n // 4]["price_kwh"]

    hours = [p["hour"] for p in prices]
    price_vals = [p["price_kwh"] for p in prices]
    colors = [_COLOR_MAP[_get_tramo(p, t1, t2, t3)] for p in price_vals]

    avg = sum(price_vals) / len(price_vals)

    fig, ax = plt.subplots(figsize=(10, 4.5), dpi=150)
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")

    bars = ax.bar(hours, price_vals, color=colors, width=0.7, edgecolor="none", zorder=3)

    ax.axhline(y=avg, color="#94a3b8", linestyle="--", linewidth=1, alpha=0.7, zorder=2)
    ax.text(23.5, avg, f" media\n {avg:.4f}", color="#94a3b8", fontsize=7,
            va="bottom", ha="right", fontweight="bold")

    cheapest_3 = {p["hour"] for p in sorted_by_price[:3]}
    dearest_3 = {p["hour"] for p in sorted_by_price[-3:]}
    for bar_obj, h, pv in zip(bars, hours, price_vals):
        if h in cheapest_3:
            ax.text(bar_obj.get_x() + bar_obj.get_width() / 2, pv,
                    "💰", ha="center", va="bottom", fontsize=7, zorder=4)
        elif h in dearest_3:
            ax.text(bar_obj.get_x() + bar_obj.get_width() / 2, pv,
                    "💀", ha="center", va="bottom", fontsize=7, zorder=4)

    ax.set_xlim(-0.6, 23.6)
    ax.set_xticks(range(0, 24, 2))
    ax.set_xticklabels([f"{h:02d}h" for h in range(0, 24, 2)], color="#cbd5e1", fontsize=8)
    ax.yaxis.set_major_formatter(ticker.FormatStrFormatter("%.3f"))
    ax.tick_params(axis="y", colors="#cbd5e1", labelsize=8)
    ax.tick_params(axis="x", colors="#cbd5e1")

    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.grid(axis="y", alpha=0.15, color="#64748b", zorder=1)

    ax.set_title(f"⚡ Precios PVPC — {day_name} {dt.day}/{dt.month:02d}",
                 color="white", fontsize=13, fontweight="bold", pad=12)
    ax.set_ylabel("€/kWh", color="#94a3b8", fontsize=9)

    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf
