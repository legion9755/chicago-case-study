"""
Use Case 2 — Exploratory Analysis & Visualization of Crime
Objective: analyse trends and patterns using Pandas, NumPy, Matplotlib and Seaborn.

Run from the project folder:   python usecases/usecase2_eda.py
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from common import DAY_ORDER, MONTHS, Report, load_crimes

rep = Report("uc2", "Use Case 2 — Exploratory Analysis & Visualization of Crime")
df = load_crimes()
print(f"Loaded {len(df):,} crimes from SQLite ({df['date'].min():%d %b %Y} -> {df['date'].max():%d %b %Y})")

# -----------------------------------------------------------------------------
# 1. Crime trend over years
# -----------------------------------------------------------------------------
rep.section("1", "Crime trend over years",
            "Plot total number of crimes per year. Visual interpretation: is the crime rate rising or decreasing?")
yearly = df.groupby("year").size()
months = df.groupby("year")["month"].nunique()
print("yearly = df.groupby('year').size()\n")
print(pd.DataFrame({"crimes": yearly, "months_covered": months}).T.to_string())
fig, ax = plt.subplots()
bars = ax.bar(yearly.index.astype(str), yearly.values, color="#1f4e79")
ax.bar_label(bars, padding=2)
ax.set(title="Total crimes per year", xlabel="Year", ylabel="Number of crimes")
rep.figure(fig, "uc2_1_crimes_per_year")
slope = np.polyfit(yearly.index, yearly.values, 1)[0]
share = yearly.max() / yearly.sum() * 100
print(f"\nLinear slope (np.polyfit): {slope:+.1f} crimes/year | {yearly.idxmax()} share: {share:.1f}% | "
      f"complete years (12 months): {(months == 12).sum()}")
rep.insight(f"The chart looks like a sharp RISE (slope {slope:+.0f}/year), but it is not a real trend: "
            f"{yearly.idxmax()} holds {share:.1f}% of the data and no year has all 12 months. Earlier years "
            "only contain crimes reported late. The crime-rate trend cannot be determined from this extract.")

# -----------------------------------------------------------------------------
# 2. Crime distribution by category
# -----------------------------------------------------------------------------
rep.section("2", "Crime distribution by category (Primary Type)",
            "Bar chart of top 10 crime categories (Primary Type). Calculate counts and percentage for each.")
cat = pd.DataFrame({"count": df["primary_type"].value_counts(),
                    "percent": df["primary_type"].value_counts(normalize=True).mul(100).round(2)})
top10 = cat.head(10)
print("df['primary_type'].value_counts()  and  value_counts(normalize=True) * 100\n")
print(top10.to_string())
fig, ax = plt.subplots(figsize=(10, 5.5))
bars = ax.barh(top10.index[::-1].str.title(), top10["count"][::-1], color="#2e75b6")
ax.bar_label(bars, labels=[f" {c} ({p}%)" for c, p in zip(top10["count"][::-1], top10["percent"][::-1])])
ax.set(title="Top 10 crime categories", xlabel="Number of crimes", xlim=(0, top10["count"].max() * 1.25))
rep.figure(fig, "uc2_2_top10_categories")
rep.insight(f"Theft ({top10['percent'].iloc[0]}%) and Battery ({top10['percent'].iloc[1]}%) together are "
            f"{top10['percent'].iloc[:2].sum():.1f}% of all crimes; the top 10 categories cover "
            f"{top10['percent'].sum():.1f}%.")

# -----------------------------------------------------------------------------
# 3. Arrests and crime outcomes
# -----------------------------------------------------------------------------
rep.section("3", "Arrests and crime outcomes", "What percentage of crimes result in arrest?")
arrest_rate = df["arrest"].mean() * 100
print(f"arrest_rate = df['arrest'].mean() * 100 = {arrest_rate:.2f}%   "
      f"({df['arrest'].sum()} arrests / {len(df)} crimes)\n")
by_type = (df.groupby("primary_type")["arrest"].agg(crimes="size", arrest_rate="mean")
             .assign(arrest_rate=lambda d: (d["arrest_rate"] * 100).round(2))
             .query("crimes >= 10").sort_values("arrest_rate", ascending=False))
print("Arrest rate by category (categories with >= 10 crimes):")
print(by_type.to_string())
fig, ax = plt.subplots(figsize=(10, 5.5))
ax.barh(by_type.index[::-1].str.title(), by_type["arrest_rate"][::-1], color="#548235")
ax.axvline(arrest_rate, color="#c00000", ls="--", label=f"overall {arrest_rate:.1f}%")
ax.set(title="Arrest rate by crime category (>= 10 crimes)", xlabel="Arrest rate (%)")
ax.legend()
rep.figure(fig, "uc2_3_arrest_rate_by_category")
rep.insight(f"{arrest_rate:.1f}% of crimes result in an arrest. Narcotics (100%) and Criminal Trespass (88%) "
            "are almost always arrests because police discover them in the act; Theft (9.5%) and Motor "
            "Vehicle Theft (0%) are reported after the fact and rarely end in arrest.")

# -----------------------------------------------------------------------------
# 4. Heatmap
# -----------------------------------------------------------------------------
rep.section("4", "Heatmap of crime by Month and Day of Week",
            "Use Seaborn heatmap of crime frequency pivoted by Month vs DayOfWeek.")
pivot = (df.pivot_table(index="month", columns="day_of_week", values="case_number", aggfunc="count", fill_value=0)
           .reindex(index=range(1, 13), columns=DAY_ORDER, fill_value=0).astype(int))
pivot.index = MONTHS
print("pivot = df.pivot_table(index='month', columns='day_of_week', values='case_number', aggfunc='count')\n")
print(pivot.to_string())
fig, ax = plt.subplots(figsize=(10, 7))
sns.heatmap(pivot, annot=True, fmt="d", cmap="YlOrRd", linewidths=.5, ax=ax, cbar_kws={"label": "Crimes"})
ax.set(title="Crime frequency: Month vs Day of Week", xlabel="", ylabel="")
rep.figure(fig, "uc2_4_heatmap_month_day")
cell = pivot.stack().idxmax()
rep.insight(f"The busiest cell is {cell[0]} / {cell[1]} ({pivot.stack().max()} crimes = "
            f"{pivot.stack().max() / pivot.values.sum() * 100:.0f}% of all). This is 4 May 2016, the date of "
            "the extract, so the heatmap reflects when the data was pulled rather than a weekly pattern.")

# -----------------------------------------------------------------------------
# 5. Top community areas
# -----------------------------------------------------------------------------
rep.section("5", "Top community areas", "List top 10 community areas with highest crime counts. Plot on a bar chart.")
top_areas = (df.groupby(["community_code", "community_name"]).size().sort_values(ascending=False)
               .head(10).reset_index(name="crimes"))
print(top_areas.to_string(index=False))
fig, ax = plt.subplots(figsize=(10, 5.5))
bars = ax.barh(top_areas["community_name"][::-1], top_areas["crimes"][::-1], color="#c55a11")
ax.bar_label(bars, padding=2)
ax.set(title="Top 10 community areas by crime count", xlabel="Number of crimes")
rep.figure(fig, "uc2_5_top10_communities")
rep.insight(f"{top_areas.iloc[0]['community_name']} ({top_areas.iloc[0]['crimes']}) leads by a wide margin, "
            f"followed by {top_areas.iloc[1]['community_name']} and {top_areas.iloc[2]['community_name']} "
            f"({top_areas.iloc[1]['crimes']} each).")

# -----------------------------------------------------------------------------
# Questions
# -----------------------------------------------------------------------------
rep.section("Q1", "Which crime category is most frequent?", "Which crime category is most frequent?")
print(f"cat.index[0] = {cat.index[0]}  ->  {cat['count'].iloc[0]} crimes ({cat['percent'].iloc[0]}%)")
rep.insight(f"{cat.index[0].title()} is the most frequent category with {cat['count'].iloc[0]} crimes "
            f"({cat['percent'].iloc[0]}%).")

rep.section("Q2", "Is the arrest rate consistent across different years?",
            "Is the arrest rate consistent across different years?")
ay = df.groupby("year")["arrest"].agg(crimes="size", arrests="sum", rate="mean")
ay["rate"] = (ay["rate"] * 100).round(2)
print(ay.to_string())
fig, ax = plt.subplots()
ax.plot(ay.index.astype(str), ay["rate"], marker="o", lw=2.5, color="#548235")
for x, (n, r) in zip(ay.index.astype(str), ay[["crimes", "rate"]].values):
    ax.annotate(f"n={int(n)}", (x, r), textcoords="offset points", xytext=(0, 8), ha="center")
ax.set(title="Arrest rate per year (n = number of crimes)", ylabel="Arrest rate (%)", ylim=(0, 115))
rep.figure(fig, "uc2_q2_arrest_rate_per_year")
rep.insight("Consistency cannot be judged: only 2016 (490 crimes, 24.3%) has enough data. 2012–2015 have "
            "1–4 crimes each, so their rates (0–100%) are driven by chance, not by policing changes.")

rep.section("Q3", "Which month has the highest crime frequency?", "Which month has the highest crime frequency?")
monthly = df.groupby("month").size().reindex(range(1, 13), fill_value=0)
monthly.index = MONTHS
print(monthly.to_frame("crimes").T.to_string())
fig, ax = plt.subplots()
bars = ax.bar(monthly.index, monthly.values, color="#2e75b6")
bars[int(np.argmax(monthly.values))].set_color("#c00000")
ax.bar_label(bars, padding=2)
ax.set(title="Crimes by month", ylabel="Number of crimes")
rep.figure(fig, "uc2_q3_crimes_by_month")
rep.insight(f"{monthly.idxmax()} has the highest frequency ({monthly.max()} crimes, "
            f"{monthly.max() / monthly.sum() * 100:.1f}%), because the extract was taken in early May 2016; "
            "it does not show real seasonality.")

rep.save()
