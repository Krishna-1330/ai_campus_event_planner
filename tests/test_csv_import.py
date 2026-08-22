import io
import unittest

from flask import Flask

from database.mongo import MemoryStore
from routes.resources import bp as resources_bp


class CsvImportTests(unittest.TestCase):
    def make_client(self):
        app = Flask(__name__)
        app.config.update(SECRET_KEY="test-secret", DEFAULT_MEMBER_PASSWORD="campus123")
        app.extensions["campusflow_store"] = MemoryStore()
        app.register_blueprint(resources_bp)
        client = app.test_client()
        with client.session_transaction() as session:
            session["campusflow_user"] = {
                "role": "admin",
                "display_name": "Test Admin",
            }
        return app, client

    def test_memory_store_starts_without_sample_records(self):
        store = MemoryStore()

        self.assertEqual(store.get_all("faculty"), [])
        self.assertEqual(store.get_all("events"), [])

    def test_csv_import_creates_records_and_member_accounts(self):
        app, client = self.make_client()
        csv_data = (
            "faculty_id,name,department,subjects,max_events_per_day\n"
            "FAC101,Ada Lovelace,Computer Science,Python|AI,2\n"
            "FAC102,Grace Hopper,Computer Science,Compilers|Systems,1\n"
        )

        response = client.post(
            "/api/data/faculty/csv",
            data={"file": (io.BytesIO(csv_data.encode("utf-8")), "faculty.csv")},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["imported"], 2)
        self.assertEqual(len(app.extensions["campusflow_store"].get_all("faculty")), 2)
        self.assertIsNotNone(app.extensions["campusflow_store"].get_one("users", {"username": "FAC101"}))

    def test_invalid_csv_does_not_import_any_records(self):
        app, client = self.make_client()
        csv_data = (
            "faculty_id,name,department\n"
            "FAC101,Ada Lovelace,Computer Science\n"
            "FAC102,,Computer Science\n"
        )

        response = client.post(
            "/api/data/faculty/csv",
            data={"file": (io.BytesIO(csv_data.encode("utf-8")), "faculty.csv")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(app.extensions["campusflow_store"].get_all("faculty"), [])

    def test_timetable_image_results_can_be_reviewed_and_imported(self):
        app, client = self.make_client()
        response = client.post(
            "/api/data/academic_calendar/image-import",
            json={"records": [
                {"date": "2026-09-01", "type": "Working Day", "reason": "Semester begins", "available": True},
                {"date": "2026-09-05", "type": "Holiday", "reason": "College holiday", "available": False},
            ]},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), {"ok": True, "created": 2, "updated": 0})
        calendar = app.extensions["campusflow_store"].get_all("academic_calendar")
        self.assertEqual(len(calendar), 2)
        self.assertFalse(next(record for record in calendar if record["date"] == "2026-09-05")["available"])

    def test_timetable_image_requires_a_vision_key_to_scan(self):
        _app, client = self.make_client()
        response = client.post(
            "/api/data/academic_calendar/scan-image",
            data={"image": (io.BytesIO(b"image"), "timetable.png")},
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("GEMINI_API_KEY", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
