"""Two-way sync with the Android app: the computer's side.

Phone -> computer ("push")
    The phone sends the transactions it made (sale, purchase, returns, payments, expense, new customer or
    supplier). Each one is applied with the SAME functions the Windows screens use (create_invoice,
    create_purchase, sale_return, ...), so stock, balances, cash and profit follow the normal rules.
    Every transaction has an id made on the phone; it is written to `sync_inbox` in the same database
    transaction, so a resend after a broken connection is answered from the inbox and never applied twice.
    A transaction the computer cannot apply (e.g. the same IMEI was already sold here) is kept in full in the
    inbox as a "conflict" for the owner; nothing is thrown away.

Computer -> phone ("pull")
    Incremental: the phone first gets a small list of [id, fingerprint] per kind of record, then asks only
    for the records that are new or changed, and drops the ones that are gone (e.g. a cancelled invoice).
    The phone therefore always gets the real documents and the real stock, never only a copied number.
"""
import hashlib
import json
from datetime import datetime

from . import masters, payments, trading
from .common import BusinessError, now, r2

KINDS = ("product", "serial", "party", "invoice", "purchase", "return", "voucher", "expense", "meta")
OP_KINDS = ("customer_add", "supplier_add", "sale", "sale_return", "purchase", "purchase_return",
            "receipt", "supplier_payment", "expense")
MAX_FETCH = 400                       # records per fetch call (the phone asks again for the rest)
MAX_PUSH = 100


# ---------------- device series ----------------
def device_series(st: dict, device_id: str) -> str:
    """Each paired phone numbers its own invoices: MB1-00001, MB2-00001 ... (never the computer's INV- series)."""
    dev = st["devices"].get(device_id) or {}
    if not dev.get("series"):
        used = {d.get("series") for d in st["devices"].values()}
        n = 1
        while f"MB{n}" in used:
            n += 1
        dev["series"] = f"MB{n}"
    return dev["series"]


# ---------------- push: phone -> computer ----------------
def _ref(c, value, what):
    """An id from the phone: a number (a record of this computer) or {"op": "<op id>"} for a record the phone
    created itself (a new customer, ...), which must have been applied before."""
    if isinstance(value, dict) and value.get("op"):
        row = c.execute("SELECT status, doc_id FROM sync_inbox WHERE op_id=?", (str(value["op"]),)).fetchone()
        if not row or row["status"] != "applied" or row["doc_id"] is None:
            raise BusinessError(f"The {what} made on the phone was not saved on the computer")
        return row["doc_id"]
    try:
        return int(value)
    except (TypeError, ValueError):
        raise BusinessError(f"Unknown {what}")


def _items(c, items, with_serials=False):
    out = []
    for it in items or []:
        row = {"product_id": _ref(c, it.get("product_id"), "product"), "qty": float(it.get("qty") or 0),
               "price": float(it.get("price") or 0)}
        if it.get("discount"):
            row["discount"] = float(it["discount"])
        for k in ("serial", "serial2"):
            if it.get(k):
                row[k] = str(it[k])
        if with_serials and it.get("serials"):
            row["serials"] = [tuple(s) if isinstance(s, (list, tuple)) else (s, None) for s in it["serials"]]
        out.append(row)
    return out


def _when(op):
    """The time the transaction was made on the phone (kept as the document's date)."""
    t = str(op.get("made_at") or "")[:19].replace("T", " ")
    try:
        datetime.strptime(t, "%Y-%m-%d %H:%M:%S")
        return t
    except ValueError:
        return now()


