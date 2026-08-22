from __future__ import annotations

import csv
from datetime import date
import io
from pathlib import Path
import re
import uuid

from flask import Blueprint, current_app, jsonify, request, url_for
from werkzeug.utils import secure_filename

from routes.auth import admin_required, current_user, ensure_resource_account
from routes.helpers import api_error, store
from services.audit_service import audit
from services.availability_service import member_is_available, resource_is_available
from services.gemini_service import extract_calendar_from_image

bp = Blueprint("resources", __name__, url_prefix="/api")

SOURCES = {"faculty": ("faculty", "faculty_id"), "volunteers": ("volunteers", "volunteer_id"), "guests": ("guests", "guest_id"), "blocks": ("blocks", "block_id"), "venues": ("venues", "venue_id"), "labs": ("labs", "lab_id"), "equipment": ("equipment", "equipment_id"), "vehicles": ("vehicles", "vehicle_id")}

# Explicit input contract for the in-app Data Manager. This avoids accepting
# arbitrary MongoDB fields from the browser while keeping every campus entity editable.
DATA_SCHEMA = {
    "faculty": {"id": "faculty_id", "prefix": "fac", "required": ["name", "department"], "fields": ["faculty_id", "name", "department", "subjects", "expertise", "skills", "contact", "email", "image", "max_events_per_day", "status"], "lists": {"subjects", "expertise", "skills"}, "numbers": {"max_events_per_day"}, "defaults": {"max_events_per_day": 2, "status": "active"}},
    "volunteers": {"id": "volunteer_id", "prefix": "vol", "required": ["name", "department"], "fields": ["volunteer_id", "name", "department", "year", "skills", "interests", "preferred_roles", "email", "image", "max_events_per_day", "status"], "lists": {"skills", "interests", "preferred_roles"}, "numbers": {"year", "max_events_per_day"}, "defaults": {"max_events_per_day": 1, "status": "active"}},
    "guests": {"id": "guest_id", "prefix": "guest", "required": ["name", "organization"], "fields": ["guest_id", "name", "designation", "organization", "expertise", "relevant_departments", "relevant_subjects", "suitable_event_types", "contact", "email", "image", "previous_events", "status"], "lists": {"expertise", "relevant_departments", "relevant_subjects", "suitable_event_types"}, "numbers": {"previous_events"}, "defaults": {"previous_events": 0, "status": "active"}},
    "blocks": {"id": "block_id", "prefix": "block", "required": ["block_name"], "fields": ["block_id", "block_name", "image", "location", "number_of_labs", "description"], "lists": set(), "numbers": {"number_of_labs"}, "defaults": {"number_of_labs": 0}},
    "labs": {"id": "lab_id", "prefix": "lab", "required": ["lab_name", "block_id", "capacity", "number_of_systems"], "fields": ["lab_id", "lab_name", "block_id", "floor", "capacity", "number_of_systems", "operating_system", "installed_software", "projectors", "microphones", "internet", "image", "status"], "lists": {"operating_system", "installed_software"}, "numbers": {"floor", "capacity", "number_of_systems", "projectors", "microphones"}, "booleans": {"internet"}, "defaults": {"projectors": 0, "microphones": 0, "internet": True, "status": "active"}},
    "venues": {"id": "venue_id", "prefix": "venue", "required": ["name", "block", "type", "capacity"], "fields": ["venue_id", "name", "block", "floor", "type", "image", "capacity", "chairs", "tables", "projectors", "microphones", "speakers", "computers", "air_conditioning", "internet", "accessibility", "status"], "lists": set(), "numbers": {"capacity", "chairs", "tables", "projectors", "microphones", "speakers", "computers"}, "booleans": {"air_conditioning", "internet", "accessibility"}, "defaults": {"floor": 1, "chairs": 0, "tables": 0, "projectors": 0, "microphones": 0, "speakers": 0, "computers": 0, "air_conditioning": True, "internet": True, "accessibility": True, "status": "active"}},
    "equipment": {"id": "equipment_id", "prefix": "eq", "required": ["type", "name", "total_quantity"], "fields": ["equipment_id", "type", "name", "total_quantity", "location", "condition", "image", "status"], "lists": set(), "numbers": {"total_quantity"}, "defaults": {"condition": "good", "status": "active"}},
    "vehicles": {"id": "vehicle_id", "prefix": "vehicle", "required": ["type", "capacity", "driver"], "fields": ["vehicle_id", "type", "capacity", "driver", "image", "status"], "lists": set(), "numbers": {"capacity"}, "defaults": {"status": "active"}},
    "academic_calendar": {"id": "calendar_id", "prefix": "calendar", "required": ["date", "type", "reason"], "fields": ["calendar_id", "date", "type", "reason", "image", "available"], "lists": set(), "numbers": set(), "booleans": {"available"}, "defaults": {"available": True}},
}

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_CSV_ROWS = 1000
MAX_CALENDAR_IMAGE_ROWS = 366
IMAGE_MIME_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}


