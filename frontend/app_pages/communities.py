"""
Communities — the 77 community areas.

  directory   every area ranked by crimes, with crimes per 1,000 residents, arrest rate and its most
              common crime type, plus a bubble map. Select a row (or use "Jump to") to open an area.
  detail      one area: KPIs compared with the city, top crime types, crimes by month, a map of
              its incidents and the incident list.

The open area is kept in the URL (?area=Austin), so it can be shared as a link.
"""
from functools import partial
from typing import Any

import pandas as pd
import streamlit as st

from lib.api import error_box, get
from lib.charts import by_month, palette, top_categories
from lib.filters import render_filters
from lib.maps import build_deck, incidents_frame

AREA, DIR_VERSION = "area", "communities_dir_version"

params = render_filters(include_community=False)

status, r = get("/analytics/communities", params)
if status != 200:
    error_box(status, r)
    st.stop()
areas = pd.DataFrame(r["data"])
city: dict[str, Any] = r["city"]
names = sorted(areas["community_name"])


def open_area(key: str, table_names: list[str]) -> None:
    rows = st.session_state[key].selection.rows
    if rows:
        st.session_state[AREA] = table_names[rows[0]]


def back_to_directory() -> None:
    st.session_state[AREA] = None
    st.session_state[DIR_VERSION] = st.session_state.get(DIR_VERSION, 0) + 1   # fresh table selection


# ---- header ----------------------------------------------------------------
with st.container(horizontal=True, vertical_alignment="bottom"):
    with st.container(gap=None):
        st.title("Communities", anchor=False)
        caption_slot = st.empty()
    st.space("stretch")
    area = st.selectbox("Community area", names, index=None, placeholder="Jump to a community area…",
                        key=AREA, bind="query-params", label_visibility="collapsed", width=300)
if area is None:
    caption_slot.caption(r["insight"])          # the city-wide summary belongs to the directory


# =============================================================================
# Directory
# =============================================================================
if area is None:
    by_rate = areas.dropna(subset=["per_1000"]).sort_values("per_1000", ascending=False)
    top, top_rate = areas.iloc[0], by_rate.iloc[0] if not by_rate.empty else None
    with st.grid(4, gap="small", min_column_width=180):
        st.metric("Areas with crimes", f"{city['areas_with_crimes']} of {city['areas']}", border=True,
                  height="stretch", help="Community areas with at least one crime matching the filters")
        st.metric("Most crimes", top["community_name"] if top["crimes"] else "—", border=True, height="stretch",
                  help=f"{int(top['crimes'])} crimes" if top["crimes"] else None)
        st.metric("Highest per resident",
                  top_rate["community_name"] if top_rate is not None and top_rate["crimes"] else "—",
                  border=True, height="stretch",
                  help=f"{top_rate['per_1000']:g} crimes per 1,000 residents" if top_rate is not None else None)
        st.metric("City-wide rate", f"{city['per_1000']:g} per 1,000" if city["per_1000"] is not None else "—",
                  border=True, height="stretch", help="All matching crimes per 1,000 Chicago residents")

    left, right = st.columns([3, 2])
    with left:
        with st.container(border=True, height="stretch"):
            st.markdown("**All community areas** · select a row to open it")
            table = areas[["rank_crimes", "community_name", "crimes", "per_1000", "arrest_rate_pct",
                           "top_crime_type", "population"]].reset_index(drop=True)
            key = f"communities_dir_{st.session_state.get(DIR_VERSION, 0)}"
            st.dataframe(
                table, hide_index=True, height=460, key=key, selection_mode="single-row",
                on_select=partial(open_area, key, table["community_name"].tolist()),
                column_config={
                    "rank_crimes": st.column_config.NumberColumn("#", width="small"),
                    "community_name": st.column_config.TextColumn("Community area", pinned=True),
                    "crimes": st.column_config.ProgressColumn(
                        "Crimes", format="%d", min_value=0, max_value=max(int(areas["crimes"].max()), 1)),
                    "per_1000": st.column_config.NumberColumn("Per 1,000 residents", format="%.2f"),
                    "arrest_rate_pct": st.column_config.ProgressColumn(
                        "Arrest rate", format="%.0f%%", min_value=0, max_value=100),
                    "top_crime_type": "Most common crime",
                    "population": st.column_config.NumberColumn("Population", format="localized"),
                },
                placeholder="—", alt="Community areas ranked by number of crimes",
            )
    with right:
        with st.container(border=True, height="stretch"):
            st.markdown("**On the map** · bubble size = crimes")
            st.pydeck_chart(build_deck("Communities", communities=areas), height=460,
                            alt="Map of community areas with bubbles sized by crime count")
    st.stop()


