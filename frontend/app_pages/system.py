"""
System — backend health, the endpoint list, the HTTP methods used for CRUD, and the ETL data-quality log.
"""
import pandas as pd
import streamlit as st

from lib.api import API_URL, api, get

st.title("System", anchor=False)
st.caption(f"Backend: `{API_URL}`")

status, health = api("GET", "/health")
ok = status == 200
with st.container(border=True):
    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown("**API health**")
        st.badge("Online" if ok else "Offline", color="green" if ok else "red",
                 icon=":material/check_circle:" if ok else ":material/error:")
        st.space("stretch")
        st.caption(f"GET {API_URL}/health → HTTP {status}")
    st.json(health, expanded=False)

c1, c2 = st.columns(2)
with c1:
    with st.container(border=True, height="stretch"):
        st.markdown("**Endpoints**")
        status, index = api("GET", "")
        if status == 200:
            st.json(index["endpoints"])
        else:
            st.caption("Endpoint list unavailable while the API is offline.")
with c2:
    with st.container(border=True, height="stretch"):
        st.markdown("**HTTP methods used for CRUD**")
        st.table(pd.DataFrame([
            ["GET", "/api/<table>", "list / search records", "200"],
            ["GET", "/api/<table>/<id>", "read one record", "200, 404"],
            ["POST", "/api/<table>", "create a record", "201, 400, 409"],
            ["PUT", "/api/<table>/<id>", "replace the whole record", "200, 400, 404"],
            ["PATCH", "/api/<table>/<id>", "change some fields", "200, 400, 404"],
            ["DELETE", "/api/<table>/<id>", "delete a record", "200, 404, 409"],
        ], columns=["Method", "URL", "Purpose", "Status codes"]).set_index("Method"))

with st.container(border=True):
    st.markdown("**Data-quality log** · from the ETL pipeline")
    status, r = get("/analytics/data-quality")
    if status == 200:
        dq = pd.DataFrame(r["data"])
        st.dataframe(dq[dq["rows_affected"] > 0], hide_index=True, alt="ETL data-quality log")
    else:
        st.caption("Data-quality log unavailable while the API is offline.")
