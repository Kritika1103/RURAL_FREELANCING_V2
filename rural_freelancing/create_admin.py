"""Create (or reset) an administrator account:  python create_admin.py
The password is typed at a prompt (or taken from ADMIN_PASSWORD) - it is never stored in the repo."""
import os, sys, getpass
import pymysql
from werkzeug.security import generate_password_hash
import config

email = (os.environ.get("ADMIN_EMAIL") or input("Admin email: ")).strip().lower()
password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Admin password (min 10 chars): ")
if "@" not in email or len(password) < 10:
    sys.exit("Use a valid email and a password of at least 10 characters.")

db = pymysql.connect(host=config.DB_HOST, user=config.DB_USER, password=config.DB_PASSWORD,
                     database=config.DB_NAME, charset="utf8mb4", autocommit=True)
cur = db.cursor()
cur.execute("SELECT id FROM users WHERE email=%s", (email,))
row = cur.fetchone()
if row:
    cur.execute("UPDATE users SET password_hash=%s, role='admin', is_active=1 WHERE id=%s",
                (generate_password_hash(password), row[0]))
    print("Existing account promoted/reset to admin:", email)
else:
    cur.execute("INSERT INTO users (name,email,password_hash,role,phone) VALUES ('Administrator',%s,%s,'admin','0000000000')",
                (email, generate_password_hash(password)))
    print("Admin created:", email)