def _with_assignments(collection, id_key):
    rows = store().get_all(collection)
    assignments = store().get_all("assignments")
    blocks = {block.get("block_id"): block.get("block_name") for block in store().get_all("blocks")} if collection == "labs" else {}
    for row in rows:
        row["current_assignments"] = [item for item in assignments if item["resource_id"] == row[id_key] and item.get("status") in {"locked", "outage"}]
        row["assignment_count"] = len(row["current_assignments"])
        if blocks:
            row["block_name"] = blocks.get(row.get("block_id"), row.get("block_id", ""))
    return rows


@bp.get("/resources")
def resources():
    resource_type = request.args.get("type")
    if resource_type:
        if resource_type not in SOURCES:
            return api_error("Unknown resource type.")
        source, key = SOURCES[resource_type]
        return jsonify({"ok": True, "resources": _with_assignments(source, key)})
    return jsonify({"ok": True, "resources": {name: _with_assignments(source, key) for name, (source, key) in SOURCES.items()}})


@bp.get("/availability")
def availability():
    name = request.args.get("name", "").strip().lower()
    start = request.args.get("start_datetime", "").strip()
    end = request.args.get("end_datetime", "").strip()
    if not name or not start or not end:
        return api_error("Provide a resource name, start time, and end time.")
    matches = []
    for resource_type, (collection, id_key) in SOURCES.items():
        if resource_type in {"academic_calendar", "blocks"}:
            continue
        for resource in store().get_all(collection):
            if name not in str(resource.get("name") or resource.get("lab_name") or resource.get("type") or "").lower():
                continue
            resource_id = resource.get(id_key)
            available = resource_is_available(store(), resource_id, start, end)
            if resource_type in {"faculty", "volunteers"}:
                available = available and member_is_available(store(), resource_id, start)
            matches.append({"resource_id": resource_id, "resource_type": resource_type, "name": resource.get("name") or resource.get("lab_name") or resource.get("type"), "available": available})
    return jsonify({"ok": True, "matches": matches, "message": "Available for that time" if any(item["available"] for item in matches) else "No matching resource is available for that time"})


for path, (source, key) in SOURCES.items():
    def endpoint(source=source, key=key):
        return jsonify({"ok": True, "resources": _with_assignments(source, key)})
    bp.add_url_rule(f"/{path}", endpoint=f"list_{path}", view_func=endpoint)


@bp.get("/data/<data_type>")
def list_data(data_type):
    if data_type not in DATA_SCHEMA:
        return api_error("Unknown data type.")
    schema = DATA_SCHEMA[data_type]
    return jsonify({"ok": True, "records": _with_assignments(data_type, schema["id"]) if data_type in SOURCES else store().get_all(data_type)})


@bp.post("/data/<data_type>")
@admin_required
def create_data(data_type):
    if data_type not in DATA_SCHEMA:
        return api_error("Unknown data type.")
    payload = request.get_json(silent=True) or {}
    values = payload.get("data")
    if not isinstance(values, dict):
        return api_error("Send a valid data object.")
    schema = DATA_SCHEMA[data_type]
    missing = [field for field in schema["required"] if not str(values.get(field, "")).strip()]
    if missing:
        return api_error(f"Required fields: {', '.join(missing)}")
    try:
        record = _normalise(values, schema)
    except ValueError as exc:
        return api_error(str(exc))
    if store().get_one(data_type, {schema["id"]: record[schema["id"]]}):
        return api_error(f"{schema['id']} already exists.", 409)
    created = store().insert(data_type, record)
    _sync_resource_account(data_type, created)
    _audit_data_change("Resource record added", data_type, created[schema["id"]])
    return jsonify({"ok": True, "record": created}), 201


