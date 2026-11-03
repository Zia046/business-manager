"""Backup and restore.

A backup is one .bmbak file (a zip) holding the ENCRYPTED database, its key salt, the company
branding file and the logo. Nothing inside is readable without the password.
Restore replaces the current files, after first saving a safety backup of the current data.
"""
import json
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from ..db.connection import DB_FILE, KEYS_FILE, SALT_FILE
from .auth import BRANDING_FILE
from .common import BusinessError

EXT = ".bmbak"
SETTINGS_FILE = "settings.json"
KEEP_AUTO_BACKUPS = 30
_REQUIRED = (DB_FILE, SALT_FILE)


# ---------- settings (stored outside the encrypted DB so they are readable at exit) ----------
def get_settings(data_dir) -> dict:
    defaults = {"auto_backup": True, "extra_folder": "",
                "thermal_printer": "", "a4_printer": "",       # "" = open the PDF viewer, "__default__" = Windows default
                "thermal_width": 80, "default_bill": "thermal"}
    try:
        defaults.update(json.loads((Path(data_dir) / SETTINGS_FILE).read_text(encoding="utf-8")))
    except Exception:
        pass
    return defaults


def save_settings(data_dir, **changes):
    s = get_settings(data_dir)
    s.update(changes)
    (Path(data_dir) / SETTINGS_FILE).write_text(json.dumps(s), encoding="utf-8")
    return s


def backups_dir(data_dir) -> Path:
    d = Path(data_dir) / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------- create ----------
def create_backup(db, dest_dir=None, prefix="backup") -> Path:
    """Write a timestamped backup. `db` is the open Database (its latest state is flushed first)."""
    data_dir = Path(db.data_dir)
    dest = Path(dest_dir) if dest_dir else backups_dir(data_dir)
    dest.mkdir(parents=True, exist_ok=True)
    db._persist()  # make sure the file on disk holds every committed change
    out = dest / f"{prefix}_{datetime.now():%Y%m%d_%H%M%S}{EXT}"
    n = 1
    while out.exists():  # two backups within the same second
        out = dest / f"{prefix}_{datetime.now():%Y%m%d_%H%M%S}_{n}{EXT}"
        n += 1
    tmp = out.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for name in (DB_FILE, SALT_FILE, KEYS_FILE, BRANDING_FILE):
            f = data_dir / name
            if f.exists():
                z.write(f, name)
        logo = data_dir / "logo"
        if logo.exists():
            for f in logo.iterdir():
                if f.is_file():
                    z.write(f, f"logo/{f.name}")
    tmp.replace(out)
    return out


def _auto_backup(db):
    s = get_settings(db.data_dir)
    out = create_backup(db, prefix="auto")
    autos = sorted(backups_dir(db.data_dir).glob(f"auto_*{EXT}"))
    for old in autos[:-KEEP_AUTO_BACKUPS]:
        old.unlink(missing_ok=True)
    if s["extra_folder"] and Path(s["extra_folder"]).exists():       # USB / second folder
        shutil.copyfile(out, Path(s["extra_folder"]) / out.name)
    return out


def auto_backup_on_exit(db):
    """Called when the program closes. Never raises: a failed backup must not block closing."""
    try:
        if not get_settings(db.data_dir)["auto_backup"]:
            return None
        return _auto_backup(db)
    except Exception:
        return None


def periodic_backup(db, every_minutes=120, now_ts=None):
    """Called from a timer while the program is open: makes an automatic backup when the last one is older
    than `every_minutes` AND something changed since. Never raises. Returns the new file or None."""
    import time
    try:
        if not get_settings(db.data_dir)["auto_backup"]:
            return None
        last = last_backup_info(db.data_dir)
        now_ts = now_ts or time.time()
        if last["time"] and (now_ts - last["time"].timestamp()) < every_minutes * 60:
            return None
        db_file = Path(db.data_dir) / DB_FILE
        if last["time"] and db_file.exists() and db_file.stat().st_mtime <= last["time"].timestamp():
            return None                                                  # nothing changed since that backup
        return _auto_backup(db)
    except Exception:
        return None


def last_backup_info(data_dir) -> dict:
    """{'time': datetime or None, 'age_hours': float or None, 'name': str}"""
    files = sorted(backups_dir(data_dir).glob(f"*{EXT}"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return {"time": None, "age_hours": None, "name": ""}
    t = datetime.fromtimestamp(files[0].stat().st_mtime)
    return {"time": t, "age_hours": (datetime.now() - t).total_seconds() / 3600, "name": files[0].name}


def verify_backup(path) -> str:
    """Checks that a backup file is complete and not damaged. Returns a short report; raises BusinessError."""
    validate_backup(path)
    with zipfile.ZipFile(path) as z:
        sizes = {i.filename: i.file_size for i in z.infolist()}
    if sizes.get(DB_FILE, 0) < 100:
        raise BusinessError("The database inside this backup is empty.")
    return f"OK - {Path(path).name} is complete ({sum(sizes.values()) // 1024} KB of data)."


def verify_latest(data_dir) -> str:
    info = last_backup_info(data_dir)
    if not info["name"]:
        raise BusinessError("There is no backup yet. Press Backup Now first.")
    return verify_backup(backups_dir(data_dir) / info["name"])


def removable_drives() -> list[str]:
    """USB / removable drive letters on Windows (empty list elsewhere)."""
    import os
    if os.name != "nt":
        return []
    try:
        import ctypes
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        out = []
        for i in range(26):
            if mask & (1 << i):
                root = f"{chr(65 + i)}:\\"
                if ctypes.windll.kernel32.GetDriveTypeW(root) == 2:      # DRIVE_REMOVABLE
                    out.append(root)
        return out
    except Exception:
        return []


def list_backups(data_dir):
    files = sorted(backups_dir(data_dir).glob(f"*{EXT}"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"path": f, "name": f.name, "size_kb": max(f.stat().st_size // 1024, 1),
             "time": datetime.fromtimestamp(f.stat().st_mtime).strftime("%d-%m-%Y %H:%M")} for f in files]


# ---------- restore ----------
def validate_backup(path) -> None:
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            bad = z.testzip()
    except (zipfile.BadZipFile, OSError):
        raise BusinessError("This file is not a valid backup.")
    if bad or not all(n in names for n in _REQUIRED):
        raise BusinessError("This backup file is damaged or incomplete.")


def restore_backup(db, backup_path) -> Path:
    """Replace the current data with a backup. Closes `db`; the program must be restarted afterwards.
    Returns the safety backup that was made of the data being replaced."""
    backup_path = Path(backup_path)
    validate_backup(backup_path)
    data_dir = Path(db.data_dir)
    safety = create_backup(db, prefix="before_restore")       # 1. keep what we are about to replace
    db.close()
    with tempfile.TemporaryDirectory(dir=data_dir) as tmp:     # 2. extract aside, then swap
        with zipfile.ZipFile(backup_path) as z:
            z.extractall(tmp)
        tmp = Path(tmp)
        if not (tmp / KEYS_FILE).exists():       # backup from before key slots: drop the slots of the new data
            (data_dir / KEYS_FILE).unlink(missing_ok=True)
        for name in (DB_FILE, SALT_FILE, KEYS_FILE, BRANDING_FILE):
            src = tmp / name
            if src.exists():
                shutil.copyfile(src, data_dir / name)
        if (tmp / "logo").exists():
            (data_dir / "logo").mkdir(exist_ok=True)
            for f in (tmp / "logo").iterdir():
                shutil.copyfile(f, data_dir / "logo" / f.name)
    (data_dir / "lock.json").unlink(missing_ok=True)
    return safety
