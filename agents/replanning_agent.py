from __future__ import annotations

from agents.venue_agent import recommend_labs, recommend_venues
from agents.people_agent import recommend_people
from agents.resource_agent import recommend_equipment, recommend_vehicle
from agents.conflict_agent import run as validate


def run(store, current_plan, requirements, event_id, unavailable_resource_id):
    """Propose alternatives without releasing any existing locks. Human approval applies changes."""
    start, end = current_plan["start_datetime"], current_plan["end_datetime"]
    labs = recommend_labs(store, requirements, start, end, {unavailable_resource_id})
    venues = current_plan.get("venues", [])
    if requirements.get("required_systems", 0) == 0:
        alternatives = recommend_venues(store, requirements, start, end, {unavailable_resource_id})
        venues = alternatives[:1]
    people = recommend_people(store, requirements, start, end)
    proposal = {**current_plan, "labs": labs, "venues": venues, "faculty": people["faculty"], "volunteers": people["volunteers"], "guests": people["guests"],
                "equipment": recommend_equipment(store, requirements, start, end), "vehicles": recommend_vehicle(store, requirements, start, end), "match_details": people["match_details"]}
    result = validate(store, proposal, requirements, exclude_event_id=event_id)
    old_ids = {item["resource_id"] for item in current_plan.get("labs", []) + current_plan.get("venues", [])}
    new_ids = {item["resource_id"] for item in proposal.get("labs", []) + proposal.get("venues", [])}
    changes = []
    if old_ids != new_ids:
        changes.append("Venue/lab allocation changed")
    old_vols = {item["resource_id"] for item in current_plan.get("volunteers", [])}
    new_vols = {item["resource_id"] for item in proposal.get("volunteers", [])}
    if old_vols != new_vols:
        changes.append(f"{len(old_vols.symmetric_difference(new_vols))} volunteer assignment(s) changed")
    if not changes:
        changes.append("Constraint validation rerun; all existing allocations remain compatible")
    return {"valid": result["valid"], "proposal": proposal, "validation": result, "changes": changes, "impact": "LOW" if result["valid"] else "HIGH", "reason": f"Resource {unavailable_resource_id} was marked unavailable for this time slot."}
