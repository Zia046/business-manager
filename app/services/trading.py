"""Sale invoices, purchases and returns.

Every function runs in ONE database transaction: if anything fails (e.g. not
enough stock) nothing is saved, so stock, ledger and cash book stay in sync.
"""
from . import imei
from .common import (audited, BusinessError, customer_balance, next_no, now, post_cash, post_ledger,
                     r2, stock_qty, supplier_balance, unpost)


# =============== PHONES (IMEI) ===============
def find_unit(c, p, i1, i2):
    """Stock record of the phone that owns these IMEI number(s). The numbers typed must be exactly
    the numbers of that one phone (a phone is never picked automatically: it is identified only by
    what the user typed)."""
    nums = [x for x in (i1, i2) if x]
    marks = ",".join("?" * len(nums))
    rows = c.execute(f"SELECT * FROM serials WHERE product_id=? AND (serial IN ({marks}) OR imei2 IN ({marks}))",
                     (p["id"], *nums, *nums)).fetchall()
    if not rows:
        raise BusinessError(f"IMEI {i1} is not in the stock record of '{p['name']}'")
    row = rows[0]
    stored = {x for x in (row["serial"], row["imei2"]) if x}
    if len(rows) > 1 or stored != set(nums):
        raise BusinessError(f"The IMEI number(s) typed do not match the stock record of this phone "
                            f"('{p['name']}', IMEI {row['serial']}"
                            f"{' / ' + row['imei2'] if row['imei2'] else ''})")
    return row


def check_sale_unit(c, p, serial, serial2):
    """The typed IMEI(s) must be a phone of this product that is in stock. Returns its stock record."""
    i1, i2 = imei.unit(serial, serial2, p["imei_mode"])
    row = find_unit(c, p, i1, i2)
    if row["status"] != "in_stock":
        raise BusinessError(f"This phone (IMEI {row['serial']}) is already sold")
    return row


# =============== SALE INVOICE ===============
def _post_invoice(c, inv_id, no, date, party, items, discount, paid, note, allow_negative_stock):
    if not items:
        raise BusinessError("Add at least one product")
    subtotal, cost_total = 0.0, 0.0
    for it in items:
        qty, price, disc = float(it["qty"]), float(it["price"]), float(it.get("discount", 0))
        if qty <= 0 or price < 0 or disc < 0:
            raise BusinessError("Quantity must be positive; price/discount cannot be negative")
        p = c.execute("SELECT * FROM products WHERE id=?", (it["product_id"],)).fetchone()
        if not p:
            raise BusinessError("Product not found")
        if p["track_serial"] and qty != 1:
            raise BusinessError(f"'{p['name']}': sell each phone on its own line with its IMEI")
        if not allow_negative_stock and qty > stock_qty(c, p["id"]):
            raise BusinessError(f"Not enough stock for '{p['name']}' "
                                f"(available {stock_qty(c, p['id']):g})")
        line = r2(qty * price - disc)
        if line < 0:
            raise BusinessError("Line discount is larger than the line amount")
        subtotal += line
        cost_total += qty * p["avg_cost"]
        unit_row = None
        if p["track_serial"]:   # a phone: sold one at a time, identified by the IMEI typed on the invoice
            if qty != 1:
                raise BusinessError(f"'{p['name']}': sell each phone on its own line with its IMEI")
            unit_row = check_sale_unit(c, p, it.get("serial"), it.get("serial2"))
        c.execute("INSERT INTO invoice_items(invoice_id,product_id,qty,price,discount,unit_cost,serial,serial2)"
                  " VALUES(?,?,?,?,?,?,?,?)",
                  (inv_id, p["id"], qty, price, disc, p["avg_cost"],
                   unit_row["serial"] if unit_row else it.get("serial"),
                   unit_row["imei2"] if unit_row else None))
        c.execute("INSERT INTO stock_moves(product_id,date,qty,unit_cost,ref_type,ref_id) "
                  "VALUES(?,?,?,?,'invoice',?)", (p["id"], date, -qty, p["avg_cost"], inv_id))
        if unit_row:
            c.execute("UPDATE serials SET status='sold', invoice_id=? WHERE id=?", (inv_id, unit_row["id"]))
    discount = float(discount or 0)
    total = r2(subtotal - discount)
    if discount < 0 or total < 0:
        raise BusinessError("Invalid invoice discount")
    paid = r2(paid)
    if paid < 0 or paid > total:
        raise BusinessError("Paid amount must be between 0 and the invoice total")
    if party["is_walkin"] and paid != total:
        raise BusinessError("Walk-in customer must pay in full. Select a saved customer for credit.")
    c.execute("UPDATE invoices SET subtotal=?,discount=?,total=?,paid=?,cost_total=?,note=?,party_id=?,"
              "date=? WHERE id=?", (r2(subtotal), discount, total, paid, r2(cost_total), note,
                                    party["id"], date, inv_id))
    post_ledger(c, party["id"], date, "invoice", inv_id, debit=total, note=no)
    post_ledger(c, party["id"], date, "invoice", inv_id, credit=paid, note=f"Paid {no}")
    post_cash(c, date, "in", paid, "invoice", inv_id, party["id"], no)


