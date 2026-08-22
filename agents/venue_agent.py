from __future__ import annotations

from itertools import combinations

from services.availability_service import resource_is_available


def recommend_labs(store, requirements, start, end, excluded_ids=None, exclude_event_id=None):
    excluded_ids = set(excluded_ids or [])
    required_systems = requirements.get("required_systems", 0)
    required_software = {item.lower() for item in requirements.get("required_software", [])}
    candidates = []
    for lab in store.get_all("labs"):
        installed = {item.lower() for item in lab.get("installed_software", [])}
        if lab["lab_id"] not in excluded_ids and lab.get("status") == "active" and required_software.issubset(installed) and resource_is_available(store, lab["lab_id"], start, end, exclude_event_id):
            candidates.append(lab)
    single_labs = [lab for lab in candidates if lab["number_of_systems"] >= required_systems]
    if single_labs:
        best = min(single_labs, key=lambda lab: (lab["number_of_systems"] - required_systems, lab["number_of_systems"]))
        score = round(required_systems / best["number_of_systems"] * 100) if required_systems else 100
        return [{"resource_id": best["lab_id"], "resource_type": "lab", "name": best["lab_name"], "quantity": 1,
                 "score": score, "positive_reasons": [f"{best['number_of_systems']} systems", "Required software installed", "Available in selected slot"], "negative_reasons": []}]
    for length in range(1, min(4, len(candidates)) + 1):
        valid = [combo for combo in combinations(candidates, length) if sum(lab["number_of_systems"] for lab in combo) >= required_systems]
        if valid:
            best = min(valid, key=lambda combo: (sum(l["number_of_systems"] for l in combo) - required_systems, len(combo)))
            total_systems = sum(lab["number_of_systems"] for lab in best)
            score = round(required_systems / total_systems * 100) if required_systems and total_systems else 100
            return [{"resource_id": lab["lab_id"], "resource_type": "lab", "name": lab["lab_name"], "quantity": 1,
                     "score": score, "positive_reasons": [f"{lab['number_of_systems']} systems", "Required software installed", "Available in selected slot"], "negative_reasons": []} for lab in best]
    return []


def recommend_venues(store, requirements, start, end, excluded_ids=None, exclude_event_id=None):
    excluded_ids = set(excluded_ids or [])
    matches = []
    for venue in store.get_all("venues"):
        if venue["venue_id"] in excluded_ids or venue.get("status") != "active":
            continue
        if venue["capacity"] >= requirements.get("minimum_capacity", 0) and resource_is_available(store, venue["venue_id"], start, end, exclude_event_id):
            required_capacity = requirements.get("minimum_capacity", 0)
            score = round(required_capacity / venue["capacity"] * 100) if required_capacity else 100
            matches.append({"resource_id": venue["venue_id"], "resource_type": "venue", "name": venue["name"], "quantity": 1, "score": score,
                            "positive_reasons": [f"Capacity fit {required_capacity}/{venue['capacity']}", "Available in selected slot"], "negative_reasons": []})
    return sorted(matches, key=lambda item: item["score"], reverse=True)
