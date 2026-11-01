"""Purchase draft (Qt-free, testable). Price is never pre-filled: it stays None until typed."""
from ..services.common import r2


class PurchaseDraft:
    def __init__(self):
        self.lines = []  # product_id, name, qty, price (None until typed), serials, track_serial

    def add_product(self, p, serials=None):
        """serials: for phones a list of (imei1, imei2 or None), one per phone; quantity = number of phones."""
        serials = serials or []
        if not p["track_serial"]:
            for ln in self.lines:
                if ln["product_id"] == p["id"]:
                    ln["qty"] += 1
                    return ln
        ln = {"product_id": p["id"], "name": p["name"], "qty": float(len(serials) or 1), "price": None,
              "serials": serials, "track_serial": bool(p["track_serial"]),
              "imei_mode": p.get("imei_mode", "single")}
        self.lines.append(ln)
        return ln

    @staticmethod
    def line_amount(ln) -> float:
        return r2(ln["qty"] * (ln["price"] or 0))

    def total(self) -> float:
        return r2(sum(self.line_amount(ln) for ln in self.lines))

    def missing_prices(self):
        return [ln for ln in self.lines if ln["price"] is None]

    def imeis_in_use(self):
        return {x for ln in self.lines for u in ln["serials"] for x in u if x}

    def serial_mismatch(self):
        """Serial-tracked lines must list exactly one IMEI per piece."""
        return [ln for ln in self.lines if ln["track_serial"] and len(ln["serials"]) != int(ln["qty"])]

    def service_items(self):
        return [{"product_id": ln["product_id"], "qty": ln["qty"], "price": ln["price"],
                 "serials": ln["serials"]} for ln in self.lines]
