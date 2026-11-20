"""
pipeline/etl.py
Extract → Transform → Load pipeline for the Chicago crime data.

    EXTRACT    6 CSV files from data/
    TRANSFORM  de-duplicate, parse dates, standardise text/booleans/codes, join IUCR,
               handle missing values, fix coordinates, add Year/Month/DayOfWeek/Hour
    LOAD       SQLite via SQLAlchemy 2 — dimension tables first, then the fact table

Run the whole pipeline in one go:
    python -m pipeline.etl
Use Case 1 (usecases/usecase1_load_clean.py) calls the same functions step by step and prints
what each step found.
"""
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.database import DATA_DIR, engine          # noqa: E402
from backend.models import Base, VIEWS_SQL              # noqa: E402

# accepted file names per dataset (the delivered IUCR file is "iucr_codes.csv.csv")
FILES = {
    "crime": ["chicago_crime_dataset.csv"],
    "iucr": ["iucr_codes.csv", "iucr_codes.csv.csv"],
    "district": ["chicago_district_ps_info.csv"],
    "ward": ["chicago_ward_offices.csv"],
    "community": ["chicago_city_community.csv"],
    "beat": ["chicago_police_beat_info.csv"],
}
RENAME = {"iucr": "iucr_code", "ward": "ward_no"}           # header fixes to match the data model
DATE_FORMATS = ["%m/%d/%Y %H:%M", "%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M:%S",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%m/%d/%Y"]
BOOL_MAP = {"TRUE": True, "T": True, "Y": True, "YES": True, "1": True, "1.0": True,
            "FALSE": False, "F": False, "N": False, "NO": False, "0": False, "0.0": False}
CHICAGO_BOX = dict(lat_min=41.64, lat_max=42.03, lon_min=-87.95, lon_max=-87.52)
PROTECTED = {"id", "case_number", "date", "iucr_code", "primary_type", "arrest", "domestic"}


class QualityLog:
    """Collects every data-quality finding: what was checked, rows affected, action taken."""

    def __init__(self, verbose=True):
        self.rows, self.verbose = [], verbose

    def add(self, check, rows_affected, action):
        self.rows.append({"check": check, "rows_affected": int(rows_affected), "action": action})
        if self.verbose:
            print(f"  [{check}] rows affected: {int(rows_affected):,} -> {action}")

    def to_frame(self):
        return pd.DataFrame(self.rows)


# =============================================================================
# EXTRACT
# =============================================================================
def data_file(key):
    for name in FILES[key]:
        if (DATA_DIR / name).exists():
            return DATA_DIR / name
    raise FileNotFoundError(f"None of {FILES[key]} found in {DATA_DIR}")


def snake(columns):
    return columns.str.strip().str.lower().str.replace(r"\s+", "_", regex=True)


def read_crime_csv():
    """Read the master file. Its last lines have an unclosed quote (truncated export) which makes
    plain pd.read_csv fail, so such quotes are closed first. Returns (df, repaired_line_numbers)."""
    lines = data_file("crime").read_text(encoding="utf-8-sig").splitlines()
    repaired = [i + 1 for i, line in enumerate(lines) if line.count('"') % 2 == 1]
    fixed = [line + '"' if line.count('"') % 2 == 1 else line for line in lines]
    df = pd.read_csv(io.StringIO("\n".join(fixed)),
                     dtype={"iucr_code": str, "case_number": str, "fbi_code": str})
    df.columns = snake(df.columns)
    return df, repaired


def read_lookup(key):
    df = pd.read_csv(data_file(key), dtype=str)
    df.columns = snake(df.columns)                     # 'PRIMARY_TYPE ' -> 'primary_type'
    df = df.rename(columns=RENAME)
    return df.apply(lambda s: s.str.strip())


def read_all_lookups():
    return {k: read_lookup(k) for k in ["iucr", "community", "district", "ward", "beat"]}


# =============================================================================
# TRANSFORM — fact table
# =============================================================================
def standardize_text(s):
    return s.astype("string").str.strip().str.replace(r"\s+", " ", regex=True).str.upper()


def remove_duplicates(df, log):
    n = df.duplicated().sum()
    df = df.drop_duplicates()
    log.add("Exact duplicate rows", n, "dropped")
    upd = pd.to_datetime(df["date_of_update"], format="%m/%d/%Y", errors="coerce")
    n = df["case_number"].duplicated().sum()
    df = (df.assign(_upd=upd).sort_values("_upd")
            .drop_duplicates("case_number", keep="last").drop(columns="_upd").sort_index())
    log.add("Duplicate case_number (primary key)", n, "kept the most recently updated record")
    n = df["case_number"].isna().sum()
    log.add("Missing case_number", n, "dropped")
    return df[df["case_number"].notna()].copy()


def parse_mixed_dates(series):
    """Try each known format in turn. Returns (datetimes, format_used_per_row)."""
    s = series.astype("string").str.strip()
    parsed = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    fmt_used = pd.Series(pd.NA, index=s.index, dtype="string")
    for fmt in DATE_FORMATS:
        todo = parsed.isna() & s.notna()
        if not todo.any():
            break
        attempt = pd.to_datetime(s[todo], format=fmt, errors="coerce")
        ok = attempt.dropna().index
        parsed.loc[ok] = attempt.loc[ok]
        fmt_used.loc[ok] = fmt
    return parsed, fmt_used


def clean_dates(df, log):
    df = df.copy()
    df["date"], fmt = parse_mixed_dates(df["date"])
    df["date_of_update"], _ = parse_mixed_dates(df["date_of_update"])
    formats = fmt.value_counts(dropna=False)
    dominant = formats.index[0]
    log.add("Date formats found", len(formats), ", ".join(f"{k}: {v}" for k, v in formats.items()))
    log.add("Date in a different format from the rest", (fmt.notna() & (fmt != dominant)).sum(),
            "parsed with the matching format")
    log.add("Date has no time of day (date only)", (fmt == "%m/%d/%Y").sum(),
            "time = 00:00; hour-of-day analysis not possible")
    bad = df["date"].isna()
    log.add("Date missing / unparseable", bad.sum(), "dropped")
    df = df[~bad]
    future = df["date"] > pd.Timestamp.today()
    log.add("Crime date in the future", future.sum(), "dropped")
    df = df[~future]
    upd_before = df["date_of_update"].notna() & (df["date_of_update"] < df["date"])
    log.add("date_of_update earlier than date", upd_before.sum(), "flagged only")
    mismatch = pd.to_numeric(df["year"], errors="coerce") != df["date"].dt.year
    log.add("year column disagrees with date", mismatch.sum(), "year rebuilt from date")
    return df.copy()


def standardize_fields(df, log):
    df = df.copy()
    before = df["location_desc"].nunique()
    for col in ["block", "location_desc", "fbi_code", "iucr_code", "case_number"]:
        df[col] = standardize_text(df[col])
    df["iucr_code"] = df["iucr_code"].str.zfill(4)             # '486' -> '0486'
    log.add("location_desc distinct values before/after standardising", before - df["location_desc"].nunique(),
            f"{before} -> {df['location_desc'].nunique()} categories")
    for col in ["arrest", "domestic"]:
        mapped = standardize_text(df[col]).map(BOOL_MAP)
        log.add(f"{col} missing / unrecognised", mapped.isna().sum(), "set to False")
        df[col] = mapped.fillna(False).astype(bool)
    for col in ["id", "beat_num", "district_code", "ward_no", "community_code"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").round().astype("Int64")
    for col in ["x_coordinate", "y_coordinate", "latitude", "longitude"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def clean_iucr(iucr_raw):
    iucr = iucr_raw.copy()
    iucr["iucr_code"] = standardize_text(iucr["iucr_code"]).str.zfill(4)
    for col in ["primary_type", "description", "index_code"]:
        iucr[col] = standardize_text(iucr[col])
    return iucr.drop_duplicates("iucr_code")


def attach_crime_type(df, iucr, log):
    df = df.drop(columns=[c for c in ["primary_type", "description"] if c in df.columns])
    df = df.merge(iucr[["iucr_code", "primary_type", "description"]], on="iucr_code", how="left")
    unknown = df["primary_type"].isna()
    log.add("IUCR code not in lookup table", unknown.sum(), "primary_type = 'UNKNOWN'")
    df["primary_type"] = df["primary_type"].fillna("UNKNOWN")
    df["description"] = df["description"].fillna("UNKNOWN")
    return df


def handle_missing(df, beat_raw, log):
    df = df.copy()
    n = df["iucr_code"].isna().sum()
    df = df[df["iucr_code"].notna()]
    log.add("Missing iucr_code", n, "dropped")

    beat = beat_raw.assign(beat_num=pd.to_numeric(beat_raw["beat_num"], errors="coerce"),
                           district=pd.to_numeric(beat_raw["district"], errors="coerce"))
    beat_to_district = beat.drop_duplicates("beat_num").set_index("beat_num")["district"]
    miss = df["district_code"].isna() & df["beat_num"].notna()
    derived = df.loc[miss, "beat_num"].map(beat_to_district).fillna(df.loc[miss, "beat_num"] // 100)
    df.loc[miss, "district_code"] = derived.astype("Int64")
    log.add("Missing district_code", miss.sum(), "derived from beat_num")

    n = df["location_desc"].isna().sum()
    df["location_desc"] = df["location_desc"].fillna("UNKNOWN")
    log.add("Missing location_desc", n, "filled with 'UNKNOWN'")
    for col in ["ward_no", "community_code"]:
        log.add(f"Missing {col}", df[col].isna().sum(), "kept NULL (not guessed)")
    log.add("Missing latitude/longitude", df["latitude"].isna().sum(), "kept NULL (not guessed)")
    return df


def fix_coordinates(df, log):
    df = df.copy()
    b = CHICAGO_BOX
    flip = df["longitude"].between(-b["lon_max"], -b["lon_min"])
    df.loc[flip, "longitude"] = -df.loc[flip, "longitude"]
    log.add("Longitude missing its minus sign", flip.sum(), "sign corrected")
    has = df["latitude"].notna() & df["longitude"].notna()
    outside = has & ~(df["latitude"].between(b["lat_min"], b["lat_max"])
                      & df["longitude"].between(b["lon_min"], b["lon_max"]))
    log.add("Coordinates outside Chicago", outside.sum(), "set to NULL")
    df.loc[outside, ["latitude", "longitude", "x_coordinate", "y_coordinate"]] = np.nan
    df["location"] = np.where(df["latitude"].notna(),
                              "(" + df["latitude"].round(8).astype(str) + ", "
                              + df["longitude"].round(8).astype(str) + ")", None)
    return df


def add_features(df):
    df = df.copy()
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["day_of_week"] = df["date"].dt.day_name()
    df["hour"] = df["date"].dt.hour
    return df


def missing_pct_numpy(df):
    """% missing per column with NumPy: mean of the boolean isna() matrix down each column."""
    mask = df.isna().to_numpy()
    return pd.Series(np.round(np.mean(mask, axis=0) * 100, 3), index=df.columns)


def drop_sparse_columns(df, log, threshold=50):
    pct = missing_pct_numpy(df)
    over = pct[pct > threshold].index.tolist()
    to_drop = [c for c in over if c not in PROTECTED]
    log.add(f"Columns with > {threshold}% missing", len(over),
            f"dropped {to_drop}" if to_drop else "none dropped")
    return df.drop(columns=to_drop)


# =============================================================================
# TRANSFORM — dimension tables
# =============================================================================
def _num(s, as_int=False):
    v = pd.to_numeric(s.astype("string").str.replace(",", "", regex=False), errors="coerce")
    return v.round().astype("Int64") if as_int else v


def clean_dimensions(lk, log):
    iucr = clean_iucr(lk["iucr"])

    com = lk["community"].copy()
    com["community_code"] = _num(com["community_code"], True)
    com["population"] = _num(com["population"], True)                 # "55,062" -> 55062
    for c in ["area_sqmile", "area_sqkm", "density_per_sqmi", "density_per_sqkm"]:
        com[c] = _num(com[c])
    com["community_name"] = standardize_text(com["community_name"])
    com = com.dropna(subset=["community_code"]).drop_duplicates("community_code")

    dist = lk["district"].copy()
    dist["district_code"] = _num(dist["district_code"], True)
    for c in ["x_coordinate", "y_coordinate", "latitude", "longitude"]:
        dist[c] = _num(dist[c])
    dist = dist.dropna(subset=["district_code"]).drop_duplicates("district_code")

    ward = lk["ward"].copy()
    ward["ward_no"] = _num(ward["ward_no"], True)
    ward = ward.dropna(subset=["ward_no"])
    dups = sorted(ward.loc[ward["ward_no"].duplicated(keep=False), "ward_no"].unique().tolist())
    log.add("Duplicate ward_no in ward offices file", ward["ward_no"].duplicated().sum(),
            f"kept the last (newest) record for wards {dups}")
    ward = ward.drop_duplicates("ward_no", keep="last")

    beat = lk["beat"].copy()
    for c in ["beat_num", "district", "sector", "beat"]:
        beat[c] = _num(beat[c], True)
    beat = beat.dropna(subset=["beat_num"])
    log.add("Duplicate beat_num in police beat file", beat["beat_num"].duplicated().sum(),
            "identical rows dropped")
    beat = beat.drop_duplicates("beat_num")
    return {"iucr": iucr, "city_community": com, "district_ps_info": dist,
            "ward_office": ward, "police_beat_info": beat}


def fix_orphans(df, dims, log):
    """Foreign keys must point at existing lookup rows."""
    df = df.copy()
    missing = sorted(set(df["iucr_code"]) - set(dims["iucr"]["iucr_code"]))
    if missing:
        dims["iucr"] = pd.concat([dims["iucr"], pd.DataFrame(
            {"iucr_code": missing, "primary_type": "UNKNOWN", "description": "CODE NOT IN LOOKUP"})])
    log.add("IUCR codes added as placeholders", len(missing), str(missing) if missing else "none needed")
    checks = {"beat_num": ("police_beat_info", "beat_num"), "district_code": ("district_ps_info", "district_code"),
              "ward_no": ("ward_office", "ward_no"), "community_code": ("city_community", "community_code")}
    for col, (table, key) in checks.items():
        orphan = df[col].notna() & ~df[col].isin(dims[table][key].dropna())
        df.loc[orphan, col] = pd.NA
        log.add(f"Orphan foreign key {col}", orphan.sum(), "set to NULL")
    return df, dims


# =============================================================================
# LOAD
# =============================================================================
FACT_COLUMNS = ["case_number", "id", "date", "block", "iucr_code", "location_desc", "arrest",
                "domestic", "beat_num", "district_code", "ward_no", "community_code", "fbi_code",
                "x_coordinate", "y_coordinate", "year", "month", "day_of_week", "hour",
                "date_of_update", "latitude", "longitude", "location"]


def create_views(conn):
    for name, ddl in VIEWS_SQL.items():
        conn.execute(text(f"DROP VIEW IF EXISTS {name}"))
        conn.execute(text(ddl))


def reset_database():
    """Drop every view and table (including Use Case 4 summary tables) so the pipeline always
    rebuilds a clean database. FK checks are switched off only while dropping."""
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys = OFF")
        insp = inspect(conn)
        for view in insp.get_view_names():
            conn.exec_driver_sql(f'DROP VIEW IF EXISTS "{view}"')
        for table in insp.get_table_names():
            conn.exec_driver_sql(f'DROP TABLE IF EXISTS "{table}"')
        conn.commit()
        conn.exec_driver_sql("PRAGMA foreign_keys = ON")


def load_to_database(df, dims):
    """(Re)create the schema from the ORM models and load lookups first, then the fact table."""
    reset_database()
    Base.metadata.create_all(engine)

    counts = {}
    with engine.begin() as conn:
        for table in ["iucr", "city_community", "district_ps_info", "ward_office", "police_beat_info"]:
            cols = [c.name for c in Base.metadata.tables[table].columns]
            frame = dims[table][[c for c in cols if c in dims[table].columns]]
            frame.to_sql(table, conn, if_exists="append", index=False)
            counts[table] = len(frame)
        fact = df[FACT_COLUMNS].copy()
        fact["arrest"] = fact["arrest"].astype(int)
        fact["domestic"] = fact["domestic"].astype(int)
        fact.to_sql("chicago_crime", conn, if_exists="append", index=False, chunksize=2000)
        counts["chicago_crime"] = len(fact)
        create_views(conn)
    return counts


# =============================================================================
# Whole pipeline
# =============================================================================
def run_pipeline(verbose=True):
    log = QualityLog(verbose)
    raw, repaired = read_crime_csv()
    log.add("Line with unclosed quote (truncated export)", len(repaired), f"quote closed on lines {repaired}")
    lk = read_all_lookups()
    df = remove_duplicates(raw, log)
    df = clean_dates(df, log)
    df = standardize_fields(df, log)
    df = attach_crime_type(df, clean_iucr(lk["iucr"]), log)
    df = handle_missing(df, lk["beat"], log)
    df = fix_coordinates(df, log)
    df = add_features(df)
    df = drop_sparse_columns(df, log)
    dims = clean_dimensions(lk, log)
    df, dims = fix_orphans(df, dims, log)
    counts = load_to_database(df, dims)
    quality = log.to_frame()
    quality.to_sql("data_quality_log", engine, if_exists="replace", index=False)
    return raw, df, dims, quality, counts


if __name__ == "__main__":
    print("Running ETL pipeline ...")
    _, _, _, _, counts = run_pipeline(verbose=True)
    print("\nLoaded into SQLite:")
    for table, n in counts.items():
        print(f"  {table:<18} {n:>6,} rows")
