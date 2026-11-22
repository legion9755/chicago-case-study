"""
lib/charts.py — the Insights charts: one ChartDef per chart (endpoint + ECharts option builder),
grouped into the three Use Case sections.

Charts render with `st.echarts_chart(theme="streamlit")`, so series colours, fonts, grid lines and
tooltips follow the app theme (light and dark) from .streamlit/config.toml. Only semantic
highlights (peak, outlier, overall line) and the heatmap scales are set here.
"""
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import streamlit as st

from lib.api import api
from lib.export import build_zip, render_png

Option = dict[str, Any]


# =============================================================================
# Palette for highlights and heatmaps, per appearance mode
# =============================================================================
@dataclass(frozen=True)
class Palette:
    highlight: str          # peak / outlier / reference lines
    muted: str              # de-emphasised bars (incomplete year)
    sequential: list[str]   # 0 → max
    diverging: list[str]    # -1 → 0 → +1
    background: str         # page background, used to mask lines behind labels


LIGHT = Palette(
    highlight="#C2261C", muted="#9DC3E6",
    sequential=["#F0F6FB", "#BCD6EE", "#66A1D3", "#2E6BA8", "#1F4E79", "#0F2840"],
    diverging=["#2E6BA8", "#93BDE2", "#F4F6F9", "#F2A48F", "#C2261C"],
    background="#FFFFFF",
)
DARK = Palette(
    highlight="#F87171", muted="#3B5A78",
    sequential=["#17212F", "#1F4E79", "#2E6BA8", "#4285C2", "#93BDE2", "#F0F6FB"],
    diverging=["#5B9BD5", "#2C4A66", "#17212F", "#7A3A36", "#F87171"],
    background="#0E1520",
)


def palette() -> Palette:
    return DARK if st.context.theme.type == "dark" else LIGHT


# =============================================================================
# Chart definitions
# =============================================================================
@dataclass
class ChartDef:
    key: str                                            # also the export file name
    title: str
    endpoint: str
    build: Callable[[dict, Palette], tuple[Option | None, pd.DataFrame]]   # option (None = empty) + data table
    alt: str
    extra: dict[str, Any] = field(default_factory=dict)  # extra query params
    filtered: bool = True                               # do the sidebar filters apply?
    insight: Callable[[dict], str] = lambda r: r["insight"]
    height: int = 320
    show_table: bool = False                            # also show the data table under the chart
    empty_message: str = "No data for these filters."


def _grid(**kw: Any) -> Option:
    return {"left": 8, "right": 28, "top": 36, "bottom": 8, "containLabel": True, **kw}


def _hbar(df: pd.DataFrame, y: str, x: str, label: str, x_name: str, extra_tooltip: list[str] | None = None,
          **series: Any) -> Option:
    """Horizontal bar chart, largest at the top."""
    return {
        "dataset": {"source": df},
        "grid": _grid(right=64),
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "xAxis": {"type": "value", "name": x_name, "nameLocation": "middle", "nameGap": 26},
        "yAxis": {"type": "category", "inverse": True, "axisTick": {"show": False}},
        "series": [{
            "type": "bar", "name": x_name, "barMaxWidth": 22,
            "encode": {"x": x, "y": y, "tooltip": [x, *(extra_tooltip or [])]},
            "label": {"show": True, "position": "right", "formatter": label},
            **series,
        }],
    }


# ---- Use Case 2 ------------------------------------------------------------
def crimes_per_year(r: dict, p: Palette) -> tuple[Option, pd.DataFrame]:
    d = pd.DataFrame(r["data"])
    d["year"] = d["year"].astype(str)
    complete = d["months_covered"] == 12
    d["Complete year"] = d["crimes"].where(complete)
    d["Incomplete year"] = d["crimes"].where(~complete)
    label = {"show": True, "position": "top"}
    series = []           # only series that have bars, so the legend never lists an empty one
    if complete.any():
        series.append({"type": "bar", "name": "Complete year", "stack": "y", "barMaxWidth": 48,
                       "encode": {"x": "year", "y": "Complete year"}, "label": label})
    if (~complete).any():
        series.append({"type": "bar", "name": "Incomplete year", "stack": "y", "barMaxWidth": 48,
                       "encode": {"x": "year", "y": "Incomplete year"}, "label": label,
                       "itemStyle": {"color": p.muted}})
    option = {
        "dataset": {"source": d[["year", "Complete year", "Incomplete year"]]},
        "legend": {"top": 0, "right": 0},
        "grid": _grid(),
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "xAxis": {"type": "category"},
        "yAxis": {"type": "value", "name": "Crimes"},
        "series": series,
    }
    return option, d[["year", "crimes", "months_covered"]]


