"""
backend/analytics.py — read-only analytics endpoints used by the Streamlit dashboard.

Every endpoint accepts the same optional filters:
    ?year_from=2015&year_to=2016&crime_type=THEFT&crime_type=BATTERY&community=25&arrest=true&domestic=false
and returns JSON shaped like  {"data": [...], "insight": "plain-English finding"}.
Insights are computed from the data, so they stay correct when the data changes.
"""
import json

import numpy as np
import pandas as pd
from flask import Blueprint, abort, jsonify, request
from sqlalchemy import bindparam, text

from backend.database import engine

analytics_bp = Blueprint("analytics", __name__, url_prefix="/api/analytics")

DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
VIEWS = {"vw_crime_yearly": "year", "vw_crime_by_category": "total_crimes DESC"}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def records(df):
    """DataFrame -> JSON-safe list of dicts (NaN -> null, numpy types -> Python)."""
    return json.loads(df.to_json(orient="records", date_format="iso"))


def flag_arg(name):
    """Optional boolean query parameter: true/1/yes -> True, false/0/no -> False, absent -> None."""
    raw = request.args.get(name)
    if raw is None or raw.strip() == "":
        return None
    value = raw.strip().lower()
    if value in ("true", "1", "yes"):
        return True
    if value in ("false", "0", "no"):
        return False
    abort(400, description=f"'{name}' must be true or false, not '{raw}'")


def crimes_df():
    """Fact rows joined with crime type + community, filtered by the query-string filters."""
    sql = """SELECT c.case_number, c.date, c.year, c.month, c.day_of_week, c.hour, c.block,
                    c.iucr_code, i.primary_type, i.description, c.location_desc, c.arrest,
                    c.domestic, c.beat_num, c.district_code, c.ward_no, c.community_code,
                    cc.community_name, cc.population, c.latitude, c.longitude
             FROM chicago_crime c
             JOIN iucr i ON i.iucr_code = c.iucr_code
             LEFT JOIN city_community cc ON cc.community_code = c.community_code
             WHERE 1 = 1"""
    params, binds = {}, []
    if (yf := request.args.get("year_from", type=int)) is not None:
        sql += " AND c.year >= :yf"; params["yf"] = yf
    if (yt := request.args.get("year_to", type=int)) is not None:
        sql += " AND c.year <= :yt"; params["yt"] = yt
    if types := request.args.getlist("crime_type"):
        sql += " AND i.primary_type IN :types"; params["types"] = types
        binds.append(bindparam("types", expanding=True))
    if comms := request.args.getlist("community", type=int):
        sql += " AND c.community_code IN :comms"; params["comms"] = comms
        binds.append(bindparam("comms", expanding=True))
    for flag in ("arrest", "domestic"):
        if (value := flag_arg(flag)) is not None:
            sql += f" AND c.{flag} = :{flag}"; params[flag] = int(value)
    stmt = text(sql).bindparams(*binds) if binds else text(sql)
    with engine.connect() as conn:
        df = pd.read_sql(stmt, conn, params=params)
    df["date"] = pd.to_datetime(df["date"], format="ISO8601")
    df["arrest"] = df["arrest"].astype(bool)
    df["domestic"] = df["domestic"].astype(bool)
    df["community_name"] = df["community_name"].fillna("UNKNOWN").str.title()
    return df


def require_rows(df):
    if df.empty:
        abort(404, description="No crimes match the selected filters")


# ---------------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------------
@analytics_bp.get("/filters")
def filter_options():
    with engine.connect() as conn:
        years = [r[0] for r in conn.execute(text("SELECT DISTINCT year FROM chicago_crime ORDER BY year"))]
        types = [r[0] for r in conn.execute(text(
            "SELECT DISTINCT i.primary_type FROM chicago_crime c JOIN iucr i USING (iucr_code) ORDER BY 1"))]
        comms = pd.read_sql(text("SELECT community_code, community_name FROM city_community ORDER BY community_name"), conn)
    comms["community_name"] = comms["community_name"].str.title()
    return jsonify({"years": years, "crime_types": types, "communities": records(comms)})


