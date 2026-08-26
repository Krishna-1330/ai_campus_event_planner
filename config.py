import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "campusflow-local-development-key")
    # Atlas remains the preferred production database.  When it is absent or
    # unreachable, CampusFlow uses this local MongoDB service instead.
    MONGO_URI = os.getenv("MONGO_URI", "")
    LOCAL_MONGO_URI = os.getenv("LOCAL_MONGO_URI", "mongodb://127.0.0.1:27017")
    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "campusflow_ai")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
    JSON_SORT_KEYS = False
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
