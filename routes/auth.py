"""Session authentication and role-aware access for CampusFlow."""
from __future__ import annotations

from datetime import datetime
from functools import wraps
import re

from flask import Blueprint, current_app, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from routes.helpers import api_error, store
from services.audit_service import audit, notify


bp = Blueprint("auth", __name__, url_prefix="/api/auth")

ROLE_COLLECTIONS = {
    "faculty": ("faculty", "faculty_id"),
    "volunteer": ("volunteers", "volunteer_id"),
}

# Members may keep their contact and matching details current, but cannot
# change their identifier, active status, or workload limit themselves.
PROFILE_FIELDS = {
    "faculty": {"name", "department", "subjects", "expertise", "skills", "contact", "email", "image"},
    "volunteer": {"name", "department", "year", "skills", "interests", "preferred_roles", "email", "image"},
}
PROFILE_LIST_FIELDS = {"subjects", "expertise", "skills", "interests", "preferred_roles"}

# Every accepted event assignment is worth a fixed number of monthly attendance points.
ATTENDANCE_POINTS_PER_EVENT = 25
ACTIVE_ASSIGNMENT_STATUSES = {"locked", "active"}
VISIBLE_EVENT_STATUSES = {"approved", "plan_ready", "replan_pending"}


def current_user():
    return session.get("campusflow_user")


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            return api_error("Sign in is required.", 401)
        if user.get("role") != "admin":
            return api_error("Only administrators can manage campus data.", 403)
        return view(*args, **kwargs)
    return wrapped


def bootstrap_users(data_store, admin_username: str, admin_password: str):
    """Create local accounts once; existing account passwords are never replaced."""
    _create_user_if_missing(data_store, admin_username, admin_password, "admin", "Campus Administrator")
    for role, (collection, id_key) in ROLE_COLLECTIONS.items():
        for record in data_store.get_all(collection):
            ensure_resource_account(data_store, role, record)


def ensure_resource_account(data_store, role: str, record: dict):
    """Give each faculty member and volunteer an account matched to their resource ID."""
    collection, id_key = ROLE_COLLECTIONS[role]
    resource_id = record.get(id_key)
    if not resource_id:
        return
    _create_user_if_missing(data_store, resource_id, resource_id, role, record.get("name", resource_id), resource_id)


def _create_user_if_missing(data_store, username, password, role, display_name, resource_id=None):
    if data_store.get_one("users", {"username": username}):
        return
    data_store.insert("users", {
        "username": username,
        "password_hash": generate_password_hash(password),
        "role": role,
        "display_name": display_name,
        "resource_id": resource_id,
    })


@bp.post("/login")
def login():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    account = next((row for row in store().get_all("users") if row.get("username", "").lower() == username.lower()), None)
    if not account or not check_password_hash(account.get("password_hash", ""), password):
        return api_error("Incorrect username or password.", 401)
    user = {key: account.get(key) for key in ("username", "role", "display_name", "resource_id")}
    session.clear()
    session["campusflow_user"] = user
    session.permanent = True
    audit(store(), "User signed in", None, f"{user['display_name']} signed in as {user['role']}", actor=user["display_name"])
    return jsonify({"ok": True, "user": user})


@bp.post("/logout")
def logout():
    user = current_user()
    if user:
        audit(store(), "User signed out", None, f"{user['display_name']} signed out", actor=user["display_name"])
    session.clear()
    return jsonify({"ok": True})


@bp.get("/me")
def me():
    return jsonify({"ok": True, "authenticated": bool(current_user()), "user": current_user()})


