from __future__ import annotations

from datetime import datetime
import re
import uuid

from flask import Blueprint, current_app, jsonify, request

from agents.orchestrator import generate_plan, _timeline_for
from agents.replanning_agent import run as generate_replan
from agents.venue_agent import recommend_labs, recommend_venues
from services.audit_service import audit, notify
from services.constraint_engine import validate_plan
from services.email_service import send_email
from services.matching_service import score_person
from routes.helpers import api_error, store


bp = Blueprint("events", __name__, url_prefix="/api/events")


@bp.post("")
def create_event():
    payload = request.get_json(silent=True) or {}
    prompt = str(payload.get("prompt", "")).strip()
    if len(prompt) < 12:
        return api_error("Describe the event in at least 12 characters.")
    event = {"event_id": str(uuid.uuid4()), "title": _event_title(prompt), "prompt": prompt, "status": "draft", "created_at": datetime.now().isoformat(timespec="seconds"),
             "readiness": 0, "approval_status": "not requested"}
    store().insert("events", event)
    audit(store(), "Event created", event["event_id"], "Natural-language event request created")
    notify(store(), "Event created", f"{event['title']} is ready for AI planning.", event["event_id"])
    return jsonify({"ok": True, "event": event}), 201


@bp.get("")
def list_events():
    rows = sorted(store().get_all("events"), key=lambda row: row.get("created_at", ""), reverse=True)
    return jsonify({"ok": True, "events": rows})


@bp.get("/<event_id>")
def get_event(event_id):
    event = store().get_one("events", {"event_id": event_id})
    if not event:
        return api_error("Event not found.", 404)
    event["tasks"] = store().get_all("tasks", {"event_id": event_id})
    event["assignments"] = store().get_all("assignments", {"event_id": event_id})
    return jsonify({"ok": True, "event": event})


@bp.put("/<event_id>")
def update_event(event_id):
    """Rename an event from the dashboard without bypassing plan validation."""
    event = store().get_one("events", {"event_id": event_id})
    if not event:
        return api_error("Event not found.", 404)
    payload = request.get_json(silent=True) or {}
    title = str(payload.get("title", "")).strip()
    if not title:
        return api_error("Event name cannot be empty.")
    if len(title) > 120:
        return api_error("Event name must be 120 characters or fewer.")
    updated = store().update_one("events", {"event_id": event_id}, {"title": title})
    audit(store(), "Event updated", event_id, f"Event renamed to {title}", actor="Campus Operations")
    return jsonify({"ok": True, "event": updated})


@bp.post("/<event_id>/plan")
def plan_event(event_id):
    event = store().get_one("events", {"event_id": event_id})
    if not event:
        return api_error("Event not found.", 404)
    result = generate_plan(store(), event, current_app.config.get("GEMINI_API_KEY", ""))
    if result["plan"]:
        readiness = _readiness(result["plan"], result["requirements"], result["validation"], approved=False)
        store().insert("event_requirements", {"requirement_id": str(uuid.uuid4()), "event_id": event_id, **result["requirements"], "created_at": datetime.now().isoformat(timespec="seconds")})
        store().update_one("events", {"event_id": event_id}, {"status": "plan_ready" if result["validation"]["valid"] else "conflict", "approval_status": "pending human approval" if result["validation"]["valid"] else "blocked", "proposed_plan": result["plan"], "workflow": result["workflow"], "validation": result["validation"], "ai_explanation": result["explanation"], "readiness": readiness, "start_datetime": result["plan"]["start_datetime"], "end_datetime": result["plan"]["end_datetime"]})
        _create_tasks(event_id, result["plan"])
        for message in result["messages"]:
            notify(store(), message["title"], message["message"], event_id)
        audit(store(), "AI plan generated", event_id, f"Generated plan with {len(result['validation']['checks'])} deterministic constraint checks")
    else:
        store().update_one("events", {"event_id": event_id}, {"status": "conflict", "workflow": result["workflow"], "validation": result["validation"]})
    return jsonify({"ok": result["validation"]["valid"], **result})