def _inv_num(no: str) -> int:
    return int(no.split("-")[1])


def suggest_invoice_no(db, reserved=(), today=None) -> str:
    """Number for a new invoice window.

    Several invoice windows can be open together; each keeps the number it was given when it opened.
    A number that was skipped (its window was closed without saving) is given to the next new invoice,
    but only on the same date as the neighbouring saved invoices - so numbers stay in date order.
    `reserved` = numbers (e.g. 'INV-00007') held by other open windows."""
    today = today or now()[:10]
    used = {}
    for r in db.query("SELECT no, date FROM invoices WHERE no LIKE 'INV-%'"):
        used[_inv_num(r["no"])] = r["date"][:10]
    held = {_inv_num(x) for x in reserved if x}
    counter = db.scalar("SELECT value FROM counters WHERE name='INV'", (), 0) or 0
    top = max([counter, *used, *held], default=0)
    for n in range(1, top + 1):
        if n in used or n in held:
            continue
        lower = max((k for k in used if k < n), default=None)
        higher = min((k for k in used if k > n), default=None)
        if (lower is None or used[lower] == today) and (higher is None or used[higher] == today) \
                and (lower is not None or higher is not None):
            return f"INV-{n:05d}"
    return f"INV-{top + 1:05d}"


def _take_invoice_no(c, wanted):
    """Use the number the window was given; if someone took it meanwhile, fall back to the next free one."""
    if wanted:
        n = _inv_num(wanted)
        if not c.execute("SELECT 1 FROM invoices WHERE no=?", (wanted,)).fetchone():
            c.execute("INSERT INTO counters(name,value) VALUES('INV',?) "
                      "ON CONFLICT(name) DO UPDATE SET value=MAX(value, excluded.value)", (n,))
            return wanted
    return next_no(c, "INV")


@audited("Sale invoice created", lambda db,a,k,r: db.scalar("SELECT no||'  total '||total FROM invoices WHERE id=?",(r,),""))
def create_invoice(db, party_id, items, discount=0.0, paid=0.0, note="", date=None,
                   allow_negative_stock=False, no=None) -> int:
    date = date or now()
    with db.transaction() as c:
        party = c.execute("SELECT * FROM parties WHERE id=? AND kind='customer'", (party_id,)).fetchone()
        if not party:
            raise BusinessError("Customer not found")
        no = _take_invoice_no(c, no)
        inv_id = c.execute("INSERT INTO invoices(no,date,party_id,subtotal,total) VALUES(?,?,?,0,0)",
                           (no, date, party_id)).lastrowid
        _post_invoice(c, inv_id, no, date, party, items, discount, paid, note, allow_negative_stock)
        return inv_id