def top_categories(r: dict, p: Palette) -> tuple[Option, pd.DataFrame]:
    d = pd.DataFrame(r["data"])
    d["primary_type"] = d["primary_type"].str.title()
    return _hbar(d, "primary_type", "crimes", "{@crimes} ({@percent}%)", "Crimes", ["percent"]), d


def arrest_by_category(r: dict, p: Palette) -> tuple[Option | None, pd.DataFrame]:
    d = pd.DataFrame(r["data"])
    if d.empty:
        return None, d
    d["primary_type"] = d["primary_type"].str.title()
    option = _hbar(
        d, "primary_type", "arrest_rate_pct", "{@arrest_rate_pct}%", "Arrest rate (%)", ["crimes", "arrests"],
        markLine={"symbol": "none", "silent": True, "z": 1,
                  "lineStyle": {"color": p.highlight, "type": "dashed", "width": 1.5},
                  # y-axis is inverted, so "start" is the top edge: keeps the label off the x-axis ticks
                  "label": {"formatter": "overall {c}%", "color": p.highlight, "position": "start",
                            "fontWeight": 600, "backgroundColor": p.background,
                            "padding": [2, 6], "borderRadius": 4},
                  "data": [{"xAxis": r["overall_pct"]}]},
    )
    # outline the value labels in the background colour so the dashed line passes behind them
    option["series"][0]["label"].update(textBorderColor=p.background, textBorderWidth=3)
    option["grid"]["top"] = 40
    option["xAxis"]["max"] = 100
    return option, d


def arrest_by_year(r: dict, p: Palette) -> tuple[Option, pd.DataFrame]:
    d = pd.DataFrame(r["data"])
    d["year"] = d["year"].astype(str)
    option = {
        "dataset": {"source": d},
        "grid": _grid(),
        "tooltip": {"trigger": "axis"},
        "xAxis": {"type": "category", "boundaryGap": False},
        "yAxis": {"type": "value", "max": 100, "name": "Arrest rate (%)", "axisLabel": {"formatter": "{value}%"}},
        "series": [{
            "type": "line", "name": "Arrest rate (%)", "symbolSize": 8, "lineStyle": {"width": 3},
            "encode": {"x": "year", "y": "arrest_rate_pct", "tooltip": ["arrest_rate_pct", "crimes", "arrests"]},
            "label": {"show": True, "position": "top", "formatter": "{@arrest_rate_pct}% · n={@crimes}"},
        }],
    }
    return option, d


def heatmap(r: dict, p: Palette) -> tuple[Option, pd.DataFrame]:
    days = [x[:3] for x in r["days"]]
    values = r["values"]
    cells = [[di, mi, int(v)] for mi, row in enumerate(values) for di, v in enumerate(row)]
    vmax = max((c[2] for c in cells), default=0)
    option = {
        "grid": _grid(bottom=56),
        "tooltip": {"position": "top"},
        "xAxis": {"type": "category", "data": days, "splitArea": {"show": True}},
        "yAxis": {"type": "category", "data": r["months"], "inverse": True, "splitArea": {"show": True}},
        "visualMap": {"min": 0, "max": max(vmax, 1), "calculable": True, "orient": "horizontal",
                      "left": "center", "bottom": 0, "itemHeight": 160,
                      "inRange": {"color": p.sequential}},
        "series": [{"type": "heatmap", "name": "Crimes", "data": cells,
                    "label": {"show": True, "fontSize": 10},
                    "itemStyle": {"borderWidth": 1, "borderColor": "transparent"},
                    "emphasis": {"itemStyle": {"shadowBlur": 6}}}],
    }
    table = pd.DataFrame(values, index=r["months"], columns=days).reset_index(names="month")
    return option, table