@bp.get("/my-availability")
def my_availability():
    user = current_user()
    if not user:
        return api_error("Sign in is required.", 401)
    if user.get("role") == "admin":
        return api_error("Availability is shown for faculty and volunteer accounts.", 400)
    collection, id_key = ROLE_COLLECTIONS[user["role"]]
    resource = store().get_one(collection, {id_key: user["resource_id"]})
    if not resource:
        return api_error("Your linked resource record could not be found.", 404)
    events = {event["event_id"]: event for event in store().get_all("events")}
    all_assignments = store().get_all("assignments", {"resource_id": user["resource_id"]})
    assignments = [assignment for assignment in all_assignments if assignment.get("status") in ACTIVE_ASSIGNMENT_STATUSES]
    for assignment in assignments:
        event = events.get(assignment.get("event_id"), {})
        assignment["event_title"] = event.get("title") or event.get("name") or assignment.get("event_id")
        assignment.setdefault("acceptance", "pending")
    pending = [assignment for assignment in assignments if assignment.get("acceptance") == "pending"]
    accepted_now = [assignment for assignment in assignments if assignment.get("acceptance") == "accepted"]
    attendance = _attendance_summary(all_assignments)
    if pending:
        message, available = "You have a new event assignment awaiting your response.", False
    elif accepted_now:
        message, available = "You have an active, accepted event assignment.", False
    else:
        message, available = "Available for assignment", True
    return jsonify({"ok": True, "resource": resource, "assignments": assignments,
                    "available": available, "message": message, "attendance": attendance})


@bp.get("/my-profile")
def my_profile():
    """Return the signed-in member's own full profile only."""
    user = current_user()
    if not user:
        return api_error("Sign in is required.", 401)
    if user.get("role") not in ROLE_COLLECTIONS:
        return api_error("Profiles are available for faculty and volunteer accounts.", 400)
    collection, id_key = ROLE_COLLECTIONS[user["role"]]
    resource = store().get_one(collection, {id_key: user["resource_id"]})
    if not resource:
        return api_error("Your linked profile could not be found.", 404)
    return jsonify({"ok": True, "profile": resource})


@bp.put("/my-profile")
def update_my_profile():
    """Allow a faculty member or volunteer to update only their own profile."""
    user = current_user()
    if not user:
        return api_error("Sign in is required.", 401)
    role = user.get("role")
    if role not in ROLE_COLLECTIONS:
        return api_error("Profiles are available for faculty and volunteer accounts.", 400)
    payload = request.get_json(silent=True) or {}
    values = payload.get("profile")
    if not isinstance(values, dict):
        return api_error("Send a valid profile object.")
    collection, id_key = ROLE_COLLECTIONS[role]
    existing = store().get_one(collection, {id_key: user["resource_id"]})
    if not existing:
        return api_error("Your linked profile could not be found.", 404)
    updates = {}
    for field in PROFILE_FIELDS[role]:
        if field not in values:
            continue
        value = values[field]
        if field in PROFILE_LIST_FIELDS:
            updates[field] = [item.strip() for item in str(value).split(",") if item.strip()]
        elif field == "year":
            try:
                year = int(value)
            except (TypeError, ValueError):
                return api_error("Year must be a whole number.")
            if year < 1 or year > 12:
                return api_error("Year must be between 1 and 12.")
            updates[field] = year
        else:
            updates[field] = str(value).strip()
    if not updates:
        return api_error("No editable profile fields were provided.")
    if "name" in updates and not updates["name"]:
        return api_error("Name cannot be empty.")
    if updates.get("email") and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", updates["email"]):
        return api_error("Email must be a valid email address.")
    updated = store().update_one(collection, {id_key: user["resource_id"]}, updates)
    if "name" in updates:
        store().update_one("users", {"username": user["username"]}, {"display_name": updates["name"]})
        user["display_name"] = updates["name"]
        session["campusflow_user"] = user
    audit(store(), "Profile updated", None, "Member updated their own profile", actor=user.get("display_name", "Campus member"))
    return jsonify({"ok": True, "profile": updated, "user": user})


@bp.get("/my-mailbox")
def my_mailbox():
    """Show only messages explicitly addressed to the signed-in member."""
    user = current_user()
    if not user:
        return api_error("Sign in is required.", 401)
    if user.get("role") not in ROLE_COLLECTIONS:
        return api_error("Mailbox is available for faculty and volunteer accounts.", 400)
    messages = store().get_all("notifications", {"recipient_resource_id": user["resource_id"]})
    return jsonify({"ok": True, "messages": sorted(messages, key=lambda row: row.get("created_at", ""), reverse=True)})


