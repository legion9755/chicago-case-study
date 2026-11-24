"""
usecases/common.py — shared helpers for the use-case scripts.

* puts the project root on sys.path so `backend` / `pipeline` can be imported
* Report: prints each section to the console AND records its output, figures and insight
  into usecases/outputs/ucN_report.json (used to build the Word document)
* load_crimes(): the cleaned fact table joined with its lookups, read from SQLite

Every script accepts an optional --step to print a single step, e.g.
    python usecases/usecase1_load_clean.py --step 2.2
The whole script still runs (later steps depend on earlier ones) and the report JSON is still
written in full; only the console output is limited to the chosen step(s). Without --step the
script prints everything, as before.
"""
import argparse
import io
import json
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import matplotlib                                     # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt                       # noqa: E402
import pandas as pd                                   # noqa: E402
import seaborn as sns                                 # noqa: E402
from sqlalchemy import text                           # noqa: E402

from backend.database import DB_PATH, engine          # noqa: E402

OUT_DIR = ROOT / "usecases" / "outputs"
OUT_DIR.mkdir(parents=True, exist_ok=True)
DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 30)
pd.set_option("display.max_colwidth", 40)
sns.set_theme(style="whitegrid")
plt.rcParams.update({"figure.figsize": (10, 5), "figure.dpi": 110, "axes.titleweight": "bold",
                     "axes.spines.top": False, "axes.spines.right": False})


class _Tee(io.TextIOBase):
    def __init__(self, console, report):
        self.console, self.report = console, report

    def write(self, s):
        if self.report.visible():
            self.console.write(s)
        if self.report.current is not None:
            self.report.current["output"] += s
        return len(s)

    def flush(self):
        self.console.flush()


class Report:
    """Use as:  rep = Report("uc2", "Use Case 2 — ...")  then rep.section(...), rep.figure(...),
    rep.insight(...), and rep.save() at the end."""

    def __init__(self, key, title):
        parser = argparse.ArgumentParser(description=title)
        parser.add_argument("--step", action="append", metavar="ID",
                            help="print only this step (e.g. 2.2 or Q1); can be given more than once")
        self.steps = parser.parse_args().step
        self.key, self.title, self.sections, self.current = key, title, [], None
        sys.stdout = _Tee(sys.__stdout__, self)
        sys.__stdout__.write("=" * 100 + f"\n{title}\n" + "=" * 100 + "\n")

    def visible(self):
        """Show console output now? Always without --step; otherwise only inside a chosen step."""
        return self.steps is None or (self.current is not None and self.current["id"] in self.steps)

    def section(self, sid, title, question=None):
        self.current = {"id": sid, "title": title, "question": question or title,
                        "output": "", "figures": [], "insight": None}
        self.sections.append(self.current)
        if self.visible():
            sys.__stdout__.write("\n" + "-" * 100 + f"\n[{sid}] {title}\n" + "-" * 100 + "\n")

    def figure(self, fig, name):
        path = OUT_DIR / f"{name}.png"
        fig.savefig(path, bbox_inches="tight", dpi=130, facecolor="white")
        plt.close(fig)
        self.current["figures"].append(str(path.relative_to(ROOT)))
        print(f"(chart saved: {path.relative_to(ROOT)})")

    def insight(self, text_):
        self.current["insight"] = text_
        # wrapped at word boundaries so a normal console window never breaks a word
        print("\n" + textwrap.fill(text_, width=130, initial_indent="INSIGHT: ", subsequent_indent=" " * 9))

    def save(self):
        sys.stdout = sys.__stdout__
        for s in self.sections:
            s["output"] = s["output"].strip("\n")
        path = OUT_DIR / f"{self.key}_report.json"
        path.write_text(json.dumps({"key": self.key, "title": self.title, "sections": self.sections},
                                   indent=2, ensure_ascii=False))
        if self.steps is None:
            print(f"\nSaved {len(self.sections)} sections to {path.relative_to(ROOT)}")
        elif unknown := sorted(set(self.steps) - {s["id"] for s in self.sections}):
            sys.exit(f"Unknown step(s) {unknown}. Steps: {[s['id'] for s in self.sections]}")


def load_crimes():
    """Fact table joined with crime type and community name, from the SQLite database."""
    if not DB_PATH.exists():
        sys.exit("Database not found. Run usecases/usecase1_load_clean.py first.")
    sql = """SELECT c.*, i.primary_type, i.description, cc.community_name, cc.population
             FROM chicago_crime c
             JOIN iucr i ON i.iucr_code = c.iucr_code
             LEFT JOIN city_community cc ON cc.community_code = c.community_code"""
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    df["date"] = pd.to_datetime(df["date"], format="ISO8601")
    df["arrest"] = df["arrest"].astype(bool)
    df["domestic"] = df["domestic"].astype(bool)
    df["community_name"] = df["community_name"].str.title()
    return df
