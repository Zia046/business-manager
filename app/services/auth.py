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
from .common import BusinessError, log_audit, set_current_user

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


def write_branding(data_dir: Path, name: str, logo_path: str | None, login_id: str | None = None):
    """Company name, logo and the last login id, kept OUTSIDE the encrypted DB so the login screen
    can show them (and ask only for the password). login_id=None keeps the one already remembered."""
    if login_id is None:
        login_id = read_branding(data_dir).get("login_id")
    (Path(data_dir) / BRANDING_FILE).write_text(
        json.dumps({"name": name, "logo": logo_path, "login_id": login_id}, ensure_ascii=False),
        encoding="utf-8")


def read_branding(data_dir: Path) -> dict:
    try:
        return json.loads((Path(data_dir) / BRANDING_FILE).read_text(encoding="utf-8"))
    except Exception:
        return {"name": "", "logo": None, "login_id": None}


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
    db = Database(data_dir, password, create=True, login_id=login_id.strip())
    with db.transaction() as c:
        c.execute("INSERT INTO company(id,name,address,phone,email,logo_path) VALUES(1,?,?,?,?,?)",
                  (name.strip(), address.strip(), phone.strip(), email.strip(), logo_path))
        c.execute("INSERT INTO users(login_id,pass_hash,role,name) VALUES(?,?,'owner','Owner')",
                  (login_id.strip(), hash_password(password)))
        # default customer used for cash sales
        c.execute("INSERT INTO parties(kind,name,is_walkin) VALUES('customer','Walk-in Customer',1)")
    write_branding(data_dir, name.strip(), logo_path, login_id.strip())
    db.user = db.one("SELECT * FROM users WHERE login_id=?", (login_id.strip(),))
    set_current_user(db.user)
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
        db = Database(data_dir, password, login_id=(login_id or "").strip())
        user = db.one("SELECT * FROM users WHERE login_id=?", ((login_id or "").strip(),))
        if not user or not user["active"] or not verify_password(password, user["pass_hash"]):
            db.close()
            raise WrongPasswordError()
    except WrongPasswordError:
        st["attempts"] += 1
        if st["attempts"] >= MAX_LOGIN_ATTEMPTS:
            st = {"attempts": 0, "until": time.time() + LOCKOUT_SECONDS}
        _save_lock(data_dir, st)
        raise BusinessError(GENERIC_ERROR)
    _save_lock(data_dir, {"attempts": 0, "until": 0})
    if not db.keys_path.exists():                  # database from before key slots: add this user's slot
        db.set_slot(user["login_id"], password)
    set_current_user(user)
    _fix_logo_path(db, data_dir)
    brand = read_branding(data_dir)
    write_branding(data_dir, brand.get("name") or "", brand.get("logo"), user["login_id"])  # remember for next time
    db.user = user
    log_audit(db, "Login", user["login_id"])
    return db


def _fix_logo_path(db, data_dir: Path):
    """After restoring a backup made on another computer/drive the stored logo path may be stale."""
    co = db.one("SELECT logo_path FROM company WHERE id=1")
    if co and co["logo_path"] and not Path(co["logo_path"]).exists():
        local = Path(data_dir) / "logo" / Path(co["logo_path"]).name
        if local.exists():
            with db.transaction() as c:
                c.execute("UPDATE company SET logo_path=? WHERE id=1", (str(local),))
            write_branding(data_dir, db.one("SELECT name FROM company WHERE id=1")["name"], str(local))


def change_credentials(db: Database, current_password: str, new_login_id: str,
                       new_password: str | None):
    """Changes the login id / password of the user who is logged in."""
    from .common import current_login
    user = db.one("SELECT * FROM users WHERE login_id=?", (current_login(),)) or db.one("SELECT * FROM users LIMIT 1")
    if not verify_password(current_password, user["pass_hash"]):
        raise BusinessError("Current password is incorrect")
    if not new_login_id.strip():
        raise BusinessError("Login ID is required")
    pw = new_password or current_password
    if len(pw) < 6:
        raise BusinessError("Password must be at least 6 characters")
    new_id = new_login_id.strip()
    if new_id != user["login_id"] and db.one("SELECT 1 FROM users WHERE login_id=?", (new_id,)):
        raise BusinessError("This Login ID is already used")
    with db.transaction() as c:
        c.execute("UPDATE users SET login_id=?, pass_hash=? WHERE id=?", (new_id, hash_password(pw), user["id"]))
    if new_id != user["login_id"]:
        db.remove_slot(user["login_id"])
    db.set_slot(new_id, pw)                        # the database key is re-locked with the new password
    set_current_user({**user, "login_id": new_id})
    log_audit(db, "Login details changed", new_id)
    brand = read_branding(db.data_dir)
    write_branding(db.data_dir, brand.get("name") or "", brand.get("logo"), new_id)


# ---------- staff accounts (owner only) ----------
def _need_owner():
    from .common import is_owner
    if not is_owner():
        raise BusinessError("Only the owner can manage staff accounts")


def list_users(db):
    return db.query("SELECT id, login_id, name, role, active FROM users ORDER BY role DESC, login_id")


def add_staff(db, owner_password, name, login_id, password):
    _need_owner()
    _check_owner_password(db, owner_password)
    login_id, name = (login_id or "").strip(), (name or "").strip()
    if not login_id or not name:
        raise BusinessError("Name and Login ID are required")
    if len(password or "") < 6:
        raise BusinessError("Password must be at least 6 characters")
    if db.one("SELECT 1 FROM users WHERE login_id=?", (login_id,)):
        raise BusinessError("This Login ID is already used")
    with db.transaction() as c:
        c.execute("INSERT INTO users(login_id,pass_hash,role,name) VALUES(?,?,'staff',?)",
                  (login_id, hash_password(password), name))
    db.set_slot(login_id, password)
    log_audit(db, "Staff account added", f"{name} ({login_id})")


def reset_staff_password(db, owner_password, login_id, new_password):
    _need_owner()
    _check_owner_password(db, owner_password)
    if len(new_password or "") < 6:
        raise BusinessError("Password must be at least 6 characters")
    user = db.one("SELECT * FROM users WHERE login_id=? AND role='staff'", (login_id,))
    if not user:
        raise BusinessError("Staff account not found")
    with db.transaction() as c:
        c.execute("UPDATE users SET pass_hash=? WHERE id=?", (hash_password(new_password), user["id"]))
    db.set_slot(login_id, new_password)
    log_audit(db, "Staff password reset", login_id)


def set_staff_active(db, owner_password, login_id, active: bool):
    _need_owner()
    _check_owner_password(db, owner_password)
    user = db.one("SELECT * FROM users WHERE login_id=? AND role='staff'", (login_id,))
    if not user:
        raise BusinessError("Staff account not found")
    with db.transaction() as c:
        c.execute("UPDATE users SET active=? WHERE id=?", (1 if active else 0, user["id"]))
    log_audit(db, "Staff account " + ("enabled" if active else "disabled"), login_id)


def _check_owner_password(db, password):
    from .common import current_login
    me = db.one("SELECT * FROM users WHERE login_id=?", (current_login(),))
    if not me or not verify_password(password or "", me["pass_hash"]):
        raise BusinessError("Your (owner) password is incorrect")
