"""
lib/export.py — "chart + insight" PNG export and the ZIP of every chart.

The on-screen charts are interactive ECharts; the exported image is drawn with matplotlib so it
is a self-contained file: the chart with a panel underneath holding the backend's insight text.

Images are only rendered when a download button is clicked (Streamlit runs the callable on a
worker thread), so this module uses matplotlib's object API (`Figure`), never `pyplot`'s global
state, and serialises rendering with a lock.
"""
import io
import json
import os
import textwrap
import threading
import zipfile
from collections.abc import Callable
from datetime import datetime
from functools import lru_cache
from typing import Any

import matplotlib
matplotlib.use("Agg")
import numpy as np                                    # noqa: E402
import pandas as pd                                   # noqa: E402
import seaborn as sns                                 # noqa: E402
from matplotlib.figure import Figure                  # noqa: E402
from matplotlib.patches import Rectangle              # noqa: E402
from PIL import Image, ImageDraw, ImageFont           # noqa: E402

# Brand palette (matches .streamlit/config.toml, light mode).
NAVY, BLUE, LIGHT_BLUE = "#1F4E79", "#2E86C1", "#9DC3E6"
GREEN, RED, ORANGE, BROWN, VIOLET = "#15803D", "#C2261C", "#C2410C", "#843C0C", "#6D28D9"

sns.set_theme(style="whitegrid")
matplotlib.rcParams.update({"axes.titleweight": "bold", "axes.titlesize": 12,
                            "axes.spines.top": False, "axes.spines.right": False})

FONT_PATH = os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans.ttf")
FONT_BOLD = os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans-Bold.ttf")

_render_lock = threading.Lock()


# =============================================================================
# One matplotlib renderer per chart key. Each receives the API response and returns a Figure.
# =============================================================================
def _fig(w: float = 7, h: float = 4.2) -> tuple[Figure, Any]:
    fig = Figure(figsize=(w, h))
    return fig, fig.subplots()


def _crimes_per_year(r: dict) -> Figure:
    d = pd.DataFrame(r["data"])
    fig, ax = _fig()
    colors = [NAVY if m == 12 else LIGHT_BLUE for m in d["months_covered"]]
    bars = ax.bar(d["year"].astype(str), d["crimes"], color=colors)
    ax.bar_label(bars, fmt="{:,.0f}", padding=2, fontsize=9)
    ax.set(title="Total crimes per year", xlabel="Year", ylabel="Crimes")
    if (d["months_covered"] < 12).any():
        ax.legend(handles=[Rectangle((0, 0), 1, 1, color=LIGHT_BLUE)], labels=["incomplete year"])
    return fig


def _top_categories(r: dict) -> Figure:
    d = pd.DataFrame(r["data"]).iloc[::-1]
    fig, ax = _fig()
    bars = ax.barh(d["primary_type"].str.title(), d["crimes"], color=BLUE)
    ax.bar_label(bars, labels=[f" {c} ({p}%)" for c, p in zip(d["crimes"], d["percent"])], fontsize=8)
    ax.set(title="Top 10 crime categories", xlabel="Crimes")
    ax.set_xlim(0, d["crimes"].max() * 1.3)
    return fig


def _arrest_by_category(r: dict) -> Figure:
    d = pd.DataFrame(r["data"])
    fig, ax = _fig()
    if not d.empty:
        d = d.iloc[::-1]
        ax.barh(d["primary_type"].str.title(), d["arrest_rate_pct"], color=GREEN)
        ax.axvline(r["overall_pct"], color=RED, ls="--", label=f"overall {r['overall_pct']}%")
        ax.legend(loc="lower right")
    ax.set(title=f"Arrest rate by category (≥{r['min_n']} crimes)", xlabel="Arrest rate (%)")
    return fig


def _arrest_by_year(r: dict) -> Figure:
    d = pd.DataFrame(r["data"])
    fig, ax = _fig()
    ax.plot(d["year"].astype(str), d["arrest_rate_pct"], marker="o", lw=2.5, color=GREEN)
    for x, y, n in zip(d["year"].astype(str), d["arrest_rate_pct"], d["crimes"]):
        ax.annotate(f"n={n}", (x, y), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=8)
    ax.set(title="Arrest rate per year (n = crimes)", xlabel="Year", ylabel="Arrest rate (%)", ylim=(0, 115))
    return fig