@bp.post("/data/<data_type>/csv")
@admin_required
def import_data_csv(data_type):
    if data_type not in DATA_SCHEMA:
        return api_error("Unknown data type.")
    upload = request.files.get("file")
    if not upload or not upload.filename:
        return api_error("Choose a CSV file to import.")
    if Path(secure_filename(upload.filename)).suffix.lower() != ".csv":
        return api_error("Choose a CSV file with a .csv extension.")
    try:
        text = upload.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return api_error("CSV files must use UTF-8 encoding.")

    reader = csv.DictReader(io.StringIO(text))
    raw_headers = reader.fieldnames or []
    header_pairs = [(str(header), str(header).strip()) for header in raw_headers]
    if not header_pairs or any(not header for _, header in header_pairs):
        return api_error("The CSV file must include a non-empty header for every column.")
    headers = [header for _, header in header_pairs]
    if len(headers) != len(set(headers)):
        return api_error("CSV column names must be unique.")

    schema = DATA_SCHEMA[data_type]
    unsupported = [header for header in headers if header not in schema["fields"]]
    if unsupported:
        return api_error(f"Unsupported CSV columns: {', '.join(unsupported)}")

    rows = list(reader)
    if len(rows) > MAX_CSV_ROWS:
        return api_error(f"CSV imports are limited to {MAX_CSV_ROWS} rows.")

    existing_ids = {str(row.get(schema["id"], "")) for row in store().get_all(data_type)}
    imported_ids = set()
    records = []
    errors = []
    for row_number, source in enumerate(rows, start=2):
        if not any(str(value or "").strip() for value in source.values()):
            continue
        values = {header: str(source.get(raw_header) or "").strip() for raw_header, header in header_pairs}
        missing = [field for field in schema["required"] if not values.get(field, "").strip()]
        if missing:
            errors.append(f"Row {row_number}: required fields missing: {', '.join(missing)}.")
            continue
        try:
            record = _normalise(values, schema)
        except ValueError as exc:
            errors.append(f"Row {row_number}: {exc}")
            continue
        record_id = record[schema["id"]]
        if record_id in existing_ids or record_id in imported_ids:
            errors.append(f"Row {row_number}: {schema['id']} '{record_id}' already exists.")
            continue
        imported_ids.add(record_id)
        records.append(record)

    if errors:
        preview = " ".join(errors[:5])
        remaining = len(errors) - 5
        suffix = f" {remaining} more row errors." if remaining > 0 else ""
        return api_error(f"CSV import failed. {preview}{suffix}", row_errors=errors[:20])
    if not records:
        return api_error("The CSV file does not contain any records to import.")

    for record in records:
        created = store().insert(data_type, record)
        _sync_resource_account(data_type, created)
    _audit_data_change("CSV import completed", data_type, f"{len(records)} record(s)")
    return jsonify({"ok": True, "imported": len(records)}), 201


@bp.post("/data/academic_calendar/scan-image")
@admin_required
def scan_calendar_image():
    image = request.files.get("image")
    try:
        extension = _image_extension(image)
    except ValueError as exc:
        return api_error(str(exc))
    image_bytes = image.read()
    if not image_bytes:
        return api_error("Choose an image to read.")
    records, error = extract_calendar_from_image(
        image_bytes, IMAGE_MIME_TYPES[extension], current_app.config.get("GEMINI_API_KEY", "")
    )
    if error:
        return api_error(error, 422)
    if not records:
        return api_error("No clearly dated working or holiday entries were found in that image.", 422)
    if len(records) > MAX_CALENDAR_IMAGE_ROWS:
        return api_error(f"A timetable image can contain at most {MAX_CALENDAR_IMAGE_ROWS} calendar days.")
    source_image = _store_image(image, extension, image_bytes)
    for record in records:
        record["image"] = source_image
    return jsonify({"ok": True, "records": records, "image": source_image})


@bp.post("/data/academic_calendar/image-import")
@admin_required
def import_calendar_image_records():
    payload = request.get_json(silent=True) or {}
    values_list = payload.get("records")
    if not isinstance(values_list, list) or not values_list:
        return api_error("Send the timetable days to import.")
    if len(values_list) > MAX_CALENDAR_IMAGE_ROWS:
        return api_error(f"A timetable image can contain at most {MAX_CALENDAR_IMAGE_ROWS} calendar days.")

    schema = DATA_SCHEMA["academic_calendar"]
    existing_by_date = {record.get("date"): record for record in store().get_all("academic_calendar")}
    seen_dates = set()
    operations = []
    errors = []
    for position, values in enumerate(values_list, start=1):
        if not isinstance(values, dict):
            errors.append(f"Entry {position}: invalid calendar record.")
            continue
        missing = [field for field in schema["required"] if not str(values.get(field, "")).strip()]
        if missing:
            errors.append(f"Entry {position}: required fields missing: {', '.join(missing)}.")
            continue
        try:
            record = _normalise(values, schema)
        except ValueError as exc:
            errors.append(f"Entry {position}: {exc}")
            continue
        if record["date"] in seen_dates:
            errors.append(f"Entry {position}: date '{record['date']}' appears more than once.")
            continue
        seen_dates.add(record["date"])
        existing = existing_by_date.get(record["date"])
        if existing:
            record[schema["id"]] = existing[schema["id"]]
        operations.append((record, existing))

    if errors:
        return api_error(f"Timetable import failed. {' '.join(errors[:5])}", row_errors=errors[:20])

    created = 0
    updated = 0
    for record, existing in operations:
        if existing:
            store().update_one("academic_calendar", {schema["id"]: record[schema["id"]]}, record)
            updated += 1
        else:
            store().insert("academic_calendar", record)
            created += 1
    _audit_data_change("Timetable image imported", "academic_calendar", f"{created} added, {updated} updated")
    return jsonify({"ok": True, "created": created, "updated": updated}), 201


