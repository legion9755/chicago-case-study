"""
frontend/streamlit_app.py — Streamlit frontend for the Chicago Crime case study.

It never touches the database directly: every number and every change goes through the
Flask REST API (backend). Start the backend first, then:

    streamlit run frontend/streamlit_app.py

Pages
  📊 Dashboard   charts for Use Cases 2, 3 and 4 with insights; each chart exports as PNG
                 (chart + insight in one image), or download everything as a ZIP
  🛠️ CRUD        GET / POST / PUT / PATCH / DELETE on any dimension table
  🔌 API status  backend health and endpoint list
"""
import io
import json
import os
import textwrap
import zipfile
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                       # noqa: E402
import numpy as np                                    # noqa: E402
import pandas as pd                                   # noqa: E402
import requests                                       # noqa: E402
import seaborn as sns                                 # noqa: E402
import streamlit as st                                # noqa: E402
from PIL import Image, ImageDraw, ImageFont           # noqa: E402

API_URL = os.getenv("API_URL", "http://127.0.0.1:5000/api").rstrip("/")

st.set_page_config(page_title="Chicago Crime — Case Study", page_icon="🚓", layout="wide")
sns.set_theme(style="whitegrid")
plt.rcParams.update({"axes.titleweight": "bold", "axes.titlesize": 12,
                     "axes.spines.top": False, "axes.spines.right": False})
BLUE, DARK, GREEN, RED, ORANGE = "#2e75b6", "#1f4e79", "#548235", "#c00000", "#c55a11"


# =============================================================================
# API client
# =============================================================================
def api(method, path, params=None, body=None):
    """Call the Flask API. Returns (status_code, json_body). Never raises."""
    url = f"{API_URL}{path}"
    try:
        r = requests.request(method, url, params=params, json=body, timeout=30)
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, {"raw": r.text[:500]}
    except requests.ConnectionError:
        return 0, {"error": f"Cannot reach the Flask API at {API_URL}. Start it with:  python run_backend.py"}


@st.cache_data(ttl=120, show_spinner=False)
def api_get_cached(path, params_json):
    return api("GET", path, params=json.loads(params_json))


def get(path, params=None):
    status, body = api_get_cached(path, json.dumps(params or {}, sort_keys=True))
    return status, body


# =============================================================================
# PNG export: chart + insight text in one image
# =============================================================================
FONT_PATH = os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans.ttf")
FONT_BOLD = os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans-Bold.ttf")


