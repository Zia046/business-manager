"""Sale invoices, purchases and returns.

Every function runs in ONE database transaction: if anything fails (e.g. not
enough stock) nothing is saved, so stock, ledger and cash book stay in sync.
"""
from .common import (BusinessError, customer_balance, next_no, now, post_cash, post_ledger,
                     r2, stock_qty, supplier_balance, unpost)


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
        if not allow_negative_stock and qty > stock_qty(c, p["id"]):
            raise BusinessError(f"Not enough stock for '{p['name']}' "
                                f"(available {stock_qty(c, p['id']):g})")
        line = r2(qty * price - disc)
        if line < 0:
            raise BusinessError("Line discount is larger than the line amount")
        subtotal += line
        cost_total += qty * p["avg_cost"]
        c.execute("INSERT INTO invoice_items(invoice_id,product_id,qty,price,discount,unit_cost,serial)"
                  " VALUES(?,?,?,?,?,?,?)",
                  (inv_id, p["id"], qty, price, disc, p["avg_cost"], it.get("serial")))
        c.execute("INSERT INTO stock_moves(product_id,date,qty,unit_cost,ref_type,ref_id) "
                  "VALUES(?,?,?,?,'invoice',?)", (p["id"], date, -qty, p["avg_cost"], inv_id))
        if p["track_serial"] and it.get("serial"):
            s = c.execute("SELECT * FROM serials WHERE serial=? AND product_id=?",
                          (it["serial"], p["id"])).fetchone()
            if not s or s["status"] != "in_stock":
                raise BusinessError(f"Serial/IMEI {it['serial']} is not available")
            c.execute("UPDATE serials SET status='sold', invoice_id=? WHERE id=?", (inv_id, s["id"]))
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


def create_invoice(db, party_id, items, discount=0.0, paid=0.0, note="", date=None,
                   allow_negative_stock=False) -> int:
    date = date or now()
    with db.transaction() as c:
        party = c.execute("SELECT * FROM parties WHERE id=? AND kind='customer'", (party_id,)).fetchone()
        if not party:
            raise BusinessError("Customer not found")
        no = next_no(c, "INV")
        inv_id = c.execute("INSERT INTO invoices(no,date,party_id,subtotal,total) VALUES(?,?,?,0,0)",
                           (no, date, party_id)).lastrowid
        _post_invoice(c, inv_id, no, date, party, items, discount, paid, note, allow_negative_stock)
        return inv_id


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
            for sn in it.get("serials", []) if p["track_serial"] else []:
                try:
                    c.execute("INSERT INTO serials(product_id,serial,purchase_id) VALUES(?,?,?)",
                              (p["id"], sn.strip(), pid))
                except Exception:
                    raise BusinessError(f"Serial/IMEI {sn} already exists")
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