def _peak_bars(d: pd.DataFrame, x: str, y: str, p: Palette, peak_name: str, y_name: str) -> Option:
    """Bars with the single highest bar highlighted (two stacked series, one value each)."""
    peak = d[y].idxmax()
    d = d.assign(**{y_name: d[y].where(d.index != peak), peak_name: d[y].where(d.index == peak)})
    label = {"show": True, "position": "top"}
    return {
        "dataset": {"source": d[[x, y_name, peak_name]]},
        "legend": {"top": 0, "right": 0},
        "grid": _grid(),
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "xAxis": {"type": "category"},
        "yAxis": {"type": "value", "name": "Crimes"},
        "series": [
            {"type": "bar", "name": y_name, "stack": "m", "encode": {"x": x, "y": y_name}, "label": label},
            {"type": "bar", "name": peak_name, "stack": "m", "encode": {"x": x, "y": peak_name}, "label": label,
             "itemStyle": {"color": p.highlight}},
        ],
    }


def by_month(r: dict, p: Palette) -> tuple[Option, pd.DataFrame]:
    d = pd.DataFrame(r["data"])
    return _peak_bars(d, "month", "crimes", p, "Peak month", "Crimes"), d


def communities_count(r: dict, p: Palette) -> tuple[Option, pd.DataFrame]:
    d = pd.DataFrame(r["by_count"])[["community_name", "crimes", "population", "per_1000"]]
    return _hbar(d, "community_name", "crimes", "{@crimes}", "Crimes", ["per_1000"]), d


def communities_rate(r: dict, p: Palette) -> tuple[Option, pd.DataFrame]:
    d = pd.DataFrame(r["by_rate"])[["community_name", "per_1000", "crimes", "population"]]
    return _hbar(d, "community_name", "per_1000", "{@per_1000}", "Crimes per 1,000 residents",
                 ["crimes", "population"]), d


# ---- Use Case 3 ------------------------------------------------------------
def by_hour(r: dict, p: Palette) -> tuple[Option, pd.DataFrame]:
    d = pd.DataFrame(r["data"])
    d["hour"] = d["hour"].map(lambda h: f"{h:02d}:00")
    option = {
        "dataset": {"source": d},
        "grid": _grid(),
        "tooltip": {"trigger": "axis"},
        "xAxis": {"type": "category", "boundaryGap": False, "axisLabel": {"interval": 1}},
        "yAxis": {"type": "value", "name": "Crimes"},
        "series": [{"type": "line", "name": "Crimes", "smooth": True, "showSymbol": True,
                    "areaStyle": {"opacity": 0.15}, "lineStyle": {"width": 3},
                    "encode": {"x": "hour", "y": "crimes"}}],
    }
    return option, d


def outliers(r: dict, p: Palette) -> tuple[Option, pd.DataFrame]:
    d = pd.DataFrame(r["counts"])
    s = r["stats"]
    arr = d["crimes"]
    lo_whisker = float(arr[arr >= s["lower_fence"]].min())
    hi_whisker = float(arr[arr <= s["upper_fence"]].max())
    out = pd.DataFrame(r["outliers"])
    cat = "Community areas"
    points = [{"value": [float(row["crimes"]), cat], "name": row["community_name"]} for _, row in out.iterrows()]
    option = {
        "grid": _grid(top=48),
        "tooltip": {"trigger": "item"},
        "legend": {"top": 0, "right": 0},
        "xAxis": {"type": "value", "name": "Crimes per community area", "nameLocation": "middle", "nameGap": 26},
        "yAxis": {"type": "category", "data": [cat], "axisLabel": {"show": False}, "axisTick": {"show": False}},
        "series": [
            {"type": "boxplot", "name": "Distribution", "boxWidth": [30, 60],
             "data": [[lo_whisker, s["q1"], s["median"], s["q3"], hi_whisker]],
             "markLine": {"symbol": "none", "lineStyle": {"color": p.highlight, "type": "dashed"},
                          "label": {"formatter": "upper fence {c}", "color": p.highlight},
                          "data": [{"xAxis": round(s["upper_fence"], 1)}]}},
            {"type": "scatter", "name": "Outliers", "symbolSize": 11, "data": points,
             "itemStyle": {"color": p.highlight},
             "label": {"show": True, "formatter": "{b}", "position": "top", "fontSize": 10}},
        ],
    }
    table = out[["community_name", "crimes", "population"]] if not out.empty else out
    return option, table