@audited("Sale invoice edited", lambda db,a,k,r: db.scalar("SELECT no||'  total '||total FROM invoices WHERE id=?",(a[0],),""))
def edit_invoice(db, invoice_id, party_id, items, discount=0.0, paid=0.0, note="",
                 allow_negative_stock=False):
    """Edit = reverse the old posting, then post the new one (single transaction)."""
    with db.transaction() as c:
        inv = c.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv or inv["status"] == "cancelled":
            raise BusinessError("Invoice not found or already cancelled")
        party = c.execute("SELECT * FROM parties WHERE id=? AND kind='customer'", (party_id,)).fetchone()
        if not party:
            raise BusinessError("Customer not found")
        unpost(c, "invoice", invoice_id)
        c.execute("UPDATE serials SET status='in_stock', invoice_id=NULL WHERE invoice_id=?", (invoice_id,))
        c.execute("DELETE FROM invoice_items WHERE invoice_id=?", (invoice_id,))
        _post_invoice(c, invoice_id, inv["no"], inv["date"], party, items, discount, paid, note,
                      allow_negative_stock)


@audited("Sale invoice cancelled", lambda db,a,k,r: db.scalar("SELECT no||'  total '||total FROM invoices WHERE id=?",(a[0],),""))
def cancel_invoice(db, invoice_id):
    with db.transaction() as c:
        inv = c.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv or inv["status"] == "cancelled":
            raise BusinessError("Invoice not found or already cancelled")
        unpost(c, "invoice", invoice_id)
        c.execute("UPDATE serials SET status='in_stock', invoice_id=NULL WHERE invoice_id=?", (invoice_id,))
        c.execute("UPDATE invoices SET status='cancelled' WHERE id=?", (invoice_id,))


def invoice_profit(db, invoice_id) -> float:
    """Profit/loss of one invoice (shown only when the 'Show Profit/Loss' box is ticked)."""
    inv = db.one("SELECT total, cost_total FROM invoices WHERE id=?", (invoice_id,))
    return r2(inv["total"] - inv["cost_total"])


def preview_profit(db, items, discount=0.0) -> float:
    """Live profit preview on the unsaved invoice screen."""
    total = cost = 0.0
    for it in items:
        p = db.one("SELECT avg_cost FROM products WHERE id=?", (it["product_id"],))
        total += float(it["qty"]) * float(it["price"]) - float(it.get("discount", 0))
        cost += float(it["qty"]) * p["avg_cost"]
    return r2(total - float(discount or 0) - cost)


