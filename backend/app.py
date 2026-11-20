"""
backend/app.py — Flask application factory.

Start the API (from the project folder, venv active):
    python run_backend.py          ->  http://127.0.0.1:5000/api/health
"""
from flask import Flask, jsonify
from sqlalchemy import inspect
from werkzeug.exceptions import HTTPException

from backend.analytics import analytics_bp
from backend.crud import crud_bp
from backend.database import DB_PATH, engine
from backend.models import DIMENSIONS


def create_app():
    app = Flask(__name__)
    app.json.sort_keys = False                     # keep column order in JSON responses
    app.register_blueprint(crud_bp)
    app.register_blueprint(analytics_bp)

    @app.get("/")
    @app.get("/api")
    def index():
        return jsonify({
            "name": "Chicago Crime API",
            "endpoints": {
                "health": "GET /api/health",
                "resources (metadata)": "GET /api/resources",
                "CRUD": {r: f"GET|POST /api/{r}   GET|PUT|PATCH|DELETE /api/{r}/<id>" for r in DIMENSIONS},
                "analytics": "GET /api/analytics/<summary|crimes-by-year|categories|arrest-rate-by-category|"
                             "arrest-rate-by-year|heatmap|crimes-by-month|crimes-by-hour|top-communities|"
                             "community-outliers|correlation|incidents|communities|data-quality>",
                "filters": "?year_from=&year_to=&crime_type=&community=&arrest=true|false&domestic=true|false",
                "views": "GET /api/analytics/views/<vw_crime_yearly|vw_crime_by_category>",
            },
        })

    @app.get("/api/health")
    def health():
        tables = inspect(engine).get_table_names()
        ok = "chicago_crime" in tables
        return jsonify({"status": "ok" if ok else "database not loaded", "database": str(DB_PATH),
                        "tables": tables}), (200 if ok else 503)

    @app.errorhandler(HTTPException)
    def http_error(err):
        """Return every error as JSON instead of an HTML page."""
        return jsonify({"error": err.name, "status": err.code, "detail": err.description}), err.code

    return app
