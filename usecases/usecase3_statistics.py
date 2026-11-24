"""
Use Case 3 — Statistical Insights & Pattern Detection
Objective: use numerical and visual analysis to derive deeper insights.

Run from the project folder:   python usecases/usecase3_statistics.py
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from common import Report, load_crimes
from backend.database import engine

rep = Report("uc3", "Use Case 3 — Statistical Insights & Pattern Detection")
df = load_crimes()

# -----------------------------------------------------------------------------
# 1. Crime intensity by time
# -----------------------------------------------------------------------------
rep.section("1", "Crime intensity by time (hourly distribution)",
            "Use Pandas groupby to get the hourly distribution and draw a line plot of crimes per hour of day.")
df["hour"] = df["date"].dt.hour
crimes_by_hour = df.groupby("hour").size().reindex(range(24), fill_value=0)
print("df['hour'] = df['date'].dt.hour\ncrimes_by_hour = df.groupby('hour').size()\n")
print(crimes_by_hour.to_frame("crimes").T.to_string())
has_time = (df["date"].dt.time != pd.Timestamp(0).time()).any()
print(f"\nDoes the source contain a time of day? {has_time}")
fig, ax = plt.subplots()
ax.plot(crimes_by_hour.index, crimes_by_hour.values, marker="o", lw=2.5, color="#7030a0")
ax.fill_between(crimes_by_hour.index, crimes_by_hour.values, alpha=.12, color="#7030a0")
ax.set(title="Crimes per hour of day" + ("" if has_time else " (source has no times -> all at 00:00)"),
       xlabel="Hour of day", ylabel="Crimes", xticks=range(24))
rep.figure(fig, "uc3_1_crimes_per_hour")
rep.insight("All 498 crimes fall at hour 0 because the source dates have no time (e.g. 5/3/2016). The midnight "
            "spike is a data limitation, not a pattern; an hourly analysis needs timestamped data.")

# -----------------------------------------------------------------------------
# 2. Community area clusters using NumPy
# -----------------------------------------------------------------------------
rep.section("2.1", "Mean crime per community area (NumPy)",
            "Use NumPy functions to compute mean crime per community area.")
areas = pd.read_sql("SELECT community_code, community_name, population FROM city_community", engine)
areas["community_name"] = areas["community_name"].str.title()
areas["crimes"] = areas["community_code"].map(df.groupby("community_code").size()).fillna(0).astype(int)
arr = areas["crimes"].to_numpy()
stats = {"areas": arr.size, "np.mean": np.mean(arr), "np.median": np.median(arr), "np.std": np.std(arr, ddof=1),
         "np.min": np.min(arr), "np.max": np.max(arr), "Q1 (np.percentile 25)": np.percentile(arr, 25),
         "Q3 (np.percentile 75)": np.percentile(arr, 75)}
print("arr = crimes per community area (all 77 areas, 0 if none)\n")
for k, v in stats.items():
    print(f"  {k:<24} {v:,.2f}")
rep.insight(f"On average a community area has {np.mean(arr):.2f} crimes (median {np.median(arr):.0f}). "
            "Mean > median means the distribution is right-skewed: a few areas carry much more crime.")

rep.section("2.2", "Outlier community areas — box plot + IQR method",
            "Identify which areas are extreme outliers in terms of crime counts (box plot, then IQR method to list them).")
q1, q3 = np.percentile(arr, [25, 75])
iqr = q3 - q1
lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
print(f"Q1 = {q1}   Q3 = {q3}   IQR = Q3 - Q1 = {iqr}")
print(f"Lower fence = Q1 - 1.5*IQR = {lower}   Upper fence = Q3 + 1.5*IQR = {upper}\n")
outliers = areas[(arr < lower) | (arr > upper)].sort_values("crimes", ascending=False)
outliers["times_median"] = (outliers["crimes"] / np.median(arr)).round(1)
print(outliers.to_string(index=False))
fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 5), gridspec_kw={"width_ratios": [1, 2]})
sns.boxplot(y=arr, ax=a1, color="#9dc3e6", width=.4, flierprops=dict(marker="o", markerfacecolor="#c00000", markersize=8))
a1.axhline(upper, color="#c00000", ls="--")
a1.set(title="Box plot of crimes per area", ylabel="Crimes")
sns.histplot(arr, bins=range(0, int(arr.max()) + 3, 2), ax=a2, color="#2e75b6")
a2.axvline(upper, color="#c00000", ls="--", label=f"upper fence {upper}")
a2.set(title="Distribution of crimes per community area", xlabel="Crimes", ylabel="Areas")
a2.legend()
rep.figure(fig, "uc3_2_community_outliers")
rep.insight(f"{len(outliers)} areas exceed the upper fence of {upper}: "
            + ", ".join(f"{r.community_name} ({r.crimes})" for r in outliers.itertuples())
            + ". Austin has 6.8x the median area. No low outliers are possible because the lower fence is negative.")

# -----------------------------------------------------------------------------
# 3. Crime cross-correlation
# -----------------------------------------------------------------------------
rep.section("3", "Crime cross-correlation",
            "Use Pandas .corr() on numeric features (Year, Month, Arrest, etc.) and visualise the matrix with a heatmap.")
num = pd.DataFrame({"year": df["year"], "month": df["month"], "hour": df["hour"],
                    "day_of_week": df["date"].dt.day_of_week, "arrest": df["arrest"].astype(int),
                    "domestic": df["domestic"].astype(int), "district_code": df["district_code"],
                    "ward_no": df["ward_no"], "community_code": df["community_code"],
                    "latitude": df["latitude"], "longitude": df["longitude"]}).astype(float)
constant = [c for c in num if num[c].nunique() <= 1]
print(f"Constant columns dropped (correlation undefined): {constant}\n")
corr = num.drop(columns=constant).corr()
print(corr.round(2).to_string())
fig, ax = plt.subplots(figsize=(10, 8))
sns.heatmap(corr, mask=np.triu(np.ones_like(corr, dtype=bool), k=1), annot=True, fmt=".2f", cmap="coolwarm",
            vmin=-1, vmax=1, center=0, linewidths=.5, square=True, ax=ax)
ax.set_title("Correlation matrix of numeric features")
rep.figure(fig, "uc3_3_correlation_heatmap")
pairs = corr.where(np.triu(np.ones(corr.shape, dtype=bool), k=1)).stack()
top = pairs.reindex(pairs.abs().sort_values(ascending=False).index).head(4)
print("\nStrongest pairs:\n" + top.round(3).to_string())
rep.insight(f"The strongest correlations (community vs latitude {corr.loc['community_code', 'latitude']:.2f}, "
            f"district vs ward {corr.loc['district_code', 'ward_no']:.2f}) only show that location codes describe "
            f"the same place. Crime outcomes barely correlate with anything: arrest vs domestic "
            f"{corr.loc['arrest', 'domestic']:.2f}, arrest vs year {corr.loc['arrest', 'year']:.2f}.")

rep.save()