def fig_to_png(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    return buf.getvalue()


def png_with_insight(chart_png, insight):
    """Append a white panel with the wrapped insight text under the chart image."""
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
    d.rectangle([pad // 2, y0 + 8, w - pad // 2, y0 + panel_h - 8], fill="#eef4fb", outline="#9dc3e6", width=2)
    d.text((pad, y0 + pad), "Insight", font=bold, fill=DARK)
    for i, line in enumerate(lines):
        d.text((pad, y0 + pad + line_h * (i + 1)), line, font=font, fill="#222222")
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def show_chart(key, fig, insight, exports):
    """Render a chart, its insight, and a PNG download; remember it for the ZIP export."""
    chart_png = fig_to_png(fig)
    st.pyplot(fig, clear_figure=True)
    plt.close(fig)
    st.info(insight, icon="💡")
    export = png_with_insight(chart_png, insight)
    exports.append((key, export, insight))
    st.download_button("⬇ Export PNG (chart + insight)", export, file_name=f"{key}.png",
                       mime="image/png", key=f"dl_{key}")


def error_box(status, body):
    st.error(f"API error {status}: {body.get('detail') or body.get('error') or body}")


# =============================================================================
# Dashboard
# =============================================================================
def page_dashboard():
    st.title("📊 Chicago Crime Dashboard")
    status, opts = get("/analytics/filters")
    if status != 200:
        error_box(status, opts)
        st.stop()

    # ---- filters -----------------------------------------------------------
    st.sidebar.header("Dashboard filters")
    years = opts["years"]
    if len(years) > 1:
        yf, yt = st.sidebar.select_slider("Year", options=years, value=(years[0], years[-1]))
    else:
        yf = yt = years[0]
    types = st.sidebar.multiselect("Crime type", opts["crime_types"], placeholder="All crime types")
    comm_map = {c["community_name"]: c["community_code"] for c in opts["communities"]}
    comms = st.sidebar.multiselect("Community area", list(comm_map), placeholder="All community areas")
    params = {"year_from": yf, "year_to": yt}
    if types:
        params["crime_type"] = types
    if comms:
        params["community"] = [comm_map[c] for c in comms]

    status, summ = get("/analytics/summary", params)
    if status != 200:
        error_box(status, summ)
        st.stop()
    s = summ["data"]
    st.caption(f"{s['date_min']} → {s['date_max']} · all data served by the Flask API at `{API_URL}`")

    zip_slot = st.container()          # filled at the end, once every chart exists
    exports = []

    k = st.columns(6)
    k[0].metric("Crimes", f"{s['total_crimes']:,}")
    k[1].metric("Arrests", f"{s['arrests']:,}")
    k[2].metric("Arrest rate", f"{s['arrest_rate_pct']}%")
    k[3].metric("Domestic", f"{s['domestic_pct']}%")
    k[4].metric("Crime types", s["crime_types"])
    k[5].metric("Community areas", s["communities"])
    (st.warning if summ["is_snapshot"] else st.info)(summ["insight"])

    # ---- Use Case 2 --------------------------------------------------------
    st.header("Use Case 2 — Exploratory analysis")
    c1, c2 = st.columns(2)
    with c1:
        _, r = get("/analytics/crimes-by-year", params)
        d = pd.DataFrame(r["data"])
        fig, ax = plt.subplots(figsize=(7, 4.2))
        colors = [DARK if m == 12 else "#9dc3e6" for m in d["months_covered"]]
        bars = ax.bar(d["year"].astype(str), d["crimes"], color=colors)
        ax.bar_label(bars, fmt="{:,.0f}", padding=2, fontsize=9)
        ax.set(title="1. Total crimes per year", xlabel="Year", ylabel="Crimes")
        if (d["months_covered"] < 12).any():
            ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color="#9dc3e6")], labels=["incomplete year"])
        show_chart("uc2_1_crimes_per_year", fig, r["insight"], exports)
    with c2:
        _, r = get("/analytics/categories", {**params, "top": 10})
        d = pd.DataFrame(r["data"]).iloc[::-1]
        fig, ax = plt.subplots(figsize=(7, 4.2))
        bars = ax.barh(d["primary_type"].str.title(), d["crimes"], color=BLUE)
        ax.bar_label(bars, labels=[f" {c} ({p}%)" for c, p in zip(d["crimes"], d["percent"])], fontsize=8)
        ax.set(title="2. Top 10 crime categories", xlabel="Crimes")
        ax.set_xlim(0, d["crimes"].max() * 1.3)
        show_chart("uc2_2_top10_categories", fig, r["insight"], exports)

    c1, c2 = st.columns(2)
    with c1:
        _, r = get("/analytics/arrest-rate-by-category", params)
        d = pd.DataFrame(r["data"])
        fig, ax = plt.subplots(figsize=(7, 4.2))
        if not d.empty:
            d = d.iloc[::-1]
            ax.barh(d["primary_type"].str.title(), d["arrest_rate_pct"], color=GREEN)
            ax.axvline(r["overall_pct"], color=RED, ls="--", label=f"overall {r['overall_pct']}%")
            ax.legend(loc="lower right")
        ax.set(title=f"3. Arrest rate by category (≥{r['min_n']} crimes)", xlabel="Arrest rate (%)")
        show_chart("uc2_3_arrest_rate_by_category", fig, r["insight"], exports)
    with c2:
        _, r = get("/analytics/arrest-rate-by-year", params)
        d = pd.DataFrame(r["data"])
        fig, ax = plt.subplots(figsize=(7, 4.2))
        ax.plot(d["year"].astype(str), d["arrest_rate_pct"], marker="o", lw=2.5, color=GREEN)
        for x, y, n in zip(d["year"].astype(str), d["arrest_rate_pct"], d["crimes"]):
            ax.annotate(f"n={n}", (x, y), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=8)
        ax.set(title="3b. Arrest rate per year (n = crimes)", xlabel="Year", ylabel="Arrest rate (%)", ylim=(0, 115))
        show_chart("uc2_3b_arrest_rate_per_year", fig, r["insight"], exports)

    c1, c2 = st.columns(2)
    with c1:
        _, r = get("/analytics/heatmap", params)
        fig, ax = plt.subplots(figsize=(7, 5))
        sns.heatmap(pd.DataFrame(r["values"], index=r["months"], columns=[x[:3] for x in r["days"]]),
                    annot=True, fmt="d", cmap="YlOrRd", linewidths=.4, ax=ax, cbar_kws={"label": "Crimes"})
        ax.set(title="4. Crime frequency: month × day of week")
        show_chart("uc2_4_heatmap_month_day", fig, r["insight"], exports)
    with c2:
        _, r = get("/analytics/crimes-by-month", params)
        d = pd.DataFrame(r["data"])
        fig, ax = plt.subplots(figsize=(7, 5))
        bars = ax.bar(d["month"], d["crimes"], color=BLUE)
        bars[int(d["crimes"].idxmax())].set_color(RED)
        ax.bar_label(bars, fontsize=8, padding=2)
        ax.set(title="Q. Which month has the highest crime frequency?", ylabel="Crimes")
        show_chart("uc2_q3_crimes_by_month", fig, r["insight"], exports)

    _, r = get("/analytics/top-communities", {**params, "top": 10})
    c1, c2 = st.columns(2)
    with c1:
        d = pd.DataFrame(r["by_count"]).iloc[::-1]
        fig, ax = plt.subplots(figsize=(7, 4.2))
        bars = ax.barh(d["community_name"], d["crimes"], color=ORANGE)
        ax.bar_label(bars, padding=2, fontsize=8)
        ax.set(title="5. Top 10 community areas (crime count)", xlabel="Crimes")
        show_chart("uc2_5_top10_communities", fig, r["insight"], exports)
    with c2:
        d = pd.DataFrame(r["by_rate"]).iloc[::-1]
        fig, ax = plt.subplots(figsize=(7, 4.2))
        bars = ax.barh(d["community_name"], d["per_1000"], color="#843c0c")
        ax.bar_label(bars, padding=2, fontsize=8)
        ax.set(title="5b. Top 10 community areas (per 1,000 residents)", xlabel="Crimes per 1,000 residents")
        show_chart("uc2_5b_top10_communities_per_capita", fig,
                   "Per-capita view: " + r["insight"], exports)

    # ---- Use Case 3 --------------------------------------------------------
    st.header("Use Case 3 — Statistical insights & pattern detection")
    c1, c2 = st.columns(2)
    with c1:
        _, r = get("/analytics/crimes-by-hour", params)
        d = pd.DataFrame(r["data"])
        fig, ax = plt.subplots(figsize=(7, 4.2))
        ax.plot(d["hour"], d["crimes"], marker="o", lw=2.5, color="#7030a0")
        ax.fill_between(d["hour"], d["crimes"], alpha=.12, color="#7030a0")
        ax.set(title="1. Crimes per hour of day" + ("" if r["has_time_of_day"] else " (no times in source)"),
               xlabel="Hour", ylabel="Crimes", xticks=range(0, 24, 2))
        show_chart("uc3_1_crimes_per_hour", fig, r["insight"], exports)
    with c2:
        _, r = get("/analytics/community-outliers", params)
        d, st_ = pd.DataFrame(r["counts"]), r["stats"]
        fig, ax = plt.subplots(figsize=(7, 4.2))
        sns.boxplot(x=d["crimes"], ax=ax, color="#9dc3e6", width=.45, whis=1.5,
                    flierprops=dict(marker="o", markerfacecolor=RED, markersize=8))
        ax.axvline(st_["upper_fence"], color=RED, ls="--", lw=1)
        ax.text(st_["upper_fence"], -0.38, f" upper fence {st_['upper_fence']:.1f}", color=RED, fontsize=8)
        for i, (_, row) in enumerate(pd.DataFrame(r["outliers"]).iterrows()):
            ax.annotate(row["community_name"], (row["crimes"], 0), xytext=(0, 14 + 12 * (i % 2)),
                        textcoords="offset points", ha="center", fontsize=8)
        ax.set(title="2. Crimes per community area — box plot + IQR outliers", xlabel="Crimes", yticks=[])
        show_chart("uc3_2_community_outliers", fig, r["insight"], exports)

    _, r = get("/analytics/correlation", params)
    corr = pd.DataFrame(r["matrix"], index=r["columns"], columns=r["columns"])
    fig, ax = plt.subplots(figsize=(9, 6.5))
    sns.heatmap(corr, mask=np.triu(np.ones_like(corr, dtype=bool), k=1), annot=True, fmt=".2f",
                cmap="coolwarm", vmin=-1, vmax=1, center=0, linewidths=.5, ax=ax, annot_kws={"size": 8})
    ax.set(title="3. Correlation matrix of numeric features")
    c1, _ = st.columns([3, 1])
    with c1:
        show_chart("uc3_3_correlation_heatmap", fig, r["insight"], exports)

    # ---- Use Case 4 --------------------------------------------------------
    st.header("Use Case 4 — Reporting from SQL views")
    st.caption("Read from the database views `vw_crime_yearly` and `vw_crime_by_category` (sidebar filters do not apply).")
    c1, c2 = st.columns(2)
    with c1:
        _, r = get("/analytics/views/vw_crime_yearly")
        d = pd.DataFrame(r["data"])
        fig, ax = plt.subplots(figsize=(7, 4.2))
        ax.bar(d["year"].astype(str), d["total_crimes"], color="#9dc3e6", label="Crimes")
        ax.set(title="vw_crime_yearly — crimes & arrest rate", xlabel="Year", ylabel="Crimes")
        ax2 = ax.twinx()
        ax2.plot(d["year"].astype(str), d["arrest_rate_pct"], color=RED, marker="o", lw=2, label="Arrest rate %")
        ax2.set_ylabel("Arrest rate (%)", color=RED)
        ax2.set_ylim(0, 115)
        ax2.grid(False)
        h1, l1 = ax.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax.legend(h1 + h2, l1 + l2, loc="upper left")
        show_chart("uc4_1_vw_crime_yearly", fig, r["insight"], exports)
        st.dataframe(d, hide_index=True, width="stretch")
    with c2:
        _, r = get("/analytics/views/vw_crime_by_category")
        d = pd.DataFrame(r["data"]).head(5).iloc[::-1]
        fig, ax = plt.subplots(figsize=(7, 4.2))
        bars = ax.barh(d["primary_type"].str.title(), d["pct_of_total"], color=DARK)
        ax.bar_label(bars, labels=[f" {p}% ({n})" for p, n in zip(d["pct_of_total"], d["total_crimes"])], fontsize=9)
        ax.set(title="vw_crime_by_category — top 5 crime types", xlabel="% of all crimes")
        ax.set_xlim(0, d["pct_of_total"].max() * 1.35)
        show_chart("uc4_2_vw_crime_by_category_top5", fig, r["insight"], exports)
        st.dataframe(pd.DataFrame(r["data"]).head(5), hide_index=True, width="stretch")

    # ---- data quality ------------------------------------------------------
    with st.expander("🧹 Data-quality log (from the ETL pipeline)"):
        _, r = get("/analytics/data-quality")
        dq = pd.DataFrame(r["data"])
        st.dataframe(dq[dq["rows_affected"] > 0], hide_index=True, width="stretch")

    # ---- export everything -------------------------------------------------
    with zip_slot:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            report = [f"Chicago Crime Dashboard export — {datetime.now():%d %b %Y %H:%M}",
                      f"Filters: {json.dumps(params)}", ""]
            for key, png, insight in exports:
                z.writestr(f"{key}.png", png)
                report += [key, f"  {insight}", ""]
            z.writestr("insights.txt", "\n".join(report))
        st.download_button(f"📦 Export all {len(exports)} charts + insights (ZIP)", buf.getvalue(),
                           file_name=f"chicago_dashboard_{datetime.now():%Y%m%d_%H%M}.zip",
                           mime="application/zip", type="primary")


