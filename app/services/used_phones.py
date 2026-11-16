"""Second-hand phones bought from a person (seller's name, CNIC, address, mobile are kept with the purchase).

Nothing here is a separate stock: the phone is saved through the normal purchase posting, so it becomes
an ordinary phone in stock (IMEI record, stock movement, cash paid in the cash book) and is sold on the
normal Sale Invoice. Its own product line holds exactly this phone's cost and sale price, so profit on
the invoice is the real profit of this phone."""
from . import imei, phones, trading
from .common import BusinessError, audited, next_no, now, r2, stock_qty
from .loans import clean_cnic

SELLERS_PARTY = "2nd Hand Phone Sellers"       # one supplier account for all walk-in sellers (always paid in cash)
TAG = "(2nd Hand)"


def _money(v, label, allow_zero=False) -> float:
    try:
        v = r2(float(v or 0))
    except (TypeError, ValueError):
        raise BusinessError(f"Enter the {label} as a number")
    if v < 0 or (v == 0 and not allow_zero):
        raise BusinessError(f"{label.capitalize()} must be greater than zero")
    return v


def _sellers_party(c) -> int:
    row = c.execute("SELECT id FROM parties WHERE kind='supplier' AND name=?", (SELLERS_PARTY,)).fetchone()
    if row:
        c.execute("UPDATE parties SET active=1 WHERE id=?", (row["id"],))
        return row["id"]
    return c.execute("INSERT INTO parties(kind,name) VALUES('supplier',?)", (SELLERS_PARTY,)).lastrowid


def _product_for(c, model, model_no, mode, price, sale_price, ph) -> int:
    """The stock line for this phone. A line is used again only when it is empty (its cost then becomes this
    phone's cost) or when it holds phones with exactly the same cost and sale price; otherwise the phone gets
    a line of its own ('... #2'), so one phone's cost never mixes with another's."""
    cat = c.execute("SELECT name FROM categories WHERE is_mobile=1 ORDER BY is_system DESC, id LIMIT 1").fetchone()
    if not cat:
        raise BusinessError("No mobile-phone category exists. Add one in Categories first.")
    size = f"{ph['ram_gb']}/{ph['storage_gb']}GB" if ph["ram_gb"] and ph["storage_gb"] else ""
    base = " ".join(x for x in (model, model_no, size) if x) + " " + TAG
    n = 1
    while True:
        name = base if n == 1 else f"{base} #{n}"
        p = c.execute("SELECT * FROM products WHERE lower(name)=lower(?)", (name,)).fetchone()
        if p is None:
            return c.execute(
                "INSERT INTO products(name,category,tags,unit,sale_price,track_serial,imei_mode,brand,mobile_type,"
                "ram_gb,storage_gb,condition) VALUES(?,?,?,'pcs',?,1,?,?,?,?,?,'used')",
                (name, cat["name"], "#used #2ndhand", sale_price, mode, ph["brand"], ph["mobile_type"],
                 ph["ram_gb"], ph["storage_gb"])).lastrowid
        if p["active"] and p["track_serial"] and p["imei_mode"] == mode and (
                p["mobile_type"] or None, p["ram_gb"], p["storage_gb"]) == (ph["mobile_type"], ph["ram_gb"], ph["storage_gb"]):
            empty = stock_qty(c, p["id"]) <= 0
            if empty or (abs(p["avg_cost"] - price) < 0.005 and abs(p["sale_price"] - sale_price) < 0.005):
                if empty:
                    c.execute("UPDATE products SET sale_price=?, condition='used' WHERE id=?", (sale_price, p["id"]))
                return p["id"]
        n += 1


@audited("2nd hand phone purchased", lambda db,a,k,r: db.scalar(
    "SELECT no||'  '||model||'  IMEI '||imei1||'  price '||price||'  from '||seller_name FROM used_phones WHERE id=?", (r,), ""))
