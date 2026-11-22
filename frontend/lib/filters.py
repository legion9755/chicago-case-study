"""
lib/filters.py — global dashboard filters.

Every filter is bound to the URL (`bind="query-params"`), so a filtered view can be shared as a
link and the selection survives page switches. The query-parameter names are the widget keys.
"""
from typing import Any

import streamlit as st

from lib.api import error_box, get, is_no_match

KEY_YEARS = "years"
KEY_TYPES = "crime_type"
KEY_COMMS = "community"
KEY_ARREST = "arrest"
KEY_DOMESTIC = "domestic"
FLAG_OPTIONS = ["Any", "Yes", "No"]
FLAG_PARAM = {"Yes": "true", "No": "false"}   # "Any" sends nothing


def require_summary(params: dict[str, Any]) -> dict[str, Any]:
    """GET /analytics/summary for the filters. Shows an empty state or an error and stops the
    page when there is nothing to show."""
    status, summ = get("/analytics/summary", params)
    if is_no_match(status, summ):
        st.info("Try a wider year range or fewer crime types / community areas, or clear the filters "
                "in the sidebar.", title="No crimes match these filters", icon=":material/filter_alt_off:")
        st.stop()
    if status != 200:
        error_box(status, summ)
        st.stop()
    return summ


def _reset() -> None:
    """Drop the filter values so each widget comes back with its default on the next run.

    (Assigning the defaults instead would clash with the widgets' own `value=` and log a warning.)
    """
    for key in (KEY_YEARS, KEY_TYPES, KEY_COMMS, KEY_ARREST, KEY_DOMESTIC):
        st.session_state.pop(key, None)


def render_filters() -> dict[str, Any]:
    """Draw the filter panel in the sidebar and return the API query params.

    Stops the page with an error box if the filter options can't be loaded.
    """
    status, opts = get("/analytics/filters")
    if status != 200:
        error_box(status, opts)
        st.stop()

    years: list[int] = opts["years"]
    comm_map: dict[str, int] = {c["community_name"]: c["community_code"] for c in opts["communities"]}

    with st.sidebar:
        with st.container(horizontal=True, vertical_alignment="center"):
            st.subheader("Filters", anchor=False)
            active_slot = st.empty()

        if len(years) > 1:
            yf, yt = st.select_slider(
                "Year", options=years, value=(years[0], years[-1]),
                key=KEY_YEARS, bind="query-params",
            )
        else:
            yf = yt = years[0]
            st.caption(f"Year: {yf} (only one year in the data)")

        types: list[str] = st.multiselect(
            "Crime type", opts["crime_types"], placeholder="All crime types",
            key=KEY_TYPES, bind="query-params",
        )
        comms: list[str] = st.multiselect(
            "Community area", list(comm_map), placeholder="All community areas",
            key=KEY_COMMS, bind="query-params",
        )

        arrest = st.segmented_control(
            "Arrest made", FLAG_OPTIONS, default="Any", required=True, key=KEY_ARREST, bind="query-params")
        domestic = st.segmented_control(
            "Domestic", FLAG_OPTIONS, default="Any", required=True, key=KEY_DOMESTIC, bind="query-params")

        active = (int((yf, yt) != (years[0], years[-1])) + int(bool(types)) + int(bool(comms))
                  + int(arrest in FLAG_PARAM) + int(domestic in FLAG_PARAM))
        if active:
            active_slot.badge(f"{active} active", color="primary")
        st.button(
            "Clear filters", icon=":material/filter_alt_off:", type="tertiary",
            on_click=_reset, disabled=not active, key="clear_filters",
        )

    params: dict[str, Any] = {"year_from": yf, "year_to": yt}
    if types:
        params["crime_type"] = types
    if comms:
        params["community"] = [comm_map[c] for c in comms if c in comm_map]
    if arrest in FLAG_PARAM:
        params["arrest"] = FLAG_PARAM[arrest]
    if domestic in FLAG_PARAM:
        params["domestic"] = FLAG_PARAM[domestic]
    return params
