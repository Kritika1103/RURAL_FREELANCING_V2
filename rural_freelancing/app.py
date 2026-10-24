"""Rural Freelancing - Flask application (run with:  python app.py)"""
import os, re, math, secrets, uuid, hmac, base64, json
import urllib.error, urllib.parse, urllib.request
from datetime import date, timedelta
from functools import wraps

import pymysql
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, g, jsonify, abort, send_from_directory)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

import config
from translations import LANGS, VOICE_CODES, translate

app = Flask(__name__)
app.config.from_object(config)
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# ---------------------------------------------------------------- database
def get_db():
    if "db" not in g:
        g.db = pymysql.connect(
            host=config.DB_HOST, user=config.DB_USER, password=config.DB_PASSWORD,
            database=config.DB_NAME, charset="utf8mb4", autocommit=True,
            cursorclass=pymysql.cursors.DictCursor)
    return g.db

@app.teardown_appcontext
def close_db(_err=None):
    db = g.pop("db", None)
    if db:
        db.close()

def query(sql, args=(), one=False):
    """SELECT helper. Always uses %s placeholders (parameterized = safe from SQL injection)."""
    with get_db().cursor() as cur:
        cur.execute(sql, args)
        rows = list(cur.fetchall())   # pymysql returns () when empty; callers expect a list
    if one:
        return rows[0] if rows else None
    return rows

def execute(sql, args=()):
    with get_db().cursor() as cur:
        cur.execute(sql, args)
        return cur.lastrowid

# ---------------------------------------------------------------- security
@app.before_request
def load_user_and_check_csrf():
    g.user = None
    if session.get("user_id"):
        g.user = query("SELECT * FROM users WHERE id=%s", (session["user_id"],), one=True)
        if g.user is None or not g.user["is_active"]:
            session.clear()
            g.user = None
    if request.method == "POST":
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
        expected = session.get("csrf_token") or ""
        # constant-time comparison (a plain != can leak how many leading characters matched)
        if not sent or not hmac.compare_digest(sent.encode(), expected.encode()):
            abort(400, "Invalid or missing CSRF token. Please reload the page.")

@app.context_processor
def inject_helpers():
    def csrf_token():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(16)
        return session["csrf_token"]
    lang = get_lang()
    return {"csrf_token": csrf_token, "current_user": g.get("user"), "lang": lang, "langs": LANGS,
            "voice_code": VOICE_CODES[lang],
            "t": lambda key, **kw: translate(lang, key, **kw),
            "cat_img": category_image}

def get_lang():
    """UI language: session choice, else the language saved on the user's profile, else English."""
    code = session.get("lang")
    if code not in LANGS and g.get("user"):
        code = (g.user.get("language") or "en")[:2]
    return code if code in LANGS else "en"

CATEGORY_IMG_DIR = os.path.join(os.path.dirname(__file__), "static", "img", "categories")

def category_image(cat_id):
    """URL of static/img/categories/<id>.(jpg|jpeg|png|webp) if the file exists, else None (emoji is used)."""
    for ext in ("jpg", "jpeg", "png", "webp"):
        if os.path.exists(os.path.join(CATEGORY_IMG_DIR, "%s.%s" % (cat_id, ext))):
            return url_for("static", filename="img/categories/%s.%s" % (cat_id, ext))
    return None

def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not g.user:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper

def role_required(role):
    def deco(f):
        @wraps(f)
        @login_required
        def wrapper(*a, **kw):
            if g.user["role"] != role:
                abort(403)
            return f(*a, **kw)
        return wrapper
    return deco

def allowed_file(name):
    return "." in name and name.rsplit(".", 1)[1].lower() in config.ALLOWED_EXTENSIONS

def save_upload(file):
    """Validate extension, make a random safe filename, save it."""
    if not file or not file.filename:
        return None
    if not allowed_file(file.filename):
        flash("Only PNG or JPG images are allowed.", "danger")
        return None
    name = uuid.uuid4().hex + "_" + secure_filename(file.filename)
    file.save(os.path.join(config.UPLOAD_FOLDER, name))
    return name

