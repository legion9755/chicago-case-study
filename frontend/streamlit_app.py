"""
frontend/streamlit_app.py — entrypoint of the Chicago Crime Streamlit frontend.

It never touches the database directly: every number and every change goes through the
Flask REST API (backend). Start the backend first, then:

    streamlit run frontend/streamlit_app.py

Pages (app_pages/)
  Overview     landing page: KPIs, highlights, mini map, crime mix, top community areas
  Communities  directory of the 77 community areas, and a detail view per area
  Insights     charts for Use Cases 2, 3 and 4 with insights; each chart exports as PNG
               (chart + insight in one image), or download everything as a ZIP
  Data admin   GET / POST / PUT / PATCH / DELETE on any dimension table
  System       backend health, endpoint list, ETL data-quality log

Shared code lives in lib/ (API client, global filters, PNG/ZIP export).
The previous single-file version is kept in legacy/streamlit_app_v1.py.
"""
import streamlit as st

from lib.api import API_URL, health

st.set_page_config(page_title="Chicago Crime Analytics", page_icon=":material/local_police:", layout="wide")

page = st.navigation(
    [
        st.Page(
            "app_pages/overview.py", title="Overview", icon=":material/dashboard:", default=True,
            help="Chicago crime at a glance: headline numbers, highlights, the crime mix and the busiest "
                 "community areas. Uses the sidebar filters.",
        ),
        st.Page(
            "app_pages/communities.py", title="Communities", icon=":material/location_city:",
            help="All 77 community areas ranked by crimes and crimes per resident, with a detail view per "
                 "area. Uses the sidebar filters (except community area).",
        ),
        st.Page(
            "app_pages/insights.py", title="Insights", icon=":material/insights:",
            help="Charts and insights for Use Cases 2–4. Filter in the sidebar; export any chart, "
                 "or all of them, as PNG with its insight.",
        ),
        st.Page(
            "app_pages/admin.py", title="Data admin", icon=":material/table_edit:",
            help="Create, read, update and delete records in the dimension tables through the REST API, "
                 "with the raw request and response shown.",
        ),
        st.Page(
            "app_pages/system.py", title="System", icon=":material/monitor_heart:",
            help="Backend health, the API endpoint list, and the ETL data-quality log.",
        ),
    ],
    position="top",
)

# Sidebar header: brand + API status. Drawn before the page runs, because pages stop early
# (st.stop) when the API is unreachable — exactly when the status badge matters most.
status, _ = health()
with st.sidebar:
    st.markdown("### :material/local_police: Chicago Crime")
    if status == 200:
        st.badge("API online", icon=":material/check_circle:", color="green", help=f"Flask API at {API_URL}")
    else:
        st.badge("API offline", icon=":material/error:", color="red",
                 help=f"No answer from {API_URL}. Start the backend with:  python run_backend.py")
    st.divider()

page.run()