@bp.put("/data/<data_type>/<record_id>")
@admin_required
def update_data(data_type, record_id):
    if data_type not in DATA_SCHEMA:
        return api_error("Unknown data type.")
    schema = DATA_SCHEMA[data_type]
    existing = store().get_one(data_type, {schema["id"]: record_id})
    if not existing:
        return api_error("Record not found.", 404)
    payload = request.get_json(silent=True) or {}
    values = payload.get("data")
    if not isinstance(values, dict):
        return api_error("Send a valid data object.")
    merged = {field: values[field] if field in values else existing.get(field) for field in schema["fields"]}
    merged[schema["id"]] = record_id
    missing = [field for field in schema["required"] if not str(merged.get(field, "")).strip()]
    if missing:
        return api_error(f"Required fields: {', '.join(missing)}")
    try:
        record = _normalise(merged, schema)
    except ValueError as exc:
        return api_error(str(exc))
    record[schema["id"]] = record_id
    updated = store().update_one(data_type, {schema["id"]: record_id}, record)
    _sync_resource_account(data_type, updated)
    _audit_data_change("Resource record updated", data_type, record_id)
    return jsonify({"ok": True, "record": updated})


@bp.post("/uploads")
@admin_required
def upload_image():
    image = request.files.get("image")
    try:
        extension = _image_extension(image)
    except ValueError as exc:
        return api_error(str(exc))
    return jsonify({"ok": True, "image": _store_image(image, extension)}), 201


def _image_extension(image):
    if not image or not image.filename:
        raise ValueError("Choose an image to upload.")
    extension = Path(secure_filename(image.filename)).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Use a JPG, PNG, GIF or WebP image.")
    return extension


def _store_image(image, extension, content: bytes | None = None):
    upload_dir = Path(current_app.static_folder) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{extension}"
    destination = upload_dir / filename
    if content is None:
        image.save(destination)
    else:
        destination.write_bytes(content)
    return url_for("static", filename=f"uploads/{filename}")


def _normalise(values, schema):
    record = dict(schema.get("defaults", {}))
    for field in schema["fields"]:
        if field not in values or values[field] in (None, ""):
            continue
        value = values[field]
        if field in schema.get("lists", set()):
            record[field] = [item.strip() for item in re.split(r"[|,]", str(value)) if item.strip()]
        elif field in schema.get("numbers", set()):
            number = int(value)
            if number < 0:
                raise ValueError(f"{field} cannot be negative.")
            record[field] = number
        elif field in schema.get("booleans", set()):
            record[field] = str(value).lower() in {"true", "1", "yes", "on"} if not isinstance(value, bool) else value
        else:
            record[field] = str(value).strip()
    identifier = schema["id"]
    record.setdefault(identifier, f"{schema['prefix']}-{uuid.uuid4().hex[:8]}")
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,64}", record[identifier]):
        raise ValueError(f"{identifier} can contain only letters, numbers, hyphens and underscores.")
    if "date" in record:
        try:
            date.fromisoformat(record["date"])
        except ValueError as exc:
            raise ValueError("date must use YYYY-MM-DD format.") from exc
    if record.get("email") and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", record["email"]):
        raise ValueError("email must be a valid email address.")
    return record


def _sync_resource_account(data_type, record):
    if data_type == "faculty":
        ensure_resource_account(store(), "faculty", record)
    elif data_type == "volunteers":
        ensure_resource_account(store(), "volunteer", record)


def _audit_data_change(action, data_type, record_id):
    user = current_user() or {}
    audit(store(), action, None, f"{data_type}: {record_id}", actor=user.get("display_name", "Campus Operations"))