@analytics_bp.get("/summary")
def summary():
    df = crimes_df(); require_rows(df)
    by_day = df["date"].dt.date.value_counts(normalize=True)
    data = {
        "total_crimes": len(df),
        "arrests": int(df["arrest"].sum()),
        "arrest_rate_pct": round(float(df["arrest"].mean()) * 100, 2),
        "domestic_pct": round(float(df["domestic"].mean()) * 100, 2),
        "crime_types": int(df["primary_type"].nunique()),
        "communities": int(df["community_code"].nunique()),
        "date_min": df["date"].min().strftime("%d %b %Y"),
        "date_max": df["date"].max().strftime("%d %b %Y"),
        "has_time_of_day": bool((df["date"].dt.time != pd.Timestamp(0).time()).any()),
        "top_year_share_pct": round(float(df["year"].value_counts(normalize=True).max()) * 100, 1),
        "top2_dates_share_pct": round(float(by_day.head(2).sum()) * 100, 1),
    }
    snapshot = bool(data["top_year_share_pct"] > 50 or data["top2_dates_share_pct"] > 50)
    insight = (f"{data['total_crimes']:,} crimes across {data['crime_types']} crime types; "
               f"{data['arrest_rate_pct']}% led to an arrest and {data['domestic_pct']}% were domestic.")
    if snapshot:
        insight += (f" Note: {data['top2_dates_share_pct']}% of these crimes fall on just two dates, so the "
                    "extract is a snapshot of recently updated records, not a full history.")
    return jsonify({"data": data, "insight": insight, "is_snapshot": snapshot})


@analytics_bp.get("/crimes-by-year")
def crimes_by_year():
    df = crimes_df(); require_rows(df)
    yearly = df.groupby("year").agg(crimes=("case_number", "size"),
                                    months_covered=("month", "nunique")).reset_index()
    share = yearly["crimes"].max() / yearly["crimes"].sum() * 100
    full = yearly[yearly["months_covered"] == 12]
    if len(full) >= 3 and share < 50:
        slope = np.polyfit(full["year"], full["crimes"], 1)[0]
        insight = (f"Across complete years crime is {'DECREASING' if slope < 0 else 'RISING'} "
                   f"by about {abs(slope):,.0f} crimes per year.")
    else:
        top = yearly.loc[yearly["crimes"].idxmax()]
        complete = "no year has all 12 months" if len(full) == 0 else f"only {len(full)} year(s) are complete"
        insight = (f"No reliable trend: {int(top['year'])} holds {share:.1f}% of all crimes and {complete}. "
                   "Earlier years contain only late-reported crimes, so the apparent rise reflects how the "
                   "data was extracted, not crime levels.")
    return jsonify({"data": records(yearly), "insight": insight})


@analytics_bp.get("/categories")
def categories():
    df = crimes_df(); require_rows(df)
    top = request.args.get("top", 10, type=int)
    vc = df["primary_type"].value_counts()
    out = pd.DataFrame({"primary_type": vc.index, "crimes": vc.values,
                        "percent": (vc.values / len(df) * 100).round(2)}).head(top)
    insight = (f"{out.iloc[0]['primary_type'].title()} is the most frequent crime "
               f"({out.iloc[0]['crimes']:,}, {out.iloc[0]['percent']}%)")
    if len(out) > 1:
        insight += f", followed by {out.iloc[1]['primary_type'].title()} ({out.iloc[1]['percent']}%)"
    insight += f". The top {len(out)} categories make up {out['percent'].sum():.1f}% of all crimes."
    return jsonify({"data": records(out), "insight": insight, "unique_crime_types": int(vc.size)})


@analytics_bp.get("/arrest-rate-by-category")
def arrest_by_category():
    df = crimes_df(); require_rows(df)
    min_n = request.args.get("min_n", max(5, int(len(df) * 0.01)), type=int)
    out = (df.groupby("primary_type")["arrest"].agg(crimes="size", arrests="sum", rate="mean")
             .query("crimes >= @min_n").reset_index())
    out["arrest_rate_pct"] = (out.pop("rate") * 100).round(2)
    out = out.sort_values("arrest_rate_pct", ascending=False)
    overall = round(float(df["arrest"].mean()) * 100, 2)
    if out.empty:
        return jsonify({"data": [], "overall_pct": overall, "min_n": min_n,
                        "insight": f"Overall arrest rate {overall}%; no category has ≥{min_n} crimes."})
    hi, lo = out.iloc[0], out.iloc[-1]
    insight = (f"Overall arrest rate is {overall}%. It ranges from {hi['arrest_rate_pct']}% for "
               f"{hi['primary_type'].title()} to {lo['arrest_rate_pct']}% for {lo['primary_type'].title()}: "
               "offences discovered by police (e.g. narcotics) almost always end in arrest, "
               "reported property crimes rarely do.")
    return jsonify({"data": records(out), "overall_pct": overall, "min_n": min_n, "insight": insight})


