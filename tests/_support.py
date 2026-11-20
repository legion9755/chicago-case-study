"""
tests/_support.py — shared setup, imported first by every test module.

* Copies db/chicago_crime.db to a temporary folder and points the backend at the copy
  (CRIME_DB_PATH), so tests — including the CRUD tests — never touch the real database.
* Starts the Flask backend on a free local port in a background thread and points the frontend
  at it (API_URL), so the page tests need no servers to be running.
"""
import atexit
import logging
import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
REAL_DB = ROOT / "db" / "chicago_crime.db"

if not REAL_DB.exists():
    raise SystemExit(f"{REAL_DB} not found — build it first:  python usecases\\usecase1_load_clean.py")

_tmp = Path(tempfile.mkdtemp(prefix="chicago_tests_"))
DB_COPY = _tmp / "chicago_crime.db"
shutil.copy(REAL_DB, DB_COPY)

# Must be set before anything imports backend.database or lib.api.
# (AppTest prints harmless "missing ScriptRunContext ... bare mode" lines; they can be ignored.)
os.environ["CRIME_DB_PATH"] = str(DB_COPY)
for path in (str(ROOT), str(FRONTEND)):
    if path not in sys.path:
        sys.path.insert(0, path)

from werkzeug.serving import make_server  # noqa: E402

from backend.app import create_app  # noqa: E402
from backend.database import engine  # noqa: E402

# Keep test output readable: no per-request access log.
logging.getLogger("werkzeug").setLevel(logging.ERROR)

app = create_app()
_server = make_server("127.0.0.1", 0, app, threaded=True)
threading.Thread(target=_server.serve_forever, daemon=True).start()
API_URL = f"http://127.0.0.1:{_server.server_port}/api"
os.environ["API_URL"] = API_URL


@atexit.register
def _cleanup() -> None:
    """Stop the backend and close its database connections (Windows keeps an open SQLite file
    locked), then delete the temporary copy."""
    _server.shutdown()
    engine.dispose()
    shutil.rmtree(_tmp, ignore_errors=True)
