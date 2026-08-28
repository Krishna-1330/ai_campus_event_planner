"""CampusFlow collection definitions for an empty first-run workspace."""
from __future__ import annotations


CAMPUS_COLLECTIONS = (
    "faculty", "volunteers", "guests", "venues", "blocks", "labs",
    "equipment", "vehicles", "academic_calendar", "events",
    "event_requirements", "assignments", "tasks", "notifications",
    "audit_logs", "users", "organizers",
)


def empty_collections():
    return {collection: [] for collection in CAMPUS_COLLECTIONS}