# =============================================================================
# Detail
# =============================================================================
row = areas[areas["community_name"] == area].iloc[0]
code = int(row["community_code"])
crimes = int(row["crimes"])

st.button("All community areas", icon=":material/arrow_back:", type="tertiary", on_click=back_to_directory,
          key="back_to_directory")
st.header(area, anchor=False)
pop = f"population {int(row['population']):,}" if pd.notna(row["population"]) else "population unknown"
rank_rate = f" · #{int(row['rank_per_1000'])} per resident" if pd.notna(row["rank_per_1000"]) else ""
st.caption(f"Community area {code} · {pop} · #{int(row['rank_crimes'])} of {city['areas']} by crimes{rank_rate}")

if crimes == 0:
    st.info(f"No crimes in {area} match the current filters. Widen the filters in the sidebar, or pick another "
            "area.", title="Nothing to show", icon=":material/filter_alt_off:")
    st.stop()


def diff(value: Any, ref: Any, digits: int = 1) -> float | None:
    return None if value is None or ref is None or pd.isna(value) else round(float(value) - float(ref), digits)


with st.grid(4, gap="small", min_column_width=180):
    st.metric("Crimes", f"{crimes:,}", diff(crimes, city["median_crimes"], 0), border=True, height="stretch",
              delta_description="vs median area", delta_color="inverse",
              help="Crimes matching the filters, compared with the median community area")
    st.metric("Per 1,000 residents", f"{row['per_1000']:g}" if pd.notna(row["per_1000"]) else "—",
              diff(row["per_1000"], city["per_1000"], 3), border=True, height="stretch",
              delta_description="vs city", delta_color="inverse")
    st.metric("Arrest rate", f"{row['arrest_rate_pct']:g}%", diff(row["arrest_rate_pct"], city["arrest_rate_pct"]),
              border=True, height="stretch", delta_description="pts vs city")
    st.metric("Domestic", f"{row['domestic_pct']:g}%", diff(row["domestic_pct"], city["domestic_pct"]),
              border=True, height="stretch", delta_description="pts vs city", delta_color="off")

area_params = {**params, "community": [code]}
p = palette()

c1, c2 = st.columns(2)
with c1:
    with st.container(border=True, height="stretch"):
        st.markdown("**Top crime types**")
        s, cats = get("/analytics/categories", {**area_params, "top": 5})
        if s == 200:
            option, _ = top_categories(cats, p)
            st.echarts_chart(option, height=280, key="area_categories", alt=f"Top crime types in {area}")
            st.caption(f":material/lightbulb: {cats['insight']}")
        else:
            error_box(s, cats)
with c2:
    with st.container(border=True, height="stretch"):
        st.markdown("**Crimes by month**")
        s, months = get("/analytics/crimes-by-month", area_params)
        if s == 200:
            option, _ = by_month(months, p)
            st.echarts_chart(option, height=280, key="area_months", alt=f"Crimes per month in {area}")
            st.caption(f":material/lightbulb: {months['insight']}")
        else:
            error_box(s, months)

s, inc_body = get("/analytics/incidents", area_params)
incidents = incidents_frame(inc_body["data"]) if s == 200 else pd.DataFrame()
c1, c2 = st.columns([2, 3])
with c1:
    with st.container(border=True, height="stretch"):
        st.markdown("**Where** · :green[●] arrest made · :blue[●] no arrest")
        view = ({"latitude": float(row["latitude"]), "longitude": float(row["longitude"]), "zoom": 12}
                if pd.notna(row["latitude"]) else None)
        st.pydeck_chart(build_deck("Points", incidents, view=view), height=380,
                        alt=f"Map of crime locations in {area}")
        if s == 200 and inc_body["mapped"] < inc_body["total"]:
            st.caption(f"{inc_body['total'] - inc_body['mapped']} incident(s) have no location and aren't shown.")
with c2:
    with st.container(border=True, height="stretch"):
        st.markdown(f"**Incidents** · {len(incidents)}, newest first")
        if s == 200:
            st.dataframe(
                incidents, hide_index=True, height=380,
                column_order=["date", "primary_type", "description", "block", "arrest", "domestic"],
                column_config={
                    "date": st.column_config.DateColumn("Date", format="D MMM YYYY"),
                    "primary_type": "Crime type", "description": "Description", "block": "Block",
                    "arrest": st.column_config.CheckboxColumn("Arrest"),
                    "domestic": st.column_config.CheckboxColumn("Domestic"),
                },
                alt=f"Crimes in {area}, newest first",
            )
        else:
            error_box(s, inc_body)
