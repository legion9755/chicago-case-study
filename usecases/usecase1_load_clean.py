"""
Use Case 1 — Load and Clean Chicago Crime Data
Objective: build a data-ingestion pipeline to read, clean and insert crime data into the database.

Run from the project folder:   python usecases/usecase1_load_clean.py
Creates/refreshes db/chicago_crime.db (SQLite, written with SQLAlchemy 2).
"""
import matplotlib.pyplot as plt
import pandas as pd
from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateTable

from common import Report
from backend.database import DB_PATH, engine
from backend.models import Base
from pipeline import etl

rep = Report("uc1", "Use Case 1 — Load and Clean Chicago Crime Data")
log = etl.QualityLog(verbose=True)

# -----------------------------------------------------------------------------
# 1. Load the dataset
# -----------------------------------------------------------------------------
rep.section("1.1", "Load the dataset (CSV) into a Pandas DataFrame — first 10 rows",
            "Load the dataset (CSV) into a Pandas DataFrame. Inspect the first 10 rows.")
raw, repaired = etl.read_crime_csv()
log.add("Line with unclosed quote (truncated export)", len(repaired), f"quote closed on lines {repaired}")
print("raw = pd.read_csv('chicago_crime_dataset.csv')   # with truncated-quote repair\n")
print(raw.iloc[:10, :10].to_string())
print()
print(raw.iloc[:10, 10:].to_string())

rep.section("1.2", "Schema and data types", "Show schema and data types.")
buf = __import__("io").StringIO()
raw.info(buf=buf)
print(buf.getvalue())

rep.section("1.3", "How many columns and rows are there?", "How many columns and rows are there?")
print(f"raw.shape = {raw.shape}")
print(f"Rows: {raw.shape[0]:,}   Columns: {raw.shape[1]}")
rep.insight(f"The master file has {raw.shape[0]:,} rows and {raw.shape[1]} columns. The last 2 lines were "
            "truncated (unclosed quote) and had to be repaired before pandas could read the file.")

lookups = etl.read_all_lookups()
print("\nLookup files:")
for k, d in lookups.items():
    print(f"  {k:<10} {d.shape[0]:>4} rows x {d.shape[1]:>2} cols")

# -----------------------------------------------------------------------------
# 2. Clean the dataset
# -----------------------------------------------------------------------------
rep.section("2.1", "Convert the Date column into datetime format",
            "Convert the Date column into datetime format.")
df = etl.remove_duplicates(raw, log)
print(f"\nBefore: date dtype = {raw['date'].dtype}, example = {raw['date'].iloc[0]!r}")
df = etl.clean_dates(df, log)
print(f"After:  date dtype = {df['date'].dtype}, example = {df['date'].iloc[0]}")
print(f"Date range: {df['date'].min():%d %b %Y} -> {df['date'].max():%d %b %Y}")
rep.insight("All 498 dates use one format (%m/%d/%Y) and converted cleanly, but they carry no time of day, "
            "so every timestamp is 00:00.")

rep.section("2.2", "Identify and handle missing values for key fields",
            "Identify and handle missing values for key fields.")
df = etl.standardize_fields(df, log)
df = etl.attach_crime_type(df, etl.clean_iucr(lookups["iucr"]), log)
key = ["case_number", "date", "iucr_code", "primary_type", "arrest", "domestic", "location_desc",
       "beat_num", "district_code", "ward_no", "community_code", "latitude", "longitude"]
before = df[key].isna().sum().rename("missing_before")
df = etl.handle_missing(df, lookups["beat"], log)
after = df[key].isna().sum().rename("missing_after")
print()
print(pd.concat([before, after], axis=1).to_string())
rep.insight("Only location_desc (4 rows, filled with 'UNKNOWN') and the coordinates (29 rows, 5.8%, kept "
            "NULL rather than invented) had gaps; every key field needed for the analysis is complete.")

rep.section("2.3", "Standardize categorical fields (strip whitespace, unify case)",
            "Standardize categorical fields (strip whitespace, unify case).")
print("Rule: s.str.strip().str.replace(r'\\s+', ' ').str.upper()   applied to block, location_desc, "
      "fbi_code, iucr_code")
print("IUCR codes padded to 4 characters with zfill(4):  '486' -> '0486'")
print("\nExample (raw -> clean):")
ex = pd.DataFrame({"raw_iucr_code": raw["iucr_code"].head(5).values, "clean_iucr_code": df["iucr_code"].head(5).values,
                   "raw_arrest": raw["arrest"].head(5).values, "clean_arrest": df["arrest"].head(5).values})
print(ex.to_string(index=False))
print(f"\nlocation_desc categories: {raw['location_desc'].nunique()} raw -> {df['location_desc'].nunique()} clean")
df = etl.fix_coordinates(df, log)

