"""
Data admin — browse and edit the dimension tables through the REST API.

  list / search   GET    /api/<table>?q=           the table
  read one        GET    /api/<table>/<id>         select a row → record panel
  create          POST   /api/<table>              "New record"
  update          PATCH  /api/<table>/<id>         "Edit" → only the changed fields
  replace         PUT    /api/<table>/<id>         "Edit" → "Replace all fields"
  delete          DELETE /api/<table>/<id>         "Delete" → confirm (409 if crimes still use it)

The developer view shows the raw request and response of the last call.
"""
from typing import Any

import pandas as pd
import streamlit as st

from lib.api import API_URL, api, error_box
from lib.records import LAST_CALL, call, changed_fields, explain, record_form, show_call

TOAST, VERSION, FOCUS = "admin_toast", "admin_grid_version", "admin_focus"
MODE_PATCH, MODE_PUT = "Update changed fields", "Replace all fields"


def finish(message: str, focus: tuple[str, Any] | None = None) -> None:
    """After a successful write: queue a toast, rebuild the table (new key) with `focus`
    = (resource, id) selected — the record just created or edited — and close the dialog."""
    st.session_state[TOAST] = message
    st.session_state[VERSION] = st.session_state.get(VERSION, 0) + 1
    st.session_state[FOCUS] = focus
    st.rerun()


def show_failure(status: int, resp: Any) -> None:
    title, message = explain(status, resp)
    st.error(message, title=title, icon=":material/error:")
    if st.session_state.get("dev_view"):
        show_call(st.session_state.get(LAST_CALL), title="API call")


def plain(value: Any) -> Any:
    """numpy scalar → Python value (for URLs and JSON)."""
    return value.item() if hasattr(value, "item") else value


# =============================================================================
# Dialogs
# =============================================================================
@st.dialog("New record", position="right", width=560)
def create_dialog(meta: dict[str, Any]) -> None:
    res = meta["resource"]
    st.caption(f"Creates a row in **{meta['label']}** with `POST /api/{res}`. "
               "Fields marked * are required; leave a field empty for NULL.")
    with st.form(f"create_{res}", border=False):
        values = record_form(meta["columns"], {}, f"create_{res}", include_pk=True)
        submitted = st.form_submit_button("Create record", type="primary", icon=":material/add:", width="stretch")
    if submitted:
        body = {k: v for k, v in values.items() if v is not None}
        status, resp = call("POST", f"/{res}", body)
        if status == 201:
            new_id = resp["item"][meta["primary_key"]]
            finish(f"Created {meta['primary_key']} {new_id}", focus=(res, new_id))
        else:
            show_failure(status, resp)


@st.dialog("Edit record", position="right", width=560)
def edit_dialog(meta: dict[str, Any], record: dict[str, Any]) -> None:
    res, pk = meta["resource"], meta["primary_key"]
    rid = record[pk]
    st.markdown(f"**{meta['label']}** · {pk} `{rid}`")
    mode = st.segmented_control(
        "Save as", [MODE_PATCH, MODE_PUT], default=MODE_PATCH, required=True, key=f"edit_mode_{res}",
        help="Update sends only the fields you change (PATCH). Replace sends every field (PUT): "
             "empty fields become NULL.",
    )
    st.caption(f"`PATCH /api/{res}/{rid}` · only changed fields are sent." if mode == MODE_PATCH else
               f"`PUT /api/{res}/{rid}` · every field is sent; empty fields become NULL.")
    with st.form(f"edit_{res}_{rid}", border=False):
        values = record_form(meta["columns"], record, f"edit_{res}_{rid}", include_pk=False)
        submitted = st.form_submit_button("Save changes", type="primary", icon=":material/save:", width="stretch")
    if submitted:
        if mode == MODE_PATCH:
            body = changed_fields(values, record)
            if not body:
                st.info("Nothing changed yet. Edit a field, then save.", icon=":material/info:")
                return
            status, resp = call("PATCH", f"/{res}/{rid}", body)
        else:
            status, resp = call("PUT", f"/{res}/{rid}", values)
        if status == 200:
            n = len(resp.get("changed_fields", values))
            finish(f"Saved {pk} {rid}" + (f" · {n} field(s) changed" if mode == MODE_PATCH else " · record replaced"),
                   focus=(res, rid))
        else:
            show_failure(status, resp)


