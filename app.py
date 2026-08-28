from __future__ import annotations

import click
from flask import Flask, jsonify, render_template, request

from config import Config
from database.collections import CAMPUS_COLLECTIONS
from database.mongo import make_store
from routes.events import bp as events_bp
from routes.dashboard import bp as dashboard_bp
from routes.resources import bp as resources_bp
from routes.campus import bp as campus_bp
from routes.operations import bp as operations_bp
from routes.auth import bp as auth_bp, bootstrap_users, current_user
from routes.helpers import api_error
from services.availability_service import sync_member_activity_statuses


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.extensions["campusflow_store"] = make_store(
        app.config["MONGO_URI"], app.config["LOCAL_MONGO_URI"], app.config["MONGO_DB_NAME"]
    )
    bootstrap_users(app.extensions["campusflow_store"], app.config["ADMIN_USERNAME"], app.config["ADMIN_PASSWORD"], app.config["ORGANIZER_ACCOUNTS"])
    app.register_blueprint(auth_bp); app.register_blueprint(events_bp); app.register_blueprint(dashboard_bp); app.register_blueprint(resources_bp); app.register_blueprint(campus_bp); app.register_blueprint(operations_bp)

    @app.before_request
    def require_authenticated_api_user():
        # Keep faculty and volunteer account status current. This updates
        # accepted members to busy only during the actual event time and
        # restores active afterwards; availability checks remain slot-based.
        if request.path.startswith("/api/"):
            sync_member_activity_statuses(app.extensions["campusflow_store"])
        if not request.path.startswith("/api/") or request.endpoint in {"auth.login", "auth.logout", "auth.me"}:
            return None
        user = current_user()
        if not user:
            return api_error("Sign in is required.", 401)
        # Faculty and volunteer accounts may only reach their own availability, their
        # own event feed, and responding to their own assignments; every other API
        # endpoint (campus data, resource management, agents, audit, etc.) is admin-only.
        member_safe_endpoints = {"auth.my_availability", "auth.my_events", "auth.respond_assignment", "auth.my_profile", "auth.update_my_profile", "auth.my_mailbox"}
        organizer_safe_prefixes = {"events."}
        if user.get("role") not in {"admin", "organizer"} and request.endpoint not in member_safe_endpoints:
            return api_error("Your account can only view its own availability and assignments.", 403)
        if user.get("role") == "organizer" and not (request.endpoint in {"auth.my_profile", "auth.update_my_profile", "dashboard.dashboard"} or any(request.endpoint.startswith(prefix) for prefix in organizer_safe_prefixes)):
            return api_error("Organizers can manage events, but resource management is restricted to administrators.", 403)
        if user.get("role") == "organizer" and request.endpoint.startswith("events.") and request.view_args and request.view_args.get("event_id"):
            event = app.extensions["campusflow_store"].get_one("events", {"event_id": request.view_args["event_id"]})
            if not event or event.get("organizer_username") != user.get("username"):
                return api_error("This event belongs to another organizer.", 403)
        return None

    @app.errorhandler(413)
    def file_too_large(_error):
        return api_error("Images must be 5 MB or smaller.", 413)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/health")
    def health():
        data_store = app.extensions["campusflow_store"]
        return jsonify({"ok": True, "service": "CampusFlow AI", "storage": data_store.storage_label, "mode": data_store.storage_mode})

    @app.cli.command("clear-data")
    @click.confirmation_option(prompt="This permanently removes all CampusFlow records. Continue?")
    def clear_data():
        data_store = app.extensions["campusflow_store"]
        for collection in CAMPUS_COLLECTIONS:
            data_store.delete_many(collection, {})
        bootstrap_users(data_store, app.config["ADMIN_USERNAME"], app.config["ADMIN_PASSWORD"], app.config["ORGANIZER_ACCOUNTS"])
        click.echo("CampusFlow is empty and ready for your campus data.")
    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