# =============== PURCHASE ===============
@audited("Stock purchase", lambda db,a,k,r: db.scalar("SELECT no||'  total '||total FROM purchases WHERE id=?",(r,),""))
def create_purchase(db, supplier_id, items, paid=0.0, note="", date=None) -> int:
    """`items` need an explicit typed price - it is never auto-filled from stored data.
    Product average cost is updated with the weighted-average method."""
    date = date or now()
    if not items:
        raise BusinessError("Add at least one product")
    with db.transaction() as c:
        sup = c.execute("SELECT * FROM parties WHERE id=? AND kind='supplier'", (supplier_id,)).fetchone()
        if not sup:
            raise BusinessError("Supplier not found")
        no = next_no(c, "PUR")
        pid = c.execute("INSERT INTO purchases(no,date,party_id,total) VALUES(?,?,?,0)",
                        (no, date, supplier_id)).lastrowid
        total = 0.0
        for it in items:
            if it.get("price") is None:
                raise BusinessError("Enter the purchase price for every product")
            qty, price = float(it["qty"]), float(it["price"])
            if qty <= 0 or price < 0:
                raise BusinessError("Quantity must be positive and price cannot be negative")
            p = c.execute("SELECT * FROM products WHERE id=?", (it["product_id"],)).fetchone()
            if not p:
                raise BusinessError("Product not found")
            on_hand = max(stock_qty(c, p["id"]), 0)
            new_avg = (on_hand * p["avg_cost"] + qty * price) / (on_hand + qty)
            c.execute("UPDATE products SET avg_cost=?, last_purchase_price=? WHERE id=?",
                      (round(new_avg, 4), price, p["id"]))
            c.execute("INSERT INTO purchase_items(purchase_id,product_id,qty,price,serial) VALUES(?,?,?,?,?)",
                      (pid, p["id"], qty, price, None))
            c.execute("INSERT INTO stock_moves(product_id,date,qty,unit_cost,ref_type,ref_id) "
                      "VALUES(?,?,?,?,'purchase',?)", (p["id"], date, qty, price, pid))
            if p["track_serial"]:
                if qty != int(qty):
                    raise BusinessError("Phones are bought in whole numbers")
                raw = it.get("serials") or []
                if len(raw) != int(qty):
                    raise BusinessError(f"'{p['name']}': enter the IMEI of every phone "
                                        f"({int(qty)} phones, {len(raw)} IMEI entries)")
                for r in raw:
                    i1, i2 = imei.as_unit(r, p["imei_mode"])
                    for x in (i1, i2):
                        if x and c.execute("SELECT 1 FROM serials WHERE serial=? OR imei2=?", (x, x)).fetchone():
                            raise BusinessError(f"IMEI {x} already exists in the stock")
                    c.execute("INSERT INTO serials(product_id,serial,imei2,purchase_id) VALUES(?,?,?,?)",
                              (p["id"], i1, i2, pid))
            total += qty * price
        total, paid = r2(total), r2(paid)
        if paid < 0 or paid > total:
            raise BusinessError("Paid amount must be between 0 and the purchase total")
        c.execute("UPDATE purchases SET total=?, paid=?, note=? WHERE id=?", (total, paid, note, pid))
        post_ledger(c, supplier_id, date, "purchase", pid, credit=total, note=no)
        post_ledger(c, supplier_id, date, "purchase", pid, debit=paid, note=f"Paid {no}")
        post_cash(c, date, "out", paid, "purchase", pid, supplier_id, no)
        return pid


# =============== RETURNS ===============
def returnable_items(db_or_conn, kind: str, doc_id: int):
    """Items of an original invoice ('sale') or purchase ('purchase') that can still be returned.
    Returns [{product_id, name, sold_qty, returned_qty, remaining, price}] where price is the
    effective unit price (line discount included for invoices)."""
    conn = getattr(db_or_conn, "conn", db_or_conn)
    if kind == "sale":
        rows = conn.execute(
            "SELECT ii.product_id, p.name, p.track_serial, p.imei_mode, SUM(ii.qty) AS qty, "
            "SUM(ii.qty*ii.price-ii.discount)/SUM(ii.qty) AS price FROM invoice_items ii "
            "JOIN products p ON p.id=ii.product_id WHERE ii.invoice_id=? GROUP BY ii.product_id", (doc_id,)).fetchall()
    else:
        rows = conn.execute(
            "SELECT pi.product_id, p.name, p.track_serial, p.imei_mode, SUM(pi.qty) AS qty, "
            "SUM(pi.qty*pi.price)/SUM(pi.qty) AS price "
            "FROM purchase_items pi JOIN products p ON p.id=pi.product_id WHERE pi.purchase_id=? "
            "GROUP BY pi.product_id", (doc_id,)).fetchall()
    out = []
    for r in rows:
        done = conn.execute("SELECT COALESCE(SUM(ri.qty),0) q FROM return_items ri JOIN returns rt ON rt.id=ri.return_id "
                            "WHERE rt.ref_doc_id=? AND rt.kind=? AND ri.product_id=?",
                            (doc_id, kind, r["product_id"])).fetchone()["q"]
        out.append({"product_id": r["product_id"], "name": r["name"], "sold_qty": r["qty"], "returned_qty": done,
                    "remaining": r["qty"] - done, "price": round(r["price"], 2),
                    "track_serial": r["track_serial"], "imei_mode": r["imei_mode"]})
    return out