@st.dialog("Delete record?")
def delete_dialog(meta: dict[str, Any], record: dict[str, Any]) -> None:
    res, pk = meta["resource"], meta["primary_key"]
    rid = record[pk]
    name = next((record[c["name"]] for c in meta["columns"]
                 if not c["primary_key"] and c["type"] == "String" and record.get(c["name"])), None)
    st.markdown(f"This permanently deletes **{meta['label']}** {pk} `{rid}`" + (f" — **{name}**." if name else "."))
    st.caption(f"`DELETE /api/{res}/{rid}`. Records still used by crimes are protected and won't be deleted.")
    with st.container(horizontal=True):
        st.space("stretch")
        if st.button("Cancel", key="delete_cancel"):
            st.rerun()
        if st.button("Delete", type="primary", icon=":material/delete:", key="delete_confirm"):
            status, resp = call("DELETE", f"/{res}/{rid}")
            if status == 200:
                finish(f"Deleted {pk} {rid}")
            else:
                show_failure(status, resp)


# =============================================================================
# Page
# =============================================================================
if toast := st.session_state.pop(TOAST, None):
    st.toast(toast, icon=":material/check_circle:")

with st.container(horizontal=True, vertical_alignment="bottom"):
    with st.container(gap=None):
        st.title("Data admin", anchor=False)
        st.caption(f"Browse and edit the dimension tables · every action is a REST call to `{API_URL}`")
    st.space("stretch")
    dev_view = st.toggle("Developer view", key="dev_view", persist_state="session",
                         help="Show the raw HTTP request and response of the last action")

status, resources = api("GET", "/resources")
if status != 200:
    error_box(status, resources)
    st.stop()

by_label = {r["label"]: r for r in resources}
default_label = next((r["label"] for r in resources if r["resource"] == "communities"), resources[0]["label"])
choice = st.segmented_control("Table", list(by_label), default=default_label, required=True, key="table",
                              bind="query-params", label_visibility="collapsed")
meta = by_label.get(choice or "", by_label[default_label])
res, pk, columns = meta["resource"], meta["primary_key"], meta["columns"]

if dev_view:
    show_call(st.session_state.get(LAST_CALL))

# ---- toolbar ---------------------------------------------------------------
with st.container(horizontal=True, vertical_alignment="center"):
    q = st.text_input("Search", key=f"q_{res}", type="search", live="300ms", icon=":material/search:",
                      placeholder=f"Search {meta['label'].lower()} (any column)", label_visibility="collapsed",
                      width=380)
    st.space("stretch")
    if st.button("New record", type="primary", icon=":material/add:", key="new_record"):
        create_dialog(meta)

status, listing = api("GET", f"/{res}", params={"q": q or "", "limit": 1000})
if status != 200:
    error_box(status, listing)
    st.stop()
items = pd.DataFrame(listing["items"], columns=[c["name"] for c in columns])

# ---- table + record panel --------------------------------------------------
left, right = st.columns([2.2, 1])
with left:
    version = st.session_state.get(VERSION, 0)
    focus = st.session_state.get(FOCUS)
    focus_rows = (items.index[items[pk] == focus[1]].tolist()[:1]
                  if focus and focus[0] == res and not items.empty else [])
    event = st.dataframe(
        items, hide_index=True, height=520, on_select="rerun", selection_mode="single-row",
        key=f"grid_{res}_{q}_{version}",      # a new search or a write starts a fresh selection
        selection_default={"selection": {"rows": focus_rows}} if focus_rows else None,
        column_config={pk: st.column_config.Column(pinned=True)},
        placeholder="—", alt=f"{meta['label']} records",
    )
    shown = f"{len(items)} of {listing['total']}" if q else f"{listing['total']}"
    st.caption(f"{shown} row(s) · `GET /api/{res}" + (f"?q={q}" if q else "") + "` · select a row to open it")

with right:
    with st.container(border=True, height=560):
        rows = event.selection.rows
        if not rows or rows[0] >= len(items):
            st.markdown("**No record selected**")
            st.caption(":material/touch_app: Select a row in the table to see the full record, "
                       "then edit or delete it.")
        else:
            rid = plain(items.iloc[rows[0]][pk])
            status, record = api("GET", f"/{res}/{rid}")
            if status != 200:
                st.warning(explain(status, record)[1], icon=":material/warning:")
            else:
                with st.container(horizontal=True, vertical_alignment="center"):
                    st.markdown(f"**{pk}** `{rid}`")
                    st.space("stretch")
                    if st.button("Edit", icon=":material/edit:", key="edit_record"):
                        edit_dialog(meta, record)
                    if st.button("Delete", icon=":material/delete:", key="delete_record", type="tertiary"):
                        delete_dialog(meta, record)
                st.caption(f"`GET /api/{res}/{rid}`")
                fields = pd.DataFrame({"field": list(record),
                                       "value": ["—" if v is None else str(v) for v in record.values()]})
                st.dataframe(fields, hide_index=True, alt=f"Fields of {pk} {rid}",
                             column_config={"field": st.column_config.Column(width="small")})
