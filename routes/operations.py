from flask import Blueprint, jsonify
from routes.helpers import store

bp = Blueprint("operations", __name__, url_prefix="/api")


@bp.get("/conflicts")
def conflicts():
    events = [row for row in store().get_all("events") if row.get("status") in {"conflict", "replan_pending"}]
    return jsonify({"ok": True, "conflicts": events})


@bp.get("/audit")
def audit():
    return jsonify({"ok": True, "logs": list(reversed(store().get_all("audit_logs")))})


@bp.get("/notifications")
def notifications():
    return jsonify({"ok": True, "notifications": list(reversed(store().get_all("notifications")))})


@bp.delete("/notifications")
def delete_notifications():
    deleted = store().delete_many("notifications", {})
    return jsonify({"ok": True, "deleted": deleted})


@bp.get("/schedule")
def schedule():
    return jsonify({"ok": True, "events": store().get_all("events"), "assignments": [row for row in store().get_all("assignments") if row.get("status") in {"locked", "outage"}]})


@bp.get("/agents")
def agents():
    events = sorted(store().get_all("events"), key=lambda row: row.get("created_at", ""), reverse=True)
    latest = events[0] if events else {}
    workflow = latest.get("workflow", [])
    return jsonify({"ok": True, "agents": workflow or [{"name": name, "status": "waiting", "detail": "Waiting for an event request"} for name in ["Event Understanding", "Schedule Agent", "Venue Agent", "People Agent", "Resource Agent", "Conflict Agent", "Coordinator"]]})
