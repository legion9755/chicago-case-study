# Chicago Crime Analytics — Case Study Implementation

**Stack:** Flask REST backend · Streamlit frontend · SQLite with SQLAlchemy 2

| Requirement | Where |
|---|---|
| Data pipeline that loads the data into the dimension tables | `pipeline/etl.py` (also driven step by step by Use Case 1) |
| CRUD (GET, POST, PUT, PATCH, DELETE) for any dimension table | `backend/crud.py`, the Streamlit **Data admin** page |
| Dashboard with exportable images and insights | `backend/analytics.py`, the Streamlit **Insights** page |
| Automated tests (API, CRUD, frontend logic, both pages) | `tests/` |
| `.py` file for every use case | `usecases/usecase1_load_clean.py` … `usecase4_reporting.py` |
| Database file | `db/chicago_crime.db` |
| Word document (app screenshots, questions, outputs, insights) | `docs/Chicago_Crime_Case_Study_Report.docx` (its app screenshots show the earlier single-page interface) |

Source: https://github.com/legion9755/chicago-case-study

---

## 1. Project structure

```
chicago-case-study/
├── data/                       6 source CSV files
├── db/chicago_crime.db         SQLite database (created by the pipeline)
├── pipeline/etl.py             Extract → Transform → Load
├── backend/
│   ├── database.py             SQLAlchemy 2 engine, session, Base (foreign keys ON)
│   ├── models.py               ORM models: 5 dimension tables + chicago_crime fact + view SQL
│   ├── crud.py                 generic REST CRUD for every dimension table
│   ├── analytics.py            dashboard endpoints (data + computed insight)
│   └── app.py                  Flask app factory, JSON error handling
├── run_backend.py              starts the Flask API (port 5000)
├── frontend/                   Streamlit UI (port 8501)
│   ├── streamlit_app.py        entrypoint: theme, top navigation, API status badge
│   ├── app_pages/              insights.py (dashboard, start page) · admin.py (CRUD)
│   └── lib/                    api.py (REST client) · filters.py (URL-synced filters) · charts.py (ECharts
│                               chart registry) · cards.py (chart card) · export.py (PNG/ZIP via matplotlib)
│                               · records.py (CRUD forms, API call log, error messages)
├── usecases/
│   ├── usecase1_load_clean.py  UC1 – load, clean, insert into the DB (runs the pipeline)
│   ├── usecase2_eda.py         UC2 – exploratory analysis and charts
│   ├── usecase3_statistics.py  UC3 – hourly pattern, NumPy stats, IQR outliers, correlation
│   ├── usecase4_reporting.py   UC4 – summary tables, SQL queries, views, pd.read_sql, charts
│   ├── common.py               shared helpers (records output for the report)
│   └── outputs/                charts (.png) and recorded outputs (.json)
├── tests/                      unittest suite: API + CRUD, frontend logic + exports, both pages (AppTest)
├── docs/                       Word report
├── .streamlit/config.toml      Streamlit settings: light/dark brand theme, telemetry off
├── .gitignore                  keeps venv/, caches and local secrets out of git
└── requirements.txt            Python ≥ 3.10; Streamlit ≥ 1.67
```

## 2. Setup (Windows)

```powershell
git clone https://github.com/legion9755/chicago-case-study.git
cd chicago-case-study
python -m venv venv
venv\Scripts\activate              # PowerShell: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 3. Run

```powershell
# build the database and run the analyses (Use Case 1 must run first)
python usecases\usecase1_load_clean.py
python usecases\usecase2_eda.py
python usecases\usecase3_statistics.py
python usecases\usecase4_reporting.py

# terminal 1 – backend
python run_backend.py                          # http://127.0.0.1:5000/api

