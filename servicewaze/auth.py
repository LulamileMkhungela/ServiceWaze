"""Lightweight auth for ServiceWaze: username + password (hashed), session tokens.

Reads (feed, status, chat messages) stay open to everyone. Writing to the
community chat requires a logged-in user. Passwords are hashed with
PBKDF2-SHA256 (salted); sessions are random tokens with 7-day expiry.
No external auth service needed — self-contained, POPIA-friendly.
"""
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from datetime import datetime, timezone

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "servicewaze.db")
SESSION_DAYS = 7


def _db():
    os.makedirs(DATA_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        pw_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        created TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS sessions(
        token TEXT PRIMARY KEY,
        username TEXT NOT NULL,
        expires REAL)""")
    con.commit()
    return con


def _hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()


def register(username, password):
    username = username.strip()
    if not (3 <= len(username) <= 24):
        return None, "Username must be 3-24 characters."
    if len(password) < 6:
        return None, "Password must be at least 6 characters."
    salt = secrets.token_hex(16)
    con = _db()
    try:
        con.execute(
            "INSERT INTO users(username, pw_hash, salt, created) VALUES(?,?,?,?)",
            (username, _hash(password, salt), salt,
             datetime.now(timezone.utc).isoformat(timespec="seconds")))
        con.commit()
    except sqlite3.IntegrityError:
        con.close()
        return None, "Username already taken."
    con.close()
    return username, None


def login(username, password):
    con = _db()
    row = con.execute("SELECT username, pw_hash, salt FROM users WHERE username=?", (username.strip(),)).fetchone()
    if not row:
        con.close()
        return None
    stored_hash, salt = row[1], row[2]
    if not hmac.compare_digest(_hash(password, salt), stored_hash):
        con.close()
        return None
    token = secrets.token_hex(32)
    con.execute("INSERT OR REPLACE INTO sessions(token, username, expires) VALUES(?,?,?)",
                (token, row[0], time.time() + SESSION_DAYS * 86400))
    con.commit()
    con.close()
    return token


def verify_token(token):
    if not token:
        return None
    con = _db()
    row = con.execute("SELECT username, expires FROM sessions WHERE token=?", (token,)).fetchone()
    con.close()
    if not row:
        return None
    if time.time() > row[1]:
        logout(token)
        return None
    return row[0]


def logout(token):
    if not token:
        return
    con = _db()
    con.execute("DELETE FROM sessions WHERE token=?", (token,))
    con.commit()
    con.close()


def me(token):
    return verify_token(token)