def _heatmap(r: dict) -> Figure:
    fig, ax = _fig(7, 5)
    sns.heatmap(pd.DataFrame(r["values"], index=r["months"], columns=[x[:3] for x in r["days"]]),
                annot=True, fmt="d", cmap="Blues", linewidths=.4, ax=ax, cbar_kws={"label": "Crimes"})
    ax.set(title="Crime frequency: month × day of week")
    return fig


def _by_month(r: dict) -> Figure:
    d = pd.DataFrame(r["data"])
    fig, ax = _fig(7, 5)
    bars = ax.bar(d["month"], d["crimes"], color=BLUE)
    bars[int(d["crimes"].idxmax())].set_color(RED)
    ax.bar_label(bars, fontsize=8, padding=2)
    ax.set(title="Which month has the highest crime frequency?", ylabel="Crimes")
    return fig


def _communities_count(r: dict) -> Figure:
    d = pd.DataFrame(r["by_count"]).iloc[::-1]
    fig, ax = _fig()
    bars = ax.barh(d["community_name"], d["crimes"], color=ORANGE)
    ax.bar_label(bars, padding=2, fontsize=8)
    ax.set(title="Top 10 community areas (crime count)", xlabel="Crimes")
    return fig


def _communities_rate(r: dict) -> Figure:
    d = pd.DataFrame(r["by_rate"]).iloc[::-1]
    fig, ax = _fig()
    bars = ax.barh(d["community_name"], d["per_1000"], color=BROWN)
    ax.bar_label(bars, padding=2, fontsize=8)
    ax.set(title="Top 10 community areas (per 1,000 residents)", xlabel="Crimes per 1,000 residents")
    return fig


def _by_hour(r: dict) -> Figure:
    d = pd.DataFrame(r["data"])
    fig, ax = _fig()
    ax.plot(d["hour"], d["crimes"], marker="o", lw=2.5, color=VIOLET)
    ax.fill_between(d["hour"], d["crimes"], alpha=.12, color=VIOLET)
    ax.set(title="Crimes per hour of day" + ("" if r["has_time_of_day"] else " (no times in source)"),
           xlabel="Hour", ylabel="Crimes", xticks=range(0, 24, 2))
    return fig


def _outliers(r: dict) -> Figure:
    d, stats = pd.DataFrame(r["counts"]), r["stats"]
    fig, ax = _fig()
    sns.boxplot(x=d["crimes"], ax=ax, color=LIGHT_BLUE, width=.45, whis=1.5,
                flierprops=dict(marker="o", markerfacecolor=RED, markersize=8))
    ax.axvline(stats["upper_fence"], color=RED, ls="--", lw=1)
    ax.text(stats["upper_fence"], -0.38, f" upper fence {stats['upper_fence']:.1f}", color=RED, fontsize=8)
    for i, (_, row) in enumerate(pd.DataFrame(r["outliers"]).iterrows()):
        ax.annotate(row["community_name"], (row["crimes"], 0), xytext=(0, 14 + 12 * (i % 2)),
                    textcoords="offset points", ha="center", fontsize=8)
    ax.set(title="Crimes per community area — box plot + IQR outliers", xlabel="Crimes", yticks=[])
    return fig


def _correlation(r: dict) -> Figure:
    corr = pd.DataFrame(r["matrix"], index=r["columns"], columns=r["columns"])
    fig, ax = _fig(9, 6.5)
    sns.heatmap(corr, mask=np.triu(np.ones_like(corr, dtype=bool), k=1), annot=True, fmt=".2f",
                cmap="coolwarm", vmin=-1, vmax=1, center=0, linewidths=.5, ax=ax, annot_kws={"size": 8})
    ax.set(title="Correlation matrix of numeric features")
    return fig