@bp.get("/my-events")
def my_events():
    """A read-only, member-safe feed of currently running and upcoming campus events."""
    user = current_user()
    if not user:
        return api_error("Sign in is required.", 401)
    if user.get("role") == "admin":
        return api_error("Use the command center for the full events pipeline.", 400)
    now = datetime.now().isoformat(timespec="seconds")
    visible = [event for event in store().get_all("events") if event.get("status") in VISIBLE_EVENT_STATUSES and event.get("start_datetime")]

    def shape(event):
        return {"event_id": event["event_id"], "title": event.get("title") or event.get("name"), "status": event.get("status"),
                "start_datetime": event.get("start_datetime"), "end_datetime": event.get("end_datetime"), "readiness": event.get("readiness", 0)}

    running = sorted([shape(e) for e in visible if e["start_datetime"] <= now <= (e.get("end_datetime") or e["start_datetime"])], key=lambda e: e["start_datetime"])
    upcoming = sorted([shape(e) for e in visible if e["start_datetime"] > now], key=lambda e: e["start_datetime"])
    return jsonify({"ok": True, "running": running, "upcoming": upcoming})


@bp.post("/assignments/<assignment_id>/respond")
def respond_assignment(assignment_id):
    """Faculty and volunteers accept or decline their own event assignment."""
    user = current_user()
    if not user:
        return api_error("Sign in is required.", 401)
    if user.get("role") not in ROLE_COLLECTIONS:
        return api_error("Only faculty and volunteer accounts respond to assignments.", 400)
    payload = request.get_json(silent=True) or {}
    decision = str(payload.get("decision", "")).strip().lower()
    if decision not in {"accept", "decline"}:
        return api_error("decision must be 'accept' or 'decline'.")
    assignment = store().get_one("assignments", {"assignment_id": assignment_id})
    if not assignment or assignment.get("resource_id") != user.get("resource_id"):
        return api_error("Assignment not found.", 404)
    if assignment.get("status") not in ACTIVE_ASSIGNMENT_STATUSES:
        return api_error("This assignment is no longer active.", 409)
    if assignment.get("acceptance") not in (None, "pending"):
        return api_error("You already responded to this assignment.", 409)
    updated = store().update_one("assignments", {"assignment_id": assignment_id}, {
        "acceptance": "accepted" if decision == "accept" else "declined",
        "acceptance_at": datetime.now().isoformat(timespec="seconds"),
        "status": "locked" if decision == "accept" else "released",
    })
    event = store().get_one("events", {"event_id": assignment.get("event_id")}) or {}
    event_title = event.get("title") or assignment.get("event_id")
    if decision == "decline":
        conflicts = event.get("assignment_conflicts", [])
        if assignment_id not in conflicts:
            conflicts.append(assignment_id)
        store().update_one("events", {"event_id": assignment.get("event_id")}, {"assignment_conflicts": conflicts, "replacement_required": True})
    audit(store(), "Assignment response", assignment.get("event_id"), f"{user['display_name']} {decision}ed the assignment for {event_title}", actor=user["display_name"])
    notify(store(), "Assignment response recorded", f"{user['display_name']} {decision}ed their assignment for {event_title}.", assignment.get("event_id"),
           "success" if decision == "accept" else "warning")
    return jsonify({"ok": True, "assignment": updated})


def _attendance_summary(assignments: list[dict]) -> dict:
    """Monthly attendance points are credited only after an event is completed."""
    accepted = [assignment for assignment in assignments if assignment.get("acceptance") == "accepted" and assignment.get("attendance_status") == "completed"]
    monthly_counts: dict[str, int] = {}
    for assignment in accepted:
        month = (assignment.get("start_datetime") or "")[:7] or "unscheduled"
        monthly_counts[month] = monthly_counts.get(month, 0) + 1
    monthly = sorted(
        [{"month": month, "events": count, "points": count * ATTENDANCE_POINTS_PER_EVENT} for month, count in monthly_counts.items()],
        key=lambda row: row["month"], reverse=True,
    )
    return {"points_per_event": ATTENDANCE_POINTS_PER_EVENT, "total_events": len(accepted),
            "total_points": len(accepted) * ATTENDANCE_POINTS_PER_EVENT, "monthly": monthly}