# ---------------------------------------------------------------- helpers
def haversine(lat1, lon1, lat2, lon2):
    """Great-circle distance in km between two GPS points."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))

def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def get_booking_or_404(booking_id):
    b = query("""SELECT b.*, s.title AS service_title, s.price AS list_price, s.price_unit,
                        cu.name AS client_name, wu.name AS worker_name
                 FROM bookings b
                 JOIN services s ON s.id=b.service_id
                 JOIN users cu ON cu.id=b.client_id
                 JOIN users wu ON wu.id=b.worker_id
                 WHERE b.id=%s""", (booking_id,), one=True)
    if not b or g.user["id"] not in (b["client_id"], b["worker_id"]):
        abort(404)
    return b

def parse_date(v):
    try:
        return date.fromisoformat(v)
    except (TypeError, ValueError):
        return None

COMMITTED = "('ACCEPTED','CONFIRMED','IN_PROGRESS')"   # statuses that reserve the worker's day

def worker_is_free(worker_id, day, exclude_booking=None):
    """True if the day is not blocked by the worker and no other committed booking holds it."""
    if query("SELECT id FROM unavailable_dates WHERE worker_id=%s AND off_date=%s", (worker_id, day), one=True):
        return False
    sql = "SELECT id FROM bookings WHERE worker_id=%s AND scheduled_date=%s AND status IN " + COMMITTED
    args = [worker_id, day]
    if exclude_booking:
        sql += " AND id<>%s"
        args.append(exclude_booking)
    return query(sql, args, one=True) is None

def to_e164(phone):
    digits = "".join(ch for ch in phone if ch.isdigit())
    return config.DEFAULT_COUNTRY_CODE + digits if len(digits) == 10 else "+" + digits

def telephony_enabled():
    return bool(config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN and config.TWILIO_NUMBER
                and re.fullmatch(r"\+\d{8,15}", config.TWILIO_NUMBER))

def place_twilio_call(caller_phone, callee_phone):
    """Twilio rings the caller first, then bridges to the other person.  Both only ever see the
    Twilio number as caller ID, so real numbers stay hidden.  Returns the call SID."""
    twiml = ('<Response><Say>Connecting you through Rural Freelancing.</Say>'
             '<Dial callerId="%s">%s</Dial></Response>' % (config.TWILIO_NUMBER, callee_phone))
    data = urllib.parse.urlencode({"To": caller_phone, "From": config.TWILIO_NUMBER, "Twiml": twiml}).encode()
    req = urllib.request.Request(
        "https://api.twilio.com/2010-04-01/Accounts/%s/Calls.json" % config.TWILIO_ACCOUNT_SID, data=data)
    cred = base64.b64encode(("%s:%s" % (config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)).encode()).decode()
    req.add_header("Authorization", "Basic " + cred)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)["sid"]

def system_message(booking_id, text):
    execute("INSERT INTO messages (booking_id, sender_id, body) VALUES (%s,NULL,%s)", (booking_id, text))

# ---------------------------------------------------------------- public pages
@app.route("/")
def index():
    categories = query("SELECT * FROM categories ORDER BY id")
    return render_template("index.html", categories=categories)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form
        name, email = f.get("name", "").strip(), f.get("email", "").strip().lower()
        phone, role = f.get("phone", "").strip(), f.get("role")
        password = f.get("password", "")
        village = f.get("village", "").strip()
        if not name or "@" not in email or role not in ("client", "worker"):
            flash("Please fill in name, a valid email and choose a role.", "danger")
        elif not (phone.isdigit() and 10 <= len(phone) <= 15):
            flash("Phone must be 10-15 digits.", "danger")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
        elif query("SELECT id FROM users WHERE email=%s", (email,), one=True):
            flash("That email is already registered.", "danger")
        else:
            uid = execute("INSERT INTO users (name,email,password_hash,role,phone,village,latitude,longitude) "
                          "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                          (name, email, generate_password_hash(password), role, phone, village,
                           to_float(f.get("latitude")), to_float(f.get("longitude"))))
            if role == "worker":
                execute("INSERT INTO worker_profiles (user_id) VALUES (%s)", (uid,))
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = query("SELECT * FROM users WHERE email=%s", (email,), one=True)
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            if not user["is_active"]:
                flash("This account has been deactivated. Please contact the administrator.", "danger")
                return render_template("login.html")
            session.clear()
            session["user_id"] = user["id"]
            session["csrf_token"] = secrets.token_hex(16)
            flash("Welcome, %s!" % user["name"], "success")
            return redirect(url_for("dashboard"))
        flash("Wrong email or password.", "danger")
    return render_template("login.html")

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("index"))

# ---------------------------------------------------------------- language + PWA
@app.route("/lang", methods=["POST"])
def set_language():
    code = request.form.get("lang", "")
    if code in LANGS:
        session["lang"] = code
        if g.user:
            execute("UPDATE users SET language=%s WHERE id=%s", (code + "-IN", g.user["id"]))
    nxt = request.form.get("next", "/")
    if not nxt.startswith("/") or nxt.startswith("//"):      # only allow local redirects
        nxt = "/"
    return redirect(nxt)

@app.route("/sw.js")
def service_worker():
    resp = send_from_directory(app.static_folder, "sw.js", mimetype="application/javascript")
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp

@app.route("/manifest.webmanifest")
def manifest():
    return send_from_directory(app.static_folder, "manifest.webmanifest", mimetype="application/manifest+json")

@app.route("/offline")
def offline():
    return render_template("offline.html")

# ---------------------------------------------------------------- dashboards / profile
@app.route("/dashboard")
@login_required
def dashboard():
    uid = g.user["id"]
    if g.user["role"] == "admin":
        return redirect(url_for("admin_home"))
    if g.user["role"] == "client":
        bookings = query("""SELECT b.*, s.title, wu.name AS other_name FROM bookings b
                            JOIN services s ON s.id=b.service_id JOIN users wu ON wu.id=b.worker_id
                            WHERE b.client_id=%s ORDER BY b.id DESC""", (uid,))
        categories = query("SELECT * FROM categories ORDER BY id")
        return render_template("dashboard_client.html", bookings=bookings, categories=categories)
    profile = query("SELECT * FROM worker_profiles WHERE user_id=%s", (uid,), one=True)
    services = query("""SELECT s.*, c.name AS category FROM services s
                        JOIN categories c ON c.id=s.category_id WHERE s.worker_id=%s""", (uid,))
    bookings = query("""SELECT b.*, s.title, cu.name AS other_name FROM bookings b
                        JOIN services s ON s.id=b.service_id JOIN users cu ON cu.id=b.client_id
                        WHERE b.worker_id=%s ORDER BY b.id DESC""", (uid,))
    rating = query("SELECT AVG(rating) a, COUNT(*) n FROM reviews WHERE worker_id=%s", (uid,), one=True)
    categories = query("SELECT * FROM categories ORDER BY name")
    off_dates = query("SELECT * FROM unavailable_dates WHERE worker_id=%s AND off_date>=%s ORDER BY off_date",
                      (uid, date.today()))
    return render_template("dashboard_worker.html", profile=profile, services=services,
                           bookings=bookings, rating=rating, categories=categories,
                           off_dates=off_dates, today=date.today().isoformat())

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    uid = g.user["id"]
    if request.method == "POST":
        f = request.form
        phone = f.get("phone", "").strip()
        if not f.get("name", "").strip() or not (phone.isdigit() and 10 <= len(phone) <= 15):
            flash("Name and a valid phone (10-15 digits) are required.", "danger")
            return redirect(url_for("profile"))
        execute("UPDATE users SET name=%s, phone=%s, village=%s, latitude=%s, longitude=%s, language=%s WHERE id=%s",
                (f["name"].strip(), phone, f.get("village", "").strip(),
                 to_float(f.get("latitude")), to_float(f.get("longitude")),
                 f.get("language", "en-IN"), uid))
        if g.user["role"] == "worker":
            photo = save_upload(request.files.get("photo"))
            execute("UPDATE worker_profiles SET skills=%s, bio=%s, experience_years=%s, available=%s WHERE user_id=%s",
                    (f.get("skills", "").strip(), f.get("bio", "").strip(),
                     int(f.get("experience_years") or 0), 1 if f.get("available") else 0, uid))
            if photo:
                execute("UPDATE worker_profiles SET photo=%s WHERE user_id=%s", (photo, uid))
        if f.get("language", "")[:2] in LANGS:
            session["lang"] = f["language"][:2]
        flash("Profile saved.", "success")
        return redirect(url_for("dashboard"))
    wp = query("SELECT * FROM worker_profiles WHERE user_id=%s", (uid,), one=True)
    return render_template("profile.html", wp=wp)

# ---------------------------------------------------------------- worker services
@app.route("/services/add", methods=["POST"])
@role_required("worker")
def add_service():
    f = request.form
    price = to_float(f.get("price"))
    if not f.get("title", "").strip() or price is None or price <= 0:
        flash("Service title and a positive price are required.", "danger")
    else:
        image = save_upload(request.files.get("image"))
        execute("INSERT INTO services (worker_id,category_id,title,description,price,price_unit,image) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (g.user["id"], int(f["category_id"]), f["title"].strip(),
                 f.get("description", "").strip(), price, f.get("price_unit", "per day"), image))
        flash("Service added.", "success")
    return redirect(url_for("dashboard"))

@app.route("/services/<int:sid>/delete", methods=["POST"])
@role_required("worker")
def delete_service(sid):
    try:
        execute("DELETE FROM services WHERE id=%s AND worker_id=%s", (sid, g.user["id"]))
        flash("Service removed.", "info")
    except pymysql.err.IntegrityError:
        flash("This service already has bookings, so it cannot be deleted.", "warning")
    return redirect(url_for("dashboard"))

@app.route("/availability/add", methods=["POST"])
@role_required("worker")
def add_unavailable():
    day = parse_date(request.form.get("off_date"))
    if not day or day < date.today():
        flash("Choose a valid date from today onwards.", "danger")
    elif query("SELECT id FROM bookings WHERE worker_id=%s AND scheduled_date=%s AND status IN " + COMMITTED,
               (g.user["id"], day), one=True):
        flash("You already have a booking on that date, so it cannot be blocked.", "warning")
    else:
        execute("INSERT IGNORE INTO unavailable_dates (worker_id, off_date) VALUES (%s,%s)", (g.user["id"], day))
        flash("Date blocked.", "success")
    return redirect(url_for("dashboard"))

@app.route("/availability/<int:aid>/delete", methods=["POST"])
@role_required("worker")
def delete_unavailable(aid):
    execute("DELETE FROM unavailable_dates WHERE id=%s AND worker_id=%s", (aid, g.user["id"]))
    return redirect(url_for("dashboard"))

# ---------------------------------------------------------------- search & matching
@app.route("/search")
def search():
    """Location-based matching + rule-based filtering (the core algorithm)."""
    category_id = request.args.get("category", type=int)
    q = request.args.get("q", "").strip()
    radius = request.args.get("radius", type=float)
    max_price = request.args.get("max_price", type=float)
    lat, lng = request.args.get("lat", type=float), request.args.get("lng", type=float)
    day = parse_date(request.args.get("date", ""))
    if lat is None and g.user and g.user["latitude"] is not None:
        lat, lng = g.user["latitude"], g.user["longitude"]

    # Rule 1: only available workers; Rule 2: category / keyword; Rule 3: price
    sql = """SELECT s.*, c.name AS category, c.icon, u.name AS worker_name, u.village,
                    u.latitude, u.longitude, wp.experience_years, wp.skills, wp.photo,
                    (SELECT AVG(rating) FROM reviews r WHERE r.worker_id=u.id) AS avg_rating,
                    (SELECT COUNT(*) FROM reviews r WHERE r.worker_id=u.id) AS review_count
             FROM services s
             JOIN categories c ON c.id=s.category_id
             JOIN users u ON u.id=s.worker_id
             JOIN worker_profiles wp ON wp.user_id=u.id
             WHERE wp.available=1"""
    args = []
    if category_id:
        sql += " AND s.category_id=%s"; args.append(category_id)
    if q:
        sql += " AND (s.title LIKE %s OR c.name LIKE %s OR wp.skills LIKE %s OR u.village LIKE %s)"
        args += ["%" + q + "%"] * 4
    if max_price:
        sql += " AND s.price<=%s"; args.append(max_price)
    if day:   # Rule 3b: worker must be free on the requested date
        sql += (" AND NOT EXISTS (SELECT 1 FROM unavailable_dates d WHERE d.worker_id=s.worker_id AND d.off_date=%s)"
                " AND NOT EXISTS (SELECT 1 FROM bookings b WHERE b.worker_id=s.worker_id AND b.scheduled_date=%s"
                " AND b.status IN " + COMMITTED + ")")
        args += [day, day]
    results = query(sql, args)

    # Rule 4: distance using Haversine formula, then radius filter
    for r in results:
        r["distance"] = None
        if lat is not None and r["latitude"] is not None:
            r["distance"] = round(haversine(lat, lng, r["latitude"], r["longitude"]), 1)
    if radius and lat is not None:
        results = [r for r in results if r["distance"] is not None and r["distance"] <= radius]
    results.sort(key=lambda r: (r["distance"] is None, r["distance"] or 0, -(float(r["avg_rating"] or 0))))

    categories = query("SELECT * FROM categories ORDER BY id")
    return render_template("search.html", results=results, categories=categories,
                           category_id=category_id, q=q, radius=radius, max_price=max_price,
                           lat=lat, lng=lng, day=day.isoformat() if day else "")

@app.route("/worker/<int:wid>")
def worker_profile(wid):
    w = query("""SELECT u.id,u.name,u.village,u.latitude,u.longitude,wp.* FROM users u
                 JOIN worker_profiles wp ON wp.user_id=u.id WHERE u.id=%s AND u.role='worker'""",
              (wid,), one=True)
    if not w:
        abort(404)
    services = query("SELECT s.*, c.name AS category, c.icon FROM services s JOIN categories c "
                     "ON c.id=s.category_id WHERE s.worker_id=%s", (wid,))
    reviews = query("SELECT r.*, u.name AS client_name FROM reviews r JOIN users u ON u.id=r.client_id "
                    "WHERE r.worker_id=%s ORDER BY r.id DESC", (wid,))
    avg = round(sum(r["rating"] for r in reviews) / len(reviews), 1) if reviews else None
    today = date.today()
    busy = query("SELECT off_date AS d FROM unavailable_dates WHERE worker_id=%s AND off_date BETWEEN %s AND %s "
                 "UNION SELECT scheduled_date FROM bookings WHERE worker_id=%s AND scheduled_date BETWEEN %s AND %s "
                 "AND status IN " + COMMITTED + " ORDER BY d",
                 (wid, today, today + timedelta(days=60), wid, today, today + timedelta(days=60)))
    return render_template("worker_profile.html", w=w, services=services, reviews=reviews,
                           avg=avg, today=today.isoformat(), busy=[r["d"] for r in busy])

# ---------------------------------------------------------------- bookings
@app.route("/book", methods=["POST"])
@role_required("client")
def book():
    f = request.form
    svc = query("SELECT * FROM services WHERE id=%s", (f.get("service_id", 0, type=int),), one=True)
    if not svc:
        abort(404)
    when, address = parse_date(f.get("scheduled_date", "")), f.get("address", "").strip()
    if not address or not when or when < date.today():
        flash("Please enter an address and a date that is today or later.", "danger")
        return redirect(url_for("worker_profile", wid=svc["worker_id"]))
    if not worker_is_free(svc["worker_id"], when):
        flash("This worker is not available on that date. Please choose another day.", "warning")
        return redirect(url_for("worker_profile", wid=svc["worker_id"]))
    my_price = to_float(f.get("offer_price"))
    if my_price and my_price > 0 and float(my_price) != float(svc["price"]):
        offered, by = my_price, "client"
    else:
        offered, by = svc["price"], "worker"
    bid = execute("INSERT INTO bookings (client_id,worker_id,service_id,scheduled_date,address,notes,offered_price,offered_by) "
                  "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                  (g.user["id"], svc["worker_id"], svc["id"], when, address, f.get("notes", "").strip(), offered, by))
    system_message(bid, "Request sent. Price on the table: Rs %s (offered by %s)." % (offered, by))
    flash("Request sent to the worker.", "success")
    return redirect(url_for("booking_detail", bid=bid))

@app.route("/bookings")
@login_required
def bookings():
    return redirect(url_for("dashboard"))

@app.route("/booking/<int:bid>")
@login_required
def booking_detail(bid):
    b = get_booking_or_404(bid)
    msgs = query("SELECT m.*, u.name FROM messages m LEFT JOIN users u ON u.id=m.sender_id "
                 "WHERE m.booking_id=%s ORDER BY m.id", (bid,))
    review = query("SELECT * FROM reviews WHERE booking_id=%s", (bid,), one=True)
    can_accept_offer = (b["offered_price"] is not None and b["agreed_price"] is None
                        and b["offered_by"] != g.user["role"]
                        and b["status"] in ("PENDING", "ACCEPTED"))
    can_offer = b["status"] in ("PENDING", "ACCEPTED")
    complaints = query("SELECT * FROM complaints WHERE booking_id=%s AND complainant_id=%s ORDER BY id DESC",
                       (bid, g.user["id"]))
    can_call = b["status"] in ("ACCEPTED", "CONFIRMED", "IN_PROGRESS")
    return render_template("booking.html", b=b, msgs=msgs, review=review, complaints=complaints,
                           can_accept_offer=can_accept_offer, can_offer=can_offer, can_call=can_call)

# allowed status changes: (current status, action) -> (new status, who may do it)
TRANSITIONS = {
    ("PENDING", "ACCEPTED"): ("ACCEPTED", "worker"),
    ("PENDING", "REJECTED"): ("REJECTED", "worker"),
    ("ACCEPTED", "CONFIRMED"): ("CONFIRMED", "client"),
    ("CONFIRMED", "IN_PROGRESS"): ("IN_PROGRESS", "worker"),
    ("IN_PROGRESS", "COMPLETED"): ("COMPLETED", "worker"),
    ("PENDING", "CANCELLED"): ("CANCELLED", "client"),
    ("ACCEPTED", "CANCELLED"): ("CANCELLED", "client"),
    ("CONFIRMED", "CANCELLED"): ("CANCELLED", "client"),
}

@app.route("/booking/<int:bid>/status", methods=["POST"])
@login_required
def booking_status(bid):
    b = get_booking_or_404(bid)
    action = request.form.get("action", "")
    rule = TRANSITIONS.get((b["status"], action))
    if not rule or rule[1] != g.user["role"]:
        flash("That action is not allowed right now.", "danger")
        return redirect(url_for("booking_detail", bid=bid))
    reserves_day = rule[0] in ("ACCEPTED", "CONFIRMED")
    db = get_db()
    if reserves_day:
        # Lock the worker row so two simultaneous accepts cannot both pass the free-day check.
        db.begin()
        with db.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE id=%s FOR UPDATE", (b["worker_id"],))
        if not worker_is_free(b["worker_id"], b["scheduled_date"], exclude_booking=bid):
            db.rollback()
            flash("This worker is already booked or unavailable on %s." % b["scheduled_date"], "danger")
            return redirect(url_for("booking_detail", bid=bid))
    execute("UPDATE bookings SET status=%s WHERE id=%s", (rule[0], bid))
    if rule[0] == "CONFIRMED" and b["agreed_price"] is None:
        execute("UPDATE bookings SET agreed_price=offered_price WHERE id=%s", (bid,))
    system_message(bid, "Status changed to %s by %s." % (rule[0], g.user["name"]))
    if reserves_day:
        db.commit()
    flash("Status updated to %s." % rule[0], "success")
    return redirect(url_for("booking_detail", bid=bid))

# ---------------------------------------------------------------- negotiation, chat, masked call
@app.route("/booking/<int:bid>/offer", methods=["POST"])
@login_required
def make_offer(bid):
    b = get_booking_or_404(bid)
    price = to_float(request.form.get("price"))
    if b["status"] not in ("PENDING", "ACCEPTED") or not price or price <= 0:
        flash("Enter a valid price while the booking is open.", "danger")
    else:
        execute("UPDATE bookings SET offered_price=%s, offered_by=%s, agreed_price=NULL WHERE id=%s",
                (price, g.user["role"], bid))
        system_message(bid, "%s offered Rs %s." % (g.user["name"], price))
    return redirect(url_for("booking_detail", bid=bid))

@app.route("/booking/<int:bid>/offer/accept", methods=["POST"])
@login_required
def accept_offer(bid):
    b = get_booking_or_404(bid)
    if (b["offered_price"] is not None and b["agreed_price"] is None
            and b["offered_by"] != g.user["role"] and b["status"] in ("PENDING", "ACCEPTED")):
        execute("UPDATE bookings SET agreed_price=offered_price WHERE id=%s", (bid,))
        system_message(bid, "%s accepted the price Rs %s." % (g.user["name"], b["offered_price"]))
        flash("Price agreed.", "success")
    return redirect(url_for("booking_detail", bid=bid))

@app.route("/booking/<int:bid>/message", methods=["POST"])
@login_required
def post_message(bid):
    b = get_booking_or_404(bid)
    body = (request.form.get("body") or (request.json or {}).get("body", "")).strip()
    if b["status"] in ("REJECTED", "CANCELLED") or not body:
        return jsonify(ok=False), 400
    execute("INSERT INTO messages (booking_id,sender_id,body) VALUES (%s,%s,%s)", (bid, g.user["id"], body[:500]))
    return jsonify(ok=True)

@app.route("/booking/<int:bid>/messages")
@login_required
def get_messages(bid):
    get_booking_or_404(bid)
    after = request.args.get("after", 0, type=int)
    rows = query("SELECT m.id, m.sender_id, m.body, DATE_FORMAT(m.created_at,'%%H:%%i') AS t, u.name "
                 "FROM messages m LEFT JOIN users u ON u.id=m.sender_id "
                 "WHERE m.booking_id=%s AND m.id>%s ORDER BY m.id", (bid, after))
    return jsonify(messages=rows, me=g.user["id"])

@app.route("/booking/<int:bid>/call", methods=["POST"])
@login_required
def masked_call(bid):
    """Masked calling.  With Twilio configured: Twilio rings the caller, then bridges to the other person
    and both only see the Twilio number.  Without it: a clearly-labelled simulation (no real call)."""
    b = get_booking_or_404(bid)
    if b["status"] not in ("ACCEPTED", "CONFIRMED", "IN_PROGRESS"):
        flash("Calling opens after the worker accepts the request.", "warning")
        return redirect(url_for("booking_detail", bid=bid))
    recent = query("SELECT COUNT(*) n FROM call_requests WHERE caller_id=%s AND created_at > NOW() - INTERVAL 1 HOUR",
                   (g.user["id"],), one=True)["n"]
    if recent >= config.CALLS_PER_HOUR:
        flash("Call limit reached. Please try again later or use the chat.", "warning")
        return redirect(url_for("booking_detail", bid=bid))
    other_id = b["worker_id"] if g.user["id"] == b["client_id"] else b["client_id"]
    other = query("SELECT phone FROM users WHERE id=%s", (other_id,), one=True)
    if telephony_enabled():
        try:
            sid = place_twilio_call(to_e164(g.user["phone"]), to_e164(other["phone"]))
        except (urllib.error.URLError, KeyError, ValueError, OSError):
            flash("The call could not be placed right now. Please use the chat.", "danger")
            return redirect(url_for("booking_detail", bid=bid))
        execute("INSERT INTO call_requests (booking_id,caller_id,mode,provider_sid) VALUES (%s,%s,'twilio',%s)",
                (bid, g.user["id"], sid))
        flash("Calling your phone now. Pick up and you will be connected. The other person sees only our number.", "info")
    else:
        execute("INSERT INTO call_requests (booking_id,caller_id,mode) VALUES (%s,%s,'demo')", (bid, g.user["id"]))
        flash("Simulated masked call (no telephony provider configured): dial proxy line +91-80000-%05d. "
              "The other person's real number stays hidden." % bid, "info")
    return redirect(url_for("booking_detail", bid=bid))

# ---------------------------------------------------------------- complaints
@app.route("/booking/<int:bid>/complaint", methods=["POST"])
@login_required
def file_complaint(bid):
    if g.user["role"] == "admin":
        abort(403)
    b = get_booking_or_404(bid)
    subject, body = request.form.get("subject", "").strip(), request.form.get("body", "").strip()
    open_n = query("SELECT COUNT(*) n FROM complaints WHERE booking_id=%s AND complainant_id=%s AND status='OPEN'",
                   (bid, g.user["id"]), one=True)["n"]
    if not subject or not body:
        flash("Please fill in the subject and what happened.", "danger")
    elif open_n >= 3:
        flash("You already have open complaints on this booking. The admin will review them.", "warning")
    else:
        against = b["worker_id"] if g.user["id"] == b["client_id"] else b["client_id"]
        execute("INSERT INTO complaints (booking_id,complainant_id,against_id,subject,body) VALUES (%s,%s,%s,%s,%s)",
                (bid, g.user["id"], against, subject[:120], body[:1000]))
        flash("Complaint sent to the administrator.", "success")
    return redirect(url_for("booking_detail", bid=bid))

# ---------------------------------------------------------------- admin module
@app.route("/admin")
@role_required("admin")
def admin_home():
    counts = {r["role"]: r["n"] for r in query("SELECT role, COUNT(*) n FROM users GROUP BY role")}
    by_status = {r["status"]: r["n"] for r in query("SELECT status, COUNT(*) n FROM bookings GROUP BY status")}
    users = query("SELECT id,name,email,role,village,is_active,created_at FROM users ORDER BY id DESC LIMIT 200")
    services = query("""SELECT s.id, s.title, s.price, s.price_unit, c.name AS category, u.name AS worker
                        FROM services s JOIN categories c ON c.id=s.category_id JOIN users u ON u.id=s.worker_id
                        ORDER BY s.id DESC LIMIT 200""")
    bookings = query("""SELECT b.id, b.status, b.scheduled_date, b.agreed_price, b.offered_price, s.title,
                               cu.name AS client, wu.name AS worker
                        FROM bookings b JOIN services s ON s.id=b.service_id
                        JOIN users cu ON cu.id=b.client_id JOIN users wu ON wu.id=b.worker_id
                        ORDER BY b.id DESC LIMIT 200""")
    complaints = query("""SELECT c.*, cu.name AS complainant, au.name AS against_name
                          FROM complaints c JOIN users cu ON cu.id=c.complainant_id JOIN users au ON au.id=c.against_id
                          ORDER BY (c.status='OPEN') DESC, c.id DESC LIMIT 200""")
    return render_template("admin.html", counts=counts, by_status=by_status, users=users,
                           services=services, bookings=bookings, complaints=complaints)

@app.route("/admin/user/<int:uid>/toggle", methods=["POST"])
@role_required("admin")
def admin_toggle_user(uid):
    u = query("SELECT * FROM users WHERE id=%s", (uid,), one=True)
    if not u:
        abort(404)
    if u["role"] == "admin":
        flash("Admin accounts cannot be deactivated here.", "warning")
    else:
        execute("UPDATE users SET is_active=%s WHERE id=%s", (0 if u["is_active"] else 1, uid))
        flash("%s %s." % (u["name"], "deactivated" if u["is_active"] else "re-activated"), "success")
    return redirect(url_for("admin_home"))

@app.route("/admin/service/<int:sid>/delete", methods=["POST"])
@role_required("admin")
def admin_delete_service(sid):
    try:
        execute("DELETE FROM services WHERE id=%s", (sid,))
        flash("Service removed.", "info")
    except pymysql.err.IntegrityError:
        flash("This service already has bookings and cannot be deleted. Deactivate the worker instead.", "warning")
    return redirect(url_for("admin_home"))

@app.route("/admin/complaint/<int:cid>/resolve", methods=["POST"])
@role_required("admin")
def admin_resolve_complaint(cid):
    note = request.form.get("admin_note", "").strip()[:500]
    execute("UPDATE complaints SET status='RESOLVED', admin_note=%s WHERE id=%s", (note, cid))
    flash("Complaint marked resolved.", "success")
    return redirect(url_for("admin_home"))

# ---------------------------------------------------------------- reviews
@app.route("/booking/<int:bid>/review", methods=["POST"])
@role_required("client")
def review(bid):
    b = get_booking_or_404(bid)
    rating = request.form.get("rating", type=int)
    if b["client_id"] != g.user["id"] or b["status"] != "COMPLETED":
        flash("You can review only completed bookings.", "danger")
    elif not rating or not 1 <= rating <= 5:
        flash("Choose a rating from 1 to 5.", "danger")
    elif query("SELECT id FROM reviews WHERE booking_id=%s", (bid,), one=True):
        flash("You already reviewed this booking.", "warning")
    else:
        execute("INSERT INTO reviews (booking_id,client_id,worker_id,rating,comment) VALUES (%s,%s,%s,%s,%s)",
                (bid, g.user["id"], b["worker_id"], rating, request.form.get("comment", "").strip()[:500]))
        flash("Thanks for your review!", "success")
    return redirect(url_for("booking_detail", bid=bid))

# ---------------------------------------------------------------- errors
@app.errorhandler(403)
def forbidden(_e):
    return render_template("error.html", code=403, msg="You do not have access to this page."), 403

@app.errorhandler(404)
def not_found(_e):
    return render_template("error.html", code=404, msg="Page not found."), 404

@app.errorhandler(400)
def bad_request(e):
    return render_template("error.html", code=400, msg=getattr(e, "description", "Bad request")), 400

@app.errorhandler(413)
def too_large(_e):
    return render_template("error.html", code=413, msg="File too large (max 2 MB)."), 413

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")   # never run debug mode on a public server
