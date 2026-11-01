"""Invoice draft: lines + totals, independent of Qt so it can be unit-tested."""
from ..services.common import r2


class InvoiceDraft:
    def __init__(self):
        self.lines = []      # dicts: product_id, name, stock, cost, qty, price, discount, serial
        self.discount = 0.0

    def add_product(self, p, serial=None, serial2=None):
        """Add a product (row from masters.search_products). Same product again => qty + 1,
        except phones which always get their own line (one phone = one line, with its IMEI)."""
        if not p["track_serial"]:
            for ln in self.lines:
                if ln["product_id"] == p["id"]:
                    ln["qty"] += 1
                    return ln
        ln = {"product_id": p["id"], "name": p["name"], "stock": p["stock"], "cost": p["avg_cost"],
              "qty": 1.0, "price": p["sale_price"], "discount": 0.0, "serial": serial,
              "serial2": serial2, "track_serial": bool(p["track_serial"]),
              "imei_mode": p.get("imei_mode", "single")}
        self.lines.append(ln)
        return ln

    @staticmethod
    def line_amount(ln) -> float:
        return r2(ln["qty"] * ln["price"] - ln["discount"])

    def subtotal(self) -> float:
        return r2(sum(self.line_amount(ln) for ln in self.lines))

    def total(self) -> float:
        return r2(self.subtotal() - self.discount)

    def cost(self) -> float:
        return r2(sum(ln["qty"] * ln["cost"] for ln in self.lines))

    def profit(self) -> float:
        """Shown only when the 'Show Profit/Loss' box is ticked; never printed."""
        return r2(self.total() - self.cost())

    def over_stock(self):
        """Lines asking for more than is in stock (to warn the user)."""
        return [ln for ln in self.lines if ln["qty"] > ln["stock"]]

    def service_items(self):
        return [{"product_id": ln["product_id"], "qty": ln["qty"], "price": ln["price"],
                 "discount": ln["discount"], "serial": ln["serial"],
                 "serial2": ln.get("serial2")} for ln in self.lines]

    def imeis_in_use(self):
        return {x for ln in self.lines for x in (ln["serial"], ln.get("serial2")) if x}