# =============================================================================
# CRUD
# =============================================================================
def show_last_call():
    call = st.session_state.get("last_call")
    if not call:
        return
    ok = 200 <= call["status"] < 300
    st.markdown(f"#### Last API call  {'✅' if ok else '❌'}")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Request**")
        st.code(f"{call['method']} {call['url']}" + (f"\n\n{json.dumps(call['body'], indent=2)}" if call["body"] else ""),
                language="http", wrap_lines=True)
    with c2:
        st.markdown(f"**Response — HTTP {call['status']}**")
        st.code(json.dumps(call["response"], indent=2, default=str), language="json", wrap_lines=True)


def do_call(method, path, body=None):
    status, resp = api(method, path, body=body)
    st.session_state["last_call"] = {"method": method, "url": f"{API_URL}{path}", "body": body,
                                     "status": status, "response": resp}
    if 200 <= status < 300:
        st.cache_data.clear()          # dashboard numbers / names may have changed
    st.rerun()


def field_inputs(columns, values, key_prefix, include_pk=True, only=None):
    """Text inputs for each column (blank = null). Types are validated by the API."""
    body = {}
    cols = st.columns(2)
    shown = [c for c in columns if (include_pk or not c["primary_key"]) and (only is None or c["name"] in only)]
    for i, c in enumerate(shown):
        label = c["name"] + (" 🔑" if c["primary_key"] else "") + ("" if c["nullable"] else " *")
        hint = c["type"] + (f", max {c['max_length']}" if c.get("max_length") else "")
        cur = values.get(c["name"])
        body[c["name"]] = cols[i % 2].text_input(label, "" if cur is None else str(cur), help=hint,
                                                 key=f"{key_prefix}_{c['name']}")
    types = {c["name"]: c["type"] for c in columns}
    return {k: to_json_value(v, types[k]) for k, v in body.items()}


