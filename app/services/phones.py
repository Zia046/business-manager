"""Mobile-phone details (type, RAM, storage, condition) and the list of phones that are in stock now.

The details live on the product line the phone belongs to; every IMEI points to its product, so each
phone keeps its details when it is sold. Old records without details keep working (they show '-')."""
from . import imei
from .common import BusinessError, audited, log_audit, now, r2, stock_qty

TYPES = {"smartphone": "Smartphone", "keypad": "Keypad / Simple Mobile"}
CONDITIONS = {"new": "New", "used": "Used"}


def _gb(value, label):
    if value in (None, "", 0, "0"):
        return None
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        raise BusinessError(f"{label} must be a number (GB), e.g. 8")
    if n <= 0 or n > 4096:
        raise BusinessError(f"{label} must be between 1 and 4096 GB")
    return n


def clean(mobile_type=None, ram_gb=None, storage_gb=None, condition=None, brand="") -> dict:
    """Checked values ready to be saved. A smartphone needs RAM and storage; a keypad phone has neither.
    mobile_type None = not said (records made before this feature, or imported lists): nothing is required."""
    mobile_type = (mobile_type or "").strip().lower() or None
    if mobile_type not in (None, *TYPES):
        raise BusinessError("Mobile type must be Smartphone or Keypad / Simple Mobile")
    condition = (condition or "").strip().lower() or None
    if condition not in (None, *CONDITIONS):
        raise BusinessError("Condition must be New or Used")
    ram, storage = _gb(ram_gb, "RAM"), _gb(storage_gb, "Storage")
    if mobile_type == "keypad":
        ram = storage = None
    elif mobile_type == "smartphone" and (ram is None or storage is None):
        raise BusinessError("Enter RAM and Storage (GB) for a smartphone, e.g. RAM 8, Storage 256")
    return {"brand": (brand or "").strip() or None, "mobile_type": mobile_type, "ram_gb": ram,
            "storage_gb": storage, "condition": condition}


def gb(value) -> str:
    return f"{int(value)} GB" if value else "-"


def spec(p) -> str:
    """Short text for lists: '8 GB / 256 GB', 'Keypad', or '' for an old record."""
    if p.get("mobile_type") == "keypad":
        return "Keypad"
    if p.get("ram_gb") or p.get("storage_gb"):
        return f"{gb(p.get('ram_gb'))} / {gb(p.get('storage_gb'))}"
    return ""


def condition_of(p) -> str:
    c = p.get("condition")
    if c in CONDITIONS:
        return c
    return "used" if "(2nd hand)" in (p.get("name") or "").lower() else "new"


def in_stock(db, text="", condition="", mobile_type="", ram=None, storage=None, sort="model", descending=False):
    """Every phone that is in the shop now (one row per IMEI). Sold phones are simply not in this list.
    text searches brand, model and IMEI. sort: model | purchase | sale | ram | storage."""
    rows = db.query(
        "SELECT s.id AS serial_id, s.serial AS imei1, s.imei2, p.id AS product_id, p.name, p.brand, p.category, "
        "p.mobile_type, p.ram_gb, p.storage_gb, p.condition, p.avg_cost, p.sale_price AS product_sale_price, "
        "pu.no AS purchase_no, pu.date AS purchase_date, "
        "(SELECT pi.price FROM purchase_items pi WHERE pi.purchase_id=s.purchase_id AND pi.product_id=s.product_id "
        " LIMIT 1) AS unit_price, up.sale_price AS used_sale_price, up.seller_name "
        "FROM serials s JOIN products p ON p.id=s.product_id "
        "LEFT JOIN purchases pu ON pu.id=s.purchase_id "
        "LEFT JOIN used_phones up ON up.purchase_id=s.purchase_id AND up.imei1=s.serial "
        "WHERE s.status='in_stock'")
    text, out = (text or "").strip().lower(), []
    for r in rows:
        r["condition"] = condition_of(r)
        r["bought_at"] = r2(r["unit_price"] if r["unit_price"] is not None else r["avg_cost"])   # on its purchase
        r["purchase_price"] = r2(r["avg_cost"])        # current purchase rate: what its sale's profit will use
        r["sale_price"] = r2(r["product_sale_price"] or 0)
        r["brand"] = r["brand"] or ""
        r["status"] = "Available"
        if condition and r["condition"] != condition:
            continue
        if mobile_type and (r["mobile_type"] or "") != mobile_type:
            continue
        if ram and r["ram_gb"] != int(ram):
            continue
        if storage and r["storage_gb"] != int(storage):
            continue
        if text and text not in " ".join((r["brand"], r["name"], r["imei1"], r["imei2"] or "")).lower():
            continue
        out.append(r)
    keys = {"model": lambda r: ((r["brand"] + " " + r["name"]).strip().lower(), r["imei1"]),
            "purchase": lambda r: r["purchase_price"], "sale": lambda r: r["sale_price"],
            "ram": lambda r: r["ram_gb"] or 0, "storage": lambda r: r["storage_gb"] or 0}
    out.sort(key=keys.get(sort, keys["model"]), reverse=bool(descending))
    return out


