"""Automated tests: security, role rules, booking state machine, negotiation, reviews,
availability / double-booking, masked calling, complaints + admin, translations, PWA, uploads."""
import io, json, os, subprocess, sys
from urllib.error import URLError

import pytest
from PIL import Image

import config
import app as app_module
from conftest import ROOT, PASSWORD, Api, future


# ------------------------------------------------------------------ pure logic
def test_haversine_known_distance():
    # Bengaluru -> Mysuru is about 126 km as the crow flies
    d = app_module.haversine(12.9716, 77.5946, 12.2958, 76.6394)
    assert 120 < d < 132

def test_haversine_zero_and_symmetric():
    assert app_module.haversine(12.5, 76.9, 12.5, 76.9) == pytest.approx(0, abs=1e-9)
    a = app_module.haversine(12.5, 76.9, 13.0, 77.5)
    b = app_module.haversine(13.0, 77.5, 12.5, 76.9)
    assert a == pytest.approx(b)

def test_config_fails_closed_without_secrets():
    env = {k: v for k, v in os.environ.items() if k not in ("SECRET_KEY", "DB_PASSWORD")}
    r = subprocess.run([sys.executable, "-c", "import config"], cwd=ROOT, env=env, capture_output=True, text=True)
    assert r.returncode != 0 and "SECRET_KEY" in r.stderr


# ------------------------------------------------------------------ security
def test_post_without_csrf_token_is_rejected(api):
    assert api.post("/login", {"email": "a@b.com", "password": "x"}, csrf=False).status_code == 400

def test_post_with_wrong_csrf_token_is_rejected(api):
    api.token()
    r = api.c.post("/login", data={"email": "a@b.com", "password": "x", "csrf_token": "forged"})
    assert r.status_code == 400

def test_sql_injection_in_search_is_harmless(api, make_user, q):
    make_user("worker")
    r = api.get("/search", query_string={"q": "' OR '1'='1' --"})
    assert r.status_code == 200
    assert b"0 worker service(s)" in r.data
    assert q("SELECT COUNT(*) n FROM users")[0]["n"] == 1

def test_passwords_are_hashed(api, q):
    api.post("/register", {"role": "client", "name": "Asha", "email": "asha@x.com", "phone": "9876543210",
                           "password": "secret123"})
    row = q("SELECT password_hash FROM users WHERE email='asha@x.com'")[0]
    assert row["password_hash"] != "secret123" and row["password_hash"].startswith(("scrypt:", "pbkdf2:"))

def test_register_validation(api, q):
    api.post("/register", {"role": "client", "name": "A", "email": "a@x.com", "phone": "123", "password": "secret123"})
    api.post("/register", {"role": "admin", "name": "A", "email": "b@x.com", "phone": "9876543210", "password": "secret123"})
    assert q("SELECT COUNT(*) n FROM users")[0]["n"] == 0          # bad phone and self-registered admin both refused

def test_login_logout_and_wrong_password(api, make_user):
    u = make_user("client")
    assert api.post("/login", {"email": u["email"], "password": "wrong"}).status_code == 200
    assert api.get("/dashboard").status_code == 302                  # still anonymous
    assert api.login(u["email"]).status_code == 302
    assert api.get("/dashboard").status_code == 200
    api.post("/logout")
    assert api.get("/dashboard").status_code == 302

def test_role_enforcement(login_as, api):
    client, worker = login_as("client"), login_as("worker")
    assert client.post("/services/add", {"title": "x", "price": "10", "category_id": "1"}).status_code == 403
    assert worker.post("/book", {"service_id": "1"}).status_code == 403
    assert client.get("/admin").status_code == 403
    assert worker.get("/admin").status_code == 403
    assert api.get("/admin").status_code == 302


# ------------------------------------------------------------------ booking state machine
ILLEGAL = [("PENDING", "COMPLETED", "worker"), ("PENDING", "CONFIRMED", "client"), ("PENDING", "IN_PROGRESS", "worker"),
           ("ACCEPTED", "COMPLETED", "worker"), ("COMPLETED", "CANCELLED", "client"), ("PENDING", "ACCEPTED", "client"),
           ("ACCEPTED", "CONFIRMED", "worker"), ("REJECTED", "ACCEPTED", "worker")]

