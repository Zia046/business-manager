"""Registration, login (with lockout), password change."""
import hashlib
import hmac
import json
import os
import re
import shutil
import time
from pathlib import Path

from ..config import LOCKOUT_SECONDS, MAX_LOGIN_ATTEMPTS
from ..db.connection import Database, WrongPasswordError
from .common import BusinessError

GENERIC_ERROR = "Invalid Login ID or Password"
LOCK_FILE = "lock.json"  # lockout state lives outside the encrypted DB (DB is unreadable before login)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    h = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, h = stored.split("$")
        test = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt),
                              n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(test.hex(), h)
    except Exception:
        return False


BRANDING_FILE = "branding.json"


def write_branding(data_dir: Path, name: str, logo_path: str | None):
    """Company name + logo copy kept OUTSIDE the encrypted DB so the login screen can show them."""
    (Path(data_dir) / BRANDING_FILE).write_text(
        json.dumps({"name": name, "logo": logo_path}, ensure_ascii=False), encoding="utf-8")


def read_branding(data_dir: Path) -> dict:
    try:
        return json.loads((Path(data_dir) / BRANDING_FILE).read_text(encoding="utf-8"))
    except Exception:
        return {"name": "", "logo": None}


def is_registered(data_dir: Path) -> bool:
    return Database.exists(data_dir)


def _validate_registration(name, address, phone, email, login_id, password, confirm):
    for label, v in (("Company Name", name), ("Address", address), ("Phone Number", phone),
                     ("Email", email), ("Login ID", login_id), ("Password", password)):
        if not (v or "").strip():
            raise BusinessError(f"{label} is required")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()):
        raise BusinessError("Email address is not valid")
    if not re.fullmatch(r"\+?[0-9][0-9\s\-]{6,18}", phone.strip()):
        raise BusinessError("Phone number is not valid")
    if len(password) < 6:
        raise BusinessError("Password must be at least 6 characters")
    if password != confirm:
        raise BusinessError("Passwords do not match")


def register(data_dir: Path, name, address, phone, email, logo_file, login_id,
             password, confirm) -> Database:
    """First-run registration. Creates the encrypted DB and returns it (logged in)."""
    if is_registered(data_dir):
        raise BusinessError("Company is already registered")
    _validate_registration(name, address, phone, email, login_id, password, confirm)
    logo_path = None
    if logo_file:
        src = Path(logo_file)
        if src.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            raise BusinessError("Logo must be a PNG or JPG file")
        dest = Path(data_dir) / "logo" / f"logo{src.suffix.lower()}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        logo_path = str(dest)
    db = Database(data_dir, password, create=True)
    with db.transaction() as c:
        c.execute("INSERT INTO company(id,name,address,phone,email,logo_path) VALUES(1,?,?,?,?,?)",
                  (name.strip(), address.strip(), phone.strip(), email.strip(), logo_path))
        c.execute("INSERT INTO users(login_id,pass_hash) VALUES(?,?)",
                  (login_id.strip(), hash_password(password)))
        # default customer used for cash sales
        c.execute("INSERT INTO parties(kind,name,is_walkin) VALUES('customer','Walk-in Customer',1)")
    write_branding(data_dir, name.strip(), logo_path)
    return db


# ---------- lockout ----------
def _lock_state(data_dir: Path) -> dict:
    try:
        return json.loads((Path(data_dir) / LOCK_FILE).read_text())
    except Exception:
        return {"attempts": 0, "until": 0}


def _save_lock(data_dir: Path, state: dict):
    (Path(data_dir) / LOCK_FILE).write_text(json.dumps(state))


def login(data_dir: Path, login_id: str, password: str) -> Database:
    st = _lock_state(data_dir)
    if st["until"] > time.time():
        mins = int((st["until"] - time.time()) // 60) + 1
        raise BusinessError(f"Too many failed attempts. Try again in {mins} minute(s).")
    try:
        db = Database(data_dir, password)
        user = db.one("SELECT * FROM users WHERE login_id=?", ((login_id or "").strip(),))
        if not user or not verify_password(password, user["pass_hash"]):
            db.close()
            raise WrongPasswordError()
    except WrongPasswordError:
        st["attempts"] += 1
        if st["attempts"] >= MAX_LOGIN_ATTEMPTS:
            st = {"attempts": 0, "until": time.time() + LOCKOUT_SECONDS}
        _save_lock(data_dir, st)
        raise BusinessError(GENERIC_ERROR)
    _save_lock(data_dir, {"attempts": 0, "until": 0})
    return db


def change_credentials(db: Database, current_password: str, new_login_id: str,
                       new_password: str | None):
    user = db.one("SELECT * FROM users LIMIT 1")
    if not verify_password(current_password, user["pass_hash"]):
        raise BusinessError("Current password is incorrect")
    if not new_login_id.strip():
        raise BusinessError("Login ID is required")
    pw = new_password or current_password
    if len(pw) < 6:
        raise BusinessError("Password must be at least 6 characters")
    with db.transaction() as c:
        c.execute("UPDATE users SET login_id=?, pass_hash=? WHERE id=?",
                  (new_login_id.strip(), hash_password(pw), user["id"]))
    if new_password:
        db.rekey(new_password)  # the encryption key follows the password
