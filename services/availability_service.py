from __future__ import annotations

from datetime import datetime


ACTIVE_ASSIGNMENT_STATUSES = {"locked", "active", "outage"}
MEMBER_ASSIGNMENT_STATUSES = {"locked", "active"}


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def overlaps(existing_start: str, existing_end: str, requested_start: str, requested_end: str) -> bool:
    """Canonical overlap rule: start < requested_end AND end > requested_start."""
    return parse_time(existing_start) < parse_time(requested_end) and parse_time(existing_end) > parse_time(requested_start)


def overlapping_assignments(store, resource_id: str, start: str, end: str, exclude_event_id: str | None = None):
    records = store.get_all("assignments", {"resource_id": resource_id})
    return [assignment for assignment in records
            if assignment.get("status") in ACTIVE_ASSIGNMENT_STATUSES
            and assignment.get("event_id") != exclude_event_id
            and overlaps(assignment["start_datetime"], assignment["end_datetime"], start, end)]


def resource_is_available(store, resource_id: str, start: str, end: str, exclude_event_id: str | None = None):
    return not overlapping_assignments(store, resource_id, start, end, exclude_event_id)


def member_is_available(store, resource_id: str, start: str, exclude_event_id: str | None = None) -> bool:
    """Accepted faculty/volunteer assignments reserve the whole calendar day."""
    requested_day = parse_time(start).date()
    return not any(
        assignment.get("status") in MEMBER_ASSIGNMENT_STATUSES
        and assignment.get("acceptance") == "accepted"
        and assignment.get("event_id") != exclude_event_id
        and parse_time(assignment["start_datetime"]).date() == requested_day
        for assignment in store.get_all("assignments", {"resource_id": resource_id})
    )


def equipment_available_quantity(store, equipment: dict, start: str, end: str, exclude_event_id: str | None = None) -> int:
    occupied = sum(a.get("quantity", 1) for a in overlapping_assignments(store, equipment["equipment_id"], start, end, exclude_event_id))
    return max(0, equipment["total_quantity"] - occupied)


def workload_for_day(store, resource_id: str, start: str, resource_type: str, exclude_event_id: str | None = None) -> int:
    day = parse_time(start).date()
    return sum(1 for assignment in store.get_all("assignments", {"resource_id": resource_id})
               if assignment.get("resource_type") == resource_type
               and assignment.get("status") in ACTIVE_ASSIGNMENT_STATUSES
               and assignment.get("event_id") != exclude_event_id
               and parse_time(assignment["start_datetime"]).date() == day)


def sync_member_activity_statuses(store, now: datetime | None = None) -> int:
    """Set member status automatically from accepted assignments in progress.

    ``inactive`` remains an administrator-controlled state.  ``busy`` is a
    temporary system state: it is set only while an accepted assignment is
    happening now and automatically returns to ``active`` afterwards.
    """
    now = now or datetime.now()
    assignments = store.get_all("assignments")
    changed = 0
    for collection, id_key in (("faculty", "faculty_id"), ("volunteers", "volunteer_id")):
        for member in store.get_all(collection):
            if member.get("status") == "inactive":
                continue
            member_id = member.get(id_key)
            busy_now = any(
                assignment.get("resource_id") == member_id
                and assignment.get("status") in MEMBER_ASSIGNMENT_STATUSES
                and assignment.get("acceptance") == "accepted"
                and parse_time(assignment["start_datetime"]) <= now < parse_time(assignment["end_datetime"])
                for assignment in assignments
            )
            next_status = "busy" if busy_now else "active"
            if member.get("status") != next_status:
                store.update_one(collection, {id_key: member_id}, {"status": next_status})
                changed += 1
    return changed
