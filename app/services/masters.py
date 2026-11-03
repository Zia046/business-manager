"""Customers, suppliers, products, company info, product search."""
from .common import BusinessError, audited, stock_qty


# ---------- parties ----------
@audited("Party added", lambda db,a,k,r: f"{a[0]}: {a[1]} (id {r})")
def add_party(db, kind, name, phone="", address="", opening_balance=0.0) -> int:
    if kind not in ("customer", "supplier"):
        raise BusinessError("Invalid party type")
    if not name.strip():
        raise BusinessError("Name is required")
    with db.transaction() as c:
        cur = c.execute("INSERT INTO parties(kind,name,phone,address,opening_balance) VALUES(?,?,?,?,?)",
                        (kind, name.strip(), phone, address, float(opening_balance)))
        return cur.lastrowid


@audited("Party edited", lambda db,a,k,r: f"id {a[0]}: {a[1]}")
def update_party(db, party_id, name, phone="", address="", opening_balance=0.0):
    p = db.one("SELECT * FROM parties WHERE id=?", (party_id,))
    if not p or p["is_walkin"]:
        raise BusinessError("This account cannot be edited")
    if not name.strip():
        raise BusinessError("Name is required")
    with db.transaction() as c:
        c.execute("UPDATE parties SET name=?,phone=?,address=?,opening_balance=? WHERE id=?",
                  (name.strip(), phone, address, float(opening_balance), party_id))


@audited("Party deleted", lambda db,a,k,r: f"id {a[0]}")
def delete_party(db, party_id):
    """Hard delete if unused, otherwise soft delete (keeps history intact)."""
    p = db.one("SELECT * FROM parties WHERE id=?", (party_id,))
    if not p or p["is_walkin"]:
        raise BusinessError("This account cannot be deleted")
    used = db.scalar("SELECT COUNT(*) FROM ledger WHERE party_id=?", (party_id,))
    with db.transaction() as c:
        if used:
            c.execute("UPDATE parties SET active=0 WHERE id=?", (party_id,))
        else:
            c.execute("DELETE FROM parties WHERE id=?", (party_id,))
    return "deactivated" if used else "deleted"


def search_parties(db, kind, text=""):
    like = f"%{text.strip()}%"
    return db.query("SELECT * FROM parties WHERE kind=? AND active=1 AND "
                    "(name LIKE ? OR phone LIKE ? OR CAST(id AS TEXT)=?) ORDER BY name LIMIT 200",
                    (kind, like, like, text.strip()))


# ---------- products ----------
MOBILE_CATEGORY = "Mobile Phone"


# ---------- categories ----------
def list_categories(db):
    return db.query("SELECT * FROM categories ORDER BY id")


def get_category(db, name):
    return db.one("SELECT * FROM categories WHERE name=? COLLATE NOCASE", ((name or "").strip(),))


def add_category(db, name) -> int:
    name = (name or "").strip()
    if not name:
        raise BusinessError("Category name is required")
    if get_category(db, name):
        raise BusinessError(f"Category '{name}' already exists")
    with db.transaction() as c:
        return c.execute("INSERT INTO categories(name) VALUES(?)", (name,)).lastrowid


def delete_category(db, category_id):
    cat = db.one("SELECT * FROM categories WHERE id=?", (category_id,))
    if not cat:
        raise BusinessError("Category not found")
    if cat["is_system"]:
        raise BusinessError(f"'{cat['name']}' is a built-in category and cannot be deleted")
    used = db.scalar("SELECT COUNT(*) FROM products WHERE category=? COLLATE NOCASE", (cat["name"],))
    if used:
        raise BusinessError(f"{used} product(s) use '{cat['name']}'. Move them to another category first.")
    with db.transaction() as c:
        c.execute("DELETE FROM categories WHERE id=?", (category_id,))


# ---------- products ----------
def _months(v) -> int:
    try:
        n = int(v or 0)
    except (TypeError, ValueError):
        raise BusinessError("Warranty must be a number of months")
    if not 0 <= n <= 120:
        raise BusinessError("Warranty must be between 0 and 120 months")
    return n


