"""
Insights — interactive charts for Use Cases 2, 3 and 4, each with the insight computed by the backend.

Each card exports as PNG (chart + insight in one image); the header exports every chart as a ZIP.
Only the selected section's charts are loaded.
"""
import json
from datetime import datetime
from functools import partial

import streamlit as st

from lib.api import API_URL
from lib.cards import chart_card
from lib.charts import CHARTS, SECTIONS, zip_all
from lib.filters import render_filters, require_summary

params = render_filters()

# ---- header ----------------------------------------------------------------
with st.container(horizontal=True, vertical_alignment="bottom"):
    with st.container(gap=None):
        st.title("Insights", anchor=False)
        caption_slot = st.empty()
    st.space("stretch")
    st.download_button(
        f"Export all {len(CHARTS)} charts", partial(zip_all, json.dumps(params, sort_keys=True)),
        file_name=f"chicago_dashboard_{datetime.now():%Y%m%d_%H%M}.zip", mime="application/zip",
        type="primary", icon=":material/folder_zip:", on_click="ignore",
        help="Every chart as PNG (chart + insight) plus insights.txt, in one ZIP. Uses the current filters.",
    )

# ---- KPIs ------------------------------------------------------------------
caption_slot.caption(f"Served by the Flask API at `{API_URL}`")
summ = require_summary(params)
s = summ["data"]
caption_slot.caption(f"{s['date_min']} → {s['date_max']} · served by the Flask API at `{API_URL}`")

with st.grid(6, gap="small", min_column_width=140):
    st.metric("Crimes", f"{s['total_crimes']:,}", border=True)
    st.metric("Arrests", f"{s['arrests']:,}", border=True)
    st.metric("Arrest rate", f"{s['arrest_rate_pct']}%", border=True)
    st.metric("Domestic", f"{s['domestic_pct']}%", border=True)
    st.metric("Crime types", s["crime_types"], border=True)
    st.metric("Community areas", s["communities"], border=True)

if summ["is_snapshot"]:
    st.warning(summ["insight"], title="This data is a snapshot", icon=":material/warning:")

# ---- section picker + cards ------------------------------------------------
# Options are the plain section names: the bound widget writes the shown label to the URL,
# so this keeps links readable (?section=Statistical+insights).
by_label = {v["label"]: k for k, v in SECTIONS.items()}
section = st.segmented_control(
    "Section", list(by_label), default=SECTIONS["uc2"]["label"], required=True, key="section",
    bind="query-params", label_visibility="collapsed",
)
sec = SECTIONS[by_label.get(section or "", "uc2")]
st.caption(sec["caption"])

for row in sec["rows"]:
    for col, key in zip(st.columns(len(row)), row):
        with col:
            chart_card(CHARTS[key], params)