@bp.post("/<event_id>/approve")
def approve_plan(event_id):
    event = store().get_one("events", {"event_id": event_id})
    if not event or not event.get("proposed_plan"):
        return api_error("A generated plan is required before approval.", 404)
    validation = validate_plan(store(), event["proposed_plan"], _requirements(event_id))
    if not validation["valid"]:
        store().update_one("events", {"event_id": event_id}, {"status": "conflict", "validation": validation, "approval_status": "blocked"})
        return api_error("This plan can no longer be approved because a constraint changed.", 409, validation=validation)
    _release_assignments(event_id)
    _lock_plan(event_id, event["proposed_plan"])
    updated = store().update_one("events", {"event_id": event_id}, {"status": "approved", "approval_status": "approved", "active_plan": event["proposed_plan"], "readiness": _readiness(event["proposed_plan"], _requirements(event_id), validation, approved=True), "validation": validation})
    _notify_assigned_people(event_id, updated["active_plan"])
    audit(store(), "Human approval", event_id, "Plan approved; resource assignments locked", actor="Campus Operations")
    notify(store(), "Resources locked", f"{event['title']} is approved and its time-slot assignments are locked.", event_id, "success")
    return jsonify({"ok": True, "event": updated, "validation": validation})


@bp.post("/<event_id>/complete")
def complete_event(event_id):
    event = store().get_one("events", {"event_id": event_id})
    if not event or event.get("status") != "approved":
        return api_error("Only an approved event can be completed.", 409)
    end_datetime = event.get("end_datetime") or (event.get("active_plan") or {}).get("end_datetime")
    end_time = datetime.fromisoformat(end_datetime.replace("Z", "+00:00")) if end_datetime else None
    current_time = datetime.now(end_time.tzinfo) if end_time and end_time.tzinfo else datetime.now()
    if not end_time or end_time > current_time:
        return api_error("An event can be completed only after its end time.", 409)
    completed_at = datetime.now().isoformat(timespec="seconds")
    store().update_many("assignments", {"event_id": event_id, "acceptance": "accepted"}, {"attendance_status": "completed", "completed_at": completed_at})
    updated = store().update_one("events", {"event_id": event_id}, {"status": "completed", "completed_at": completed_at})
    audit(store(), "Event completed", event_id, "Event completed; accepted participants credited", actor="Campus Operations")
    notify(store(), "Event completed", f"{event.get('title', 'Event')} is completed and participant attendance was updated.", event_id, "success")
    return jsonify({"ok": True, "event": updated})


@bp.post("/<event_id>/recheck-resources/<resource_type>")
def recheck_resources(event_id, resource_type):
    event = store().get_one("events", {"event_id": event_id})
    plan = dict((event or {}).get("active_plan") or (event or {}).get("proposed_plan") or {})
    if not event or not plan:
        return api_error("A generated event plan is required first.", 404)
    if resource_type not in {"labs", "venues"}:
        return api_error("Resource type must be labs or venues.")
    requirements = _requirements(event_id)
    if resource_type == "labs":
        matches = recommend_labs(store(), requirements, plan["start_datetime"], plan["end_datetime"], exclude_event_id=event_id if event.get("status") == "approved" else None)
    else:
        matches = recommend_venues(store(), requirements, plan["start_datetime"], plan["end_datetime"], exclude_event_id=event_id if event.get("status") == "approved" else None)[:1]
    current_matches = plan.get(resource_type, [])
    current_score = min((item.get("score", 0) for item in current_matches), default=0)
    new_score = min((item.get("score", 0) for item in matches), default=0)
    improved = bool(matches) and (not current_matches or new_score > current_score)
    if improved:
        plan[resource_type] = matches
    else:
        matches = current_matches
    validation = validate_plan(store(), plan, requirements, exclude_event_id=event_id if event.get("status") == "approved" else None)
    status = "plan_ready" if validation["valid"] and event.get("status") != "approved" else event.get("status")
    counts = dict(event.get("resource_recheck_counts", {}))
    counts[resource_type] = counts.get(resource_type, 0) + 1
    updated = store().update_one("events", {"event_id": event_id}, {"proposed_plan": plan, "active_plan": plan if event.get("status") == "approved" else event.get("active_plan"), "validation": validation, "status": status, "resource_recheck_counts": counts})
    return jsonify({"ok": validation["valid"], "updated": improved, "count": counts[resource_type], "matches": matches, "event": updated, "validation": validation})