@audited("Sale return", lambda db,a,k,r: db.scalar("SELECT no||'  total '||total FROM returns WHERE id=?",(r,),""))
def sale_return(db, party_id, items, refunded=0.0, ref_invoice_id=None, note="", date=None) -> int:
    """Customer returns goods: stock +, customer balance reduced, optional cash refund."""
    date = date or now()
    if not items:
        raise BusinessError("Add at least one product")
    with db.transaction() as c:
        party = c.execute("SELECT * FROM parties WHERE id=? AND kind='customer'", (party_id,)).fetchone()
        if not party:
            raise BusinessError("Customer not found")
        no = next_no(c, "SRT")
        rid = c.execute("INSERT INTO returns(no,kind,date,party_id,ref_doc_id,total) "
                        "VALUES(?,'sale',?,?,?,0)", (no, date, party_id, ref_invoice_id)).lastrowid
        total = 0.0
        for it in items:
            qty, price = float(it["qty"]), float(it["price"])
            if qty <= 0 or price < 0:
                raise BusinessError("Invalid quantity or price")
            cost = None
            if ref_invoice_id:
                row = c.execute("SELECT unit_cost, qty FROM invoice_items WHERE invoice_id=? AND product_id=?",
                                (ref_invoice_id, it["product_id"])).fetchone()
                if not row:
                    raise BusinessError("Product is not on the selected invoice")
                cost = row["unit_cost"]
            if cost is None:
                cost = c.execute("SELECT avg_cost FROM products WHERE id=?",
                                 (it["product_id"],)).fetchone()["avg_cost"]
            p = c.execute("SELECT * FROM products WHERE id=?", (it["product_id"],)).fetchone()
            if not p:
                raise BusinessError("Product not found")
            if p["track_serial"]:   # a returned phone must be identified by its IMEI
                if qty != 1:
                    raise BusinessError(f"'{p['name']}': return phones one by one with their IMEI")
                i1, i2 = imei.unit(it.get("serial"), it.get("serial2"), p["imei_mode"])
                row = find_unit(c, p, i1, i2)
                if row["status"] != "sold":
                    raise BusinessError(f"This phone (IMEI {row['serial']}) was not sold, so it cannot be returned")
                if ref_invoice_id and row["invoice_id"] != ref_invoice_id:
                    raise BusinessError(f"This phone (IMEI {row['serial']}) is not on the selected invoice")
                c.execute("UPDATE serials SET status='in_stock', invoice_id=NULL WHERE id=?", (row["id"],))
            c.execute("INSERT INTO return_items(return_id,product_id,qty,price,unit_cost) VALUES(?,?,?,?,?)",
                      (rid, it["product_id"], qty, price, cost))
            if ref_invoice_id:
                done = c.execute("SELECT COALESCE(SUM(ri.qty),0) q FROM return_items ri JOIN returns r "
                                 "ON r.id=ri.return_id WHERE r.ref_doc_id=? AND r.kind='sale' "
                                 "AND ri.product_id=?", (ref_invoice_id, it["product_id"])).fetchone()["q"]
                sold = c.execute("SELECT SUM(qty) q FROM invoice_items WHERE invoice_id=? AND product_id=?",
                                 (ref_invoice_id, it["product_id"])).fetchone()["q"]
                if done > sold:
                    raise BusinessError("Return quantity is more than sold quantity")
            c.execute("INSERT INTO stock_moves(product_id,date,qty,unit_cost,ref_type,ref_id) "
                      "VALUES(?,?,?,?,'sale_return',?)", (it["product_id"], date, qty, cost, rid))
            total += qty * price
        total, refunded = r2(total), r2(refunded)
        if refunded < 0 or refunded > total:
            raise BusinessError("Refund cannot be more than the return total")
        c.execute("UPDATE returns SET total=?, refunded=?, note=? WHERE id=?", (total, refunded, note, rid))
        post_ledger(c, party_id, date, "sale_return", rid, credit=total, note=no)
        post_ledger(c, party_id, date, "sale_return", rid, debit=refunded, note=f"Refund {no}")
        post_cash(c, date, "out", refunded, "sale_return", rid, party_id, no)
        return rid