def _vw_yearly(r: dict) -> Figure:
    d = pd.DataFrame(r["data"])
    fig, ax = _fig()
    ax.bar(d["year"].astype(str), d["total_crimes"], color=LIGHT_BLUE, label="Crimes")
    ax.set(title="vw_crime_yearly — crimes & arrest rate", xlabel="Year", ylabel="Crimes")
    ax2 = ax.twinx()
    ax2.plot(d["year"].astype(str), d["arrest_rate_pct"], color=RED, marker="o", lw=2, label="Arrest rate %")
    ax2.set_ylabel("Arrest rate (%)", color=RED)
    ax2.set_ylim(0, 115)
    ax2.grid(False)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left")
    return fig


def _vw_category(r: dict) -> Figure:
    d = pd.DataFrame(r["data"]).head(5).iloc[::-1]
    fig, ax = _fig()
    bars = ax.barh(d["primary_type"].str.title(), d["pct_of_total"], color=NAVY)
    ax.bar_label(bars, labels=[f" {p}% ({n})" for p, n in zip(d["pct_of_total"], d["total_crimes"])], fontsize=9)
    ax.set(title="vw_crime_by_category — top 5 crime types", xlabel="% of all crimes")
    ax.set_xlim(0, d["pct_of_total"].max() * 1.35)
    return fig


FIGURES: dict[str, Callable[[dict], Figure]] = {
    "uc2_1_crimes_per_year": _crimes_per_year,
    "uc2_2_top10_categories": _top_categories,
    "uc2_3_arrest_rate_by_category": _arrest_by_category,
    "uc2_3b_arrest_rate_per_year": _arrest_by_year,
    "uc2_4_heatmap_month_day": _heatmap,
    "uc2_q3_crimes_by_month": _by_month,
    "uc2_5_top10_communities": _communities_count,
    "uc2_5b_top10_communities_per_capita": _communities_rate,
    "uc3_1_crimes_per_hour": _by_hour,
    "uc3_2_community_outliers": _outliers,
    "uc3_3_correlation_heatmap": _correlation,
    "uc4_1_vw_crime_yearly": _vw_yearly,
    "uc4_2_vw_crime_by_category_top5": _vw_category,
}


# =============================================================================
# Image assembly
# =============================================================================
def fig_to_png(fig: Figure) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    return buf.getvalue()


def png_with_insight(chart_png: bytes, insight: str) -> bytes:
    """Append a panel with the wrapped insight text under the chart image."""
    chart = Image.open(io.BytesIO(chart_png)).convert("RGB")
    w = chart.width
    size = max(16, min(22, w // 45))
    font, bold = ImageFont.truetype(FONT_PATH, size), ImageFont.truetype(FONT_BOLD, size)
    chars = max(40, int(w / (size * 0.58)))
    lines = textwrap.wrap(insight, width=chars)
    line_h, pad = int(size * 1.45), 24
    panel_h = pad * 2 + line_h * (len(lines) + 1)
    out = Image.new("RGB", (w, chart.height + panel_h), "white")
    out.paste(chart, (0, 0))
    d = ImageDraw.Draw(out)
    y0 = chart.height
    d.rectangle([pad // 2, y0 + 8, w - pad // 2, y0 + panel_h - 8], fill="#EEF4FB", outline=LIGHT_BLUE, width=2)
    d.text((pad, y0 + pad), "Insight", font=bold, fill=NAVY)
    for i, line in enumerate(lines):
        d.text((pad, y0 + pad + line_h * (i + 1)), line, font=font, fill="#222222")
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


@lru_cache(maxsize=128)
def render_png(key: str, response_json: str, insight: str) -> bytes:
    """Chart + insight as one PNG. Cached per (chart, data, insight); safe to call off-thread."""
    with _render_lock:
        fig = FIGURES[key](json.loads(response_json))
        return png_with_insight(fig_to_png(fig), insight)


def build_zip(items: list[tuple[str, bytes, str]], params: dict[str, Any], skipped: list[str]) -> bytes:
    """Every exported chart as PNG plus insights.txt."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        report = [f"Chicago Crime Dashboard export — {datetime.now():%d %b %Y %H:%M}",
                  f"Filters: {json.dumps(params)}", ""]
        for key, png, insight in items:
            z.writestr(f"{key}.png", png)
            report += [key, f"  {insight}", ""]
        if skipped:
            report += ["Not exported (no data for these filters): " + ", ".join(skipped)]
        z.writestr("insights.txt", "\n".join(report))
    return buf.getvalue()
