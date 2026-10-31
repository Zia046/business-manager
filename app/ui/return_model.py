"""Return draft (Qt-free). Used by both Sale Return and Purchase Return screens."""
from ..services.common import r2


class ReturnDraft:
    def __init__(self, kind):
        self.kind = kind          # 'sale' or 'purchase'
        self.lines = []           # product_id, name, max_qty (None = unlimited/manual), qty, price (None = to type)

    def clear(self):
        self.lines = []

    def load_from_document(self, items):
        """items: rows from trading.returnable_items -> one line each, return qty starts at 0."""
        self.lines = [{"product_id": i["product_id"], "name": i["name"], "max_qty": i["remaining"],
                       "doc_qty": i["sold_qty"], "qty": 0.0, "price": i["price"]} for i in items]

    def add_manual(self, p):
        for ln in self.lines:
            if ln["product_id"] == p["id"]:
                ln["qty"] += 1
                return ln
        price = p["sale_price"] if self.kind == "sale" else None   # supplier price must be typed
        ln = {"product_id": p["id"], "name": p["name"], "max_qty": None, "doc_qty": None, "qty": 1.0, "price": price}
        self.lines.append(ln)
        return ln

    @staticmethod
    def line_amount(ln) -> float:
        return r2(ln["qty"] * (ln["price"] or 0))

    def total(self) -> float:
        return r2(sum(self.line_amount(ln) for ln in self.lines if ln["qty"] > 0))

    def active(self):
        return [ln for ln in self.lines if ln["qty"] > 0]

    def problems(self):
        out = []
        if not self.active():
            out.append("Enter a return quantity for at least one product.")
        for ln in self.active():
            if ln["price"] is None:
                out.append(f"Type the price for {ln['name']}.")
            if ln["max_qty"] is not None and ln["qty"] > ln["max_qty"] + 1e-9:
                out.append(f"{ln['name']}: only {ln['max_qty']:g} can still be returned.")
        return out

    def service_items(self):
        return [{"product_id": ln["product_id"], "qty": ln["qty"], "price": ln["price"]} for ln in self.active()]
