from __future__ import annotations

from flask import current_app, jsonify


def store():
    return current_app.extensions["campusflow_store"]


def api_error(message, status=400, **extra):
    return jsonify({"ok": False, "error": message, **extra}), status


def app_mode():
    return store().storage_mode