@pytest.mark.parametrize("status,action,who", ILLEGAL)
def test_illegal_transitions_are_blocked(login_as, make_user, make_service, make_booking, q, status, action, who):
    client, worker = login_as("client"), login_as("worker")
    sid = make_service(worker.user["id"])
    bid = make_booking(client.user["id"], worker.user["id"], sid, status=status)
    actor = client if who == "client" else worker
    actor.post("/booking/%d/status" % bid, {"action": action})
    assert q("SELECT status FROM bookings WHERE id=%s", (bid,))[0]["status"] == status

def test_full_happy_path(login_as, make_service, make_booking, q):
    client, worker = login_as("client"), login_as("worker")
    bid = make_booking(client.user["id"], worker.user["id"], make_service(worker.user["id"]))
    status = lambda: q("SELECT status FROM bookings WHERE id=%s", (bid,))[0]["status"]
    for actor, action in [(worker, "ACCEPTED"), (client, "CONFIRMED"), (worker, "IN_PROGRESS"), (worker, "COMPLETED")]:
        actor.post("/booking/%d/status" % bid, {"action": action})
        assert status() == action
    assert float(q("SELECT agreed_price FROM bookings WHERE id=%s", (bid,))[0]["agreed_price"]) == 500

def test_outsider_cannot_see_or_post_to_booking(login_as, make_service, make_booking):
    client, worker, stranger = login_as("client"), login_as("worker"), login_as("client")
    bid = make_booking(client.user["id"], worker.user["id"], make_service(worker.user["id"]))
    assert stranger.get("/booking/%d" % bid).status_code == 404
    assert stranger.post("/booking/%d/message" % bid, {"body": "hi"}).status_code == 404


# ------------------------------------------------------------------ negotiation + reviews
def test_price_negotiation(login_as, make_service, q):
    client, worker = login_as("client"), login_as("worker")
    sid = make_service(worker.user["id"], price=500)
    client.post("/book", {"service_id": sid, "scheduled_date": future(), "address": "Farm", "offer_price": "400"})
    b = q("SELECT * FROM bookings")[0]
    assert b["offered_by"] == "client" and float(b["offered_price"]) == 400
    client.post("/booking/%d/offer/accept" % b["id"])                 # cannot accept your own offer
    assert q("SELECT agreed_price FROM bookings")[0]["agreed_price"] is None
    worker.post("/booking/%d/offer/accept" % b["id"])
    assert float(q("SELECT agreed_price FROM bookings")[0]["agreed_price"]) == 400
    worker.post("/booking/%d/offer" % b["id"], {"price": "450"})      # counter resets the agreement
    row = q("SELECT * FROM bookings")[0]
    assert row["agreed_price"] is None and float(row["offered_price"]) == 450 and row["offered_by"] == "worker"

def test_review_rules(login_as, make_service, make_booking, q):
    client, worker = login_as("client"), login_as("worker")
    bid = make_booking(client.user["id"], worker.user["id"], make_service(worker.user["id"]), status="IN_PROGRESS")
    client.post("/booking/%d/review" % bid, {"rating": "5"})
    assert q("SELECT COUNT(*) n FROM reviews")[0]["n"] == 0           # not completed yet
    q("UPDATE bookings SET status='COMPLETED' WHERE id=%s", (bid,))
    client.post("/booking/%d/review" % bid, {"rating": "9"})
    assert q("SELECT COUNT(*) n FROM reviews")[0]["n"] == 0           # invalid rating
    client.post("/booking/%d/review" % bid, {"rating": "5", "comment": "great"})
    client.post("/booking/%d/review" % bid, {"rating": "1"})          # second review refused
    rows = q("SELECT rating FROM reviews")
    assert len(rows) == 1 and rows[0]["rating"] == 5
    assert worker.post("/booking/%d/review" % bid, {"rating": "5"}).status_code == 403


