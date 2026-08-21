"""Rule-based specialist agents used by the CampusFlow prototype.

The predictable calculations deliberately stay in Python; an LLM can be added later
to improve wording and requirement extraction without replacing safety checks.
"""
from __future__ import annotations

import re
from math import ceil


def analyse_requirements(text: str) -> dict:
    lower = text.lower()
    attendance = re.search(r"(\d{2,5})\s*(?:students|participants|people|attendees)", lower)
    days = re.search(r"(\d+)\s*-?day", lower)
    competitions = re.search(r"(\d+)\s*(?:competitions?|contests?)", lower)
    workshops = re.search(r"(\d+)\s*workshops?", lower)
    name = "Campus Event"
    for keyword, label in [("technical fest", "Technical Fest"), ("hackathon", "Campus Hackathon"), ("placement", "Placement Drive"), ("conference", "Campus Conference"), ("workshop", "Campus Workshop")]:
        if keyword in lower:
            name = label
            break
    return {"name": name, "description": text.strip(), "participants": int(attendance.group(1)) if attendance else 200,
            "days": int(days.group(1)) if days else 1, "competitions": int(competitions.group(1)) if competitions else 1,
            "workshops": int(workshops.group(1)) if workshops else 1,
            "needs_inauguration": "inauguration" in lower or "opening" in lower}


def choose_venue(venues: list[dict], people: int, activity: str) -> dict:
    suitable = [v for v in venues if v["available"] and v["capacity"] >= people]
    if not suitable:
        return {"name": "UNASSIGNED", "capacity": 0, "features": "No suitable venue"}
    if "workshop" in activity.lower() or "coding" in activity.lower():
        lab = next((v for v in suitable if "Lab" in v["name"]), None)
        if lab:
            return lab
    return min(suitable, key=lambda v: v["capacity"])


def build_plan(requirements: dict, venues: list[dict]) -> dict:
    activities = []
    if requirements["needs_inauguration"]:
        activities.append(("Inauguration", requirements["participants"], "09:00", "10:00", ["Projectors", "Microphones"]))
    activities.append(("Coding Competition", min(requirements["participants"], 120), "10:30", "13:00", ["Laptop kits", "Projectors"]))
    for i in range(requirements["workshops"]):
        activities.append((f"Workshop {i + 1}", min(requirements["participants"], 180), "14:00", "16:00", ["Projectors", "Microphones"]))
    for i in range(max(requirements["competitions"] - 1, 0)):
        activities.append((f"Competition {i + 2}", min(requirements["participants"], 250), "10:30", "13:00", ["Projectors"]))
    schedule = []
    for index, (activity, people, start, end, equipment) in enumerate(activities):
        day = index % requirements["days"] + 1
        venue = choose_venue(venues, people, activity)
        schedule.append({"activity": activity, "day": day, "start": start, "end": end, "venue": venue["name"], "participants": people, "equipment": equipment})
    volunteer_count = max(10, ceil(requirements["participants"] / 25))
    tasks = [
        {"title": "Confirm venue bookings", "owner": "Venue Team", "deadline": "7 days before event", "priority": "High"},
        {"title": f"Assign {volunteer_count} volunteers", "owner": "Volunteer Lead", "deadline": "5 days before event", "priority": "High"},
        {"title": "Test equipment and Wi-Fi", "owner": "Tech Team", "deadline": "2 days before event", "priority": "Medium"},
        {"title": "Share stakeholder briefing", "owner": "Communications", "deadline": "1 day before event", "priority": "Medium"},
    ]
    return {**requirements, "schedule": schedule, "volunteers_needed": volunteer_count, "security_needed": max(2, ceil(requirements["participants"] / 150)), "tasks": tasks,
            "approvals": [{"item": "Venue permissions", "reason": "Campus facilities must be approved by administration"}, {"item": "Security plan", "reason": "Large-attendance event requires security review"}, {"item": "Budget estimate", "reason": "Equipment and support costs need faculty approval"}]}


def overlaps(first: dict, second: dict) -> bool:
    return first["start_time"] < second["end_time"] and second["start_time"] < first["end_time"]


def detect_conflicts(schedule: list[dict], venues: list[dict], resources: list[dict]) -> list[dict]:
    conflicts = []
    capacity = {v["name"]: v["capacity"] for v in venues}
    for item in schedule:
        if item["participants"] > capacity.get(item["venue"], 0):
            conflicts.append({"type": "Capacity", "message": f"{item['activity']} has {item['participants']} people but {item['venue']} holds {capacity.get(item['venue'], 0)}."})
    for index, first in enumerate(schedule):
        for second in schedule[index + 1:]:
            if first["day"] == second["day"] and first["venue"] == second["venue"] and overlaps(first, second):
                conflicts.append({"type": "Double booking", "message": f"{first['venue']} is booked for both {first['activity']} and {second['activity']} at overlapping times."})
    stock = {r["name"]: r["quantity"] for r in resources}
    for item in schedule:
        used = item.get("equipment", [])
        for equipment in used:
            same_time = [x for x in schedule if x["day"] == item["day"] and overlaps(item, x) and equipment in x.get("equipment", [])]
            if len(same_time) > stock.get(equipment, 0):
                conflicts.append({"type": "Resource", "message": f"{equipment} is over-allocated during {item['start_time']}–{item['end_time']} on Day {item['day']}."})
    return conflicts


def alternatives(conflict: dict, schedule: list[dict], venues: list[dict]) -> str:
    if conflict["type"] == "Double booking":
        booked = {item["venue"] for item in schedule}
        free = next((v for v in venues if v["name"] not in booked), None)
        return f"Move one activity to {free['name']} (capacity {free['capacity']}) or change it to a later time slot." if free else "Move one activity to a later time slot."
    if conflict["type"] == "Capacity":
        return "Move this activity to Main Auditorium or Open Ground, then request approval for the change."
    return "Use a different time slot or request additional equipment from the central store."