def _barcode(db, code, product_id=None) -> str:
    """Optional product barcode: letters/digits only, and never shared by two products."""
    code = (code or "").strip()
    if not code:
        return ""
    if not code.isalnum() or len(code) > 40:
        raise BusinessError("Barcode may contain only letters and digits (up to 40)")
    other = db.one("SELECT id, name FROM products WHERE barcode=? AND id<>? AND active=1", (code, product_id or 0))
    if other:
        raise BusinessError(f"This barcode is already used by '{other['name']}'")
    return code


def barcode_for(product) -> str:
    """What is printed/scanned for a product: its own barcode, or its ID as 6 digits."""
    return product.get("barcode") or f"{product['id']:06d}"


@audited("Product added", lambda db,a,k,r: f"{a[0] if a else k.get('name')} (id {r})")
def add_product(db, name, sale_price=0.0, purchase_price=0.0, opening_stock=0.0, category="",
                tags="", unit="pcs", low_stock_level=0.0, track_serial=False, imei_mode="single",
                warranty_months=0, barcode="") -> int:
    """A category must be chosen. Mobile phones are always IMEI-tracked, must say whether they have a
    single or double IMEI, and cannot have an opening stock (phones enter stock through Stock Purchase,
    where every IMEI number is compulsory)."""
    if not name.strip():
        raise BusinessError("Product name is required")
    warranty_months = _months(warranty_months)
    barcode = _barcode(db, barcode)
    if min(sale_price, purchase_price, opening_stock) < 0:
        raise BusinessError("Prices and stock cannot be negative")
    cat = get_category(db, category)
    if not cat:
        raise BusinessError("Select a category for the product")
    mobile = bool(cat["is_mobile"])
    if mobile:
        if imei_mode not in ("single", "double"):
            raise BusinessError("Select whether this phone has a single or double IMEI")
        if opening_stock:
            raise BusinessError("Mobile phones cannot have an opening stock. Add them through Stock "
                                "Purchase, where their IMEI numbers are entered.")
    else:
        imei_mode = "single"
    with db.transaction() as c:
        cur = c.execute(
            "INSERT INTO products(name,category,tags,unit,last_purchase_price,avg_cost,sale_price,"
            "opening_stock,low_stock_level,track_serial,imei_mode,warranty_months,barcode) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (name.strip(), cat["name"], tags, unit, purchase_price, purchase_price, sale_price,
             opening_stock, low_stock_level, int(mobile), imei_mode, warranty_months, barcode or None))
        return cur.lastrowid


@audited("Product edited", lambda db,a,k,r: f"id {a[0]}: " + ", ".join(f"{x}={y}" for x,y in k.items()))
def update_product(db, product_id, **fields):
    allowed = {"name", "category", "tags", "unit", "sale_price", "low_stock_level", "imei_mode", "warranty_months", "barcode"}
    bad = set(fields) - allowed
    if bad:
        raise BusinessError(f"Cannot edit: {', '.join(sorted(bad))}")
    if not fields:
        return
    p = db.one("SELECT * FROM products WHERE id=?", (product_id,))
    if not p:
        raise BusinessError("Product not found")
    if "name" in fields and not str(fields["name"]).strip():
        raise BusinessError("Product name is required")
    if "warranty_months" in fields:
        fields["warranty_months"] = _months(fields["warranty_months"])
    if "barcode" in fields:
        fields["barcode"] = _barcode(db, fields["barcode"], product_id) or None
    has_history = db.scalar("SELECT COUNT(*) FROM stock_moves WHERE product_id=?", (product_id,)) > 0
    if "category" in fields:
        cat = get_category(db, fields["category"])
        if not cat:
            raise BusinessError("Select a category for the product")
        fields["category"] = cat["name"]
        if bool(cat["is_mobile"]) != bool(p["track_serial"]):
            if has_history:
                raise BusinessError("A product that already has stock history cannot be moved to or from "
                                    "the Mobile Phone category.")
            fields["track_serial"] = int(cat["is_mobile"])
        mobile = bool(cat["is_mobile"])
    else:
        mobile = bool(p["track_serial"])
    if "imei_mode" in fields:
        if not mobile:
            fields["imei_mode"] = "single"
        elif fields["imei_mode"] not in ("single", "double"):
            raise BusinessError("Select whether this phone has a single or double IMEI")
        elif fields["imei_mode"] != p["imei_mode"] and db.scalar(
                "SELECT COUNT(*) FROM serials WHERE product_id=?", (product_id,)):
            raise BusinessError("Single/double IMEI cannot be changed after IMEI numbers were entered.")
    sets = ", ".join(f"{k}=?" for k in fields)
    with db.transaction() as c:
        c.execute(f"UPDATE products SET {sets} WHERE id=?", (*fields.values(), product_id))


