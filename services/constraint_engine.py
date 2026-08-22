from __future__ import annotations

from services.availability_service import equipment_available_quantity, member_is_available, resource_is_available, workload_for_day
from database.mongo import RESOURCE_COLLECTIONS


def validate_plan(store, plan: dict, requirements: dict, exclude_event_id: str | None = None) -> dict:
    """Deterministic authority for all lockable resources and calendar requirements."""
    checks, errors = [], []
    start, end = plan["start_datetime"], plan["end_datetime"]
    calendar = store.get_one("academic_calendar", {"date": start[:10]})
    calendar_ok = bool(calendar and calendar.get("available"))
    _check(checks, errors, calendar_ok, "Date available", (calendar or {}).get("reason", "Date is not configured as working"))
    lab_systems = 0
    required_software = {s.lower() for s in requirements.get("required_software", [])}
    software_ok = True
    for item in plan.get("labs", []):
        lab = store.get_one("labs", {"lab_id": item["resource_id"]})
        is_available = bool(lab and resource_is_available(store, item["resource_id"], start, end, exclude_event_id))
        _check(checks, errors, is_available, f"{item.get('name', item['resource_id'])} available", "Lab is unavailable or missing")
        if lab:
            lab_systems += lab["number_of_systems"]
            installed = {s.lower() for s in lab.get("installed_software", [])}
            if not required_software.issubset(installed):
                software_ok = False
    _check(checks, errors, lab_systems >= requirements.get("required_systems", 0), f"{lab_systems} systems available", f"Need {requirements.get('required_systems', 0)} systems")
    _check(checks, errors, software_ok, "Required software installed", "One or more labs lack required software")
    for item in plan.get("venues", []):
        venue = store.get_one("venues", {"venue_id": item["resource_id"]})
        ok = bool(venue and venue["capacity"] >= requirements.get("minimum_capacity", 0) and resource_is_available(store, item["resource_id"], start, end, exclude_event_id))
        _check(checks, errors, ok, f"{item.get('name', item['resource_id'])} capacity and availability", "Venue is unavailable or undersized")
    for category, human_name in [("faculty", "Faculty"), ("volunteers", "Volunteers"), ("guests", "Guest"), ("vehicles", "Vehicle")]:
        for item in plan.get(category, []):
            kind = item["resource_type"]
            doc = store.get_one(RESOURCE_COLLECTIONS[kind], {_id_key(kind): item["resource_id"]})
            availability = doc and resource_is_available(store, item["resource_id"], start, end, exclude_event_id)
            if kind in {"faculty", "volunteer"}:
                availability = availability and member_is_available(store, item["resource_id"], start, exclude_event_id)
            workload_ok = True
            if kind in {"faculty", "volunteer"}:
                workload_ok = workload_for_day(store, item["resource_id"], start, kind, exclude_event_id) < doc.get("max_events_per_day", 1)
            _check(checks, errors, bool(availability and workload_ok), f"{human_name}: {item.get('name', item['resource_id'])}", "Unavailable or at workload limit")
    for item in plan.get("equipment", []):
        doc = store.get_one("equipment", {"equipment_id": item["resource_id"]})
        remaining = equipment_available_quantity(store, doc, start, end, exclude_event_id) if doc else 0
        _check(checks, errors, remaining >= item.get("quantity", 1), f"{item.get('name', item['resource_id'])}: {remaining} units available", "Insufficient equipment quantity")
    return {"valid": not errors, "checks": checks, "errors": errors}


def _id_key(kind):
    return {"faculty": "faculty_id", "volunteer": "volunteer_id", "guest": "guest_id", "venue": "venue_id", "lab": "lab_id", "equipment": "equipment_id", "vehicle": "vehicle_id"}[kind]


def _check(checks, errors, ok, label, issue):
    checks.append({"label": label, "passed": bool(ok), "detail": "Satisfied" if ok else issue})
    if not ok:
        errors.append(f"{label}: {issue}")
