"""Storage adapter with Atlas, local MongoDB, and temporary-memory fallback.

All time-dependent availability is calculated from the assignments collection.
Resource documents intentionally have no `available` flag.
"""
from __future__ import annotations

import copy
import os
import uuid
from typing import Any

from pymongo import ASCENDING, MongoClient
from pymongo.errors import PyMongoError

from database.collections import empty_collections


RESOURCE_COLLECTIONS = {
    "faculty": "faculty", "volunteer": "volunteers", "guest": "guests",
    "venue": "venues", "lab": "labs", "equipment": "equipment", "vehicle": "vehicles",
}


class MemoryStore:
    """Temporary fallback when MongoDB is unavailable."""
    storage_mode = "memory"
    storage_label = "Temporary memory"

    def __init__(self):
        self.data: dict[str, list[dict[str, Any]]] = empty_collections()

    def get_all(self, collection: str, query: dict | None = None) -> list[dict]:
        rows = copy.deepcopy(self.data.get(collection, []))
        if not query:
            return rows
        return [row for row in rows if _matches(row, query)]

    def get_one(self, collection: str, query: dict) -> dict | None:
        return next((row for row in self.get_all(collection, query) if _matches(row, query)), None)

    def insert(self, collection: str, document: dict) -> dict:
        row = copy.deepcopy(document)
        row.setdefault("_id", str(uuid.uuid4()))
        self.data.setdefault(collection, []).append(row)
        return copy.deepcopy(row)

    def update_one(self, collection: str, query: dict, updates: dict) -> dict | None:
        for row in self.data.get(collection, []):
            if _matches(row, query):
                row.update(copy.deepcopy(updates))
                return copy.deepcopy(row)
        return None

    def update_many(self, collection: str, query: dict, updates: dict) -> int:
        count = 0
        for row in self.data.get(collection, []):
            if _matches(row, query):
                row.update(copy.deepcopy(updates)); count += 1
        return count

    def delete_many(self, collection: str, query: dict) -> int:
        before = len(self.data.get(collection, []))
        self.data[collection] = [r for r in self.data.get(collection, []) if not _matches(r, query)]
        return before - len(self.data[collection])


class MongoStore:
    def __init__(self, uri: str, database_name: str, storage_mode: str):
        self.client = MongoClient(uri, serverSelectionTimeoutMS=4000)
        self.client.admin.command("ping")
        self.db = self.client.get_database(database_name)
        self.storage_mode = storage_mode
        self.storage_label = "MongoDB Atlas" if storage_mode == "atlas" else "Local MongoDB"
        self.ensure_indexes()

    def ensure_indexes(self):
        self.db.assignments.create_index([
            ("resource_id", ASCENDING), ("start_datetime", ASCENDING), ("end_datetime", ASCENDING), ("status", ASCENDING)
        ])
        self.db.assignments.create_index([("event_id", ASCENDING), ("status", ASCENDING)])
        self.db.events.create_index([("status", ASCENDING), ("start_datetime", ASCENDING)])
        self.db.audit_logs.create_index([("timestamp", -1)])
        self.db.notifications.create_index([("created_at", -1)])
        self.db.users.create_index([("username", ASCENDING)], unique=True)

    def get_all(self, collection: str, query: dict | None = None) -> list[dict]:
        return [_clean(row) for row in self.db[collection].find(query or {})]

    def get_one(self, collection: str, query: dict) -> dict | None:
        row = self.db[collection].find_one(query)
        return _clean(row) if row else None

    def insert(self, collection: str, document: dict) -> dict:
        row = copy.deepcopy(document)
        row.setdefault("_id", str(uuid.uuid4()))
        self.db[collection].insert_one(row)
        return _clean(row)

    def update_one(self, collection: str, query: dict, updates: dict) -> dict | None:
        self.db[collection].update_one(query, {"$set": copy.deepcopy(updates)})
        return self.get_one(collection, query)

    def update_many(self, collection: str, query: dict, updates: dict) -> int:
        return self.db[collection].update_many(query, {"$set": copy.deepcopy(updates)}).modified_count

    def delete_many(self, collection: str, query: dict) -> int:
        return self.db[collection].delete_many(query).deleted_count


def _clean(row: dict) -> dict:
    row = copy.deepcopy(row)
    row["_id"] = str(row.get("_id", ""))
    return row


def _matches(row: dict, query: dict) -> bool:
    for key, expected in query.items():
        if isinstance(expected, dict) and "$in" in expected:
            if row.get(key) not in expected["$in"]:
                return False
        elif row.get(key) != expected:
            return False
    return True


def make_store(atlas_uri: str = "", local_uri: str = "", database_name: str = "campusflow_ai"):
    """Prefer Atlas, then use a local MongoDB server, then temporary memory.

    This lets the same project run persistently on a laptop without removing
    the existing Atlas deployment path.
    """
    attempted = set()
    for label, uri, mode in (("MongoDB Atlas", atlas_uri, "atlas"), ("local MongoDB", local_uri, "local")):
        if not uri or uri in attempted:
            continue
        attempted.add(uri)
        try:
            store = MongoStore(uri, database_name, mode)
            print(f"CampusFlow connected to {label} database '{database_name}'.")
            return store
        except PyMongoError as exc:
            print(f"CampusFlow could not connect to {label} ({exc}).")
    print("CampusFlow is using non-persistent temporary memory.")
    return MemoryStore()