# -----------------------------------------------------------------------------
# 3. Generate new features
# -----------------------------------------------------------------------------
rep.section("3", "Generate new features: Year, Month, DayOfWeek from the Date field",
            "Extract Year, Month, and DayOfWeek from the Date field.")
df = etl.add_features(df)
print("df['year'] = df['date'].dt.year\ndf['month'] = df['date'].dt.month\n"
      "df['day_of_week'] = df['date'].dt.day_name()\ndf['hour'] = df['date'].dt.hour\n")
print(df[["case_number", "date", "year", "month", "day_of_week", "hour"]].head(8).to_string(index=False))

# -----------------------------------------------------------------------------
# 4. NumPy
# -----------------------------------------------------------------------------
rep.section("4", "Use NumPy: % missing per column; drop columns with > 50% missing",
            "Calculate the percentage of missing values per column. Can you drop any columns with > 50% missing?")
print("mask = df.isna().to_numpy()\nmissing_pct = np.mean(mask, axis=0) * 100\n")
raw_pct = etl.missing_pct_numpy(raw)
clean_pct = etl.missing_pct_numpy(df.reindex(columns=raw.columns))
table = pd.DataFrame({"raw_missing_%": raw_pct, "clean_missing_%": clean_pct}).sort_values("raw_missing_%", ascending=False)
print(table.to_string())
df = etl.drop_sparse_columns(df, log)
fig, ax = plt.subplots(figsize=(10, 4.5))
t = table[table["raw_missing_%"] > 0]
ax.barh(t.index[::-1], t["raw_missing_%"][::-1], color="#7f7f7f")
ax.axvline(50, color="#c00000", ls="--", label="50% drop threshold")
ax.set(title="Missing values per column (raw file)", xlabel="% missing", xlim=(0, 60))
ax.legend()
rep.figure(fig, "uc1_missing_values")
rep.insight(f"No column exceeds 50% missing (maximum {raw_pct.max():.2f}% for the coordinate columns), "
            "so no column is dropped. Key fields are also protected from automatic dropping.")

# -----------------------------------------------------------------------------
# 5. Insert into the database
# -----------------------------------------------------------------------------
rep.section("5.1", "Design a crime table schema", "Design a crime table schema.")
dims = etl.clean_dimensions(lookups, log)
df, dims = etl.fix_orphans(df, dims, log)
print("\nStar schema: 1 fact table (chicago_crime) + 5 dimension tables, linked by foreign keys.\n")
print(str(CreateTable(Base.metadata.tables["chicago_crime"]).compile(engine)).strip())

rep.section("5.2", "Write the data with SQLAlchemy", "Use SQLAlchemy or PyMySQL to write data.")
counts = etl.load_to_database(df, dims)
quality = log.to_frame()
quality.to_sql("data_quality_log", engine, if_exists="replace", index=False)
print(f"Database: {DB_PATH.name}  (SQLite, SQLAlchemy 2)\n")
print("df.to_sql(table, conn, if_exists='append')  -- dimension tables first, fact table last\n")
with engine.connect() as conn:
    for table_name, n in counts.items():
        in_db = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
        print(f"  {table_name:<18} loaded {n:>4}   rows in DB {in_db:>4}   {'OK' if n == in_db else 'MISMATCH'}")
print("\nTables & views:", inspect(engine).get_table_names() + inspect(engine).get_view_names())

# -----------------------------------------------------------------------------
# Questions
# -----------------------------------------------------------------------------
rep.section("Q1", "How many unique crime types exist in the dataset?",
            "How many unique crime types exist in the dataset?")
n_types = df["primary_type"].nunique()
print(f"df['primary_type'].nunique() = {n_types}")
print(f"df['iucr_code'].nunique()    = {df['iucr_code'].nunique()}  (detailed IUCR sub-codes)\n")
print(df["primary_type"].value_counts().to_string())
rep.insight(f"There are {n_types} unique crime types (primary_type), split into {df['iucr_code'].nunique()} "
            "detailed IUCR codes. Theft and Battery are the largest.")

rep.section("Q2", "Are there anomalies in date formats or obvious outliers?",
            "Are there anomalies in date formats or obvious outliers?")
print(quality[quality["rows_affected"] > 0].to_string(index=False))
by_day = df["date"].dt.date.value_counts()
print(f"\nCrimes per year:\n{df['year'].value_counts().sort_index().to_string()}")
print(f"\nBusiest dates:\n{by_day.head(4).to_string()}")
print(f"\nNumeric ranges:\n{df[['latitude', 'longitude', 'beat_num', 'ward_no', 'community_code']].describe().loc[['min', 'max']].to_string()}")
rep.insight("No date-format conflicts, future dates or out-of-Chicago coordinates were found. The real anomalies "
            "are: dates have no time of day; 89% of crimes fall on 3–4 May 2016 (the file is a snapshot of "
            "recently updated records, older dates are late reports); 2 truncated lines; 8 duplicate wards and "
            "2 duplicate beats in the lookup files.")

rep.save()
