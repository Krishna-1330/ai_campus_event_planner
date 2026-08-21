"""REST API backend for CampusFlow AI.

Run with: uvicorn backend:app --reload --port 8000
API documentation: http://127.0.0.1:8000/docs
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ai_service import ai_is_configured, enrich_plan
from database import DB_PATH, add_resource, add_venue, authenticate, create_event, create_user, execute, initialize_database, notify, rows
from planner import alternatives, analyse_requirements, build_plan, detect_conflicts

app = FastAPI(title="CampusFlow AI API", version="1.0.0", description="Backend for campus event planning and coordination.")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


class Credentials(BaseModel):
    email: str
    password: str = Field(min_length=1)


class Registration(Credentials):
    name: str = Field(min_length=2)


class Brief(BaseModel):
    description: str = Field(min_length=10)


class StatusUpdate(BaseModel):
    status: str


class Message(BaseModel):
    message: str = Field(min_length=1)


class VenueCreate(BaseModel):
    name: str = Field(min_length=2)
    capacity: int = Field(gt=0)
    features: str = Field(min_length=2)


class ResourceCreate(BaseModel):
    name: str = Field(min_length=2)
    quantity: int = Field(gt=0)
    category: str = Field(min_length=2)


@app.on_event("startup")
def start() -> None:
    initialize_database()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "online", "service": "CampusFlow AI backend", "openai": "configured" if ai_is_configured() else "not configured"}


@app.get("/api/database/status")
def database_status() -> dict[str, object]:
    """A safe status endpoint: it confirms the database without exposing its contents."""
    return {
        "status": "connected",
        "engine": "SQLite",
        "database": DB_PATH.name,
        "counts": {
            "users": len(rows("SELECT id FROM users")),
            "events": len(rows("SELECT id FROM events")),
            "venues": len(rows("SELECT id FROM venues")),
            "resources": len(rows("SELECT id FROM resources")),
        },
    }


@app.post("/api/auth/login")
def login(credentials: Credentials) -> dict[str, Any]:
    user = authenticate(credentials.email, credentials.password)
    if not user:
        raise HTTPException(401, "Incorrect email or password")
    return {"user": user}


@app.post("/api/auth/register", status_code=201)
def register(payload: Registration) -> dict[str, str]:
    if not create_user(payload.name, payload.email, payload.password):
        raise HTTPException(409, "An account with this email already exists")
    return {"message": "Account created"}


@app.get("/api/events")
def events() -> list[dict]:
    return rows("SELECT * FROM events ORDER BY id DESC")


@app.get("/api/events/{event_id}")
def event(event_id: int) -> dict:
    found = rows("SELECT * FROM events WHERE id = ?", (event_id,))
    if not found:
        raise HTTPException(404, "Event not found")
    return found[0]


@app.get("/api/events/{event_id}/schedule")
def schedule(event_id: int) -> list[dict]:
    result = rows("SELECT * FROM schedules WHERE event_id = ? ORDER BY day, start_time", (event_id,))
    for item in result:
        item["equipment"] = json.loads(item["equipment"])
    return result


@app.post("/api/plan")
def make_plan(brief: Brief) -> dict:
    requirements = analyse_requirements(brief.description)
    venues = rows("SELECT * FROM venues ORDER BY capacity DESC")
    plan = build_plan(requirements, venues)
    plan["ai_insights"] = enrich_plan(brief.description, plan)
    return plan


@app.post("/api/events", status_code=201)
def save_event(plan: dict) -> dict[str, int]:
    required = {"name", "description", "participants", "days", "schedule", "tasks", "approvals"}
    if not required.issubset(plan):
        raise HTTPException(422, "This is not a complete event plan")
    return {"event_id": create_event(plan)}


@app.get("/api/venues")
def venues() -> list[dict]:
    return rows("SELECT * FROM venues ORDER BY capacity DESC")


@app.post("/api/venues", status_code=201)
def create_venue(payload: VenueCreate) -> dict[str, str]:
    try:
        add_venue(payload.name, payload.capacity, payload.features)
    except Exception as exc:
        raise HTTPException(409, "Venue name already exists") from exc
    return {"message": "Venue added"}


@app.get("/api/resources")
def resources() -> list[dict]:
    return rows("SELECT * FROM resources ORDER BY category, name")


@app.post("/api/resources", status_code=201)
def create_resource(payload: ResourceCreate) -> dict[str, str]:
    try:
        add_resource(payload.name, payload.quantity, payload.category)
    except Exception as exc:
        raise HTTPException(409, "Resource name already exists") from exc
    return {"message": "Resource added"}


@app.post("/api/events/{event_id}/conflicts")
def check_conflicts(event_id: int) -> list[dict]:
    event_schedule = schedule(event_id)
    conflicts = detect_conflicts(event_schedule, venues(), resources())
    return [{**conflict, "recommendation": alternatives(conflict, event_schedule, venues())} for conflict in conflicts]


@app.get("/api/events/{event_id}/tasks")
def tasks(event_id: int) -> list[dict]:
    return rows("SELECT * FROM tasks WHERE event_id = ? ORDER BY id DESC", (event_id,))


@app.patch("/api/tasks/{task_id}")
def update_task(task_id: int, update: StatusUpdate) -> dict[str, str]:
    execute("UPDATE tasks SET status = ? WHERE id = ?", (update.status, task_id))
    return {"message": "Task updated"}


@app.get("/api/events/{event_id}/approvals")
def approvals(event_id: int) -> list[dict]:
    return rows("SELECT * FROM approvals WHERE event_id = ?", (event_id,))


@app.patch("/api/approvals/{approval_id}")
def update_approval(approval_id: int, update: StatusUpdate) -> dict[str, str]:
    execute("UPDATE approvals SET status = ? WHERE id = ?", (update.status, approval_id))
    return {"message": "Approval updated"}


@app.get("/api/events/{event_id}/notifications")
def notifications(event_id: int) -> list[dict]:
    return rows("SELECT * FROM notifications WHERE event_id = ? ORDER BY id DESC", (event_id,))


@app.post("/api/events/{event_id}/notifications", status_code=201)
def create_notification(event_id: int, payload: Message) -> dict[str, str]:
    notify(event_id, payload.message)
    return {"message": "Notification added"}