@audited("Purchase return", lambda db,a,k,r: db.scalar("SELECT no||'  total '||total FROM returns WHERE id=?",(r,),""))
def purchase_return(db, supplier_id, items, received=0.0, ref_purchase_id=None, note="", date=None) -> int:
    """Goods sent back to supplier: stock -, supplier balance reduced, optional cash received."""
    date = date or now()
    if not items:
        raise BusinessError("Add at least one product")
    with db.transaction() as c:
        sup = c.execute("SELECT * FROM parties WHERE id=? AND kind='supplier'", (supplier_id,)).fetchone()
        if not sup:
            raise BusinessError("Supplier not found")
        no = next_no(c, "PRT")
        rid = c.execute("INSERT INTO returns(no,kind,date,party_id,ref_doc_id,total) "
                        "VALUES(?,'purchase',?,?,?,0)", (no, date, supplier_id, ref_purchase_id)).lastrowid
        total = 0.0
        for it in items:
            qty, price = float(it["qty"]), float(it["price"])
            if qty <= 0 or price < 0:
                raise BusinessError("Invalid quantity or price")
            p = c.execute("SELECT * FROM products WHERE id=?", (it["product_id"],)).fetchone()
            if qty > stock_qty(c, p["id"]):
                raise BusinessError(f"Not enough stock of '{p['name']}' to return")
            if ref_purchase_id:
                left = {x["product_id"]: x["remaining"] for x in returnable_items(c, "purchase", ref_purchase_id)}
                if p["id"] not in left:
                    raise BusinessError(f"'{p['name']}' is not on the selected purchase")
                if qty > left[p["id"]]:
                    raise BusinessError(f"Return quantity of '{p['name']}' is more than bought "
                                        f"(only {left[p['id']]:g} can still be returned)")
            if p["track_serial"]:   # a phone goes back to the supplier: identified by its IMEI, leaves the stock
                if qty != 1:
                    raise BusinessError(f"'{p['name']}': return phones one by one with their IMEI")
                i1, i2 = imei.unit(it.get("serial"), it.get("serial2"), p["imei_mode"])
                row = find_unit(c, p, i1, i2)
                if row["status"] != "in_stock":
                    raise BusinessError(f"This phone (IMEI {row['serial']}) is sold, it cannot be returned "
                                        "to the supplier")
                if ref_purchase_id and row["purchase_id"] != ref_purchase_id:
                    raise BusinessError(f"This phone (IMEI {row['serial']}) is not on the selected purchase")
                c.execute("DELETE FROM serials WHERE id=?", (row["id"],))
            c.execute("INSERT INTO return_items(return_id,product_id,qty,price,unit_cost) VALUES(?,?,?,?,?)",
                      (rid, p["id"], qty, price, p["avg_cost"]))
            c.execute("INSERT INTO stock_moves(product_id,date,qty,unit_cost,ref_type,ref_id) "
                      "VALUES(?,?,?,?,'purchase_return',?)", (p["id"], date, -qty, p["avg_cost"], rid))
            total += qty * price
        total, received = r2(total), r2(received)
        if received < 0 or received > total:
            raise BusinessError("Received amount cannot be more than the return total")
        c.execute("UPDATE returns SET total=?, refunded=?, note=? WHERE id=?", (total, received, note, rid))
        post_ledger(c, supplier_id, date, "purchase_return", rid, debit=total, note=no)
        post_ledger(c, supplier_id, date, "purchase_return", rid, credit=received, note=f"Refund {no}")
        post_cash(c, date, "in", received, "purchase_return", rid, supplier_id, no)
        return rid


__all__ = ["customer_balance", "supplier_balance"]
