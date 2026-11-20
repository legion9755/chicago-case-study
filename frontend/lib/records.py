"""
lib/records.py — helpers for the Data admin page: typed record forms, API calls that are recorded
for the developer view, and plain-language error messages.
"""
import json
from typing import Any

import streamlit as st

from lib.api import API_URL, api, clear_cache

LAST_CALL = "admin_last_call"


# =============================================================================
# API calls
# =============================================================================
def call(method: str, path: str, body: Any = None) -> tuple[int, Any]:
    """Call the API and remember the request/response for the developer view.

    After a successful write the analytics cache is cleared: names and numbers may have changed.
    """
    status, resp = api(method, path, body=body)
    st.session_state[LAST_CALL] = {"method": method, "url": f"{API_URL}{path}", "body": body,
                                   "status": status, "response": resp}
    if 200 <= status < 300 and method != "GET":
        clear_cache()
    return status, resp


def _friendly(msg: str) -> str:
    """Python conversion errors from the API's validator, in plain words."""
    if msg.startswith("could not convert string to float") or msg.startswith("invalid literal"):
        return "must be a number"
    return msg


def explain(status: int, resp: Any) -> tuple[str, str]:
    """(title, message) describing a failed call in plain language."""
    detail = resp.get("detail") or resp.get("error") if isinstance(resp, dict) else resp
    if status == 0:
        return "API unreachable", str(detail)
    if status == 400 and isinstance(detail, dict) and "validation_errors" in detail:
        lines = [f"- **{field}** {_friendly(str(msg))}" for field, msg in detail["validation_errors"].items()]
        return "Please fix these fields", "\n".join(lines)
    if status == 409:
        return ("Record in use" if "referenced" in str(detail) else "Can't do that"), str(detail)
    if status == 404:
        return "Not found", f"{detail}. It may have been deleted already; close this dialog to refresh."
    return f"API error {status}", str(detail)


def show_call(call_info: dict[str, Any] | None, *, title: str = "Last API call") -> None:
    """The raw request and response of a call (developer view)."""
    if not call_info:
        return
    ok = 200 <= call_info["status"] < 300
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(f"**{title}**")
            st.badge(f"HTTP {call_info['status']}", color="green" if ok else "red",
                     icon=":material/check_circle:" if ok else ":material/error:")
        c1, c2 = st.columns(2)
        with c1:
            st.caption("Request")
            st.code(f"{call_info['method']} {call_info['url']}"
                    + (f"\n\n{json.dumps(call_info['body'], indent=2)}" if call_info["body"] else ""),
                    language="http", wrap_lines=True)
        with c2:
            st.caption("Response")
            st.code(json.dumps(call_info["response"], indent=2, default=str), language="json", wrap_lines=True)


# =============================================================================
# Forms
# =============================================================================
def _to_value(text: str, col_type: str) -> Any:
    """Blank -> None; Float columns -> float when the text is a number (otherwise the text is sent
    as-is and the API answers 400 with a field-level message)."""
    text = text.strip()
    if text == "":
        return None
    if col_type == "Float":
        try:
            return float(text.replace(",", ""))
        except ValueError:
            return text
    return text


def record_form(columns: list[dict], current: dict[str, Any], key_prefix: str, *,
                include_pk: bool) -> dict[str, Any]:
    """One input per column, typed by the column type, in a two-column layout.

    Required (NOT NULL) fields are marked *. Blank means NULL. Returns {column: value}.
    """
    values: dict[str, Any] = {}
    shown = [c for c in columns if include_pk or not c["primary_key"]]
    cols = st.columns(2)
    for i, c in enumerate(shown):
        name, ctype, cur = c["name"], c["type"], current.get(c["name"])
        label = name + (" :material/key:" if c["primary_key"] else "") + ("" if c["nullable"] else " *")
        hint = ctype + (f", max {c['max_length']} characters" if c.get("max_length") else "")
        hint += "" if c["nullable"] else " · required"
        key = f"{key_prefix}_{name}"
        with cols[i % 2]:
            if ctype == "Integer":
                values[name] = st.number_input(
                    label, value=None if cur is None else int(cur), step=1, format="%d", key=key, help=hint,
                    placeholder="empty", required=not c["nullable"])
            else:
                values[name] = _to_value(st.text_input(
                    label, "" if cur is None else str(cur), max_chars=c.get("max_length"), key=key, help=hint,
                    placeholder="empty", required=not c["nullable"]), ctype)
    return values


def changed_fields(values: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Only the fields whose value differs from the stored record (the PATCH body)."""
    return {k: v for k, v in values.items() if v != current.get(k)}
