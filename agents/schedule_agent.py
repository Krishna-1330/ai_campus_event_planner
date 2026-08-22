from __future__ import annotations

from datetime import date, timedelta


def recommend_slot(store, requirements: dict):
    """Returns next permitted working day; resource conflicts are validated downstream."""
    today = date.today()
    for offset in range(1, 45):
        candidate = today + timedelta(days=offset)
        calendar = store.get_one("academic_calendar", {"date": candidate.isoformat()})
        if calendar and calendar.get("available"):
            return {"start_datetime": f"{candidate.isoformat()}T09:00:00", "end_datetime": f"{candidate.isoformat()}T16:00:00", "reason": f"{calendar['type']} with campus operating hours available"}
    return {"start_datetime": None, "end_datetime": None, "reason": "No working day in planning horizon"}
