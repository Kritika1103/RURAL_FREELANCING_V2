"""Adds DEMO users and services. Run once after database.sql:  python seed.py
Demo credentials are for testing only - delete them before any real use."""
import pymysql
from werkzeug.security import generate_password_hash
import config

db = pymysql.connect(host=config.DB_HOST, user=config.DB_USER, password=config.DB_PASSWORD,
                     database=config.DB_NAME, charset="utf8mb4", autocommit=True,
                     cursorclass=pymysql.cursors.DictCursor)
cur = db.cursor()

def add_user(name, email, pw, role, phone, village, lat, lng):
    cur.execute("SELECT id FROM users WHERE email=%s", (email,))
    row = cur.fetchone()
    if row:
        return row["id"]
    cur.execute("INSERT INTO users (name,email,password_hash,role,phone,village,latitude,longitude) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (name, email, generate_password_hash(pw), role, phone, village, lat, lng))
    uid = cur.lastrowid
    if role == "worker":
        cur.execute("INSERT INTO worker_profiles (user_id,skills,bio,experience_years,available) "
                    "VALUES (%s,%s,%s,%s,1)", (uid, "", "Demo worker profile.", 5))
    return uid

def cat(name):
    cur.execute("SELECT id FROM categories WHERE name=%s", (name,))
    return cur.fetchone()["id"]

add_user("Demo Client", "client@example.com", "Client@123", "client", "9000000001", "Mandya", 12.5266, 76.8970)

workers = [
 ("Ramesh Kumar", "worker@example.com", "Electrician", "House wiring and pump-set repair", 500, "per day", 12.5218, 76.8951, "electrician, wiring, pump repair"),
 ("Suresh Gowda", "suresh@example.com", "Tractor Operation", "Tractor ploughing with own tractor", 1200, "per day", 12.5500, 76.9200, "tractor, ploughing, tilling"),
 ("Manjunath", "manju@example.com", "Plumber", "Pipe fitting and borewell connection", 450, "per day", 12.6000, 76.9500, "plumbing, pipes"),
 ("Lakshmi Devi", "lakshmi@example.com", "Harvesting", "Paddy and sugarcane harvesting team", 400, "per day", 12.4000, 76.8000, "harvesting, sugarcane, paddy"),
 ("Basavaraj", "basu@example.com", "Carpenter", "Doors, windows and farm tools", 600, "per day", 12.9000, 77.2000, "carpentry, furniture"),
]
for name, email, category, title, price, unit, lat, lng, skills in workers:
    uid = add_user(name, email, "Worker@123", "worker", "9000000" + str(100 + len(email)), "Near Mandya", lat, lng)
    cur.execute("UPDATE worker_profiles SET skills=%s WHERE user_id=%s", (skills, uid))
    cur.execute("SELECT id FROM services WHERE worker_id=%s", (uid,))
    if not cur.fetchone():
        cur.execute("INSERT INTO services (worker_id,category_id,title,description,price,price_unit) "
                    "VALUES (%s,%s,%s,%s,%s,%s)", (uid, cat(category), title, title + ".", price, unit))
print("Demo data added.")
