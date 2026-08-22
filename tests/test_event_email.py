import unittest
from unittest.mock import patch

from flask import Flask

from database.mongo import MemoryStore
from routes.events import bp as events_bp


class EventEmailTests(unittest.TestCase):
    def make_client(self):
        app = Flask(__name__)
        app.config.update(
            SECRET_KEY="test-secret",
            SMTP_HOST="smtp.example.test",
            SMTP_FROM="campus@example.test",
        )
        app.extensions["campusflow_store"] = MemoryStore()
        app.register_blueprint(events_bp)
        return app, app.test_client()

    def seed_approvable_event(self, app):
        plan = {
            "start_datetime": "2026-09-10T09:00:00",
            "end_datetime": "2026-09-10T11:00:00",
            "labs": [], "venues": [], "faculty": [{"resource_id": "FAC101", "resource_type": "faculty", "name": "Ada Lovelace"}],
            "volunteers": [], "guests": [], "equipment": [], "vehicles": [],
        }
        store = app.extensions["campusflow_store"]
        store.insert("events", {"event_id": "event-1", "title": "AI Workshop", "status": "plan_ready", "proposed_plan": plan})
        store.insert("event_requirements", {"requirement_id": "req-1", "event_id": "event-1"})
        store.insert("faculty", {"faculty_id": "FAC101", "name": "Ada Lovelace", "email": "ada@example.test"})

    @patch("routes.events.send_email", return_value="sent")
    @patch("routes.events.validate_plan", return_value={"valid": True, "checks": []})
    def test_email_is_sent_only_after_successful_approval(self, _validate, send_email):
        app, client = self.make_client()
        self.seed_approvable_event(app)

        response = client.post("/api/events/event-1/approve")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(app.extensions["campusflow_store"].get_one("events", {"event_id": "event-1"})["status"], "approved")
        send_email.assert_called_once()
        self.assertEqual(send_email.call_args.args[1], "ada@example.test")

    @patch("routes.events.send_email")
    @patch("routes.events.validate_plan", return_value={"valid": False, "checks": [], "errors": ["Venue unavailable"]})
    def test_email_is_not_sent_when_approval_fails(self, _validate, send_email):
        app, client = self.make_client()
        self.seed_approvable_event(app)

        response = client.post("/api/events/event-1/approve")

        self.assertEqual(response.status_code, 409)
        send_email.assert_not_called()


if __name__ == "__main__":
    unittest.main()