@analytics_bp.get("/arrest-rate-by-year")
def arrest_by_year():
    df = crimes_df(); require_rows(df)
    out = df.groupby("year")["arrest"].agg(crimes="size", arrests="sum", rate="mean").reset_index()
    out["arrest_rate_pct"] = (out.pop("rate") * 100).round(2)
    reliable = out[out["crimes"] >= 30]
    if len(reliable) >= 3:
        rng = reliable["arrest_rate_pct"].max() - reliable["arrest_rate_pct"].min()
        insight = (f"Across years with ≥30 crimes the arrest rate varies by {rng:.1f} percentage points: "
                   f"{'fairly consistent' if rng < 3 else 'NOT consistent'}.")
    else:
        small = out[out["crimes"] < 30]
        insight = (f"Consistency cannot be judged: only {len(reliable)} year(s) have ≥30 crimes. "
                   f"The other years have {small['crimes'].min() if len(small) else 0}–"
                   f"{small['crimes'].max() if len(small) else 0} crimes each, so their rates swing "
                   "between 0% and 100% by chance.")
    return jsonify({"data": records(out), "insight": insight})


@analytics_bp.get("/heatmap")
def heatmap():
    df = crimes_df(); require_rows(df)
    pv = (df.pivot_table(index="month", columns="day_of_week", values="case_number",
                         aggfunc="count", fill_value=0)
            .reindex(index=range(1, 13), columns=DAY_ORDER, fill_value=0).astype(int))
    m, d = np.unravel_index(pv.values.argmax(), pv.shape)
    share = pv.values.max() / pv.values.sum() * 100
    insight = (f"Busiest cell: {MONTHS[m]} / {DAY_ORDER[d]} with {pv.values.max():,} crimes "
               f"({share:.0f}% of the total). Busiest weekday overall: {pv.sum().idxmax()}.")
    if share > 30:
        insight += " One cell dominating means the heatmap reflects the extract dates, not a weekly pattern."
    return jsonify({"months": MONTHS, "days": DAY_ORDER, "values": pv.values.tolist(), "insight": insight})


@analytics_bp.get("/crimes-by-month")
def crimes_by_month():
    df = crimes_df(); require_rows(df)
    counts = df.groupby("month").size().reindex(range(1, 13), fill_value=0)
    days = df.groupby("month")["date"].apply(lambda s: s.dt.normalize().nunique()).reindex(range(1, 13))
    out = pd.DataFrame({"month": MONTHS, "crimes": counts.values,
                        "crimes_per_day": (counts / days).round(2).fillna(0).values})
    top = out.loc[out["crimes"].idxmax()]
    share = top["crimes"] / out["crimes"].sum() * 100
    insight = f"{top['month']} has the most crimes ({top['crimes']:,}, {share:.1f}%)."
    if share > 40:
        insight += " This reflects when the extract was taken, not seasonality."
    return jsonify({"data": records(out), "insight": insight})


@analytics_bp.get("/crimes-by-hour")
def crimes_by_hour():
    df = crimes_df(); require_rows(df)
    counts = df.groupby("hour").size().reindex(range(24), fill_value=0)
    has_time = bool((df["date"].dt.time != pd.Timestamp(0).time()).any())
    if has_time:
        insight = (f"Peak hour {counts.idxmax()}:00 ({counts.max():,} crimes); "
                   f"quietest {counts.idxmin()}:00 ({counts.min():,}).")
    else:
        insight = ("The source dates have no time of day (e.g. 5/3/2016), so every crime is stamped 00:00. "
                   "df['date'].dt.hour returns 0 for all rows; the single midnight spike is a data "
                   "limitation, not a crime pattern.")
    return jsonify({"data": [{"hour": h, "crimes": int(c)} for h, c in counts.items()],
                    "has_time_of_day": has_time, "insight": insight})


