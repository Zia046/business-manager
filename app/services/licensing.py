"""Offline licence: the program works only on a computer for which the owner issued an Activation Key.

How it works
  * Every computer has a Machine Code (derived from the Windows MachineGuid). It is shown on the
    activation screen.
  * The owner (Burhan Nexus) turns that Machine Code into an Activation Key with his private key
    (tools/keygen_gui.py). The private key is NEVER part of the program or the repository.
  * The program only holds the matching PUBLIC key, so it can check a key but cannot create one.
  * A key is bound to one Machine Code and may have an expiry date (or be for life).
"""
import base64
import hashlib
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

LICENSE_FILE = "license.key"
STATE_FILE = "license.state"

# PUBLIC key (hex). Replace together with the private key if the owner ever changes it.
PUBLIC_KEY_HEX = "434536811a15aa4a623b96945aee7138850c30b12b2c47a3f38c27f3b22f013a"

_EPOCH = date(2024, 1, 1)
_LIFETIME = 0xFFFF
_VERSION = 1
WARN_DAYS = 7


# ---------------- machine code ----------------
def _raw_machine_id() -> str:
    if sys.platform.startswith("win"):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography",
                                0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
                return str(winreg.QueryValueEx(k, "MachineGuid")[0])
        except OSError:
            pass
    for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            return Path(p).read_text().strip()
        except OSError:
            continue
    return f"mac-{uuid.getnode():012x}"


def _machine_bytes(raw: str) -> bytes:
    return hashlib.sha256(b"BN-machine|" + raw.encode("utf-8")).digest()[:10]


def _group(text: str, n: int) -> str:
    return "-".join(text[i:i + n] for i in range(0, len(text), n))


def machine_code(raw: str | None = None) -> str:
    """e.g. 'K3F7-Q2XA-9PLM-4TRB' (16 characters)."""
    code = base64.b32encode(_machine_bytes(raw or _raw_machine_id())).decode().rstrip("=")
    return _group(code, 4)


def _clean(text: str) -> str:
    return "".join(ch for ch in (text or "").upper() if ch.isalnum())


# ---------------- keys ----------------
def encode_key(machine: str, expiry: date | None, sign) -> str:
    """Used by the key generator. `sign(payload) -> 64 byte signature`."""
    mb = base64.b32decode(_clean(machine) + "=" * (-len(_clean(machine)) % 8))
    if len(mb) != 10:
        raise ValueError("Machine code is not valid")
    days = _LIFETIME if expiry is None else (expiry - _EPOCH).days
    if expiry is not None and not 0 <= days < _LIFETIME:
        raise ValueError("Expiry date is out of range")
    payload = bytes([_VERSION]) + mb + days.to_bytes(2, "big")
    raw = payload + sign(payload)
    return _group(base64.b32encode(raw).decode().rstrip("="), 8)


def read_key(key_text: str, machine_raw: str | None = None, public_hex: str | None = None):
    """Returns (ok, expiry_or_None, message). Does not look at today's date."""
    try:
        txt = _clean(key_text)
        raw = base64.b32decode(txt + "=" * (-len(txt) % 8))
        payload, sig = raw[:13], raw[13:]
        if len(raw) != 77 or payload[0] != _VERSION:
            return False, None, "This is not a valid activation key."
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_hex or PUBLIC_KEY_HEX)).verify(sig, payload)
    except (ValueError, InvalidSignature):
        return False, None, "This is not a valid activation key."
    if payload[1:11] != _machine_bytes(machine_raw or _raw_machine_id()):
        return False, None, "This key was issued for a different computer."
    days = int.from_bytes(payload[11:13], "big")
    return True, (None if days == _LIFETIME else _EPOCH + timedelta(days=days)), "ok"


# ---------------- status on this computer ----------------
def status(data_dir, today: date | None = None, machine_raw: str | None = None, public_hex: str | None = None):
    """Returns dict(valid, reason, expiry, days_left)."""
    today = today or date.today()
    p = Path(data_dir) / LICENSE_FILE
    if not p.exists():
        return {"valid": False, "reason": "", "expiry": None, "days_left": None}
    ok, expiry, msg = read_key(p.read_text(encoding="utf-8", errors="ignore"), machine_raw, public_hex)
    if not ok:
        return {"valid": False, "reason": msg, "expiry": None, "days_left": None}
    if expiry is not None:
        seen = _last_seen(data_dir)
        if seen and today < seen - timedelta(days=1):
            return {"valid": False, "reason": "The computer date was moved back. Set the correct date.",
                    "expiry": expiry, "days_left": None}
        if today > expiry:
            return {"valid": False, "reason": f"Your licence expired on {expiry:%d-%m-%Y}. "
                                               "Contact Burhan Nexus for a new activation key.",
                    "expiry": expiry, "days_left": 0}
        _save_seen(data_dir, today)
    return {"valid": True, "reason": "", "expiry": expiry,
            "days_left": None if expiry is None else (expiry - today).days}


def activate(data_dir, key_text, machine_raw=None, public_hex=None, today=None):
    ok, expiry, msg = read_key(key_text, machine_raw, public_hex)
    if not ok:
        return False, msg
    if expiry is not None and (today or date.today()) > expiry:
        return False, f"This key expired on {expiry:%d-%m-%Y}."
    (Path(data_dir) / LICENSE_FILE).write_text(key_text.strip(), encoding="utf-8")
    return True, "Activated"


def _last_seen(data_dir):
    try:
        return datetime.strptime((Path(data_dir) / STATE_FILE).read_text().strip(), "%Y-%m-%d").date()
    except (OSError, ValueError):
        return None


def _save_seen(data_dir, today):
    seen = _last_seen(data_dir)
    if seen is None or today > seen:
        try:
            (Path(data_dir) / STATE_FILE).write_text(today.isoformat())
        except OSError:
            pass
