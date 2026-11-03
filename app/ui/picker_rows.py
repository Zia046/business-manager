"""Rows of the 'Select from list' window (Qt-free so they can be tested)."""
def money(x) -> str:
    return f"{x:,.2f}"


def picker_columns(owner: bool):
    """Staff never see what a product cost; the owner sees the last purchase price and the average cost."""
    cols = ["ID", "Product", "Category", "In stock", "Sale price"]
    return cols + (["Last purchase price", "Average cost"] if owner else [])


def picker_row(p, owner: bool):
    row = [str(p["id"]), p["name"], p.get("category") or "", f"{p['stock']:g}", money(p["sale_price"])]
    if owner:
        row += [money(p.get("last_purchase_price") or 0), money(p.get("avg_cost") or 0)]
    return row
