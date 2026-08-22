"""Gemini is optional enrichment; deterministic parsing remains a safe fallback."""
from __future__ import annotations

import base64
from datetime import date
import json
import re
import requests


def fallback_requirements(prompt: str) -> dict:
    text = prompt.lower()
    attendees = _number_before(text, r"(?:students|participants|attendees)") or 80
    faculty = _number_before(text, r"faculty") or (2 if "hackathon" in text else 1)
    volunteers = _number_before(text, r"volunteers?") or (5 if "hackathon" in text else 3)
    guests = _number_before(text, r"guest(?: speaker)?") or (1 if "hackathon" in text else 0)
    days = _number_before(text, r"day") or 1
    event_type = "hackathon" if "hackathon" in text else "workshop" if "workshop" in text else "seminar" if "seminar" in text else "campus event"
    software = []
    for canonical, aliases in {"Python": ["python"], "VS Code": ["vs code", "vscode"], "Jupyter": ["jupyter"]}.items():
        if any(alias in text for alias in aliases): software.append(canonical)
    if event_type == "hackathon":
        software = list(dict.fromkeys(software + ["Python", "VS Code"]))
    equipment = []
    for label, words, default in [("Projector", ["projector"], 2), ("Microphone", ["microphone", "mic"], 2), ("Speaker", ["speaker"], 2)]:
        if any(word in text for word in words) or event_type == "hackathon": equipment.append({"type": label, "quantity": default})
    return {"event_type": event_type, "expected_attendees": attendees, "duration_days": days, "duration_hours": 7 if days == 1 else 7 * days,
            "preferred_departments": ["CSE", "IT"], "required_faculty": faculty, "required_volunteers": volunteers, "required_guests": guests,
            "venue_type": "Computer Lab" if event_type == "hackathon" else "Seminar Hall", "minimum_capacity": attendees, "required_systems": attendees if event_type == "hackathon" else 0,
            "required_equipment": equipment, "required_software": software, "required_roles": ["Technical Support", "Registration", "Logistics", "Help Desk"],
            "topics": ["AI", "Machine Learning", "Python"] if "ai" in text or event_type == "hackathon" else [event_type.title()], "source": "deterministic fallback"}


def extract_requirements(prompt: str, api_key: str = "") -> dict:
    fallback = fallback_requirements(prompt)
    if not api_key:
        return fallback
    schema = {"type": "OBJECT", "properties": {"event_type": {"type": "STRING"}, "expected_attendees": {"type": "INTEGER"}, "duration_days": {"type": "INTEGER"}, "required_faculty": {"type": "INTEGER"}, "required_volunteers": {"type": "INTEGER"}, "required_guests": {"type": "INTEGER"}, "required_systems": {"type": "INTEGER"}, "required_software": {"type": "ARRAY", "items": {"type": "STRING"}}, "topics": {"type": "ARRAY", "items": {"type": "STRING"}}}}
    instruction = "Extract campus event requirements as JSON. Do not invent exact availability. " + json.dumps({"request": prompt, "fallback_defaults": fallback})
    try:
        response = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent", params={"key": api_key}, timeout=12,
            # The REST GenerateContent API uses snake_case fields here (verified against
            # the official Gemini API reference); schema values use Gemini's enum casing.
            json={"contents": [{"parts": [{"text": instruction}]}], "generationConfig": {"response_mime_type": "application/json", "response_schema": schema}})
        response.raise_for_status()
        parsed = json.loads(response.json()["candidates"][0]["content"]["parts"][0]["text"])
        for field in ("event_type", "expected_attendees", "duration_days", "required_faculty", "required_volunteers", "required_guests", "required_systems", "required_software", "topics"):
            if field in parsed and parsed[field] not in (None, "", []): fallback[field] = parsed[field]
        fallback["minimum_capacity"] = fallback["expected_attendees"]
        fallback["source"] = "Gemini structured extraction + deterministic defaults"
    except (requests.RequestException, ValueError, KeyError, TypeError):
        fallback["source"] = "deterministic fallback (Gemini unavailable)"
    return fallback


def extract_calendar_from_image(image_bytes: bytes, mime_type: str, api_key: str = "") -> tuple[list[dict] | None, str | None]:
    """Read reliably dated working and holiday entries from a timetable image."""
    if not api_key:
        return None, "Set GEMINI_API_KEY to read timetable images automatically. You can still add calendar days manually or by CSV."
    schema = {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {
                "date": {"type": "STRING"},
                "type": {"type": "STRING"},
                "reason": {"type": "STRING"},
                "available": {"type": "BOOLEAN"},
            },
        },
    }
    instruction = (
        "Read this academic timetable or calendar image. Return one JSON item for each date where an exact "
        "YYYY-MM-DD date and its working/holiday status are clearly visible. Use available=true for working "
        "instructional days and available=false for holidays, closures, exams, or other unavailable days. "
        "Use a concise reason. Do not invent dates, years, colors, or statuses that are unclear in the image."
    )
    try:
        response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
            params={"key": api_key},
            timeout=20,
            json={
                "contents": [{"parts": [
                    {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode("ascii")}},
                    {"text": instruction},
                ]}],
                "generationConfig": {"response_mime_type": "application/json", "response_schema": schema},
            },
        )
        response.raise_for_status()
        parsed = json.loads(response.json()["candidates"][0]["content"]["parts"][0]["text"])
        if not isinstance(parsed, list):
            raise ValueError("Expected a list of calendar entries.")
        records = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            day = str(item.get("date", "")).strip()
            date.fromisoformat(day)
            available = item.get("available")
            if not isinstance(available, bool):
                available = str(available).lower() in {"true", "1", "yes", "working"}
            records.append({
                "date": day,
                "type": str(item.get("type") or ("Working Day" if available else "Holiday")).strip(),
                "reason": str(item.get("reason") or ("Recognized from timetable image")).strip(),
                "available": available,
            })
        return records, None
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None, "CampusFlow could not read dated working and holiday entries from that image. Use a clearer image, or add the dates by CSV or manually."


def _number_before(text: str, noun_pattern: str):
    match = re.search(r"(\d+)\s+(?:[\w-]+\s+){0,2}" + noun_pattern, text)
    return int(match.group(1)) if match else None