def correlation(r: dict, p: Palette) -> tuple[Option, pd.DataFrame]:
    cols = r["columns"]
    m = r["matrix"]
    cells = [[j, i, None if m[i][j] is None else round(float(m[i][j]), 2)]
             for i in range(len(cols)) for j in range(len(cols)) if j <= i]
    option = {
        "grid": _grid(bottom=56, top=12),
        "tooltip": {"position": "top"},
        "xAxis": {"type": "category", "data": cols, "axisLabel": {"rotate": 35}, "splitArea": {"show": True}},
        "yAxis": {"type": "category", "data": cols, "inverse": True, "splitArea": {"show": True}},
        "visualMap": {"min": -1, "max": 1, "calculable": True, "orient": "horizontal", "left": "center",
                      "bottom": 0, "itemHeight": 200, "inRange": {"color": p.diverging}},
        "series": [{"type": "heatmap", "name": "r", "data": cells, "label": {"show": True, "fontSize": 10}}],
    }
    return option, pd.DataFrame(m, index=cols, columns=cols).reset_index(names="feature")


# ---- Use Case 4 ------------------------------------------------------------
def vw_yearly(r: dict, p: Palette) -> tuple[Option, pd.DataFrame]:
    d = pd.DataFrame(r["data"])
    src = d.assign(year=d["year"].astype(str))
    option = {
        "dataset": {"source": src[["year", "total_crimes", "arrest_rate_pct"]]},
        "legend": {"top": 0, "right": 0},
        "grid": _grid(),
        "tooltip": {"trigger": "axis"},
        "xAxis": {"type": "category"},
        "yAxis": [{"type": "value", "name": "Crimes"},
                  {"type": "value", "name": "Arrest rate", "max": 100, "splitLine": {"show": False},
                   "axisLabel": {"formatter": "{value}%"}}],
        "series": [
            {"type": "bar", "name": "Crimes", "barMaxWidth": 48, "encode": {"x": "year", "y": "total_crimes"}},
            {"type": "line", "name": "Arrest rate (%)", "yAxisIndex": 1, "symbolSize": 8,
             "lineStyle": {"width": 3, "color": p.highlight}, "itemStyle": {"color": p.highlight},
             "encode": {"x": "year", "y": "arrest_rate_pct"}},
        ],
    }
    return option, d


def vw_category(r: dict, p: Palette) -> tuple[Option, pd.DataFrame]:
    d = pd.DataFrame(r["data"]).head(5)
    src = d.assign(primary_type=d["primary_type"].str.title())
    option = _hbar(src, "primary_type", "pct_of_total", "{@pct_of_total}% ({@total_crimes})", "% of all crimes",
                   ["total_crimes"])
    return option, d