def to_json_value(text, col_type):
    """Blank -> None; numeric columns -> int/float when the text is a valid number
    (otherwise the text is sent as-is and the API answers 400 with a validation message)."""
    text = text.strip()
    if text == "":
        return None
    if col_type in ("Integer", "Float"):
        try:
            num = float(text.replace(",", ""))
            return int(num) if col_type == "Integer" and num.is_integer() else num
        except ValueError:
            return text
    return text


def page_crud():
    st.title("🛠️ CRUD — dimension tables")
    st.caption("Every action below is a real HTTP request to the Flask API; the request and the response are shown.")
    status, resources = api("GET", "/resources")
    if status != 200:
        error_box(status, resources)
        st.stop()
    res_map = {f"{r['label']}  ·  /api/{r['resource']}  ({r['rows']} rows)": r for r in resources}
    default = next(i for i, r in enumerate(resources) if r["resource"] == "communities")
    meta = res_map[st.selectbox("Table", list(res_map), index=default)]
    res, pk, columns = meta["resource"], meta["primary_key"], meta["columns"]

    show_last_call()

    st.subheader(f"📄 GET /api/{res}")
    q = st.text_input("Search (any column)", key=f"q_{res}", placeholder="e.g. austin")
    status, listing = api("GET", f"/{res}", params={"q": q, "limit": 1000})
    if status != 200:
        error_box(status, listing)
        return
    items = pd.DataFrame(listing["items"])
    st.caption(f"`GET {API_URL}/{res}?q={q}&limit=1000` → HTTP {status} · {listing['total']} row(s)")
    st.dataframe(items, hide_index=True, width="stretch", height=260)

    status, all_rows = api("GET", f"/{res}", params={"limit": 1000})
    ids = [row[pk] for row in all_rows["items"]]

    t_get, t_post, t_put, t_patch, t_del = st.tabs(
        ["🔍 Read one (GET)", "➕ Create (POST)", "♻️ Replace (PUT)", "✏️ Update (PATCH)", "🗑️ Delete (DELETE)"])

    with t_get:
        rid = st.selectbox(f"{pk}", ids, key=f"get_id_{res}")
        if st.button("Send GET", key=f"get_btn_{res}"):
            do_call("GET", f"/{res}/{rid}")

    with t_post:
        st.caption("Fields marked * are required. Leave a field blank for NULL.")
        with st.form(f"post_{res}", clear_on_submit=True):
            body = field_inputs(columns, {}, f"post_{res}")
            if st.form_submit_button("Send POST", type="primary"):
                do_call("POST", f"/{res}", {k: v for k, v in body.items() if v is not None})

    with t_put:
        st.caption("PUT replaces the **whole** record: every field is sent; blank fields become NULL.")
        rid = st.selectbox(f"{pk} to replace", ids, key=f"put_id_{res}")
        _, current = api("GET", f"/{res}/{rid}")
        with st.form(f"put_{res}_{rid}"):
            body = field_inputs(columns, current, f"put_{res}_{rid}", include_pk=False)
            if st.form_submit_button("Send PUT", type="primary"):
                do_call("PUT", f"/{res}/{rid}", body)

    with t_patch:
        st.caption("PATCH changes **only** the fields you pick; everything else stays as it is.")
        rid = st.selectbox(f"{pk} to update", ids, key=f"patch_id_{res}")
        _, current = api("GET", f"/{res}/{rid}")
        editable = [c["name"] for c in columns if not c["primary_key"]]
        chosen = st.multiselect("Fields to change", editable, key=f"patch_fields_{res}_{rid}")
        if chosen:
            with st.form(f"patch_{res}_{rid}"):
                body = field_inputs(columns, current, f"patch_{res}_{rid}", include_pk=False, only=chosen)
                if st.form_submit_button("Send PATCH", type="primary"):
                    do_call("PATCH", f"/{res}/{rid}", body)

    with t_del:
        rid = st.selectbox(f"{pk} to delete", ids, key=f"del_id_{res}")
        _, current = api("GET", f"/{res}/{rid}")
        st.json(current, expanded=False)
        st.caption("Records still used by crimes are protected: the API answers 409 Conflict.")
        sure = st.checkbox("Yes, delete this record", key=f"del_ok_{res}_{rid}")
        if st.button("Send DELETE", disabled=not sure, key=f"del_btn_{res}", type="primary"):
            do_call("DELETE", f"/{res}/{rid}")


