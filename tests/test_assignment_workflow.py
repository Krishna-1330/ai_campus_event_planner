import unittest

from flask import Flask

from database.mongo import MemoryStore
from routes.auth import bp as auth_bp
from routes.events import bp as events_bp
from routes.resources import bp as resources_bp
from routes.operations import bp as operations_bp
from routes.auth import _attendance_summary
from agents.venue_agent import recommend_labs, recommend_venues


class AssignmentWorkflowTests(unittest.TestCase):
    def make_app(self):
        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test-secret"
        app.extensions["campusflow_store"] = MemoryStore()
        app.register_blueprint(auth_bp)
        app.register_blueprint(events_bp)
        app.register_blueprint(resources_bp)
        app.register_blueprint(operations_bp)
        return app

    def test_acceptance_blocks_member_for_same_date(self):
        from services.availability_service import member_is_available
        store = MemoryStore()
        store.insert("assignments", {"resource_id": "FAC1", "event_id": "e1", "status": "locked", "acceptance": "accepted", "start_datetime": "2026-09-10T09:00:00", "end_datetime": "2026-09-10T11:00:00"})
        self.assertFalse(member_is_available(store, "FAC1", "2026-09-10T15:00:00"))
        self.assertTrue(member_is_available(store, "FAC1", "2026-09-11T09:00:00"))

    def test_availability_search_returns_matching_resource(self):
        app = self.make_app()
        store = app.extensions["campusflow_store"]
        store.insert("faculty", {"faculty_id": "FAC1", "name": "Ada Lovelace", "status": "active"})
        with app.test_client() as client:
            response = client.get("/api/availability?name=Ada&start_datetime=2026-09-10T09:00:00&end_datetime=2026-09-10T11:00:00")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["matches"][0]["available"])

    def test_venue_score_reflects_capacity_fit(self):
        store = MemoryStore()
        store.insert("venues", {"venue_id": "V50", "name": "Exact Hall", "capacity": 50, "status": "active"})
        store.insert("venues", {"venue_id": "V100", "name": "Large Hall", "capacity": 100, "status": "active"})
        matches = recommend_venues(store, {"minimum_capacity": 50}, "2026-09-10T09:00:00", "2026-09-10T11:00:00")
        self.assertEqual([item["resource_id"] for item in matches], ["V50", "V100"])
        self.assertEqual([item["score"] for item in matches], [100, 50])

    def test_multiple_suitable_labs_choose_one_best_lab(self):
        store = MemoryStore()
        store.insert("labs", {"lab_id": "L80", "lab_name": "Large Lab", "number_of_systems": 80, "installed_software": [], "status": "active"})
        store.insert("labs", {"lab_id": "L40", "lab_name": "Exact Lab", "number_of_systems": 40, "installed_software": [], "status": "active"})
        matches = recommend_labs(store, {"required_systems": 40}, "2026-09-10T09:00:00", "2026-09-10T11:00:00")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["resource_id"], "L40")

    def test_recheck_persists_new_best_venue(self):
        app = self.make_app()
        store = app.extensions["campusflow_store"]
        store.insert("events", {"event_id": "event-recheck", "status": "plan_ready", "proposed_plan": {"start_datetime": "2026-09-10T09:00:00", "end_datetime": "2026-09-10T11:00:00", "venues": [{"resource_id": "V100", "name": "Large Hall", "score": 50}]}})
        store.insert("event_requirements", {"event_id": "event-recheck", "minimum_capacity": 50})
        store.insert("venues", {"venue_id": "V50", "name": "Exact Hall", "capacity": 50, "status": "active"})
        store.insert("venues", {"venue_id": "V100", "name": "Large Hall", "capacity": 100, "status": "active"})
        with app.test_client() as client:
            response = client.post("/api/events/event-recheck/recheck-resources/venues")
        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["updated"])
        self.assertEqual(payload["matches"][0]["resource_id"], "V50")
        self.assertEqual(store.get_one("events", {"event_id": "event-recheck"})["proposed_plan"]["venues"][0]["resource_id"], "V50")

    def test_delete_all_notifications(self):
        app = self.make_app()
        store = app.extensions["campusflow_store"]
        store.insert("notifications", {"title": "One", "message": "First"})
        store.insert("notifications", {"title": "Two", "message": "Second"})
        with app.test_client() as client:
            response = client.delete("/api/notifications")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["deleted"], 2)
        self.assertEqual(store.get_all("notifications"), [])

    def test_timeline_replan_tracks_attempt_count(self):
        app = self.make_app()
        store = app.extensions["campusflow_store"]
        store.insert("events", {"event_id": "event-2", "title": "Workshop", "status": "plan_ready", "proposed_plan": {"start_datetime": "2026-09-10T09:00:00", "end_datetime": "2026-09-10T11:00:00", "timeline": [{"time": "09:00", "title": "Start"}]}})
        store.insert("event_requirements", {"event_id": "event-2", "event_type": "workshop"})
        with app.test_client() as client:
            response = client.post("/api/events/event-2/replan-timeline")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["count"], 1)
        self.assertTrue(response.get_json()["updated"])

    def test_attendance_counts_only_completed_accepted_assignments(self):
        assignments = [
            {"acceptance": "accepted", "attendance_status": "completed", "start_datetime": "2026-09-10T09:00:00"},
            {"acceptance": "accepted", "start_datetime": "2026-09-11T09:00:00"},
            {"acceptance": "declined", "attendance_status": "completed", "start_datetime": "2026-09-12T09:00:00"},
        ]
        summary = _attendance_summary(assignments)
        self.assertEqual(summary["total_events"], 1)
        self.assertEqual(summary["total_points"], 25)


if __name__ == "__main__":
    unittest.main()