# ------------------------------------------------------------------ availability / scheduling
def test_invalid_date_does_not_crash(login_as, make_service, q):
    client, worker = login_as("client"), login_as("worker")
    sid = make_service(worker.user["id"])
    r = client.post("/book", {"service_id": sid, "scheduled_date": "2026-13-45", "address": "Farm"})
    assert r.status_code == 302 and q("SELECT COUNT(*) n FROM bookings")[0]["n"] == 0

def test_blocked_date_cannot_be_booked(login_as, make_service, q):
    client, worker = login_as("client"), login_as("worker")
    sid = make_service(worker.user["id"])
    worker.post("/availability/add", {"off_date": future(7)})
    client.post("/book", {"service_id": sid, "scheduled_date": future(7), "address": "Farm"})
    assert q("SELECT COUNT(*) n FROM bookings")[0]["n"] == 0
    client.post("/book", {"service_id": sid, "scheduled_date": future(8), "address": "Farm"})
    assert q("SELECT COUNT(*) n FROM bookings")[0]["n"] == 1

def test_no_double_booking(login_as, make_service, make_booking, q):
    c1, c2, worker = login_as("client"), login_as("client"), login_as("worker")
    sid = make_service(worker.user["id"])
    first = make_booking(c1.user["id"], worker.user["id"], sid, when=future(6))
    second = make_booking(c2.user["id"], worker.user["id"], sid, when=future(6))   # both pending: allowed
    worker.post("/booking/%d/status" % first, {"action": "ACCEPTED"})
    worker.post("/booking/%d/status" % second, {"action": "ACCEPTED"})            # same day: refused
    st = {r["id"]: r["status"] for r in q("SELECT id,status FROM bookings")}
    assert st[first] == "ACCEPTED" and st[second] == "PENDING"
    c2.post("/book", {"service_id": sid, "scheduled_date": future(6), "address": "Farm"})   # new request refused too
    assert q("SELECT COUNT(*) n FROM bookings")[0]["n"] == 2

def test_cannot_block_a_date_with_a_booking(login_as, make_service, make_booking, q):
    client, worker = login_as("client"), login_as("worker")
    make_booking(client.user["id"], worker.user["id"], make_service(worker.user["id"]), when=future(9), status="CONFIRMED")
    worker.post("/availability/add", {"off_date": future(9)})
    assert q("SELECT COUNT(*) n FROM unavailable_dates")[0]["n"] == 0

def test_search_by_date_excludes_busy_workers(api, make_user, make_service, q):
    free, busy = make_user("worker"), make_user("worker")
    make_service(free["id"], title="Free electrician"); make_service(busy["id"], title="Busy electrician")
    q("INSERT INTO unavailable_dates (worker_id, off_date) VALUES (%s,%s)", (busy["id"], future(3)))
    page = api.get("/search", query_string={"date": future(3)}).data.decode()
    assert "Free electrician" in page and "Busy electrician" not in page
    assert future(3) in api.get("/worker/%d" % busy["id"]).data.decode()       # shown as 'not free on'


# ------------------------------------------------------------------ masked calling
@pytest.fixture
def accepted(login_as, make_service, make_booking):
    client = login_as("client", phone="9111111111")
    worker = login_as("worker", phone="9222222222")
    bid = make_booking(client.user["id"], worker.user["id"], make_service(worker.user["id"]), status="ACCEPTED")
    return client, worker, bid

def test_call_is_simulated_without_provider(accepted, q):
    client, _, bid = accepted
    client.post("/booking/%d/call" % bid)
    assert q("SELECT mode FROM call_requests")[0]["mode"] == "demo"

def test_call_blocked_before_acceptance(login_as, make_service, make_booking, q):
    client, worker = login_as("client"), login_as("worker")
    bid = make_booking(client.user["id"], worker.user["id"], make_service(worker.user["id"]), status="PENDING")
    client.post("/booking/%d/call" % bid)
    assert q("SELECT COUNT(*) n FROM call_requests")[0]["n"] == 0

