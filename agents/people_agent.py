from __future__ import annotations

from services.matching_service import score_person, score_guest


def recommend_people(store, requirements, start, end):
    faculty = sorted([score_person(row, requirements, start, end, store, "faculty") for row in store.get_all("faculty")], key=lambda row: row["score"], reverse=True)
    volunteers = sorted([score_person(row, requirements, start, end, store, "volunteer") for row in store.get_all("volunteers")], key=lambda row: row["score"], reverse=True)
    guests = sorted([score_guest(row, requirements, start, end, store) for row in store.get_all("guests")], key=lambda row: row["score"], reverse=True)
    return {
        "faculty": [_assignment(row, "faculty", "mentor") for row in faculty if row["available"]][:requirements.get("required_faculty", 0)],
        "volunteers": [_assignment(row, "volunteer", "event volunteer") for row in volunteers if row["available"]][:requirements.get("required_volunteers", 0)],
        "guests": [_assignment(row, "guest", "guest speaker") for row in guests if row["available"]][:requirements.get("required_guests", 0)],
        "match_details": {"faculty": faculty[:5], "volunteers": volunteers[:8], "guests": guests[:5]},
    }


def _assignment(match, resource_type, assignment_type):
    person = match["resource"]
    return {"resource_id": match["resource_id"], "resource_type": resource_type, "name": person["name"], "quantity": 1, "assignment_type": assignment_type,
            "score": match["score"], "positive_reasons": match["positive_reasons"], "negative_reasons": match["negative_reasons"], "workload": match["workload"]}