def purchase(db, seller_name, model, imei1, price, cnic="", address="", phone="", model_no="", imei2="",
             sale_price=0, date=None, note="", mobile_type=None, ram_gb=None, storage_gb=None, brand="") -> int:
    """Buy one second-hand phone for cash. IMEI 1 is compulsory, IMEI 2 is optional. A smartphone needs RAM and
    storage (GB), a keypad phone does not. Returns the record id."""
    seller_name, model, model_no = (seller_name or "").strip(), (model or "").strip(), (model_no or "").strip()
    if not seller_name:
        raise BusinessError("Customer / seller name is required")
    if not model:
        raise BusinessError("Mobile model is required (e.g. Infinix Hot 40)")
    cnic = clean_cnic(cnic)
    ph = phones.clean(mobile_type, ram_gb, storage_gb, "used", brand or model.split()[0])
    price = _money(price, "purchase price")
    sale_price = _money(sale_price, "sale price", allow_zero=True)
    mode = "double" if (imei2 or "").strip() else "single"
    i1, i2 = imei.unit(imei1, imei2, mode)
    date = date or now()
    with db.transaction() as c:
        for x in (i1, i2):
            if not x:
                continue
            old = c.execute("SELECT s.id, s.status, p.name FROM serials s JOIN products p ON p.id=s.product_id "
                            "WHERE s.serial=? OR s.imei2=?", (x, x)).fetchone()
            if old and old["status"] == "in_stock":
                raise BusinessError(f"IMEI {x} is already in your stock ({old['name']}). "
                                    "The same phone cannot be added twice.")
            if old:         # a phone this shop sold earlier is being bought back: it enters the stock again
                c.execute("DELETE FROM serials WHERE id=?", (old["id"],))
        product_id = _product_for(c, model, model_no, mode, price, sale_price, ph)
        no = next_no(c, "UPH")
        purchase_id = trading.post_purchase(
            c, _sellers_party(c), [{"product_id": product_id, "qty": 1, "price": price, "serials": [(i1, i2)]}],
            price, f"{no}: 2nd hand phone from {seller_name}" + (f" ({cnic})" if cnic else ""), date)
        return c.execute(
            "INSERT INTO used_phones(no,date,seller_name,cnic,address,phone,model,model_no,imei1,imei2,price,"
            "sale_price,purchase_id,product_id,note) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (no, date, seller_name, cnic, (address or "").strip(), (phone or "").strip(), model, model_no, i1, i2,
             price, sale_price, purchase_id, product_id, (note or "").strip())).lastrowid


_SELECT = ("SELECT u.*, p.name AS product_name, p.mobile_type, p.ram_gb, p.storage_gb, p.brand, s.status AS stock_status, i.no AS invoice_no, i.date AS sold_date, "
           "(SELECT ii.price - ii.discount FROM invoice_items ii WHERE ii.invoice_id=s.invoice_id AND ii.serial=s.serial "
           "LIMIT 1) AS sold_price FROM used_phones u LEFT JOIN products p ON p.id=u.product_id "
           "LEFT JOIN serials s ON s.serial=u.imei1 AND s.purchase_id=u.purchase_id "
           "LEFT JOIN invoices i ON i.id=s.invoice_id ")


def _with_status(r):
    st = r["stock_status"]
    r["status"] = "In stock" if st == "in_stock" else "Sold" if st == "sold" else "Returned / removed"
    r["profit"] = r2(r["sold_price"] - r["price"]) if st == "sold" and r["sold_price"] is not None else None
    return r


def history(db, text="", date_from=None, date_to=None):
    """Purchase history of second-hand phones, newest first. `text` searches seller, model and IMEI."""
    sql, args = _SELECT + "WHERE 1=1", []
    if date_from:
        sql, args = sql + " AND u.date >= ?", args + [date_from + " 00:00:00"]
    if date_to:
        sql, args = sql + " AND u.date <= ?", args + [date_to + " 23:59:59"]
    text = (text or "").strip()
    if text:
        like = f"%{text}%"
        sql += (" AND (u.seller_name LIKE ? OR u.model LIKE ? OR u.model_no LIKE ? OR u.imei1 LIKE ? "
                "OR u.imei2 LIKE ? OR u.cnic LIKE ? OR u.phone LIKE ? OR u.no LIKE ?)")
        args += [like] * 8
    return [_with_status(r) for r in db.query(sql + " ORDER BY u.date DESC, u.id DESC", tuple(args))]


def detail(db, record_id):
    r = db.one(_SELECT + "WHERE u.id=?", (record_id,))
    return _with_status(r) if r else None
