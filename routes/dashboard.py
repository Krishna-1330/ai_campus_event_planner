from __future__ import annotations

from datetime import datetime
from flask import Blueprint, jsonify

from routes.auth import current_user
from routes.helpers import app_mode, store

bp = Blueprint("dashboard", __name__, url_prefix="/api")


@bp.get("/dashboard")
def dashboard():
    events = store().get_all("events")
    user = current_user()
    if user.get("role") == "organizer":
        events = [event for event in events if event.get("organizer_username") == user.get("username")]
    active = [event for event in events if event.get("status") in {"approved", "replan_pending", "plan_ready"}]
    assignments = store().get_all("assignments")
    locked = [item for item in assignments if item.get("status") in {"locked", "outage"}]
    resources = sum(len(store().get_all(collection)) for collection in ["faculty", "volunteers", "guests", "venues", "labs", "equipment", "vehicles"])
    conflicts = [event for event in events if event.get("status") in {"conflict", "replan_pending"}]
    readiness = round(sum(event.get("readiness", 0) for event in active) / len(active)) if active else 0
    return jsonify({"ok": True, "mode": app_mode(), "metrics": {"active_events": len(active), "upcoming_events": len([event for event in events if event.get("start_datetime", "") >= datetime.now().isoformat()]), "resource_utilization": round((len(locked) / max(resources, 1)) * 100), "conflicts": len(conflicts), "readiness": readiness},
                    "events": sorted(events, key=lambda e: e.get("created_at", ""), reverse=True)[:8], "activity": store().get_all("audit_logs")[-8:]})
