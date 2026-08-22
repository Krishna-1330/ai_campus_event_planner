from __future__ import annotations

from services.availability_service import member_is_available, resource_is_available, workload_for_day


def _words(requirements: dict):
    text = " ".join([requirements.get("event_type", ""), *requirements.get("topics", []), *requirements.get("required_software", [])]).lower()
    return set(text.replace("/", " ").replace(",", " ").split())


def _overlap(values, terms):
    haystack = " ".join(values or []).lower()
    return any(term in haystack for term in terms)


def score_person(person: dict, requirements: dict, start: str, end: str, store, person_type: str):
    terms = _words(requirements)
    score, positive, negative = 35, [], []
    department_match = person.get("department") in requirements.get("preferred_departments", [])
    if department_match:
        score += 18; positive.append(f"{person['department']} department match +18")
    skills = person.get("expertise", []) + person.get("skills", []) + person.get("subjects", []) + person.get("interests", [])
    if _overlap(skills, terms):
        score += 24; positive.append("Topic and expertise match +24")
    else:
        negative.append("Limited direct topic overlap")
    if person_type == "volunteer" and _overlap(person.get("preferred_roles", []), [r.lower() for r in requirements.get("required_roles", [])]):
        score += 12; positive.append("Preferred event role +12")
    available = resource_is_available(store, person[_id_key(person_type)], start, end)
    if person_type in {"faculty", "volunteer"}:
        available = available and member_is_available(store, person[_id_key(person_type)], start)
    if available:
        score += 18; positive.append("Available in requested time +18")
    else:
        negative.append("Time-slot conflict")
    workload = workload_for_day(store, person[_id_key(person_type)], start, person_type)
    max_events = person.get("max_events_per_day", 1)
    if workload < max_events:
        score += 5; positive.append("Low workload +5")
    else:
        negative.append("Daily workload limit reached")
    # ``busy`` is a temporary current-time indicator. Time-slot availability
    # remains the source of truth for the requested event time.
    if person.get("status") == "inactive":
        score -= 50; negative.append("Inactive resource")
    return {"resource": person, "resource_id": person[_id_key(person_type)], "score": max(0, min(100, score)), "positive_reasons": positive,
            "negative_reasons": negative, "available": available and workload < max_events, "workload": workload}


def _id_key(person_type: str):
    return {"faculty": "faculty_id", "volunteer": "volunteer_id", "guest": "guest_id"}[person_type]


def score_guest(guest: dict, requirements: dict, start: str, end: str, store):
    terms = _words(requirements)
    score, positive, negative = 42, [], []
    if _overlap(guest.get("expertise", []), terms):
        score += 30; positive.append("Relevant expertise +30")
    if requirements.get("event_type") in guest.get("suitable_event_types", []):
        score += 12; positive.append("Suitable event format +12")
    available = resource_is_available(store, guest["guest_id"], start, end)
    if available:
        score += 16; positive.append("Available in requested time +16")
    else:
        negative.append("Time-slot conflict")
    return {"resource": guest, "resource_id": guest["guest_id"], "score": min(score, 100), "positive_reasons": positive,
            "negative_reasons": negative, "available": available, "workload": workload_for_day(store, guest["guest_id"], start, "guest")}