def filter_values(db) -> dict:
    """The RAM and storage sizes that exist among the phones in stock (for the filter boxes)."""
    rows = db.query("SELECT DISTINCT p.ram_gb, p.storage_gb FROM serials s JOIN products p ON p.id=s.product_id "
                    "WHERE s.status='in_stock'")
    return {"ram": sorted({r["ram_gb"] for r in rows if r["ram_gb"]}),
            "storage": sorted({r["storage_gb"] for r in rows if r["storage_gb"]})}


# ---------------- edit / remove one phone of the stock ----------------
_ATTRS = ("name", "brand", "mobile_type", "ram_gb", "storage_gb", "condition", "imei_mode")


def phone(db, serial_id):
    """One phone in stock with everything the Edit form shows."""
    for r in in_stock(db):
        if r["serial_id"] == serial_id:
            return r
    return None


def _same(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        return abs(float(a or 0) - float(b or 0)) < 0.005
    return (a or None) == (b or None)


def _line_for(c, old, want, rate, sale):
    """The product line the phone moves to when its details differ from the other phones of its old line:
    an existing line with the same details that is empty (or has the same rate and price), else a new one."""
    n = 1
    while True:
        name = want["name"] if n == 1 else f"{want['name']} #{n}"
        p = c.execute("SELECT * FROM products WHERE lower(name)=lower(?) AND id<>?", (name, old["id"])).fetchone()
        if p is None:
            return c.execute(
                "INSERT INTO products(name,category,tags,unit,last_purchase_price,avg_cost,sale_price,track_serial,"
                "imei_mode,warranty_months,brand,mobile_type,ram_gb,storage_gb,condition) "
                "VALUES(?,?,?,?,?,?,?,1,?,?,?,?,?,?,?)",
                (name, old["category"], old["tags"], old["unit"] or "pcs", rate, rate, sale, want["imei_mode"],
                 old["warranty_months"], want["brand"], want["mobile_type"], want["ram_gb"], want["storage_gb"],
                 want["condition"])).lastrowid
        if p["active"] and p["track_serial"] and all(_same(p[k], want[k]) for k in _ATTRS if k != "name"):
            empty = stock_qty(c, p["id"]) <= 0
            if empty or (_same(p["avg_cost"], rate) and _same(p["sale_price"], sale)):
                if empty:
                    c.execute("UPDATE products SET avg_cost=?, last_purchase_price=?, sale_price=? WHERE id=?",
                              (rate, rate, sale, p["id"]))
                return p["id"]
        n += 1


@audited("Phone in stock edited", lambda db,a,k,r: r)
def edit_phone(db, serial_id, name, imei1, purchase_rate, sale_price, imei2="", brand="", mobile_type=None,
               ram_gb=None, storage_gb=None, condition=None) -> str:
    """Correct one phone that is in stock: model, brand, type, RAM, storage, condition, IMEI(s), purchase rate and
    selling price. Saved invoices and purchases are not touched (they keep their own prices and IMEIs).

    When the phone is the only one of its product line the line itself is corrected; when other phones share
    the line, only this phone moves to a line of its own, so the other phones keep their details."""
    from .masters import purchase_rate as _rate
    name = (name or "").strip()
    if not name:
        raise BusinessError("Model name is required")
    rate = _rate(purchase_rate)
    try:
        sale = r2(float(sale_price or 0))
    except (TypeError, ValueError):
        raise BusinessError("Enter the selling price as a number")
    if sale < 0:
        raise BusinessError("Selling price cannot be negative")
    mode = "double" if (imei2 or "").strip() else "single"
    i1, i2 = imei.unit(imei1, imei2, mode)
    with db.transaction() as c:
        s = c.execute("SELECT * FROM serials WHERE id=?", (serial_id,)).fetchone()
        if not s or s["status"] != "in_stock":
            raise BusinessError("This phone is not in stock any more (it was sold or removed)")
        old = c.execute("SELECT * FROM products WHERE id=?", (s["product_id"],)).fetchone()
        ph = clean(mobile_type if mobile_type is not None else old["mobile_type"], ram_gb, storage_gb,
                   condition or old["condition"], brand)
        want = {"name": name, "imei_mode": mode, **ph}
        for x in (i1, i2):
            if x and c.execute("SELECT 1 FROM serials WHERE id<>? AND (serial=? OR imei2=?)", (serial_id, x, x)).fetchone():
                raise BusinessError(f"IMEI {x} belongs to another phone in your records")
        changes = [f"{k}: {old[k]} -> {want[k]}" for k in _ATTRS if not _same(old[k], want[k])]
        if not _same(old["avg_cost"], rate):
            changes.append(f"purchase rate: {old['avg_cost']:g} -> {rate:g}")
        if not _same(old["sale_price"], sale):
            changes.append(f"selling price: {old['sale_price']:g} -> {sale:g}")
        if s["serial"] != i1 or (s["imei2"] or None) != i2:
            changes.append(f"IMEI: {s['serial']}/{s['imei2'] or '-'} -> {i1}/{i2 or '-'}")
        target = old["id"]
        product_change = any(not _same(old[k], want[k]) for k in _ATTRS) or not _same(old["avg_cost"], rate) \
            or not _same(old["sale_price"], sale)
        if product_change:
            others = c.execute("SELECT COUNT(*) AS n FROM serials WHERE product_id=? AND id<>?",
                               (old["id"], serial_id)).fetchone()["n"]
            if others == 0:                      # its own line: correct the line
                c.execute("UPDATE products SET name=?, brand=?, mobile_type=?, ram_gb=?, storage_gb=?, condition=?, "
                          "imei_mode=?, avg_cost=?, last_purchase_price=?, sale_price=? WHERE id=?",
                          (want["name"], want["brand"], want["mobile_type"], want["ram_gb"], want["storage_gb"],
                           want["condition"], mode, rate, rate, sale, old["id"]))
            else:                                # shared line: this phone alone moves to its own line
                target = _line_for(c, old, want, rate, sale)
                stamp, note = now(), f"IMEI {i1} details corrected"
                c.execute("INSERT INTO stock_moves(product_id,date,qty,unit_cost,ref_type,ref_id,note) "
                          "VALUES(?,?,-1,?,'phone_edit',?,?)", (old["id"], stamp, old["avg_cost"], serial_id, note))
                c.execute("INSERT INTO stock_moves(product_id,date,qty,unit_cost,ref_type,ref_id,note) "
                          "VALUES(?,?,1,?,'phone_edit',?,?)", (target, stamp, rate, serial_id, note))
        c.execute("UPDATE serials SET product_id=?, serial=?, imei2=? WHERE id=?", (target, i1, i2, serial_id))
        c.execute("UPDATE used_phones SET imei1=?, imei2=?, product_id=?, sale_price=? "
                  "WHERE purchase_id IS ? AND imei1=?", (i1, i2, target, sale, s["purchase_id"], s["serial"]))
        return f"IMEI {i1}: " + ("; ".join(changes) or "no change")


def remove_phone(db, serial_id, reason) -> None:
    """Take one phone out of the stock (entered by mistake, lost, damaged...). The reason is required and is kept,
    with the IMEI and its cost, in the stock record and the audit log. Saved purchases are not changed; a phone
    that goes back to its supplier should be entered as a Purchase Return instead (that also settles the money)."""
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise BusinessError("Write why this phone is removed (at least 3 letters)")
    with db.transaction() as c:
        s = c.execute("SELECT s.*, p.name, p.avg_cost FROM serials s JOIN products p ON p.id=s.product_id "
                      "WHERE s.id=?", (serial_id,)).fetchone()
        if not s or s["status"] != "in_stock":
            raise BusinessError("This phone is not in stock any more (it was sold or removed)")
        note = (f"IMEI {s['serial']}" + (f" / {s['imei2']}" if s["imei2"] else "") + f" removed: {reason}")[:300]
        c.execute("INSERT INTO stock_moves(product_id,date,qty,unit_cost,ref_type,ref_id,note) "
                  "VALUES(?,?,-1,?,'phone_removed',?,?)", (s["product_id"], now(), s["avg_cost"], serial_id, note))
        c.execute("DELETE FROM serials WHERE id=?", (serial_id,))
    log_audit(db, "Phone removed from stock", f"{s['name']}  {note}  cost {s['avg_cost']:g}")