def db_has_imei(db, product_id) -> bool:
    return db.scalar("SELECT COUNT(*) FROM serials WHERE product_id=?", (product_id,)) > 0


@audited("Product deleted", lambda db,a,k,r: f"id {a[0]}")
def delete_product(db, product_id):
    used = db.scalar("SELECT COUNT(*) FROM stock_moves WHERE product_id=?", (product_id,))
    with db.transaction() as c:
        if used:
            c.execute("UPDATE products SET active=0 WHERE id=?", (product_id,))
        else:
            c.execute("DELETE FROM products WHERE id=?", (product_id,))
    return "deactivated" if used else "deleted"


def search_products(db, text="", limit=50):
    """Search by name, hash-tag, id, partial text, or similar spelling (fuzzy)."""
    text = text.strip()
    rows = db.query("SELECT p.*, p.opening_stock + COALESCE((SELECT SUM(qty) FROM stock_moves "
                    "WHERE product_id=p.id),0) AS stock FROM products p WHERE active=1")
    if not text:
        return sorted(rows, key=lambda r: r["name"].lower())[:limit]
    t = text.lstrip("#").lower()
    scanned = [r for r in rows if (r.get("barcode") or "").lower() == t]      # a barcode scanner types the code
    if scanned:
        return scanned
    if t.isdigit() and len(t) == 6:                                           # printed label code = ID, 6 digits
        hit = [r for r in rows if r["id"] == int(t)]
        if hit:
            return hit
    if t.isdigit():
        hit = [r for r in rows if r["id"] == int(t)]
        if hit:
            return hit
    exact = [r for r in rows if t in r["name"].lower() or t in (r["tags"] or "").lower()
             or t in (r["category"] or "").lower()]
    if exact:
        return sorted(exact, key=lambda r: r["name"].lower())[:limit]
    # similar spelling: rapidfuzz if installed, otherwise Python's difflib
    try:
        from rapidfuzz import fuzz
        score = lambda a, b: fuzz.partial_ratio(a, b)
    except ImportError:
        from difflib import SequenceMatcher

        def score(a, b):
            if not b:
                return 0
            best = 0
            for w in b.replace("#", " ").split() + [b]:
                best = max(best, SequenceMatcher(None, a, w).ratio() * 100)
            return best
    scored = [(max(score(t, r["name"].lower()), score(t, (r["tags"] or "").lower())), r) for r in rows]
    return [r for s, r in sorted(scored, key=lambda x: -x[0]) if s >= 70][:limit]


# ---------- company ----------
def get_company(db):
    return db.one("SELECT * FROM company WHERE id=1")


@audited("Company information edited", lambda db,a,k,r: str(a[0]))
def update_company(db, name, address, phone, email, logo_path=None):
    if not all(x.strip() for x in (name, address, phone, email)):
        raise BusinessError("All company fields are required")
    with db.transaction() as c:
        if logo_path:
            c.execute("UPDATE company SET logo_path=? WHERE id=1", (logo_path,))
        c.execute("UPDATE company SET name=?,address=?,phone=?,email=? WHERE id=1",
                  (name.strip(), address.strip(), phone.strip(), email.strip()))
    from .auth import write_branding  # keep login-screen branding in sync
    write_branding(db.data_dir, name.strip(), get_company(db)["logo_path"])


__all__ = ["stock_qty"]