@bp.post("/<event_id>/replan-timeline")
def replan_timeline(event_id):
    event = store().get_one("events", {"event_id": event_id})
    plan = dict((event or {}).get("active_plan") or (event or {}).get("proposed_plan") or {})
    if not event or not plan:
        return api_error("A generated event plan is required first.", 404)
    current = plan.get("timeline", [])
    proposed = _timeline_for(_requirements(event_id))
    improved_or_equal = _timeline_quality(proposed) >= _timeline_quality(current)
    if improved_or_equal:
        plan["timeline"] = proposed
    count = event.get("timeline_replan_count", 0) + 1
    updated = store().update_one("events", {"event_id": event_id}, {"active_plan": plan if event.get("status") == "approved" else event.get("active_plan"), "proposed_plan": plan, "timeline_replan_count": count})
    return jsonify({"ok": True, "updated": improved_or_equal, "count": count, "timeline": plan.get("timeline", []), "event": updated})


@bp.post("/<event_id>/simulate-conflict")
def simulate_conflict(event_id):
    event = store().get_one("events", {"event_id": event_id})
    if not event or not event.get("active_plan"):
        return api_error("Approve a plan before simulating a live resource outage.", 409)
    payload = request.get_json(silent=True) or {}
    resource_id = payload.get("resource_id") or (event["active_plan"].get("labs") or event["active_plan"].get("venues") or [{}])[0].get("resource_id")
    if not resource_id:
        return api_error("The active plan has no lockable venue or lab.")
    # A time-bounded outage is represented as an assignment, never as a global availability switch.
    incident_id = f"incident-{uuid.uuid4()}"
    store().insert("assignments", {"assignment_id": str(uuid.uuid4()), "resource_id": resource_id, "event_id": incident_id, "resource_type": "lab" if resource_id.startswith("lab-") else "venue", "start_datetime": event["active_plan"]["start_datetime"], "end_datetime": event["active_plan"]["end_datetime"], "assignment_type": "resource_outage", "quantity": 1, "status": "outage"})
    proposal = generate_replan(store(), event["active_plan"], _requirements(event_id), event_id, resource_id)
    store().update_one("events", {"event_id": event_id}, {"status": "replan_pending" if proposal["valid"] else "conflict", "pending_replan": proposal, "incident_id": incident_id, "readiness": max(0, event.get("readiness", 0) - 24)})
    audit(store(), "Conflict detected", event_id, f"Simulated time-slot outage for {resource_id}")
    audit(store(), "Replanning triggered", event_id, proposal["reason"])
    notify(store(), "Resource conflict detected", f"{resource_id} became unavailable. Replanning is awaiting human review.", event_id, "warning")
    return jsonify({"ok": proposal["valid"], "replan": proposal})


@bp.post("/<event_id>/replan")
def replan_event(event_id):
    event = store().get_one("events", {"event_id": event_id})
    if not event or not event.get("active_plan"):
        return api_error("An approved event is required for replanning.", 409)
    payload = request.get_json(silent=True) or {}
    resource_id = payload.get("resource_id") or (event["active_plan"].get("labs") or event["active_plan"].get("venues") or [{}])[0].get("resource_id")
    proposal = generate_replan(store(), event["active_plan"], _requirements(event_id), event_id, resource_id)
    store().update_one("events", {"event_id": event_id}, {"pending_replan": proposal, "status": "replan_pending" if proposal["valid"] else "conflict"})
    return jsonify({"ok": proposal["valid"], "replan": proposal})


@bp.post("/<event_id>/approve-replan")
def approve_replan(event_id):
    event = store().get_one("events", {"event_id": event_id})
    pending = (event or {}).get("pending_replan")
    if not pending or not pending.get("valid"):
        return api_error("No valid replan is awaiting approval.", 409)
    validation = validate_plan(store(), pending["proposal"], _requirements(event_id), exclude_event_id=event_id)
    if not validation["valid"]:
        return api_error("The replan is no longer valid.", 409, validation=validation)
    _release_assignments(event_id)
    _lock_plan(event_id, pending["proposal"])
    store().update_many("assignments", {"event_id": event.get("incident_id")}, {"status": "released"})
    updated = store().update_one("events", {"event_id": event_id}, {"status": "approved", "approval_status": "approved", "active_plan": pending["proposal"], "proposed_plan": pending["proposal"], "pending_replan": None, "assignment_conflicts": [], "replacement_required": False, "validation": validation, "readiness": _readiness(pending["proposal"], _requirements(event_id), validation, True)})
    _notify_assigned_people(event_id, updated["active_plan"])
    audit(store(), "Plan updated", event_id, "Human approved dynamic replan; old assignments released and new assignments locked", actor="Campus Operations")
    notify(store(), "Replan applied", f"A validated alternative plan is now active for {event['title']}.", event_id, "success")
    return jsonify({"ok": True, "event": updated})


