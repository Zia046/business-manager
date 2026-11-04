"""Price/barcode labels. Two layouts:
   'sheet'  : A4 sheet of sticker labels (3 columns x 7 rows, 70 x 38 mm)
   'roll'   : one label per page on a label printer roll (default 50 x 30 mm)
   'grid'   : A4 page with N labels per page; the rows/columns are worked out from N automatically"""
import math
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from ..services.masters import barcode_for
from .invoice_pdf import _fonts

SHEET = dict(cols=3, rows=7, w=70 * mm, h=38 * mm)


def _fit(c, text, font, size, width):
    while size > 5 and c.stringWidth(text, font, size) > width:
        size -= 0.5
    return size


def grid_layout(n: int, page=A4, margin=8 * mm):
    """Rows x columns for n labels on one page: as few empty places as possible, labels not too tall or thin.
    Returns (cols, rows, label_w, label_h)."""
    n = max(1, min(int(n), 84))
    uw, uh = page[0] - 2 * margin, page[1] - 2 * margin
    best = None
    for cols in range(1, 7):
        for rows in range(1, 15):
            if cols * rows < n:
                continue
            fw, fh = uw / cols, uh / rows                      # room each label has on the page
            w, h = min(fw, 90 * mm), min(fh, 50 * mm)          # but a label is never drawn bigger than this
            if w < 28 * mm or h < 15 * mm:
                continue
            score = ((cols * rows - n) * 3, abs(math.log((fw / fh) / 1.9)))
            if best is None or score < best[0]:
                best = (score, cols, rows, w, h)
    if best is None:
        raise ValueError("Too many labels for one page")
    return best[1:]


def _label(c, x, y, w, h, shop, product, price):
    reg, bold = _fonts()
    pad = 2.5 * mm
    from reportlab.graphics.barcode import code128          # imported here: the program starts even if it is missing
    if h < 26 * mm:                                  # small label: name + price on one line, bars below
        code = barcode_for(product)
        pr = f"Rs. {price:,.0f}"
        c.setFont(bold, 9)
        pw = c.stringWidth(pr, bold, 9)
        size = _fit(c, product["name"], bold, 8, w - 2 * pad - pw - 2 * mm)
        c.setFont(bold, size)
        c.drawString(x + pad, y + h - 4.2 * mm, product["name"])
        c.setFont(bold, 9)
        c.drawRightString(x + w - pad, y + h - 4.2 * mm, pr)
        bc = code128.Code128(code, barHeight=max(h - 13 * mm, 4 * mm), barWidth=0.33 * mm, humanReadable=False)
        scale = min(1.0, (w - 2 * pad) / bc.width)
        c.saveState()
        c.translate(x + (w - bc.width * scale) / 2, y + 4.5 * mm)
        c.scale(scale, 1)
        bc.drawOn(c, 0, 0)
        c.restoreState()
        c.setFont(reg, 6.5)
        c.drawCentredString(x + w / 2, y + 1.6 * mm, code)
        return
    c.setFont(reg, 6.5)
    c.drawCentredString(x + w / 2, y + h - 4 * mm, shop[:40])
    name = product["name"]
    size = _fit(c, name, bold, 9, w - 2 * pad)
    c.setFont(bold, size)
    c.drawCentredString(x + w / 2, y + h - 8.5 * mm, name)
    c.setFont(bold, 13)
    c.drawCentredString(x + w / 2, y + h - 14 * mm, f"Rs. {price:,.0f}")
    from reportlab.graphics.barcode import code128
    code = barcode_for(product)
    bc = code128.Code128(code, barHeight=h - 24 * mm if h > 28 * mm else 8 * mm, barWidth=0.33 * mm,
                         humanReadable=False)
    scale = min(1.0, (w - 2 * pad) / bc.width)
    c.saveState()
    c.translate(x + (w - bc.width * scale) / 2, y + 5.5 * mm)
    c.scale(scale, 1)
    bc.drawOn(c, 0, 0)
    c.restoreState()
    c.setFont(reg, 6.5)
    c.drawCentredString(x + w / 2, y + 2 * mm, code)


def build_labels_pdf(db, items, out_path, layout="sheet", roll_mm=(50, 30), per_page=None) -> str:
    """items: [(product_id, copies)]. Returns the PDF path."""
    shop = db.scalar("SELECT name FROM company WHERE id=1", (), "")
    labels = []
    for pid, copies in items:
        p = db.one("SELECT * FROM products WHERE id=?", (pid,))
        if p:
            labels += [p] * max(int(copies), 0)
    if not labels:
        raise ValueError("Choose at least one product")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    if layout == "roll":
        w, h = roll_mm[0] * mm, roll_mm[1] * mm
        c = canvas.Canvas(str(out_path), pagesize=(w, h))
        for p in labels:
            _label(c, 0, 0, w, h, shop, p, p["sale_price"])
            c.showPage()
    else:
        c = canvas.Canvas(str(out_path), pagesize=A4)
        if layout == "grid":
            cols, rows, lw, lh = grid_layout(per_page or 21)
            per_page = int(per_page or 21)
        else:
            cols, rows, lw, lh = SHEET["cols"], SHEET["rows"], SHEET["w"], SHEET["h"]
            per_page = cols * rows
        left = (A4[0] - cols * lw) / 2
        top = (A4[1] - rows * lh) / 2 + rows * lh if layout != "grid" else A4[1] - 8 * mm
        for i, p in enumerate(labels):
            k = i % per_page
            col, row = k % cols, k // cols
            x, y = left + col * lw, top - (row + 1) * lh
            c.setStrokeGray(0.8)
            c.rect(x, y, lw, lh)
            _label(c, x, y, lw, lh, shop, p, p["sale_price"])
            if k == per_page - 1 and i != len(labels) - 1:
                c.showPage()
        c.showPage()
    c.save()
    return str(out_path)
