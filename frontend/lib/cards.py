"""
lib/cards.py — the chart card used on the Insights page.

Each card is its own parallel fragment: cards load concurrently behind a skeleton, and using a
card's menu reruns only that card. The PNG (chart + insight) is rendered only when clicked.
"""
import json
from functools import partial
from typing import Any

import pandas as pd
import requests
import streamlit as st

from lib.api import API_URL, error_message, get, is_no_match
from lib.charts import ChartDef, palette, query_for
from lib.export import render_png

MENU_DATA = ":material/table_chart: View data"
MENU_API = ":material/api: API request"


def _request_url(path: str, query: dict[str, Any]) -> str:
    url = requests.Request("GET", f"{API_URL}{path}", params=query).prepare().url
    return url or f"{API_URL}{path}"


@st.dialog("Chart details", width="large")
def _details(c: ChartDef, mode: str, table: pd.DataFrame, url: str, insight: str) -> None:
    st.markdown(f"**{c.title}**")
    if mode == MENU_DATA:
        st.caption("The data behind this chart. Use the table toolbar to search or download it as CSV.")
        st.dataframe(table, hide_index=True, alt=f"Data for {c.title}")
    else:
        st.caption("Every number on this page comes from the Flask REST API. This chart's request:")
        st.code(f"GET {url}", language="http", wrap_lines=True)
        st.caption("Try it from PowerShell:")
        st.code(f'Invoke-RestMethod "{url}"', language="powershell", wrap_lines=True)
        st.caption("Insight returned by the API:")
        st.markdown(f"> {insight}")


@st.fragment(parallel=True)
def chart_card(c: ChartDef, params: dict[str, Any]) -> None:
    query = query_for(c, params)
    with st.container(border=True, height="stretch"):
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.markdown(f"**{c.title}**")
            st.space("stretch")
            actions = st.container(horizontal=True, gap="small", width="content")

        with st.skeleton(height=c.height):
            status, r = get(c.endpoint, query)

        if status != 200:
            if is_no_match(status, r):
                st.info(c.empty_message, icon=":material/filter_alt_off:")
            else:
                st.error(error_message(status, r), icon=":material/error:")
            return

        option, table = c.build(r, palette())
        insight = c.insight(r)
        if option is None:
            st.info(c.empty_message, icon=":material/filter_alt_off:")
        else:
            st.echarts_chart(option, height=c.height, key=f"chart_{c.key}", alt=c.alt)
        st.caption(f":material/lightbulb: {insight}")
        if c.show_table:
            st.dataframe(table, hide_index=True, alt=f"Rows of {c.title}")

        with actions:
            st.download_button(
                "PNG", partial(render_png, c.key, json.dumps(r), insight), file_name=f"{c.key}.png",
                mime="image/png", key=f"png_{c.key}", icon=":material/download:", type="tertiary",
                help="Download this chart with its insight as one PNG image", on_click="ignore",
            )
            choice = st.menu_button(":material/more_vert:", [MENU_DATA, MENU_API], key=f"menu_{c.key}",
                                    type="tertiary", help="More")
    if choice:
        _details(c, choice, table, _request_url(c.endpoint, query), insight)
