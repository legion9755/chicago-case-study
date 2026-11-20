"""
Use Case 4 — Database Reporting & Integration
Objective: store, query and present analytical results from the database.

The assignment asks for a Python database *connector* for this use case. With SQLite that is
Python's built-in `sqlite3` module: the same DB-API pattern as mysql-connector
(connect -> cursor -> execute / executemany -> commit).

Run from the project folder:   python usecases/usecase4_reporting.py
"""
import sqlite3
from datetime import datetime

import matplotlib.pyplot as plt
import pandas as pd

from common import Report
from backend.database import DB_PATH

rep = Report("uc4", "Use Case 4 — Database Reporting & Integration")
conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA foreign_keys = ON")
cur = conn.cursor()


def show(sql, params=()):
    """Run a query with the sqlite3 cursor and print it as a table."""
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    out = pd.DataFrame(cur.fetchall(), columns=cols)
    print(out.to_string(index=False))
    return out


# -----------------------------------------------------------------------------
# 1. Design & populate summary tables
# -----------------------------------------------------------------------------
rep.section("1", "Design & populate summary tables (Python DB connector)",
            "Create tables and load the data through the Python database connector.")
DDL = {
    "summary_crime_yearly": """CREATE TABLE summary_crime_yearly (
        year INTEGER PRIMARY KEY, total_crimes INTEGER NOT NULL, total_arrests INTEGER NOT NULL,
        arrest_rate_pct REAL NOT NULL, domestic_crimes INTEGER NOT NULL)""",
    "summary_crime_category": """CREATE TABLE summary_crime_category (
        primary_type TEXT PRIMARY KEY, total_crimes INTEGER NOT NULL, pct_of_total REAL NOT NULL,
        total_arrests INTEGER NOT NULL, arrest_rate_pct REAL NOT NULL)""",
    "summary_community": """CREATE TABLE summary_community (
        community_code INTEGER PRIMARY KEY REFERENCES city_community(community_code),
        community_name TEXT NOT NULL, population INTEGER, total_crimes INTEGER NOT NULL,
        crimes_per_1000_pop REAL)""",
}
LOAD = {
    "summary_crime_yearly": """INSERT INTO summary_crime_yearly
        SELECT year, COUNT(*), SUM(arrest), ROUND(100.0 * AVG(arrest), 2), SUM(domestic)
        FROM chicago_crime GROUP BY year""",
    "summary_crime_category": """INSERT INTO summary_crime_category
        SELECT i.primary_type, COUNT(*), ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM chicago_crime), 2),
               SUM(c.arrest), ROUND(100.0 * AVG(c.arrest), 2)
        FROM chicago_crime c JOIN iucr i ON i.iucr_code = c.iucr_code GROUP BY i.primary_type""",
    "summary_community": """INSERT INTO summary_community
        SELECT cc.community_code, cc.community_name, cc.population, COUNT(*),
               ROUND(1000.0 * COUNT(*) / NULLIF(cc.population, 0), 2)
        FROM chicago_crime c JOIN city_community cc ON cc.community_code = c.community_code
        GROUP BY cc.community_code""",
}
try:
    for table, ddl in DDL.items():
        cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute(ddl)
        cur.execute(LOAD[table])
        print(f"cursor.execute(CREATE + INSERT ... SELECT)  ->  {table:<24} {cur.rowcount:>3} rows")
    # parameterised insert from Python data (executemany with ? placeholders)
    cur.execute("DROP TABLE IF EXISTS etl_run_log")
    cur.execute("CREATE TABLE etl_run_log (step TEXT PRIMARY KEY, rows_written INTEGER, run_at TEXT)")
    rows = [(t, cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0], datetime.now().isoformat(timespec="seconds"))
            for t in DDL]
    cur.executemany("INSERT INTO etl_run_log VALUES (?, ?, ?)", rows)
    conn.commit()
    print(f"cursor.executemany(INSERT ... VALUES (?, ?, ?))  ->  etl_run_log {len(rows)} rows")
    print("conn.commit()\n")
except sqlite3.Error:
    conn.rollback()
    raise
show("SELECT * FROM summary_crime_yearly ORDER BY year")
rep.insight("Three summary tables were created and filled with INSERT … SELECT so the database computes the "
            "aggregates itself; executemany with ? placeholders shows the safe way to insert Python data.")

# -----------------------------------------------------------------------------
# 2. Queries
# -----------------------------------------------------------------------------
rep.section("2.1", "SQL: crime count per year", "Write SQL to compute crime count per year.")
q = "SELECT year, COUNT(*) AS crime_count FROM chicago_crime GROUP BY year ORDER BY year"
print(q + "\n")
yearly = show(q)
rep.insight(f"2016 has {yearly['crime_count'].iloc[-1]} of {yearly['crime_count'].sum()} crimes; 2012–2015 contain "
            "only a handful of late-reported cases.")

rep.section("2.2", "SQL: top 5 crime types and their percentages",
            "Write SQL to compute the top 5 crime types and their percentages.")
