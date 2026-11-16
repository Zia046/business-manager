"""Small settings kept inside the database (so they are encrypted and travel with a backup)."""
import json

from .common import now


def get(db, key, default=None):
    row = db.one("SELECT value FROM app_settings WHERE key=?", (key,))
    if not row or row["value"] is None:
        return default
    try:
        return json.loads(row["value"])
    except ValueError:
        return default


def put(conn, key, value):
    """Write inside the caller's transaction."""
    conn.execute("INSERT INTO app_settings(key,value,updated_at) VALUES(?,?,?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                 (key, json.dumps(value, ensure_ascii=False), now()))


def save(db, key, value):
    with db.transaction() as c:
        put(c, key, value)