@bp.post("/<event_id>/reject-replan")
def reject_replan(event_id):
    event = store().get_one("events", {"event_id": event_id})
    if not event or not event.get("pending_replan"):
        return api_error("No replan is awaiting a decision.", 409)
    store().update_one("events", {"event_id": event_id}, {"status": "conflict", "pending_replan": None})
    audit(store(), "Replan rejected", event_id, "Human rejected proposed replanning changes", actor="Campus Operations")
    return jsonify({"ok": True})


@bp.get("/<event_id>/assignments/<assignment_id>/alternatives")
def assignment_alternatives(event_id, assignment_id):
    event = store().get_one("events", {"event_id": event_id})
    assignment = store().get_one("assignments", {"assignment_id": assignment_id, "event_id": event_id})
    if not event or not assignment:
        return api_error("Assignment not found.", 404)
    if assignment.get("acceptance") != "declined":
        return api_error("Alternatives are available only for declined assignments.", 409)
    return jsonify({"ok": True, "alternatives": _find_assignment_alternatives(event, assignment)})


@bp.post("/<event_id>/assignments/<assignment_id>/replace")
def replace_assignment(event_id, assignment_id):
    event = store().get_one("events", {"event_id": event_id})
    assignment = store().get_one("assignments", {"assignment_id": assignment_id, "event_id": event_id})
    if not event or not assignment:
        return api_error("Assignment not found.", 404)
    if assignment.get("acceptance") != "declined":
        return api_error("Only declined assignments can be replaced.", 409)
    payload = request.get_json(silent=True) or {}
    replacement_id = str(payload.get("resource_id", "")).strip()
    replacement = next((item for item in _find_assignment_alternatives(event, assignment) if item["resource_id"] == replacement_id), None)
    if not replacement:
        return api_error("That replacement is no longer available.", 409)
    plan = dict(event.get("active_plan") or event.get("proposed_plan") or {})
    group = "volunteers" if assignment.get("resource_type") == "volunteer" else assignment.get("resource_type")
    plan[group] = [replacement if item.get("resource_id") == assignment.get("resource_id") else item for item in plan.get(group, [])]
    validation = validate_plan(store(), plan, _requirements(event_id), exclude_event_id=event_id)
    if not validation["valid"]:
        return api_error("The replacement creates a new plan conflict.", 409, validation=validation)
    store().update_one("assignments", {"assignment_id": assignment_id}, {"status": "released", "replacement_for": replacement_id})
    replacement_record = {"assignment_id": str(uuid.uuid4()), "resource_id": replacement_id, "event_id": event_id,
        "resource_type": assignment["resource_type"], "start_datetime": assignment["start_datetime"],
        "end_datetime": assignment["end_datetime"], "assignment_type": assignment.get("assignment_type"),
        "quantity": assignment.get("quantity", 1), "status": "locked", "acceptance": "pending", "replacement_for": assignment_id}
    store().insert("assignments", replacement_record)
    conflicts = [item for item in event.get("assignment_conflicts", []) if item != assignment_id]
    updated = store().update_one("events", {"event_id": event_id}, {"active_plan": plan, "proposed_plan": plan, "validation": validation, "assignment_conflicts": conflicts, "replacement_required": bool(conflicts)})
    _notify_assigned_people(event_id, {**plan, group: [replacement]})
    audit(store(), "Assignment replaced", event_id, f"Replaced declined assignment with {replacement_id}", actor="Campus Operations")
    return jsonify({"ok": True, "event": updated, "replacement": replacement_record})


def _requirements(event_id):
    requirements = store().get_all("event_requirements", {"event_id": event_id})
    return requirements[-1] if requirements else {}


def _timeline_quality(timeline):
    return (len(timeline), sum(bool(item.get("description")) for item in timeline), sum(bool(item.get("owner")) for item in timeline))


def _find_assignment_alternatives(event, assignment):
    kind = assignment.get("resource_type")
    collection = {"faculty": "faculty", "volunteer": "volunteers"}.get(kind)
    if not collection:
        return []
    id_key = {"faculty": "faculty_id", "volunteer": "volunteer_id"}[kind]
    requirements = _requirements(event["event_id"])
    people = [person for person in store().get_all(collection) if person.get(id_key) != assignment.get("resource_id")]
    scored = [score_person(person, requirements, assignment["start_datetime"], assignment["end_datetime"], store(), kind) for person in people]
    return [{"resource_id": item["resource_id"], "resource_type": kind, "name": item["resource"].get("name", item["resource_id"]), "score": item["score"],
             "available": item["available"], "positive_reasons": item["positive_reasons"], "negative_reasons": item["negative_reasons"]}
            for item in sorted(scored, key=lambda item: (item["available"], item["score"]), reverse=True) if item["available"]][:5]


