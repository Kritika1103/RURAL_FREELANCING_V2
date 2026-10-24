"""Test setup.  Tests ALWAYS run against a separate database (rural_freelancing_test) that is
dropped and recreated each run, so your real data is never touched.

Run:   $env:DB_PASSWORD="your-mysql-password"     (PowerShell)
       python -m pytest -q
"""
import os, re, sys
from datetime import date, timedelta

import pymysql
import pytest
from werkzeug.security import generate_password_hash

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TEST_DB = "rural_freelancing_test"
os.environ["DB_NAME"] = TEST_DB                       # force the test database, ignore any outside value
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
if not os.environ.get("DB_PASSWORD"):
    pytest.exit("Set the DB_PASSWORD environment variable (your MySQL password) before running tests.", returncode=2)

import config                      # noqa: E402
import app as app_module           # noqa: E402

PASSWORD = "Passw0rd!"
TABLES = ["complaints", "call_requests", "reviews", "messages", "bookings",
          "unavailable_dates", "services", "worker_profiles", "users"]


def _connect(database=None):
    return pymysql.connect(host=config.DB_HOST, user=config.DB_USER, password=config.DB_PASSWORD,
                           database=database, charset="utf8mb4", autocommit=True,
                           cursorclass=pymysql.cursors.DictCursor)


@pytest.fixture(scope="session", autouse=True)
def _database():
    conn = _connect()
    with conn.cursor() as cur:
        cur.execute("DROP DATABASE IF EXISTS `%s`" % TEST_DB)
        cur.execute("CREATE DATABASE `%s` CHARACTER SET utf8mb4" % TEST_DB)
        cur.execute("USE `%s`" % TEST_DB)
        sql = open(os.path.join(ROOT, "database.sql"), encoding="utf-8").read()
        sql = "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())
        for stmt in (x.strip() for x in sql.split(";")):
            if stmt and not re.match(r"(?i)(create database|use)\b", stmt):   # skip the real-DB lines
                cur.execute(stmt)
    conn.close()
    yield


@pytest.fixture(autouse=True)
def _clean(_database):
    conn = _connect(TEST_DB)
    with conn.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS=0")
        for t in TABLES:
            cur.execute("TRUNCATE TABLE " + t)
        cur.execute("SET FOREIGN_KEY_CHECKS=1")
    conn.close()


@pytest.fixture
def q():
    """Run raw SQL against the test DB: q('SELECT ...', args) -> list of dict rows."""
    conn = _connect(TEST_DB)
    def run(sql, args=()):
        with conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchall()
    yield run
    conn.close()


class Api:
    """Thin wrapper around Flask's test client that adds the CSRF token to every POST."""
    def __init__(self):
        app_module.app.config["TESTING"] = True
        self.c = app_module.app.test_client()

    def token(self):
        with self.c.session_transaction() as s:
            s.setdefault("csrf_token", "test-token")
            return s["csrf_token"]

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, data=None, csrf=True, **kw):
        d = dict(data or {})
        if csrf:
            d["csrf_token"] = self.token()
        return self.c.post(url, data=d, **kw)

    def login(self, email):
        return self.post("/login", {"email": email, "password": PASSWORD})


@pytest.fixture
def api():
    return Api()


@pytest.fixture
def make_user(q):
    counter = {"n": 0}
    def make(role="client", lat=None, lng=None, phone="9000000001", name=None):
        counter["n"] += 1
        email = "%s%d@test.com" % (role, counter["n"])
        q("INSERT INTO users (name,email,password_hash,role,phone,latitude,longitude) VALUES (%s,%s,%s,%s,%s,%s,%s)",
          (name or "%s %d" % (role.title(), counter["n"]), email, generate_password_hash(PASSWORD), role, phone, lat, lng))
        uid = q("SELECT id FROM users WHERE email=%s", (email,))[0]["id"]
        if role == "worker":
            q("INSERT INTO worker_profiles (user_id, skills, bio, experience_years, available) VALUES (%s,'wiring','bio',3,1)", (uid,))
        return {"id": uid, "email": email, "phone": phone}
    return make


@pytest.fixture
def login_as(make_user):
    def go(role="client", **kw):
        user = make_user(role, **kw)
        client = Api()
        client.login(user["email"])
        client.user = user
        return client
    return go


@pytest.fixture
def make_service(q):
    def make(worker_id, category_id=1, price=500, title="Wiring"):
        q("INSERT INTO services (worker_id,category_id,title,description,price) VALUES (%s,%s,%s,'d',%s)",
          (worker_id, category_id, title, price))
        return q("SELECT id FROM services WHERE worker_id=%s ORDER BY id DESC LIMIT 1", (worker_id,))[0]["id"]
    return make


@pytest.fixture
def make_booking(q):
    def make(client_id, worker_id, service_id, when=None, status="PENDING", offered=500, by="worker"):
        when = when or (date.today() + timedelta(days=5)).isoformat()
        q("INSERT INTO bookings (client_id,worker_id,service_id,status,scheduled_date,address,offered_price,offered_by) "
          "VALUES (%s,%s,%s,%s,%s,'Village road',%s,%s)", (client_id, worker_id, service_id, status, when, offered, by))
        return q("SELECT id FROM bookings ORDER BY id DESC LIMIT 1")[0]["id"]
    return make


def future(days=5):
    return (date.today() + timedelta(days=days)).isoformat()
