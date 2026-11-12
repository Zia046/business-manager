"""Offline licence: a 7-day free trial on every new computer, then an Activation Key issued by the owner.

Free trial
  * Starts by itself on the first launch on a computer and gives full use for TRIAL_DAYS days.
  * The start date is kept in several places on the computer (signed, and tied to that computer), so
    re-installing the program or deleting the data folder does not start a new trial, and moving the
    Windows date back does not give extra days.

Activation key
  * Every computer has a Machine Code (derived from the Windows MachineGuid). It is shown on the
    activation screen.
  * The owner (Burhan Nexus) turns that Machine Code into an Activation Key with his private key
    (tools/keygen_gui.py). The private key is NEVER part of the program or the repository.
  * The program only holds the matching PUBLIC key, so it can check a key but cannot create one.
  * A key is bound to one Machine Code and may have an expiry date (or be for life).
"""
import base64
import hashlib
import hmac
import os
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
TRIAL_DAYS = 7
TRIAL_FILE = "trial.dat"


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


# ---------------- 7-day free trial ----------------
class FileStore:
    """One place where the trial record is kept: a small file."""

    def __init__(self, path):
        self.path = Path(path)

    def read(self):
        try:
            return self.path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            return ""

    def write(self, text):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(text, encoding="utf-8")
        except OSError:
            pass


class RegistryStore:
    """Another place: the Windows registry of this user (survives un-install and a deleted data folder)."""
    KEY, NAME = r"Software\BNSys\Shell", "State"

    def read(self):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.KEY, 0, winreg.KEY_READ) as k:
                return str(winreg.QueryValueEx(k, self.NAME)[0]).strip()
        except (ImportError, OSError):
            return ""

    def write(self, text):
        try:
            import winreg
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.KEY) as k:
                winreg.SetValueEx(k, self.NAME, 0, winreg.REG_SZ, text)
        except (ImportError, OSError):
            pass


def default_trial_stores(data_dir):
    stores = [FileStore(Path(data_dir) / TRIAL_FILE)]
    if sys.platform.startswith("win"):
        stores.append(RegistryStore())
        for env, name in (("PROGRAMDATA", "sys.dat"), ("LOCALAPPDATA", "cache.dat")):
            if os.environ.get(env):
                stores.append(FileStore(Path(os.environ[env]) / "BNSys" / name))
    else:
        stores.append(FileStore(Path.home() / ".config" / "bnsys" / "state"))
    return stores


def _trial_mac(machine_raw, body: str) -> str:
    key = hashlib.sha256(b"BN-trial-v1|" + (machine_raw or _raw_machine_id()).encode("utf-8")
                         + bytes.fromhex(PUBLIC_KEY_HEX)).digest()
    return hmac.new(key, body.encode("utf-8"), hashlib.sha256).hexdigest()[:40]


def _trial_pack(machine_raw, start: date, last: date) -> str:
    body = f"1|{_clean(machine_code(machine_raw))}|{start.isoformat()}|{last.isoformat()}"
    return f"{body}|{_trial_mac(machine_raw, body)}"


def _trial_parse(machine_raw, text):
    """-> ("ok", start, last) | ("none",) for empty or another computer's record | ("bad",) if changed by hand."""
    if not text:
        return ("none",)
    parts = text.split("|")
    if len(parts) != 5 or parts[0] != "1":
        return ("bad",)
    if parts[1] != _clean(machine_code(machine_raw)):
        return ("none",)                        # data folder copied from another computer: not ours
    if not hmac.compare_digest(parts[4], _trial_mac(machine_raw, "|".join(parts[:4]))):
        return ("bad",)
    try:
        return ("ok", date.fromisoformat(parts[2]), date.fromisoformat(parts[3]))
    except ValueError:
        return ("bad",)


def trial_status(data_dir, today: date | None = None, machine_raw: str | None = None, stores=None):
    """Starts the trial on the very first call on this computer. Returns dict(active, days_left, start, reason)."""
    today = today or date.today()
    stores = default_trial_stores(data_dir) if stores is None else stores
    raw = [s.read() for s in stores]
    found = [_trial_parse(machine_raw, t) for t in raw]
    good = [f for f in found if f[0] == "ok"]
    if any(f[0] == "bad" for f in found):
        if good:                                # keep the honest copies; the changed one is repaired below
            pass
        else:
            return {"active": False, "days_left": 0, "start": None,
                    "reason": "The free-trial record on this computer was changed. Please activate the software."}
    if not good:
        start = last = today                    # first launch on this computer: the trial begins now
    else:
        start = min(f[1] for f in good)
        last = max(f[2] for f in good)
        if today < last - timedelta(days=1):
            return {"active": False, "days_left": 0, "start": start,
                    "reason": "The computer date was moved back. Set the correct date and open the software again."}
        last = max(last, today)
    record = _trial_pack(machine_raw, start, last)
    for s, old in zip(stores, raw):
        if old != record:
            s.write(record)                     # also puts back a copy that was deleted
    left = TRIAL_DAYS - (last - start).days
    if left <= 0:
        return {"active": False, "days_left": 0, "start": start,
                "reason": f"Your {TRIAL_DAYS}-day free trial has ended. Enter a License Key to keep using the "
                          "software. All your data is safe."}
    return {"active": True, "days_left": left, "start": start, "reason": ""}


def overall(data_dir, today: date | None = None, machine_raw: str | None = None, public_hex: str | None = None,
            stores=None):
    """What the program should do now. state: licensed | trial | expired; can_run; label (shown in Settings)."""
    lic = status(data_dir, today, machine_raw, public_hex)
    if lic["valid"]:
        label = "Lifetime Activated" if lic["expiry"] is None else f"Activated (valid until {lic['expiry']:%d-%m-%Y})"
        return {"state": "licensed", "can_run": True, "label": label, "reason": "", "days_left": lic["days_left"]}
    trial = trial_status(data_dir, today, machine_raw, stores)
    if trial["active"]:
        return {"state": "trial", "can_run": True, "reason": "", "days_left": trial["days_left"],
                "label": f"Free Trial - Active ({trial['days_left']} day(s) left)"}
    return {"state": "expired", "can_run": False, "label": "Trial Expired", "days_left": 0,
            "reason": lic["reason"] or trial["reason"]}