def _apply(db, op, series):
    """-> (doc_type, doc_id, doc_no, warning). Raises BusinessError when the computer cannot accept it."""
    k, d, date = op["kind"], op.get("data") or {}, _when(op)
    note = str(d.get("note") or "")[:300]
    if k in ("customer_add", "supplier_add"):
        pid = masters.add_party(db, "customer" if k == "customer_add" else "supplier", str(d.get("name") or ""),
                                phone=str(d.get("phone") or ""), address=str(d.get("address") or ""))
        return "party", pid, "", ""
    with db.transaction() as c:                 # (a read: ids from the phone -> ids here)
        party = _ref(c, d.get("party_id"), "customer/supplier") if k not in ("expense",) else None
        items = _items(c, d.get("items"), with_serials=(k == "purchase"))
    if k == "sale":
        no = str(d.get("no") or "")
        if not no.startswith(series + "-"):
            raise BusinessError("Invoice number is not in this phone's series")
        before = {it["product_id"]: _qty(db, it["product_id"]) for it in items}
        inv = trading.create_invoice(db, party, items, discount=float(d.get("discount") or 0),
                                     paid=float(d.get("paid") or 0), note=note, date=date,
                                     allow_negative_stock=True, no=no)
        short = [db.scalar("SELECT name FROM products WHERE id=?", (pid,)) for pid in before if _qty(db, pid) < 0]
        warn = ("Stock went below zero for: " + ", ".join(short)) if short else ""
        return "invoice", inv, no, warn
    if k == "sale_return":
        rid = trading.sale_return(db, party, items, refunded=float(d.get("refunded") or 0), note=note, date=date)
        return "return", rid, db.scalar("SELECT no FROM returns WHERE id=?", (rid,)), ""
    if k == "purchase":
        pid = trading.create_purchase(db, party, items, paid=float(d.get("paid") or 0), note=note, date=date)
        return "purchase", pid, db.scalar("SELECT no FROM purchases WHERE id=?", (pid,)), ""
    if k == "purchase_return":
        rid = trading.purchase_return(db, party, items, received=float(d.get("received") or 0), note=note, date=date)
        return "return", rid, db.scalar("SELECT no FROM returns WHERE id=?", (rid,)), ""
    if k == "receipt":
        no = payments.receive_from_customer(db, party, float(d.get("amount") or 0), note=note, date=date)
        return "voucher", db.scalar("SELECT id FROM vouchers WHERE no=?", (no,)), no, ""
    if k == "supplier_payment":
        no = payments.pay_supplier(db, party, float(d.get("amount") or 0), note=note, date=date)
        return "voucher", db.scalar("SELECT id FROM vouchers WHERE no=?", (no,)), no, ""
    if k == "expense":
        eid = payments.add_expense(db, str(d.get("category") or ""), float(d.get("amount") or 0), note=note, date=date)
        return "expense", eid, "", ""
    raise BusinessError("Unknown kind of transaction")


def _qty(db, product_id):
    from .common import stock_qty
    return stock_qty(db.conn, product_id)


def _answer(row):
    return {"op_id": row["op_id"], "status": row["status"], "doc_type": row["doc_type"], "doc_id": row["doc_id"],
            "doc_no": row["doc_no"] or "", "message": row["message"] or ""}


def push(db, device_id, series, ops) -> list:
    """Apply the phone's transactions in the order they were made. Returns one answer per transaction."""
    out = []
    for op in list(ops or [])[:MAX_PUSH]:
        op_id = str(op.get("op_id") or "")[:80]
        if len(op_id) < 8 or op.get("kind") not in OP_KINDS:
            out.append({"op_id": op_id, "status": "conflict", "message": "Badly formed transaction"})
            continue
        old = db.one("SELECT * FROM sync_inbox WHERE op_id=?", (op_id,))
        if old:                                         # sent again (connection broke before the answer)
            out.append(_answer(old))
            continue
        payload = json.dumps(op, ensure_ascii=False)[:200_000]
        try:
            doc_type, doc_id, doc_no, warn = _apply(db, op, series)
            status, message = "applied", warn
        except BusinessError as exc:
            doc_type = doc_id = doc_no = None
            status, message = "conflict", str(exc)
        with db.transaction() as c:
            c.execute("INSERT INTO sync_inbox(op_id,device_id,kind,made_at,received_at,status,doc_type,doc_id,"
                      "doc_no,message,payload) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (op_id, device_id, op["kind"], str(op.get("made_at") or "")[:19], now(), status, doc_type,
                       doc_id, doc_no, message, payload))
        out.append(_answer(db.one("SELECT * FROM sync_inbox WHERE op_id=?", (op_id,))))
    return out


def conflicts(db, include_dismissed=False):
    rows = db.query("SELECT * FROM sync_inbox WHERE status IN ('conflict'" + (",'dismissed'" if include_dismissed
                    else "") + ") ORDER BY received_at DESC")
    for r in rows:
        try:
            r["data"] = json.loads(r["payload"]).get("data") or {}
        except ValueError:
            r["data"] = {}
    return rows


def dismiss_conflict(db, op_id):
    """The owner has dealt with it (e.g. entered it by hand). The record itself stays in the inbox."""
    with db.transaction() as c:
        c.execute("UPDATE sync_inbox SET status='dismissed' WHERE op_id=? AND status='conflict'", (op_id,))


# ---------------- pull: computer -> phone ----------------
def _fp(obj) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]


def _lines(db, sql, key):
    out = {}
    for r in db.query(sql):
        out.setdefault(r.pop(key), []).append(r)
    return out


