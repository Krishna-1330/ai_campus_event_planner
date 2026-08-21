"""Server-side OpenAI integration for natural-language planning insights."""
from __future__ import annotations

import json
import os

from dotenv import load_dotenv

load_dotenv()


def ai_is_configured() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def fallback_insights(message: str) -> dict:
    return {
        "enabled": False,
        "summary": message,
        "venue_reasoning": "Venues were selected by capacity and activity requirements.",
        "risks": ["Review approvals before event day."],
        "stakeholder_briefing": "Draft plan is ready for coordinator review.",
    }


def enrich_plan(brief: str, plan: dict) -> dict:
    """Ask OpenAI for explanations, without allowing it to overwrite safe plan data."""
    if not ai_is_configured():
        return fallback_insights("AI key not configured. CampusFlow used its local planning agents.")
    try:
        from openai import OpenAI

        client = OpenAI()
        prompt = f"""You are the communication layer of a campus event-planning system.
Event brief: {brief}
Reliable Python planning output: {json.dumps(plan, default=str)}

Do not change the schedule, capacity numbers, resources, or approvals. Explain them.
Return ONLY valid JSON with exactly these fields: summary (string), venue_reasoning
(string), risks (array of 3 short strings), stakeholder_briefing (string of at
most 90 words). Keep the writing practical and concise."""
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-5.6"),
            input=prompt,
        )
        data = json.loads(response.output_text)
        return {"enabled": True, **data}
    except Exception as exc:
        result = fallback_insights("OpenAI was unavailable, so local planning agents completed the plan.")
        result["error"] = str(exc)
        return result
