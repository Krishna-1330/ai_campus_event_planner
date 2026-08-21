"""Small SQLite data layer for the CampusFlow demo."""
from __future__ import annotations

import json
import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).with_name("campusflow.db")


def connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database() -> None:
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                participants INTEGER NOT NULL,
                days INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'Draft',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'Coordinator',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS venues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                capacity INTEGER NOT NULL,
                features TEXT NOT NULL,
                available INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                quantity INTEGER NOT NULL,
                category TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                activity TEXT NOT NULL,
                day INTEGER NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                venue TEXT NOT NULL,
                participants INTEGER NOT NULL,
                equipment TEXT NOT NULL,
                FOREIGN KEY(event_id) REFERENCES events(id)
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                owner TEXT NOT NULL,
                deadline TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'To do',
                priority TEXT NOT NULL,
                FOREIGN KEY(event_id) REFERENCES events(id)
            );
            CREATE TABLE IF NOT EXISTS approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                item TEXT NOT NULL,
                reason TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                FOREIGN KEY(event_id) REFERENCES events(id)
            );
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(event_id) REFERENCES events(id)
            );
            """
        )
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            salt = secrets.token_hex(16)
            digest = hashlib.pbkdf2_hmac("sha256", b"demo1234", salt.encode(), 100_000).hex()
            conn.execute("INSERT INTO users(name, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
                         ("Demo Coordinator", "demo@campusflow.ai", f"{salt}${digest}", "Administrator", datetime.now().isoformat(timespec="seconds")))
        if conn.execute("SELECT COUNT(*) FROM venues").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO venues(name, capacity, features) VALUES (?, ?, ?)",
                [
                    ("Main Auditorium", 1000, "Stage, projector, sound system"),
                    ("Seminar Hall A", 300, "Projector, whiteboard"),
                    ("Seminar Hall B", 180, "Projector, whiteboard"),
                    ("Innovation Lab", 120, "Computers, high-speed Wi-Fi"),
                    ("Open Ground", 2000, "Outdoor stage, power points"),
                ],
            )
            conn.executemany(
                "INSERT INTO resources(name, quantity, category) VALUES (?, ?, ?)",
                [
                    ("Projectors", 4, "Equipment"), ("Microphones", 12, "Equipment"),
                    ("Laptop kits", 80, "Equipment"), ("Volunteers", 70, "People"),
                    ("Security staff", 12, "People"), ("Buses", 4, "Transport"),
                ],
            )


def rows(sql: str, params: tuple = ()) -> list[dict]:
    with connection() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def execute(sql: str, params: tuple = ()) -> int:
    with connection() as conn:
        cursor = conn.execute(sql, params)
        conn.commit()
        return cursor.lastrowid


def create_event(plan: dict) -> int:
    event_id = execute(
        "INSERT INTO events(name, description, participants, days, created_at) VALUES (?, ?, ?, ?, ?)",
        (plan["name"], plan["description"], plan["participants"], plan["days"], datetime.now().isoformat(timespec="seconds")),
    )
    for item in plan["schedule"]:
        execute(
            "INSERT INTO schedules(event_id, activity, day, start_time, end_time, venue, participants, equipment) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (event_id, item["activity"], item["day"], item["start"], item["end"], item["venue"], item["participants"], json.dumps(item["equipment"])),
        )
    for task in plan["tasks"]:
        execute("INSERT INTO tasks(event_id, title, owner, deadline, priority) VALUES (?, ?, ?, ?, ?)",
                (event_id, task["title"], task["owner"], task["deadline"], task["priority"]))
    for approval in plan["approvals"]:
        execute("INSERT INTO approvals(event_id, item, reason) VALUES (?, ?, ?)",
                (event_id, approval["item"], approval["reason"]))
    execute("INSERT INTO notifications(event_id, message, created_at) VALUES (?, ?, ?)",
            (event_id, "AI plan generated. Please review pending approvals.", datetime.now().strftime("%d %b %H:%M")))
    return event_id


def add_venue(name: str, capacity: int, features: str) -> None:
    execute("INSERT INTO venues(name, capacity, features) VALUES (?, ?, ?)", (name, capacity, features))


def add_resource(name: str, quantity: int, category: str) -> None:
    execute("INSERT INTO resources(name, quantity, category) VALUES (?, ?, ?)", (name, quantity, category))


def notify(event_id: int, message: str) -> None:
    execute("INSERT INTO notifications(event_id, message, created_at) VALUES (?, ?, ?)",
            (event_id, message, datetime.now().strftime("%d %b, %I:%M %p")))


def create_user(name: str, email: str, password: str) -> bool:
    """Create a local user. Passwords are salted and hashed, never stored as text."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
    try:
        execute("INSERT INTO users(name, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
                (name.strip(), email.strip().lower(), f"{salt}${digest}", "Coordinator", datetime.now().isoformat(timespec="seconds")))
        return True
    except sqlite3.IntegrityError:
        return False


def authenticate(email: str, password: str) -> dict | None:
    found = rows("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
    if not found:
        return None
    user = found[0]
    salt, stored = user["password_hash"].split("$", 1)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
    if hmac.compare_digest(stored, digest):
        return {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"]}
    return None