q = """SELECT i.primary_type,
       COUNT(*)                                           AS crime_count,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_of_total
FROM chicago_crime c
JOIN iucr i ON i.iucr_code = c.iucr_code
GROUP BY i.primary_type
ORDER BY crime_count DESC
LIMIT 5"""
print(q + "\n")
top5 = show(q)
rep.insight(f"The top 5 types make up {top5['pct_of_total'].sum():.2f}% of all crimes. SUM(COUNT(*)) OVER () is a "
            "window function: it puts the grand total on every row, before LIMIT is applied.")

rep.section("2.3", "SQL: arrest count per year", "Write SQL to compute arrest count per year.")
q = """SELECT year, SUM(arrest) AS arrest_count, COUNT(*) AS crime_count,
       ROUND(100.0 * AVG(arrest), 2) AS arrest_rate_pct
FROM chicago_crime GROUP BY year ORDER BY year"""
print(q + "\n")
show(q)
rep.insight("2016 has 119 arrests from 490 crimes (24.29%). arrest is stored as 0/1, so SUM gives the count "
            "and AVG gives the rate.")

# -----------------------------------------------------------------------------
# 3. Views
# -----------------------------------------------------------------------------
rep.section("3", "Database stored views", "Create views vw_crime_yearly and vw_crime_by_category.")
VIEWS = {
    "vw_crime_yearly": """CREATE VIEW vw_crime_yearly AS
SELECT year, COUNT(*) AS total_crimes, SUM(arrest) AS total_arrests,
       ROUND(100.0 * AVG(arrest), 2) AS arrest_rate_pct, SUM(domestic) AS domestic_crimes
FROM chicago_crime GROUP BY year""",
    "vw_crime_by_category": """CREATE VIEW vw_crime_by_category AS
SELECT i.primary_type, COUNT(*) AS total_crimes,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_of_total,
       SUM(c.arrest) AS total_arrests, ROUND(100.0 * AVG(c.arrest), 2) AS arrest_rate_pct
FROM chicago_crime c JOIN iucr i ON i.iucr_code = c.iucr_code GROUP BY i.primary_type""",
}
for name, ddl in VIEWS.items():
    cur.execute(f"DROP VIEW IF EXISTS {name}")
    cur.execute(ddl)
    print(ddl + ";\n")
conn.commit()
show("SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view') ORDER BY type, name")
rep.insight("A view stores only the query, so it is always current; the summary tables store results and must "
            "be refreshed when the data changes.")

# -----------------------------------------------------------------------------
# 4. Pandas integration
# -----------------------------------------------------------------------------
rep.section("4", "Pandas integration — read the views into DataFrames",
            'Read these views into Pandas DataFrames for further analysis: pd.read_sql("SELECT * FROM vw_crime_yearly", conn)')
vy = pd.read_sql("SELECT * FROM vw_crime_yearly ORDER BY year", conn)
vc = pd.read_sql("SELECT * FROM vw_crime_by_category ORDER BY total_crimes DESC", conn)
print('vy = pd.read_sql("SELECT * FROM vw_crime_yearly", conn)\n')
print(vy.to_string(index=False))
print('\nvc = pd.read_sql("SELECT * FROM vw_crime_by_category", conn)\n')
vc["share_of_all_arrests_%"] = (vc["total_arrests"] / vc["total_arrests"].sum() * 100).round(1)
print(vc.head(10).to_string(index=False))
top_arrest = vc.sort_values("total_arrests", ascending=False).iloc[0]
rep.insight(f"Further analysis in Pandas: {top_arrest['primary_type'].title()} produces the most arrests "
            f"({top_arrest['share_of_all_arrests_%']}% of all arrests) even though it is only "
            f"{top_arrest['pct_of_total']}% of crimes.")

# -----------------------------------------------------------------------------
# 5. Visualization from database data
# -----------------------------------------------------------------------------
rep.section("5", "Visualization from database data", "Plot SQL-extracted data with Matplotlib and Seaborn.")
fig, ax = plt.subplots()
ax.bar(vy["year"].astype(str), vy["total_crimes"], color="#9dc3e6", label="Total crimes")
ax.set(title="Crimes and arrest rate per year (from vw_crime_yearly)", xlabel="Year", ylabel="Crimes")
ax2 = ax.twinx()
ax2.plot(vy["year"].astype(str), vy["arrest_rate_pct"], color="#c00000", marker="o", lw=2.5, label="Arrest rate %")
ax2.set(ylabel="Arrest rate (%)", ylim=(0, 115))
ax2.grid(False)
h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, loc="upper left")
rep.figure(fig, "uc4_1_vw_crime_yearly")

top = vc.head(10).iloc[::-1]
fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 5.5), sharey=True)
a1.barh(top["primary_type"].str.title(), top["pct_of_total"], color="#2e75b6")
a1.set(title="Share of all crimes (%)", xlabel="%")
a2.barh(top["primary_type"].str.title(), top["arrest_rate_pct"], color="#548235")
a2.set(title="Arrest rate (%)", xlabel="%")
fig.suptitle("Top 10 crime categories (from vw_crime_by_category)", fontweight="bold")
rep.figure(fig, "uc4_2_vw_crime_by_category")
print("Both charts are drawn only from data read out of the database views.")
rep.insight("The most common crimes are not the ones that lead to arrests: Theft is 21% of crimes but has a "
            "9.5% arrest rate, while Narcotics (6.4% of crimes) has a 100% arrest rate.")

conn.close()
rep.save()