@analytics_bp.get("/top-communities")
def top_communities():
    df = crimes_df(); require_rows(df)
    top = request.args.get("top", 10, type=int)
    out = (df.dropna(subset=["community_code"])
             .groupby(["community_code", "community_name", "population"], dropna=False)
             .size().reset_index(name="crimes"))
    out["per_1000"] = (out["crimes"] / out["population"] * 1000).round(2)
    by_count = out.nlargest(top, "crimes")
    by_rate = out.dropna(subset=["per_1000"]).nlargest(top, "per_1000")
    insight = (f"{by_count.iloc[0]['community_name']} has the most crimes ({by_count.iloc[0]['crimes']}). "
               f"Per 1,000 residents the highest is {by_rate.iloc[0]['community_name']} "
               f"({by_rate.iloc[0]['per_1000']}), so small communities can rank high on rate.")
    return jsonify({"by_count": records(by_count), "by_rate": records(by_rate), "insight": insight})


@analytics_bp.get("/community-outliers")
def community_outliers():
    df = crimes_df(); require_rows(df)
    with engine.connect() as conn:
        allc = pd.read_sql(text("SELECT community_code, community_name, population FROM city_community"), conn)
    counts = df.groupby("community_code").size()
    allc["crimes"] = allc["community_code"].map(counts).fillna(0).astype(int)   # areas with 0 crimes count too
    allc["community_name"] = allc["community_name"].str.title()
    arr = allc["crimes"].to_numpy()
    q1, q3 = np.percentile(arr, [25, 75])
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    outl = allc[(arr < lo) | (arr > hi)].sort_values("crimes", ascending=False)
    stats = {"areas": int(arr.size), "mean": round(float(np.mean(arr)), 2), "median": float(np.median(arr)),
             "std": round(float(np.std(arr, ddof=1)), 2), "min": int(arr.min()), "max": int(arr.max()),
             "q1": float(q1), "q3": float(q3), "iqr": float(iqr), "lower_fence": float(lo), "upper_fence": float(hi)}
    names = ", ".join(outl["community_name"]) or "none"
    insight = (f"Mean {stats['mean']} crimes per community area (median {stats['median']}). "
               f"IQR rule: outlier if > {hi:.1f}. Extreme high-crime areas: {names}.")
    return jsonify({"stats": stats, "counts": records(allc), "outliers": records(outl), "insight": insight})


@analytics_bp.get("/correlation")
def correlation():
    df = crimes_df(); require_rows(df)
    num = pd.DataFrame({"year": df["year"], "month": df["month"], "hour": df["hour"],
                        "day_of_week": df["date"].dt.day_of_week, "arrest": df["arrest"].astype(int),
                        "domestic": df["domestic"].astype(int),
                        "district_code": df["district_code"], "ward_no": df["ward_no"],
                        "community_code": df["community_code"],
                        "latitude": df["latitude"], "longitude": df["longitude"]}).astype(float)
    constant = [c for c in num if num[c].nunique() <= 1]
    corr = num.drop(columns=constant).corr().round(3)
    pairs = corr.where(np.triu(np.ones(corr.shape, dtype=bool), k=1)).stack()
    top = pairs.abs().sort_values(ascending=False).head(3)
    desc = "; ".join(f"{a} vs {b}: r = {pairs[(a, b)]:+.2f}" for a, b in top.index)
    arrest_year = corr.loc["arrest", "year"] if "year" in corr else float("nan")
    insight = (f"Strongest pairs: {desc} — these are location codes describing the same place, "
               f"i.e. geography, not a crime insight. Arrest vs year r = {arrest_year:+.2f}.")
    if constant:
        insight += f" Dropped constant column(s): {constant}."
    return jsonify({"columns": corr.columns.tolist(),
                    "matrix": json.loads(corr.to_json(orient="values")),
                    "dropped_constant": constant, "insight": insight})


@analytics_bp.get("/views/<name>")
def read_view(name):
    if name not in VIEWS:
        abort(404, description=f"Unknown view. Available: {list(VIEWS)}")
    with engine.connect() as conn:
        df = pd.read_sql(text(f"SELECT * FROM {name} ORDER BY {VIEWS[name]}"), conn)
    if name == "vw_crime_yearly":
        top = df.loc[df["total_crimes"].idxmax()]
        insight = (f"From vw_crime_yearly: {int(top['year'])} has {int(top['total_crimes'])} crimes "
                   f"with an arrest rate of {top['arrest_rate_pct']}%.")
    else:
        top5 = df.head(5)
        insight = (f"From vw_crime_by_category: the top 5 types ({', '.join(top5['primary_type'].str.title())}) "
                   f"account for {top5['pct_of_total'].sum():.2f}% of all crimes.")
    return jsonify({"view": name, "data": records(df), "insight": insight})

