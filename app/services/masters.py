"""Customers, suppliers, products, company info, product search."""
from .common import BusinessError, stock_qty


# ---------- parties ----------
def add_party(db, kind, name, phone="", address="", opening_balance=0.0) -> int:
    if kind not in ("customer", "supplier"):
        raise BusinessError("Invalid party type")
    if not name.strip():
        raise BusinessError("Name is required")
    with db.transaction() as c:
        cur = c.execute("INSERT INTO parties(kind,name,phone,address,opening_balance) VALUES(?,?,?,?,?)",
                        (kind, name.strip(), phone, address, float(opening_balance)))
        return cur.lastrowid


def update_party(db, party_id, name, phone="", address="", opening_balance=0.0):
    p = db.one("SELECT * FROM parties WHERE id=?", (party_id,))
    if not p or p["is_walkin"]:
        raise BusinessError("This account cannot be edited")
    if not name.strip():
        raise BusinessError("Name is required")
    with db.transaction() as c:
        c.execute("UPDATE parties SET name=?,phone=?,address=?,opening_balance=? WHERE id=?",
                  (name.strip(), phone, address, float(opening_balance), party_id))


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
def add_product(db, name, sale_price=0.0, purchase_price=0.0, opening_stock=0.0, category="",
                tags="", unit="pcs", low_stock_level=0.0, track_serial=False) -> int:
    if not name.strip():
        raise BusinessError("Product name is required")
    if min(sale_price, purchase_price, opening_stock) < 0:
        raise BusinessError("Prices and stock cannot be negative")
    with db.transaction() as c:
        cur = c.execute(
            "INSERT INTO products(name,category,tags,unit,last_purchase_price,avg_cost,sale_price,"
            "opening_stock,low_stock_level,track_serial) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (name.strip(), category, tags, unit, purchase_price, purchase_price, sale_price,
             opening_stock, low_stock_level, int(track_serial)))
        return cur.lastrowid


def update_product(db, product_id, **fields):
    allowed = {"name", "category", "tags", "unit", "sale_price", "low_stock_level", "track_serial"}
    bad = set(fields) - allowed
    if bad:
        raise BusinessError(f"Cannot edit: {', '.join(sorted(bad))}")
    if not fields:
        return
    if "name" in fields and not str(fields["name"]).strip():
        raise BusinessError("Product name is required")
    sets = ", ".join(f"{k}=?" for k in fields)
    with db.transaction() as c:
        c.execute(f"UPDATE products SET {sets} WHERE id=?", (*fields.values(), product_id))


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