def test_real_call_uses_provider_and_hides_numbers(accepted, q, monkeypatch):
    client, _, bid = accepted
    for k, v in (("TWILIO_ACCOUNT_SID", "ACtest"), ("TWILIO_AUTH_TOKEN", "tok"), ("TWILIO_NUMBER", "+14155550123")):
        monkeypatch.setattr(config, k, v)
    seen = {}
    def fake(caller, callee):
        seen.update(caller=caller, callee=callee); return "CA123"
    monkeypatch.setattr(app_module, "place_twilio_call", fake)
    r = client.post("/booking/%d/call" % bid, follow_redirects=True)
    assert seen == {"caller": "+919111111111", "callee": "+919222222222"}
    row = q("SELECT mode, provider_sid FROM call_requests")[0]
    assert row["mode"] == "twilio" and row["provider_sid"] == "CA123"
    assert b"9222222222" not in r.data                                    # the other person's number is never shown

def test_call_provider_failure_is_handled(accepted, q, monkeypatch):
    client, _, bid = accepted
    for k, v in (("TWILIO_ACCOUNT_SID", "ACtest"), ("TWILIO_AUTH_TOKEN", "tok"), ("TWILIO_NUMBER", "+14155550123")):
        monkeypatch.setattr(config, k, v)
    def boom(*a): raise URLError("down")
    monkeypatch.setattr(app_module, "place_twilio_call", boom)
    assert client.post("/booking/%d/call" % bid).status_code == 302
    assert q("SELECT COUNT(*) n FROM call_requests")[0]["n"] == 0

def test_call_rate_limit(accepted, q):
    client, _, bid = accepted
    for _ in range(config.CALLS_PER_HOUR + 2):
        client.post("/booking/%d/call" % bid)
    assert q("SELECT COUNT(*) n FROM call_requests")[0]["n"] == config.CALLS_PER_HOUR

def test_e164_formatting():
    assert app_module.to_e164("9876543210") == "+919876543210"
    assert app_module.to_e164("919876543210") == "+919876543210"


# ------------------------------------------------------------------ complaints + admin
def test_complaint_flow_and_admin_actions(login_as, make_service, make_booking, q):
    client, worker, admin = login_as("client"), login_as("worker"), login_as("admin")
    bid = make_booking(client.user["id"], worker.user["id"], make_service(worker.user["id"]), status="CONFIRMED")
    client.post("/booking/%d/complaint" % bid, {"subject": "No show", "body": "Worker did not come"})
    c = q("SELECT * FROM complaints")[0]
    assert c["against_id"] == worker.user["id"] and c["status"] == "OPEN"
    assert b"No show" in admin.get("/admin").data
    admin.post("/admin/complaint/%d/resolve" % c["id"], {"admin_note": "Warned worker"})
    assert q("SELECT status, admin_note FROM complaints")[0] == {"status": "RESOLVED", "admin_note": "Warned worker"}
    assert worker.post("/admin/complaint/%d/resolve" % c["id"], {}).status_code == 403

def test_admin_can_deactivate_user(login_as, api, make_user, q):
    admin, victim = login_as("admin"), login_as("worker")
    admin.post("/admin/user/%d/toggle" % victim.user["id"])
    assert q("SELECT is_active FROM users WHERE id=%s", (victim.user["id"],))[0]["is_active"] == 0
    assert victim.get("/dashboard").status_code == 302                     # live session is cut off
    assert b"deactivated" in api.login(victim.user["email"]).data          # cannot log in again
    admin.post("/admin/user/%d/toggle" % admin.user["id"])                 # admins are protected
    assert q("SELECT is_active FROM users WHERE id=%s", (admin.user["id"],))[0]["is_active"] == 1

def test_admin_dashboard_redirect(login_as):
    assert login_as("admin").get("/dashboard").headers["Location"].endswith("/admin")