def _lock_plan(event_id, plan):
    # Faculty and volunteers must accept their own assignment before it counts as
    # confirmed; every other lockable resource type has no sign-in account to accept it.
    needs_acceptance = {"faculty", "volunteers"}
    for group in ("labs", "venues", "faculty", "volunteers", "guests", "equipment", "vehicles"):
        for item in plan.get(group, []):
            record = {"assignment_id": str(uuid.uuid4()), "resource_id": item["resource_id"], "event_id": event_id, "resource_type": item["resource_type"],
                "start_datetime": plan["start_datetime"], "end_datetime": plan["end_datetime"], "assignment_type": item.get("assignment_type", group[:-1]), "quantity": item.get("quantity", 1), "status": "locked"}
            if group in needs_acceptance:
                record["acceptance"] = "pending"
            store().insert("assignments", record)
    audit(store(), "Resource locked", event_id, "All approved plan resources are represented by time-slot assignment records")


def _notify_assigned_people(event_id, plan):
    """Send member notices and optional email after the approved event is saved."""
    event = store().get_one("events", {"event_id": event_id}) or {}
    when = plan["start_datetime"].replace("T", " ")
    recipients = {
        "faculty": ("faculty", "faculty_id"),
        "volunteers": ("volunteers", "volunteer_id"),
        "guests": ("guests", "guest_id"),
    }
    for group, (collection, id_key) in recipients.items():
        for item in plan.get(group, []):
            person = store().get_one(collection, {id_key: item["resource_id"]}) or {}
            person_name = person.get("name") or item.get("name") or "Campus member"
            is_member = group in {"faculty", "volunteers"}
            message = f"You have been assigned to {event.get('title', 'a campus event')} on {when}."
            if is_member:
                message += " Please sign in to CampusFlow to accept or decline the assignment."
                notify(store(), "New event assignment", message, event_id, "info", item["resource_id"], item["resource_type"])
            delivery = send_email(
                current_app.config,
                person.get("email", ""),
                f"CampusFlow assignment: {event.get('title', 'Campus event')}",
                f"Hello {person_name},\n\n{message}\n\nCampusFlow AI",
            )
            if delivery == "sent":
                audit(store(), "Assignment email sent", event_id, f"Email sent to {group}: {item['resource_id']}")
            elif delivery == "failed":
                audit(store(), "Assignment email failed", event_id, f"Email delivery failed for {group}: {item['resource_id']}")


def _release_assignments(event_id):
    count = store().update_many("assignments", {"event_id": event_id, "status": "locked"}, {"status": "released"})
    if count:
        audit(store(), "Assignment released", event_id, f"Released {count} previous resource assignment(s)")


def _create_tasks(event_id, plan):
    store().delete_many("tasks", {"event_id": event_id})
    for title, owner, priority in [("Confirm venue and lab access", "Facilities", "high"), ("Test systems and required software", "IT Operations", "high"), ("Confirm faculty and guest speaker", "Academic Coordinator", "high"), ("Assign volunteer shifts", "Student Affairs", "medium"), ("Prepare registration desk", "Operations", "medium"), ("Arrange certificates and evaluation rubric", "Event Lead", "medium"), ("Publish in-app event briefing", "Communications", "low")]:
        store().insert("tasks", {"task_id": str(uuid.uuid4()), "event_id": event_id, "title": title, "owner": owner, "deadline": plan["start_datetime"], "priority": priority, "status": "todo"})


def _readiness(plan, req, validation, approved):
    categories = [bool(plan.get("labs") or plan.get("venues")), bool(plan.get("faculty")), bool(plan.get("volunteers")), bool(plan.get("equipment")), validation.get("valid"), approved]
    return round(sum(categories) / len(categories) * 100)


def _event_title(prompt):
    lower = prompt.lower()
    if "hackathon" in lower:
        return "AI Hackathon" if "ai" in lower else "Campus Hackathon"
    if "workshop" in lower:
        return "Campus Workshop"
    if "seminar" in lower:
        return "Campus Seminar"
    words = re.findall(r"[A-Za-z0-9]+", prompt)
    return " ".join(words[:5]).title() or "Campus Event"