# =============================================================================
# API status
# =============================================================================
def page_status():
    st.title("🔌 Backend status")
    status, health = api("GET", "/health")
    (st.success if status == 200 else st.error)(f"GET {API_URL}/health → HTTP {status}")
    st.json(health)
    status, index = api("GET", "")
    if status == 200:
        st.subheader("Endpoints")
        st.json(index["endpoints"])
    st.subheader("HTTP methods used for CRUD")
    st.table(pd.DataFrame([
        ["GET", "/api/<table>", "list / search records", "200"],
        ["GET", "/api/<table>/<id>", "read one record", "200, 404"],
        ["POST", "/api/<table>", "create a record", "201, 400, 409"],
        ["PUT", "/api/<table>/<id>", "replace the whole record", "200, 400, 404"],
        ["PATCH", "/api/<table>/<id>", "change some fields", "200, 400, 404"],
        ["DELETE", "/api/<table>/<id>", "delete a record", "200, 404, 409"],
    ], columns=["Method", "URL", "Purpose", "Status codes"]))


# =============================================================================
# Navigation
# =============================================================================
st.sidebar.title("🚓 Chicago Crime")
page = st.sidebar.radio("Page", ["📊 Dashboard", "🛠️ CRUD", "🔌 API status"], label_visibility="collapsed")
ok_status, _ = api("GET", "/health")
st.sidebar.caption(("🟢" if ok_status == 200 else "🔴") + f" Flask API: `{API_URL}`")
if page.startswith("📊"):
    page_dashboard()
elif page.startswith("🛠️"):
    page_crud()
else:
    page_status()
