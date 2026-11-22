"""
frontend/streamlit_app.py — entrypoint of the Chicago Crime Streamlit frontend.

It never touches the database directly: every number and every change goes through the
Flask REST API (backend). Start the backend first, then:

    streamlit run frontend/streamlit_app.py

Pages (app_pages/)
  Insights     dashboard: charts for Use Cases 2, 3 and 4 with insights; each chart exports as PNG
               (chart + insight in one image), or download everything as a ZIP
  Data admin   GET / POST / PUT / PATCH / DELETE on any dimension table

Shared code lives in lib/ (API client, global filters, PNG/ZIP export).
"""
import streamlit as st

from lib.api import API_URL, health

st.set_page_config(page_title="Chicago Crime Analytics", page_icon=":material/local_police:", layout="wide")

page = st.navigation(
    [
        st.Page(
            "app_pages/insights.py", title="Insights", icon=":material/insights:", default=True,
            help="Charts and insights for Use Cases 2–4. Filter in the sidebar; export any chart, "
                 "or all of them, as PNG with its insight.",
        ),
        st.Page(
            "app_pages/admin.py", title="Data admin", icon=":material/table_edit:",
            help="Create, read, update and delete records in the dimension tables through the REST API, "
                 "with the raw request and response shown.",
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
