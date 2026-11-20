"""
Overview — the landing page: headline KPIs (compared with all data when filters are active),
four highlight cards, the crime mix and the top community areas. Links lead to the detailed charts.
"""
from typing import Any

import pandas as pd
import streamlit as st

from lib.api import error_message, get, is_no_match
from lib.charts import SECTIONS, communities_count, crime_mix, palette
from lib.filters import active_filters, link_params, render_filters, require_summary
from lib.maps import build_deck, incidents_frame

INSIGHTS = "app_pages/insights.py"
COMMUNITIES = "app_pages/communities.py"

params = render_filters()
filtered = active_filters() > 0


def fetch(path: str, extra: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """GET with the current filters; None if the API has no data for them.

    Any other failure (e.g. an outdated backend without this endpoint) is shown as an error.
    """
    status, body = get(path, {**params, **(extra or {})})
    if status == 200:
        return body
    if not is_no_match(status, body):
        st.error(error_message(status, body), icon=":material/error:")
    return None


def insights_link(label: str, section: str = "uc2") -> None:
    """Link to the Insights page, opened on `section` and keeping the current filters."""
    st.page_link(INSIGHTS, label=label, icon=":material/arrow_forward:", icon_position="right",
                 query_params=link_params(section=SECTIONS[section]["label"]))


# ---- header ----------------------------------------------------------------
with st.container(horizontal=True, vertical_alignment="bottom"):
    with st.container(gap=None):
        st.title("Overview", anchor=False)
        caption_slot = st.empty()
    st.space("stretch")
    insights_link("All charts & exports")

summ = require_summary(params)
s = summ["data"]
caption_slot.caption(f"Chicago crime at a glance · {s['date_min']} → {s['date_max']}"
                     + (" · filtered view" if filtered else ""))

if summ["is_snapshot"]:
    st.warning(summ["insight"], title="This data is a snapshot", icon=":material/warning:")

# ---- KPIs ------------------------------------------------------------------
# With filters active, each rate shows its difference from the unfiltered data.
base_status, base_body = get("/analytics/summary", {}) if filtered else (0, None)
base = base_body["data"] if base_status == 200 else None
by_month = fetch("/analytics/crimes-by-month")
by_year = fetch("/analytics/arrest-rate-by-year")


def pp_delta(field: str) -> float | None:
    return round(s[field] - base[field], 1) if base else None


vs_all = "pts vs all data" if base else None
with st.grid(4, gap="small", min_column_width=180):
    st.metric(
        "Crimes", f"{s['total_crimes']:,}", border=True, height="stretch",
        help="Number of crimes matching the filters. Sparkline: crimes per month (Jan → Dec).",
        chart_data=[m["crimes"] for m in by_month["data"]] if by_month else None, chart_type="bar",
        delta=f"{s['total_crimes'] / base['total_crimes'] * 100:.1f}% of all" if base else None,
        delta_arrow="off", delta_color="blue",   # fixed colour: also keeps the sparkline on-brand

    )
    st.metric(
        "Arrest rate", f"{s['arrest_rate_pct']}%", pp_delta("arrest_rate_pct"), border=True, height="stretch",
        delta_description=vs_all, help="Share of crimes that led to an arrest. Sparkline: arrest rate per year.",
        chart_data=[y["arrest_rate_pct"] for y in by_year["data"]] if by_year else None, chart_type="line",
    )
    st.metric(
        "Domestic", f"{s['domestic_pct']}%", pp_delta("domestic_pct"), border=True, height="stretch",
        delta_description=vs_all, delta_color="off", help="Share of crimes flagged as domestic.",
    )
    st.metric(
        "Community areas", f"{s['communities']} of 77", border=True, height="stretch",
        help="Chicago community areas with at least one crime matching the filters.",
    )

# ---- highlights ------------------------------------------------------------
st.subheader("Highlights", anchor=False)
cats = fetch("/analytics/categories", {"top": 5})
comms = fetch("/analytics/top-communities", {"top": 5})
heat = fetch("/analytics/heatmap")
arrests = fetch("/analytics/arrest-rate-by-category")

with st.grid(4, gap="small", min_column_width=220):
    with st.container(border=True, height="stretch"):
        st.caption(":material/category: Most common crime")
        if cats and cats["data"]:
            top = cats["data"][0]
            st.markdown(f"### {top['primary_type'].title()}")
            st.progress(min(top["percent"] / 100, 1.0), text=f"{top['crimes']:,} crimes · {top['percent']}% of all")
        else:
            st.caption("No data for these filters.")
        insights_link("Crime categories")

    with st.container(border=True, height="stretch"):
        st.caption(":material/location_on: Hotspot community area")
        if comms and comms["by_count"]:
            top = comms["by_count"][0]
            st.markdown(f"### {top['community_name']}")
            st.caption(f"{top['crimes']:,} crimes")
            if comms["by_rate"]:
                rate = comms["by_rate"][0]
                st.caption(f"Highest per resident: **{rate['community_name']}** ({rate['per_1000']} per 1,000)")
            st.page_link(COMMUNITIES, label=f"Open {top['community_name']}", icon=":material/arrow_forward:",
                         icon_position="right", query_params=link_params(area=top["community_name"]))
        else:
            st.caption("No data for these filters.")
            insights_link("Community areas")

    with st.container(border=True, height="stretch"):
        st.caption(":material/calendar_month: Busiest day")
        if heat:
            grid = pd.DataFrame(heat["values"], index=heat["months"], columns=heat["days"])
            day, month = grid.sum().idxmax(), grid.sum(axis=1).idxmax()
            st.markdown(f"### {day}")
            st.caption(f"{int(grid.sum()[day]):,} crimes on {day}s · busiest month: **{month}**")
        else:
            st.caption("No data for these filters.")
        insights_link("Timing patterns")

    with st.container(border=True, height="stretch"):
        st.caption(":material/gavel: Arrest gap")
        if arrests and len(arrests["data"]) == 1:
            only = arrests["data"][0]
            st.markdown(f"### {only['arrest_rate_pct']:g}%")
            st.caption(f"Arrest rate for **{only['primary_type'].title()}**, the only crime type with enough "
                       "crimes in this view.")
        elif arrests and arrests["data"]:
            hi, lo = arrests["data"][0], arrests["data"][-1]
            st.markdown(f"### {hi['arrest_rate_pct']:g}% → {lo['arrest_rate_pct']:g}%")
            st.caption(f"Highest: **{hi['primary_type'].title()}** · lowest: **{lo['primary_type'].title()}** "
                       f"(overall {arrests['overall_pct']}%)")
        else:
            st.caption("Too few crimes per category for these filters.")
        insights_link("Arrest rates")

# ---- map -------------------------------------------------------------------
inc = fetch("/analytics/incidents")
with st.container(border=True):
    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown("**Where crimes happen**")
        if inc:
            st.caption(f"{inc['mapped']:,} of {inc['total']:,} incidents have a location")
        st.space("stretch")
        map_layer = st.segmented_control("Map style", ["Points", "Heatmap"], default="Points", required=True,
                                         key="overview_map", persist_state="session",
                                         label_visibility="collapsed")
        st.page_link(COMMUNITIES, label="All community areas", icon=":material/arrow_forward:",
                     icon_position="right", query_params=link_params())
    if inc and inc["mapped"]:
        st.pydeck_chart(build_deck(map_layer or "Points", incidents_frame(inc["data"])), height=340,
                        alt=f"{map_layer or 'Points'} of crime locations across Chicago")
        if map_layer != "Heatmap":
            st.caption(":green[●] arrest made · :blue[●] no arrest · hover a point for details")
    else:
        st.caption("No mapped incidents for these filters.")

# ---- charts ----------------------------------------------------------------
p = palette()
c1, c2 = st.columns(2)
with c1:
    with st.container(border=True, height="stretch"):
        st.markdown("**Crime mix** · top 5 types")
        if cats:
            option, _ = crime_mix(cats, p, s["total_crimes"])
            st.echarts_chart(option, height=300, key="overview_mix",
                             alt="Donut chart of the five most common crime types and all others")
            st.caption(f":material/lightbulb: {cats['insight']}")
        else:
            st.caption("No data for these filters.")
with c2:
    with st.container(border=True, height="stretch"):
        st.markdown("**Top community areas** · crime count")
        if comms:
            option, _ = communities_count(comms, p)
            st.echarts_chart(option, height=300, key="overview_communities",
                             alt="Horizontal bar chart of the five community areas with the most crimes")
            st.caption(f":material/lightbulb: {comms['insight']}")
        else:
            st.caption("No data for these filters.")
