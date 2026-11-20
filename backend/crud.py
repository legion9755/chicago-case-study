"""
backend/crud.py — generic REST CRUD for every dimension table.

    GET     /api/resources                 metadata: tables, columns, types, row counts
    GET     /api/<resource>                list   (?q=search&limit=100&offset=0)
    GET     /api/<resource>/<pk>           read one
    POST    /api/<resource>                create            -> 201 / 400 / 409
    PUT     /api/<resource>/<pk>           replace (full)    -> 200 / 400 / 404
    PATCH   /api/<resource>/<pk>           update  (partial) -> 200 / 400 / 404
    DELETE  /api/<resource>/<pk>           delete            -> 200 / 404 / 409 (still referenced)

<resource> is one of: communities, districts, wards, beats, iucr
"""
from flask import Blueprint, abort, jsonify, request
from sqlalchemy import Float, Integer, String, func, or_, select
from sqlalchemy.exc import IntegrityError

from backend.database import SessionLocal
from backend.models import DIMENSIONS, ChicagoCrime

crud_bp = Blueprint("crud", __name__, url_prefix="/api")

# which fact-table column references each dimension (used to explain 409 on DELETE)
REFERENCED_BY = {
    "communities": ChicagoCrime.community_code,
    "districts": ChicagoCrime.district_code,
    "wards": ChicagoCrime.ward_no,
    "beats": ChicagoCrime.beat_num,
    "iucr": ChicagoCrime.iucr_code,
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def get_model(resource):
    if resource not in DIMENSIONS:
        abort(404, description=f"Unknown resource '{resource}'. Use one of {list(DIMENSIONS)}")
    return DIMENSIONS[resource][0]


def pk_column(model):
    return model.__mapper__.primary_key[0]


def to_dict(obj):
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def coerce(column, value):
    """Convert an incoming JSON value to the column's type, or raise ValueError."""
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None
    if isinstance(value, bool):
        raise ValueError("booleans are not valid here")
    ctype = column.type
    if isinstance(ctype, Integer):
        f = float(str(value).replace(",", ""))          # accepts "12,345"
        if not f.is_integer():
            raise ValueError("must be a whole number")
        return int(f)
    if isinstance(ctype, Float):
        return float(str(value).replace(",", ""))
    if isinstance(ctype, String):
        s = str(value).strip()
        if ctype.length and len(s) > ctype.length:
            raise ValueError(f"max length is {ctype.length} characters")
        if column.name == "iucr_code":                   # same rule as the pipeline: '486' -> '0486'
            s = s.upper().zfill(4)
            if len(s) > ctype.length:
                raise ValueError(f"max length is {ctype.length} characters")
        elif column.name == "primary_type":
            s = s.upper()
        return s
    return value


def parse_pk(model, raw):
    try:
        return coerce(pk_column(model), raw)
    except ValueError:
        abort(400, description=f"Invalid {pk_column(model).name}: '{raw}'")


def validate(model, payload, mode):
    """mode = 'create' | 'replace' | 'patch'. Returns clean dict or aborts with 400."""
    if not isinstance(payload, dict) or not payload:
        abort(400, description="Request body must be a non-empty JSON object")
    columns = {c.name: c for c in model.__table__.columns}
    pk = pk_column(model).name
    unknown = sorted(set(payload) - set(columns))
    if unknown:
        abort(400, description=f"Unknown field(s): {unknown}. Allowed: {list(columns)}")

    errors, clean = {}, {}
    for name, value in payload.items():
        try:
            clean[name] = coerce(columns[name], value)
        except (ValueError, TypeError) as exc:
            errors[name] = str(exc)

    # required (NOT NULL) columns
    required = [n for n, c in columns.items() if not c.nullable]
    if mode == "create":
        for n in required:
            if clean.get(n) is None:
                errors.setdefault(n, "is required")
    elif mode == "replace":
        for n in required:
            if n != pk and clean.get(n) is None:
                errors.setdefault(n, "is required for PUT (full replacement)")
    elif mode == "patch":
        for n in required:
            if n in clean and clean[n] is None:
                errors[n] = "cannot be set to null"
    if errors:
        abort(400, description={"validation_errors": errors})
    return clean


# ---------------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------------
@crud_bp.get("/resources")
def list_resources():
    out = []
    with SessionLocal() as s:
        for name, (model, label) in DIMENSIONS.items():
            out.append({
                "resource": name, "label": label, "table": model.__tablename__,
                "primary_key": pk_column(model).name,
                "rows": s.scalar(select(func.count()).select_from(model)),
                "columns": [{"name": c.name, "type": type(c.type).__name__,
                             "nullable": c.nullable, "primary_key": c.primary_key,
                             "max_length": getattr(c.type, "length", None)}
                            for c in model.__table__.columns],
            })
    return jsonify(out)


@crud_bp.get("/<resource>")
def list_items(resource):
    model = get_model(resource)
    limit = min(request.args.get("limit", 100, type=int), 1000)
    offset = request.args.get("offset", 0, type=int)
    q = request.args.get("q", "").strip()
    stmt = select(model)
    if q:
        conds = [c.cast(String).ilike(f"%{q}%") for c in model.__table__.columns]
        stmt = stmt.where(or_(*conds))
    with SessionLocal() as s:
        total = s.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = s.scalars(stmt.order_by(pk_column(model)).limit(limit).offset(offset)).all()
        return jsonify({"resource": resource, "total": total, "limit": limit, "offset": offset,
                        "items": [to_dict(r) for r in rows]})


@crud_bp.get("/<resource>/<pk>")
def get_item(resource, pk):
    model = get_model(resource)
    with SessionLocal() as s:
        obj = s.get(model, parse_pk(model, pk))
        if obj is None:
            abort(404, description=f"{resource} '{pk}' not found")
        return jsonify(to_dict(obj))


@crud_bp.post("/<resource>")
def create_item(resource):
    model = get_model(resource)
    data = validate(model, request.get_json(silent=True), "create")
    pk_name = pk_column(model).name
    with SessionLocal() as s:
        if s.get(model, data[pk_name]) is not None:
            abort(409, description=f"{resource} with {pk_name}={data[pk_name]} already exists "
                                   "(use PUT or PATCH to modify it)")
        obj = model(**data)
        s.add(obj)
        s.commit()
        return jsonify({"message": "created", "item": to_dict(obj)}), 201


@crud_bp.put("/<resource>/<pk>")
def replace_item(resource, pk):
    model = get_model(resource)
    key = parse_pk(model, pk)
    data = validate(model, request.get_json(silent=True), "replace")
    pk_name = pk_column(model).name
    if pk_name in data and data[pk_name] != key:
        abort(400, description=f"{pk_name} in the body ({data[pk_name]}) does not match the URL ({key})")
    with SessionLocal() as s:
        obj = s.get(model, key)
        if obj is None:
            abort(404, description=f"{resource} '{pk}' not found (use POST to create it)")
        for col in model.__table__.columns:          # PUT = replace every non-key field
            if col.name != pk_name:
                setattr(obj, col.name, data.get(col.name))
        s.commit()
        return jsonify({"message": "replaced", "item": to_dict(obj)})


@crud_bp.patch("/<resource>/<pk>")
def patch_item(resource, pk):
    model = get_model(resource)
    key = parse_pk(model, pk)
    data = validate(model, request.get_json(silent=True), "patch")
    pk_name = pk_column(model).name
    if pk_name in data and data[pk_name] != key:
        abort(400, description=f"The primary key {pk_name} cannot be changed")
    with SessionLocal() as s:
        obj = s.get(model, key)
        if obj is None:
            abort(404, description=f"{resource} '{pk}' not found")
        changed = {}
        for name, value in data.items():
            if name != pk_name and getattr(obj, name) != value:
                changed[name] = {"old": getattr(obj, name), "new": value}
                setattr(obj, name, value)
        s.commit()
        return jsonify({"message": "updated", "changed_fields": changed, "item": to_dict(obj)})


@crud_bp.delete("/<resource>/<pk>")
def delete_item(resource, pk):
    model = get_model(resource)
    key = parse_pk(model, pk)
    with SessionLocal() as s:
        obj = s.get(model, key)
        if obj is None:
            abort(404, description=f"{resource} '{pk}' not found")
        s.delete(obj)
        try:
            s.commit()
        except IntegrityError:
            s.rollback()
            n = s.scalar(select(func.count()).where(REFERENCED_BY[resource] == key))
            abort(409, description=f"Cannot delete {resource} '{pk}': it is referenced by {n} crime "
                                   "record(s). Delete or re-assign those crimes first.")
        return jsonify({"message": "deleted", "item": to_dict(obj)})
