"""Settings. All secrets come from environment variables, never from this file."""
import os

SECRET_KEY = os.environ.get("SECRET_KEY")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
if not SECRET_KEY or not DB_PASSWORD:
    raise RuntimeError("Set the SECRET_KEY and DB_PASSWORD environment variables before starting")

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_USER = os.environ.get("DB_USER", "root")
DB_NAME = os.environ.get("DB_NAME", "rural_freelancing")

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads")
MAX_CONTENT_LENGTH = 2 * 1024 * 1024          # 2 MB upload limit
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}

# Optional real masked calling (Twilio). Leave unset to use the simulated demo.
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.environ.get("TWILIO_NUMBER")      # your Twilio number in E.164, e.g. +14155550123
DEFAULT_COUNTRY_CODE = os.environ.get("DEFAULT_COUNTRY_CODE", "+91")
CALLS_PER_HOUR = 3                                    # abuse / cost guard per user
