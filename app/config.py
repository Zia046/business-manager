"""Application-wide constants and data-folder handling."""
import os
from pathlib import Path

APP_NAME = "Business Manager"
APP_VERSION = "0.3.0"
DATA_FOLDER_NAME = "BusinessManagerData"
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SECONDS = 300

# Fixed developer / sales contact (shown on the home page and on every printout; not editable in the program)
DEVELOPER_NAME = "Burhan Nexus"
DEVELOPER_PHONE = "03475093446"
DEVELOPER_EMAIL = "ziaullah.046@gmail.com"
SOFTWARE_CONTACT_LINE = f"To buy this software, contact: {DEVELOPER_PHONE}"


def resolve_data_dir(override: str | None = None) -> tuple[Path, bool]:
    """Return (data_dir, used_fallback).

    Prefers D:\\BusinessManagerData; falls back to C:\\ when D: does not exist.
    `override` is used by tests and for non-Windows development.
    """
    if override:
        base, fallback = Path(override), False
    elif os.name == "nt" and Path("D:\\").exists():
        base, fallback = Path("D:\\") / DATA_FOLDER_NAME, False
    elif os.name == "nt":
        base, fallback = Path("C:\\") / DATA_FOLDER_NAME, True
    else:  # dev machines (Linux/Mac)
        base, fallback = Path.home() / DATA_FOLDER_NAME, True
    for sub in ("", "backups", "invoices", "logo"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    return base, fallback
