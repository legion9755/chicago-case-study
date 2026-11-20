"""
lib/api.py — the only way the frontend talks to the Flask REST API.

The frontend never touches the database: every number and every change goes through here.
"""
import json
import os
from typing import Any

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://127.0.0.1:5000/api").rstrip("/")


def api(method: str, path: str, params: dict | None = None, body: Any = None,
        timeout: float = 30) -> tuple[int, Any]:
    """Call the Flask API. Returns (status_code, json_body). Never raises.

    status_code is 0 when the API can't be reached.
    """
    url = f"{API_URL}{path}"
    try:
        r = requests.request(method, url, params=params, json=body, timeout=timeout)
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, {"raw": r.text[:500]}
    except requests.ConnectionError:
        return 0, {"error": f"Cannot reach the Flask API at {API_URL}. Start it with:  python run_backend.py"}
    except requests.Timeout:
        return 0, {"error": f"The Flask API at {API_URL} did not answer within {timeout:g} seconds."}


@st.cache_data(ttl=120, show_spinner=False)
def _get_cached(path: str, params_json: str) -> tuple[int, Any]:
    return api("GET", path, params=json.loads(params_json))


def get(path: str, params: dict | None = None) -> tuple[int, Any]:
    """Cached GET (2 minutes). Use for read-only analytics data.

    Only successful answers (and "no crimes match these filters") stay cached. Any other error is
    evicted and fetched again, so a restarted or fixed backend is picked up on the next load
    instead of the error being replayed for 2 minutes.
    """
    key = json.dumps(params or {}, sort_keys=True)
    status, body = _get_cached(path, key)
    if status == 200 or is_no_match(status, body):
        return status, body
    _get_cached.clear(path, key)
    return api("GET", path, params=params or {})


def health() -> tuple[int, Any]:
    """Backend health. Not cached, so the sidebar badge is never stale; the short timeout
    keeps a hung backend from blocking the page (a stopped one is refused instantly)."""
    return api("GET", "/health", timeout=3)


def clear_cache() -> None:
    """Call after a successful write: dashboard numbers and names may have changed."""
    st.cache_data.clear()


def is_no_match(status: int, body: Any) -> bool:
    """True when the API answered 404 because no crimes match the filters — as opposed to a 404
    for an endpoint this backend doesn't have (e.g. a backend started before an update)."""
    return status == 404 and isinstance(body, dict) and "match" in str(body.get("detail", ""))


def error_message(status: int, body: Any) -> str:
    if status == 404 and not is_no_match(status, body):
        return (f"The backend at {API_URL} doesn't have this endpoint yet. It is probably still running an "
                "older version: restart it (Ctrl+C, then  python run_backend.py)  and reload this page.")
    if isinstance(body, dict):
        detail = body.get("detail") or body.get("error") or body
    else:
        detail = body
    return f"API error {status}: {detail}" if status else str(detail)


def error_box(status: int, body: Any) -> None:
    st.error(error_message(status, body), icon=":material/error:")
