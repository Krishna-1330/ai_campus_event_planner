from __future__ import annotations

from datetime import datetime

from agents import event_understanding, schedule_agent, venue_agent, people_agent, resource_agent, conflict_agent, communication_agent


AGENT_NAMES = ["Event Understanding", "Schedule Agent", "Venue Agent", "People Agent", "Resource Agent", "Conflict Agent", "Coordinator"]


def generate_plan(store, event: dict, gemini_key: str = ""):
    requirements = event_understanding.run(event["prompt"], gemini_key)
    slot = schedule_agent.recommend_slot(store, requirements)
    workflow = [{"name": name, "status": "completed", "detail": "Completed deterministic hand-off"} for name in AGENT_NAMES]
    if not slot["start_datetime"]:
        workflow[1].update(status="conflict", detail="No permitted academic date found")
        return {"requirements": requirements, "workflow": workflow, "plan": None, "validation": {"valid": False, "errors": [slot["reason"]], "checks": []}}
    labs = venue_agent.recommend_labs(store, requirements, slot["start_datetime"], slot["end_datetime"])
    venues = [] if requirements.get("required_systems", 0) else venue_agent.recommend_venues(store, requirements, slot["start_datetime"], slot["end_datetime"])[:1]
    people = people_agent.recommend_people(store, requirements, slot["start_datetime"], slot["end_datetime"])
    plan = {"start_datetime": slot["start_datetime"], "end_datetime": slot["end_datetime"], "schedule_reason": slot["reason"], "labs": labs, "venues": venues,
            "faculty": people["faculty"], "volunteers": people["volunteers"], "guests": people["guests"], "equipment": resource_agent.recommend_equipment(store, requirements, slot["start_datetime"], slot["end_datetime"]),
            "vehicles": resource_agent.recommend_vehicle(store, requirements, slot["start_datetime"], slot["end_datetime"]), "match_details": people["match_details"],
            "timeline": _timeline_for(requirements)}
    validation = conflict_agent.run(store, plan, requirements)
    if not validation["valid"]:
        workflow[-2].update(status="conflict", detail="Constraint validation found blocking issues")
    explanation = _explanation(event, requirements, plan, validation)
    return {"requirements": requirements, "workflow": workflow, "plan": plan, "validation": validation, "explanation": explanation, "messages": communication_agent.messages_for_plan(event, plan)}


def _explanation(event, req, plan, validation):
    labs = ", ".join(item["name"] for item in plan.get("labs", [])) or ", ".join(item["name"] for item in plan.get("venues", []))
    return f"CampusFlow interpreted {event['title']} as a {req['event_type']} for {req['expected_attendees']} attendees. It selected {labs or 'no location'} after checking the academic calendar, capacity, installed software, overlapping assignments and workload limits. {len(validation['checks'])} deterministic constraints were evaluated."


def _timeline_for(requirements):
    event_type = requirements.get("event_type", "event")
    activity = {"workshop": "Lead the hands-on workshop activity and support participants.", "seminar": "Deliver the seminar content and take questions from attendees.", "hackathon": "Run the build activity, mentor teams, and track progress."}.get(event_type, "Run the main event activity and support participants.")
    return [{"time": "09:00", "title": "Check-in and registration", "description": "Welcome attendees, verify registration, and hand out badges.", "owner": "Operations"}, {"time": "09:30", "title": "Opening briefing", "description": f"Explain the {event_type} agenda, expectations, safety rules, and team instructions.", "owner": "Faculty"}, {"time": "10:00", "title": "Main activity", "description": activity, "owner": "Participants"}, {"time": "13:00", "title": "Questions and discussion", "description": "Facilitate questions, clarify the work, and record important follow-ups.", "owner": "Faculty"}, {"time": "15:00", "title": "Wrap-up and evaluation", "description": "Review outcomes, collect feedback, and announce the next steps.", "owner": "Event Lead"}]