def records(db, kind, ids=None) -> dict:
    """{id: record} of one kind (all, or only `ids`). Owner-only figures are left out for staff phones later."""
    def where(col):
        if ids is None:
            return ""
        return f" WHERE {col} IN ({','.join(str(int(i)) for i in ids) or '0'})"

    if kind == "product":
        from .reports import stock_position
        qty = {r["id"]: r["qty"] for r in stock_position(db)["rows"]}
        rows = db.query("SELECT id, name, category, brand, barcode, unit, sale_price, avg_cost, low_stock_level, "
                        "track_serial, imei_mode, mobile_type, ram_gb, storage_gb, condition, active FROM products"
                        + where("id"))
        for r in rows:
            r["qty"] = r2(qty.get(r["id"], 0))
            r["avg_cost"] = r2(r["avg_cost"])
        return {r["id"]: r for r in rows}
    if kind == "serial":
        rows = db.query("SELECT id, product_id, serial, imei2, status, invoice_id FROM serials" + where("id"))
        return {r["id"]: r for r in rows}
    if kind == "party":
        from .reports import all_balances
        bal = {}
        for k in ("customer", "supplier"):
            for r in all_balances(db, k)["rows"]:
                bal[r["id"]] = r["balance"]
        rows = db.query("SELECT id, kind, name, phone, address, is_walkin, active FROM parties" + where("id"))
        for r in rows:
            r["balance"] = r2(bal.get(r["id"], 0))
        return {r["id"]: r for r in rows}
    if kind == "invoice":
        rows = db.query("SELECT i.id, i.no, i.date, i.party_id, p.name AS party, i.subtotal, i.discount, i.total, "
                        "i.paid, i.note, i.status FROM invoices i JOIN parties p ON p.id=i.party_id"
                        + where("i.id"))
        lines = _lines(db, "SELECT ii.invoice_id, ii.product_id, pr.name, ii.qty, ii.price, ii.discount, ii.serial, "
                           "ii.serial2 FROM invoice_items ii JOIN products pr ON pr.id=ii.product_id"
                           + where("ii.invoice_id") + " ORDER BY ii.id", "invoice_id")
        for r in rows:
            r["lines"] = lines.get(r["id"], [])
            r["origin"] = "mobile" if not r["no"].startswith("INV-") else "computer"
        return {r["id"]: r for r in rows}
    if kind == "purchase":
        rows = db.query("SELECT u.id, u.no, u.date, u.party_id, p.name AS party, u.total, u.paid, u.note, u.status "
                        "FROM purchases u JOIN parties p ON p.id=u.party_id" + where("u.id"))
        lines = _lines(db, "SELECT pi.purchase_id, pi.product_id, pr.name, pi.qty, pi.price FROM purchase_items pi "
                           "JOIN products pr ON pr.id=pi.product_id" + where("pi.purchase_id") + " ORDER BY pi.id",
                       "purchase_id")
        for r in rows:
            r["lines"] = lines.get(r["id"], [])
        return {r["id"]: r for r in rows}
    if kind == "return":
        rows = db.query("SELECT r.id, r.no, r.kind, r.date, r.party_id, p.name AS party, r.total, r.refunded, r.note "
                        "FROM returns r JOIN parties p ON p.id=r.party_id" + where("r.id"))
        lines = _lines(db, "SELECT ri.return_id, ri.product_id, pr.name, ri.qty, ri.price FROM return_items ri "
                           "JOIN products pr ON pr.id=ri.product_id" + where("ri.return_id") + " ORDER BY ri.id",
                       "return_id")
        for r in rows:
            r["lines"] = lines.get(r["id"], [])
        return {r["id"]: r for r in rows}
    if kind == "voucher":
        rows = db.query("SELECT v.id, v.no, v.kind, v.date, v.party_id, p.name AS party, v.amount, v.note "
                        "FROM vouchers v LEFT JOIN parties p ON p.id=v.party_id" + where("v.id"))
        return {r["id"]: r for r in rows}
    if kind == "expense":
        return {r["id"]: r for r in db.query("SELECT id, date, category, amount, note FROM expenses" + where("id"))}
    if kind == "meta":
        from .business_overview import overview
        from .reports import dashboard
        co = db.one("SELECT name FROM company WHERE id=1") or {"name": ""}
        cats = [r["name"] for r in db.query("SELECT name FROM categories ORDER BY name")]
        exp = [r["category"] for r in db.query("SELECT DISTINCT category FROM expenses ORDER BY category")]
        return {1: {"id": 1, "shop": co["name"], "dashboard": dashboard(db), "overview": overview(db),
                    "categories": cats, "expense_categories": exp}}
    raise BusinessError("Unknown kind")


def manifest(db) -> dict:
    """{kind: [[id, fingerprint], ...]} - small; the phone compares it with what it has."""
    return {k: [[i, _fp(r)] for i, r in records(db, k).items()] for k in KINDS}


def fetch(db, wanted: dict) -> dict:
    """{kind: [ids]} -> {kind: [records with their fingerprint]} (at most MAX_FETCH records in all)."""
    out, left = {}, MAX_FETCH
    for k in KINDS:
        ids = [int(i) for i in (wanted or {}).get(k) or []][:left]
        if not ids:
            continue
        recs = records(db, k, ids)
        out[k] = [dict(r, _fp=_fp(r)) for r in recs.values()]
        left -= len(ids)
        if left <= 0:
            break
    return out