# ------------------------------------------------------------------ translations
def test_language_switch(api):
    api.post("/lang", {"lang": "kn"})
    assert "ನಿಮ್ಮ ಹಳ್ಳಿಯ ಹತ್ತಿರ" in api.get("/").data.decode()
    assert "ಬಡಗಿ" in api.get("/").data.decode()                           # category names translated too
    api.post("/lang", {"lang": "hi"})
    assert "अपने गाँव के पास" in api.get("/").data.decode()
    api.post("/lang", {"lang": "xx"})                                      # unknown code is ignored
    assert "अपने गाँव के पास" in api.get("/").data.decode()

def test_language_redirect_is_local_only(api):
    r = api.post("/lang", {"lang": "en", "next": "//evil.example"})
    assert r.headers["Location"].endswith("/") and "evil" not in r.headers["Location"]

def test_language_saved_on_profile_for_logged_in_user(login_as, q):
    u = login_as("client")
    u.post("/lang", {"lang": "kn"})
    assert q("SELECT language FROM users WHERE id=%s", (u.user["id"],))[0]["language"] == "kn-IN"

def test_translation_tables_are_complete():
    from translations import EN, HI, KN
    assert set(EN) == set(HI) == set(KN)


# ------------------------------------------------------------------ PWA / mobile
def test_pwa_files(api):
    m = json.loads(api.get("/manifest.webmanifest").data)
    assert m["display"] == "standalone" and {i["sizes"] for i in m["icons"]} >= {"192x192", "512x512"}
    sw = api.get("/sw.js")
    assert "javascript" in sw.content_type and sw.headers["Service-Worker-Allowed"] == "/"
    assert api.get("/static/icons/icon-192.png").status_code == 200
    assert api.get("/offline").status_code == 200
    assert b'rel="manifest"' in api.get("/").data


# ------------------------------------------------------------------ image-based selection
def _png():
    buf = io.BytesIO(); Image.new("RGB", (8, 8), "green").save(buf, "PNG"); buf.seek(0); return buf

def test_service_photo_upload(login_as, q):
    worker = login_as("worker")
    worker.post("/services/add", {"category_id": "1", "title": "Ploughing", "price": "900",
                                  "image": (_png(), "field.png")}, content_type="multipart/form-data")
    img = q("SELECT image FROM services")[0]["image"]
    path = os.path.join(config.UPLOAD_FOLDER, img or "none")
    try:
        assert img and os.path.exists(path)
        assert img in worker.get("/search").data.decode()                  # shown on the search card
    finally:
        if img and os.path.exists(path):
            os.remove(path)

def test_non_image_upload_is_refused(login_as, q):
    worker = login_as("worker")
    worker.post("/services/add", {"category_id": "1", "title": "X", "price": "9",
                                  "image": (io.BytesIO(b"MZ"), "virus.exe")}, content_type="multipart/form-data")
    assert q("SELECT image FROM services")[0]["image"] is None

def test_category_picture_replaces_emoji_when_present(api):
    path = os.path.join(ROOT, "static", "img", "categories", "1.png")
    _png_img = Image.new("RGB", (8, 8), "green"); _png_img.save(path)
    try:
        assert b"img/categories/1.png" in api.get("/").data
    finally:
        os.remove(path)
    assert b"img/categories/1.png" not in api.get("/").data


# ------------------------------------------------------------------ every page renders (all roles, all languages)
@pytest.mark.parametrize("lang", ["en", "hi", "kn"])
def test_all_pages_render(login_as, make_service, make_booking, lang):
    client, worker, admin = login_as("client"), login_as("worker"), login_as("admin")
    bid = make_booking(client.user["id"], worker.user["id"], make_service(worker.user["id"]), status="COMPLETED")
    anon = Api()
    for who, urls in [(anon, ["/", "/login", "/register", "/search", "/worker/%d" % worker.user["id"], "/offline"]),
                      (client, ["/dashboard", "/profile", "/booking/%d" % bid, "/search?category=1&date=" + future()]),
                      (worker, ["/dashboard", "/profile", "/booking/%d" % bid]),
                      (admin, ["/admin", "/profile"])]:
        who.post("/lang", {"lang": lang})
        for url in urls:
            assert who.get(url).status_code == 200, url