# =============================================================================
# Registry
# =============================================================================
CHARTS: dict[str, ChartDef] = {c.key: c for c in [
    ChartDef("uc2_1_crimes_per_year", "Total crimes per year", "/analytics/crimes-by-year", crimes_per_year,
             alt="Bar chart of total crimes per year; incomplete years shown lighter"),
    ChartDef("uc2_2_top10_categories", "Top 10 crime categories", "/analytics/categories", top_categories,
             alt="Horizontal bar chart of the 10 most frequent crime categories", extra={"top": 10}),
    ChartDef("uc2_3_arrest_rate_by_category", "Arrest rate by category", "/analytics/arrest-rate-by-category",
             arrest_by_category, alt="Horizontal bar chart of arrest rate per crime category with the overall rate",
             empty_message="No crime category has enough crimes for these filters."),
    ChartDef("uc2_3b_arrest_rate_per_year", "Arrest rate per year", "/analytics/arrest-rate-by-year",
             arrest_by_year, alt="Line chart of arrest rate per year, labelled with the number of crimes"),
    ChartDef("uc2_4_heatmap_month_day", "Month × day of week", "/analytics/heatmap", heatmap,
             alt="Heatmap of crime counts by month and day of week", height=420),
    ChartDef("uc2_q3_crimes_by_month", "Which month has the most crimes?", "/analytics/crimes-by-month", by_month,
             alt="Bar chart of crimes per month with the peak month highlighted", height=420),
    ChartDef("uc2_5_top10_communities", "Top 10 community areas · crime count", "/analytics/top-communities",
             communities_count, alt="Horizontal bar chart of the 10 community areas with the most crimes",
             extra={"top": 10}),
    ChartDef("uc2_5b_top10_communities_per_capita", "Top 10 community areas · per 1,000 residents",
             "/analytics/top-communities", communities_rate,
             alt="Horizontal bar chart of the 10 community areas with the most crimes per 1,000 residents",
             extra={"top": 10}, insight=lambda r: "Per-capita view: " + r["insight"]),
    ChartDef("uc3_1_crimes_per_hour", "Crimes per hour of day", "/analytics/crimes-by-hour", by_hour,
             alt="Line chart of crimes per hour of day"),
    ChartDef("uc3_2_community_outliers", "Community-area outliers (IQR rule)", "/analytics/community-outliers",
             outliers, alt="Box plot of crimes per community area with outlier areas labelled"),
    ChartDef("uc3_3_correlation_heatmap", "Correlation matrix of numeric features", "/analytics/correlation",
             correlation, alt="Lower-triangle correlation heatmap of numeric crime features", height=480),
    ChartDef("uc4_1_vw_crime_yearly", "vw_crime_yearly · crimes & arrest rate", "/analytics/views/vw_crime_yearly",
             vw_yearly, alt="Bars of crimes per year with a line of arrest rate, from the SQL view",
             filtered=False, show_table=True),
    ChartDef("uc4_2_vw_crime_by_category_top5", "vw_crime_by_category · top 5 crime types",
             "/analytics/views/vw_crime_by_category", vw_category,
             alt="Horizontal bar chart of the top 5 crime types as a share of all crimes, from the SQL view",
             filtered=False, show_table=True),
]}

# Layout per section: each inner list is one row (1 = full width, 2 = side by side).
SECTIONS: dict[str, dict[str, Any]] = {
    "uc2": {"label": "Exploratory analysis",
            "caption": "Use case 2 — volumes, categories, arrest rates, timing and community areas.",
            "rows": [["uc2_1_crimes_per_year", "uc2_2_top10_categories"],
                     ["uc2_3_arrest_rate_by_category", "uc2_3b_arrest_rate_per_year"],
                     ["uc2_4_heatmap_month_day", "uc2_q3_crimes_by_month"],
                     ["uc2_5_top10_communities", "uc2_5b_top10_communities_per_capita"]]},
    "uc3": {"label": "Statistical insights",
            "caption": "Use case 3 — hourly pattern, IQR outliers and correlations.",
            "rows": [["uc3_1_crimes_per_hour", "uc3_2_community_outliers"],
                     ["uc3_3_correlation_heatmap"]]},
    "uc4": {"label": "SQL views",
            "caption": "Use case 4 — read from the database views `vw_crime_yearly` and `vw_crime_by_category`. "
                       "The sidebar filters do not apply here.",
            "rows": [["uc4_1_vw_crime_yearly", "uc4_2_vw_crime_by_category_top5"]]},
}


def query_for(c: ChartDef, params: dict[str, Any]) -> dict[str, Any]:
    return {**(params if c.filtered else {}), **c.extra}


# =============================================================================
# ZIP of every chart (runs off-thread when the download button is clicked)
# =============================================================================
def zip_all(params_json: str) -> bytes:
    """Fetch every chart's data straight from the API and render all PNGs + insights.txt."""
    params = json.loads(params_json)
    items, skipped = [], []
    for c in CHARTS.values():
        status, r = api("GET", c.endpoint, params=query_for(c, params))
        if status != 200:
            skipped.append(c.key)
            continue
        insight = c.insight(r)
        items.append((c.key, render_png(c.key, json.dumps(r), insight), insight))
    return build_zip(items, params, skipped)
