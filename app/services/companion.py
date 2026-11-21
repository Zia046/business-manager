"""What the Android Companion app may ask the Windows program, and how the two trust each other.

Nothing here opens a network port (see companion_server.py) and nothing here is a second database:
every answer is read from the shop's own records at the moment of the request.

Trust
  * The owner presses "Pair a new phone" on the PC and gets a 6-digit code (valid 5 minutes, 5 tries).
  * Phone and PC make a shared secret with an elliptic-curve key exchange (P-256); the code is mixed
    into the key, so a device that does not know the code ends up with a useless key.
  * From then on every request and every answer is encrypted with AES-256-GCM using that phone's key.
    An unknown phone, or a phone the owner removed, gets nothing but "not paired".
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import date, datetime, timedelta

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from . import loans, settings_store, sms_template
from .common import BusinessError, now, r2

API_VERSION = 1
HTTP_PORT, DISCOVERY_PORT = 47820, 47821
DISCOVER_ASK, APP_TAG = b"BNBC_DISCOVER_1", "BNBC"
KEY_STATE, KEY_ENABLED = "companion", "companion_enabled"
CODE_SECONDS, CODE_TRIES = 300, 5
OVERDUE_DAYS = 30               # no payment for this many days = overdue (a late qist is overdue at once)
LEDGER_ROWS = 300               # newest ledger lines sent per customer
_LABELS = {"invoice": "Sale", "receipt": "Cash received", "sale_return": "Sale return",
           "customer_payment": "Cash paid to customer", "opening": "Opening balance",
           "loan": "Loan given", "repayment": "Repayment", "adjustment": "Adjustment"}


class ApiError(Exception):
    def __init__(self, status, code, message=""):
        super().__init__(message or code)
        self.status, self.code, self.message = status, code, message or code


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def _unb64(s) -> bytes:
    try:
        return base64.b64decode(s or "", validate=True)
    except Exception:
        raise ApiError(400, "bad_request", "Badly formed data")


# ---------------- stored state: this PC's identity and the paired phones ----------------
def state(db) -> dict:
    st = settings_store.get(db, KEY_STATE)
    if st and st.get("priv"):
        return st
    priv = ec.generate_private_key(ec.SECP256R1())
    st = {"server_id": secrets.token_hex(8), "devices": {},
          "priv": priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                     serialization.NoEncryption()).decode()}
    settings_store.save(db, KEY_STATE, st)
    return st


def is_enabled(db) -> bool:
    return bool(settings_store.get(db, KEY_ENABLED, False))


def set_enabled(db, on: bool):
    settings_store.save(db, KEY_ENABLED, bool(on))


def devices(db) -> list:
    return [{"id": k, "name": v.get("name") or "Phone", "paired_at": v.get("paired_at", "")}
            for k, v in sorted(state(db)["devices"].items(), key=lambda kv: kv[1].get("paired_at", ""))]


def remove_device(db, device_id):
    st = state(db)
    if st["devices"].pop(device_id, None) is not None:
        settings_store.save(db, KEY_STATE, st)


def _public_b64(st) -> str:
    priv = serialization.load_pem_private_key(st["priv"].encode(), None)
    return _b64(priv.public_key().public_bytes(serialization.Encoding.DER,
                                               serialization.PublicFormat.SubjectPublicKeyInfo))


def hello(db) -> dict:
    """The only thing an unpaired device can read: that this is a Business Manager, and its public key."""
    st = state(db)
    co = db.one("SELECT name FROM company WHERE id=1") or {"name": ""}
    return {"app": APP_TAG, "api": API_VERSION, "server_id": st["server_id"], "shop": co["name"],
            "pub": _public_b64(st), "port": HTTP_PORT}


# ---------------- pairing ----------------
class Pairing:
    """The 6-digit code shown on the PC. Lives in memory only."""

    def __init__(self):
        self.code, self.until, self.tries = None, 0.0, 0

    def start(self) -> str:
        self.code = f"{secrets.randbelow(1_000_000):06d}"
        self.until, self.tries = time.time() + CODE_SECONDS, 0
        return self.code

    def stop(self):
        self.code = None

    def active(self) -> bool:
        return bool(self.code) and time.time() < self.until and self.tries < CODE_TRIES

    def seconds_left(self) -> int:
        return max(0, int(self.until - time.time())) if self.active() else 0


def session_key(shared: bytes, code: str, device_id: str) -> bytes:
    salt = hashlib.sha256(f"BNBC1|{code}|{device_id}".encode()).digest()
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=b"bnbc-session").derive(shared)


def proof(key: bytes, text: str) -> str:
    return hmac.new(key, text.encode(), hashlib.sha256).hexdigest()


def pair(db, pairing: Pairing, body: dict) -> dict:
    device_id = str(body.get("device_id") or "")[:64]
    name = str(body.get("name") or "Phone")[:60]
    if len(device_id) < 8:
        raise ApiError(400, "bad_request", "Badly formed data")
    if not pairing.active():
        raise ApiError(403, "no_code", "Pairing is not open. On the PC press 'Pair a new phone' and use the new code.")
    st = state(db)
    try:
        theirs = serialization.load_der_public_key(_unb64(body.get("pub")))
        priv = serialization.load_pem_private_key(st["priv"].encode(), None)
        shared = priv.exchange(ec.ECDH(), theirs)
    except ApiError:
        raise
    except Exception:
        raise ApiError(400, "bad_request", "Badly formed data")
    key = session_key(shared, pairing.code, device_id)
    if not hmac.compare_digest(proof(key, "pair|" + device_id), str(body.get("proof") or "")):
        pairing.tries += 1
        if pairing.tries >= CODE_TRIES:
            pairing.stop()
        raise ApiError(403, "wrong_code", "The code is not correct.")
    pairing.stop()                                          # one phone per code
    st["devices"][device_id] = {"name": name, "key": _b64(key), "paired_at": now()}
    settings_store.save(db, KEY_STATE, st)
    return {"ok": True, "server_id": st["server_id"], "proof": proof(key, "ok|" + st["server_id"]),
            "shop": hello(db)["shop"]}


# ---------------- encrypted envelope ----------------
def seal(key: bytes, device_id: str, obj) -> dict:
    nonce = os.urandom(12)
    data = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return {"d": device_id, "n": _b64(nonce), "c": _b64(AESGCM(key).encrypt(nonce, data, device_id.encode()))}


def unseal(key: bytes, env: dict):
    try:
        raw = AESGCM(key).decrypt(_unb64(env.get("n")), _unb64(env.get("c")), str(env.get("d") or "").encode())
        return json.loads(raw.decode("utf-8"))
    except (InvalidTag, ValueError):
        raise ApiError(401, "not_paired", "This phone is not paired with this computer (or was removed). Pair again.")


def api(db, env: dict) -> dict:
    """One encrypted request -> one encrypted answer."""
    device_id = str(env.get("d") or "")
    dev = state(db)["devices"].get(device_id)
    if not dev:
        raise ApiError(401, "not_paired", "This phone is not paired with this computer (or was removed). Pair again.")
    key = _unb64(dev["key"])
    req = unseal(key, env)
    op = OPS.get(str(req.get("op") or ""))
    if op is None:
        return seal(key, device_id, {"ok": False, "error": "unknown_op", "message": "Update the app"})
    try:
        out = {"ok": True, "data": op(db, req.get("args") or {}, dev)}
    except sms_template.TemplateConflict as exc:
        out = {"ok": False, "error": "conflict", "message": str(exc), "data": exc.current}
    except BusinessError as exc:
        out = {"ok": False, "error": "invalid", "message": str(exc)}
    return seal(key, device_id, out)


# ---------------- the data ----------------
def _today(args=None):
    return date.today()


def _days_since(stamp, today) -> int:
    try:
        return (today - date.fromisoformat((stamp or "")[:10])).days
    except ValueError:
        return 0


def _customer(db, row, late, today, with_ledger):
    led = db.query("SELECT * FROM ledger WHERE party_id=? ORDER BY date, id", (row["id"],))
    party = db.one("SELECT opening_balance FROM parties WHERE id=?", (row["id"],))
    opening = r2(party["opening_balance"] or 0)
    bought = r2(max(opening, 0) + sum(l["debit"] for l in led))
    paid = r2(max(-opening, 0) + sum(l["credit"] for l in led))
    pays = [l["date"] for l in led if l["credit"] > 0 and l["ref_type"] in ("receipt", "invoice")]
    last_payment = max(pays) if pays else ""
    first_debt = min((l["date"] for l in led if l["debit"] > 0), default="")
    late_n, late_amount = late.get(row["id"], (0, 0.0))
    quiet = _days_since(last_payment or first_debt, today) if (last_payment or first_debt) else 0
    overdue = late_n > 0 or quiet > OVERDUE_DAYS
    reason = (f"{late_n} qist late ({late_amount:,.0f})" if late_n else
              f"No payment for {quiet} days" if overdue else "")
    out = {"id": f"C-{row['id']}", "type": "customer", "name": row["name"], "phone": row["phone"] or "",
           "total_purchase": bought, "total_paid": paid, "balance": r2(row["balance"]),
           "last_payment": last_payment[:10], "overdue": overdue, "overdue_reason": reason}
    if with_ledger:
        bal, lines = opening, []
        if opening:
            lines.append({"id": f"C-{row['id']}-open", "date": "", "desc": "Opening balance",
                          "debit": max(opening, 0), "credit": max(-opening, 0), "balance": opening})
        for l in led:
            bal = r2(bal + l["debit"] - l["credit"])
            desc = _LABELS.get(l["ref_type"], l["ref_type"].replace("_", " ").title())
            if l.get("note"):
                desc += f" - {l['note']}"
            lines.append({"id": f"C-{l['id']}", "date": l["date"][:16], "desc": desc[:120], "debit": r2(l["debit"]),
                          "credit": r2(l["credit"]), "balance": bal})
        out["ledger"] = lines[-LEDGER_ROWS:]
    return out


def _loan_person(db, p, today, with_ledger):
    hist = loans.history(db, p["id"])
    pays = [h["date"] for h in hist if h["kind"] == "repayment"]
    last_payment = max(pays) if pays else ""
    first = hist[0]["date"] if hist else ""
    quiet = _days_since(last_payment or first, today) if hist else 0
    overdue = quiet > OVERDUE_DAYS
    out = {"id": f"L-{p['id']}", "type": "loan", "name": p["name"], "phone": p["phone"] or "",
           "total_purchase": p["given"], "total_paid": p["returned"], "balance": p["balance"],
           "last_payment": last_payment[:10], "overdue": overdue,
           "overdue_reason": f"No payment for {quiet} days" if overdue else ""}
    if with_ledger:
        out["ledger"] = [{"id": f"L-{h['id']}", "date": h["date"][:16],
                          "desc": (_LABELS[h["kind"]] + (f" - {h['note']}" if h.get("note") else ""))[:120],
                          "debit": h["amount"] if h["kind"] == "loan" else 0,
                          "credit": h["amount"] if h["kind"] != "loan" else 0, "balance": h["balance"]}
                         for h in hist][-LEDGER_ROWS:]
    return out


def outstanding_list(db, with_ledger=True, today=None) -> list:
    """Everyone with a balance above zero: customers (credit sales) and persons with a cash loan.
    IDs are 'C-<customer id>' and 'L-<loan person id>', so the phone never matches people by name."""
    from .installments import due_list
    from .reports import outstanding
    today = today or _today()
    late = {}
    for q in due_list(db, today.isoformat()):
        if q["days_late"] > 0:
            n, amount = late.get(q["party_id"], (0, 0.0))
            late[q["party_id"]] = (n + 1, r2(amount + q["remaining"]))
    o = outstanding(db)
    rows = [_customer(db, r, late, today, with_ledger) for r in o["customers"] if r["balance"] > 0.004]
    rows += [_loan_person(db, p, today, with_ledger) for p in o["loans"]]
    rows.sort(key=lambda r: -r["balance"])
    return rows


def summary(db, rows=None, today=None) -> dict:
    today = today or _today()
    rows = outstanding_list(db, False, today) if rows is None else rows
    day = today.isoformat()
    recovered = db.scalar("SELECT COALESCE(SUM(amount),0) FROM cash_book WHERE direction='in' AND "
                          "ref_type IN ('receipt','loan_repayment') AND date BETWEEN ? AND ?",
                          (day + " 00:00:00", day + " 23:59:59"))
    over = [r for r in rows if r["overdue"]]
    return {"total_outstanding": r2(sum(r["balance"] for r in rows)), "customers": len(rows),
            "today_recoveries": r2(recovered), "overdue_count": len(over),
            "overdue_amount": r2(sum(r["balance"] for r in over)), "currency": "PKR"}


def transactions(db, limit=40) -> list:
    """The newest money movements of customers and loan persons (what the phone shows as recent activity)."""
    rows = db.query(
        "SELECT cb.id, cb.date, cb.direction, cb.amount, cb.ref_type, cb.note, pa.name FROM cash_book cb "
        "LEFT JOIN parties pa ON pa.id=cb.party_id WHERE cb.ref_type IN "
        "('receipt','loan_repayment','cash_loan','invoice','customer_payment') ORDER BY cb.date DESC, cb.id DESC "
        "LIMIT ?", (int(limit),))
    names = {"receipt": "Cash received", "loan_repayment": "Loan repaid", "cash_loan": "Loan given",
             "invoice": "Cash sale", "customer_payment": "Paid to customer"}
    return [{"id": f"T-{r['id']}", "date": r["date"][:16], "kind": names[r["ref_type"]],
             "name": r["name"] or (r["note"] or "").split(" - ")[0], "amount": r2(r["amount"]),
             "direction": r["direction"]} for r in rows]


def _find(db, args, with_ledger=True):
    wanted = str(args.get("id") or "")
    for r in outstanding_list(db, with_ledger):
        if r["id"] == wanted:
            return r
    raise BusinessError("This customer has no outstanding balance any more")


def _overview(db):
    from .business_overview import overview
    return overview(db)


def _op_sync(db, args, dev):
    rows = outstanding_list(db, True)
    from .business_overview import overview
    return {"summary": summary(db, rows), "customers": rows, "transactions": transactions(db),
            "overview": overview(db),            # stock, mobiles, sales, purchases, money, activity
            "template": sms_template.current(db), "business": sms_template.business(db),
            "instructions": sms_template.INSTRUCTIONS_UR, "default_template": sms_template.default_text(db),
            "shop": hello(db)["shop"], "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


def _op_template_save(db, args, dev):
    by = f"Android ({dev.get('name') or 'phone'})"
    if args.get("restore_default"):
        return sms_template.restore_default(db, args.get("base_version"), by)
    return sms_template.save(db, args.get("text"), args.get("base_version"), by)


def _op_business_save(db, args, dev):
    return sms_template.save_business(db, **{k: args[k] for k in sms_template.BUSINESS_FIELDS if k in args})


OPS = {
    "status": lambda db, a, d: {"shop": hello(db)["shop"], "api": API_VERSION,
                                "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
    "sync": _op_sync,
    "summary": lambda db, a, d: summary(db),
    "overview": lambda db, a, d: _overview(db),
    "customers": lambda db, a, d: outstanding_list(db, False),
    "ledger": lambda db, a, d: _find(db, a)["ledger"],
    "payments": lambda db, a, d: [l for l in _find(db, a)["ledger"] if l["credit"] > 0],
    "transactions": lambda db, a, d: transactions(db, min(int(a.get("limit") or 40), 200)),
    "template_get": lambda db, a, d: sms_template.current(db),
    "template_save": _op_template_save,
    "business_get": lambda db, a, d: sms_template.business(db),
    "business_save": _op_business_save,
}