# terminal 2 – frontend (venv active here too)
streamlit run frontend\streamlit_app.py        # opens http://localhost:8501
```

`python -m pipeline.etl` rebuilds the database on its own (without the Use Case 1 printout).
Re-running the pipeline always recreates a clean database, so you can run the scripts in any
order afterwards.

**After changing code:** restart the backend when anything in `backend/` changed, and restart
Streamlit when anything in `frontend/lib/` changed (Streamlit reloads page files by itself, but
not the modules they import).

### Tests

```powershell
python -m unittest discover -s tests -v        # ~15 s, no servers needed
```

The suite copies `db/chicago_crime.db` to a temporary folder and starts its own backend on a
free port, so it never changes the real database and can run while the app is running.

| File | Covers |
|---|---|
| `tests/test_backend.py` | every analytics endpoint, filters (incl. bad values → 400), no-match → 404, CRUD round trip (POST / duplicate 409 / PATCH / PUT / DELETE), validation errors, protected delete (409) |
| `tests/test_logic.py` | error-message helpers, PATCH change detection, every chart builder, PNG export, ZIP of all 13 charts |
| `tests/test_pages.py` | both pages render without errors; filters change the KPIs; empty state; Insights sections; Data admin table switch |

Clicking table rows and buttons inside dialogs can't be automated with AppTest;
check those by hand in a browser. AppTest prints "missing ScriptRunContext … bare mode" lines;
they are harmless.

## 4. REST API

Resources: `communities` (city_community), `districts`, `wards`, `beats`, `iucr`.

| Method | URL | Purpose | Status codes |
|---|---|---|---|
| GET | `/api/resources` | tables, columns, types, row counts | 200 |
| GET | `/api/<resource>?q=&limit=&offset=` | list / search | 200 |
| GET | `/api/<resource>/<id>` | read one | 200, 404 |
| POST | `/api/<resource>` | create | 201, 400, 409 |
| PUT | `/api/<resource>/<id>` | replace the whole record | 200, 400, 404 |
| PATCH | `/api/<resource>/<id>` | change some fields | 200, 400, 404 |
| DELETE | `/api/<resource>/<id>` | delete (409 if crimes still reference it) | 200, 404, 409 |
| GET | `/api/analytics/<name>` | dashboard data + insight (filters, summary, crimes-by-year, categories, arrest-rate-by-category, arrest-rate-by-year, heatmap, crimes-by-month, crimes-by-hour, top-communities, community-outliers, correlation) | 200, 404 |
| GET | `/api/analytics/views/<view>` | `vw_crime_yearly`, `vw_crime_by_category` | 200, 404 |

Analytics filters: `?year_from=2016&year_to=2016&crime_type=THEFT&crime_type=BATTERY&community=25&arrest=true&domestic=false`
(`arrest` / `domestic` accept `true` or `false`; anything else answers 400.)

Test from PowerShell:
```powershell
Invoke-RestMethod http://127.0.0.1:5000/api/communities/25
Invoke-RestMethod -Method Post http://127.0.0.1:5000/api/communities -ContentType "application/json" -Body '{"community_code": 78, "community_name": "Test"}'
Invoke-RestMethod -Method Patch http://127.0.0.1:5000/api/communities/78 -ContentType "application/json" -Body '{"population": 1000}'
Invoke-RestMethod -Method Delete http://127.0.0.1:5000/api/communities/78
```

## 5. Using the app

Pages are in the top navigation bar. Light/dark mode is in the ⋮ menu → Settings.

The sidebar filters (year, crime type, community area, arrest made, domestic) apply to
Insights and are kept in the URL.

* **Insights** (start page): use the sidebar filters, and pick a section
  (Exploratory analysis · Statistical insights · SQL views) above the charts. Filters and the
  section are saved in the URL, so a view can be shared as a link. Charts are interactive
  (hover for values) and each shows an insight computed by the backend.
  * **PNG** on a chart saves it with its insight inside the image.
  * **⋮ → View data** shows the numbers behind the chart (downloadable as CSV);
    **⋮ → API request** shows the exact REST call.
  * **Export all charts** saves all 13 charts plus `insights.txt` as a ZIP, using the current filters.
* **Data admin:** pick a table above the grid; search filters as you type (`GET /api/<table>?q=`).
  * Select a row to open the record on the right (`GET /api/<table>/<id>`).
  * **New record** opens a form (`POST`). After saving, the new record is selected.
  * **Edit** opens a side panel: *Update changed fields* sends only what you changed (`PATCH`);
    *Replace all fields* sends every field, and empty fields become NULL (`PUT`).
  * **Delete** asks for confirmation (`DELETE`). Records still used by crimes are refused by
    the API (409) and the reason is shown.
  * **Developer view** (top right) shows the raw HTTP request and response of the last action.

## 6. Notes on the data

* The crime file's last two lines are truncated (unclosed quote). The pipeline repairs them.
* Dates have no time of day, so the hourly analysis can't show a pattern (everything is 00:00).
* 89% of the 498 crimes fall on 3–4 May 2016. The file is a snapshot of recently updated
  records, so year and month trends reflect the extract date, not real seasonality. Insights
  are computed from the data and say so automatically.
* Lookup quirks handled: `iucr_codes.csv.csv` name and header spaces, `ward` → `ward_no`,
  8 duplicate wards (newest record kept), 2 duplicate beats.

## 7. Troubleshooting

| Problem | Fix |
|---|---|
| Streamlit says it cannot reach the Flask API / sidebar badge says **API offline** | start `python run_backend.py` in another terminal (venv active) |
| A page says *"The backend … doesn't have this endpoint yet"* | the backend is running older code: Ctrl+C it, run `python run_backend.py` again, reload the page |
| `ImportError: cannot import name …` from `lib.…`, or a change doesn't show up | Streamlit is running older `frontend/lib/` code: Ctrl+C it and run `streamlit run frontend\streamlit_app.py` again |
| `Database not found` | run `python usecases\usecase1_load_clean.py` first |
| `ModuleNotFoundError` | activate the venv and `pip install -r requirements.txt` |
| Port 5000 busy | PowerShell: `$env:API_PORT="5001"` before `run_backend.py`, and `$env:API_URL="http://127.0.0.1:5001/api"` before Streamlit (cmd: `set API_PORT=5001` / `set API_URL=…`) |
