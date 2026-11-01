"""Purchase slip and payment/receipt voucher PDFs (A5/A4 simple layouts)."""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, A5
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..config import SOFTWARE_CONTACT_LINE
from ..services import reports
from .invoice_pdf import ACCENT, _esc, _fonts, _m, _qty


def _styles():
    reg, bold = _fonts()
    mk = lambda n, **k: ParagraphStyle(n, **{"fontName": reg, "fontSize": 10, "leading": 13, **k})
    return reg, bold, mk


def _header(co, mk, bold, width):
    logo = ""
    if co["logo_path"] and Path(co["logo_path"]).exists():
        logo = Image(co["logo_path"], width=20 * mm, height=20 * mm, kind="proportional")
    text = [Paragraph(_esc(co["name"]).upper(), mk("nm", fontName=bold, fontSize=16, leading=19, textColor=ACCENT)),
            Paragraph("<br/>".join(_esc(x) for x in (co["address"], f"Mobile: {co['phone']}", co["email"]) if x),
                      mk("ct", textColor=colors.HexColor("#4b5563")))]
    t = Table([[logo, text]], colWidths=[24 * mm, width - 24 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, 0), 1.2, ACCENT),
                           ("BOTTOMPADDING", (0, 0), (-1, 0), 6)]))
    return t


def _contact(mk):
    return Paragraph(_esc(SOFTWARE_CONTACT_LINE), mk("sw", fontSize=7, alignment=1, textColor=colors.grey))


def build_purchase_pdf(db, purchase_id: int, out_path) -> str:
    d = reports.purchase_detail(db, purchase_id)
    if d is None:
        raise ValueError("Purchase not found")
    reg, bold, mk = _styles()
    pur, party, co = d["purchase"], d["party"], d["company"]
    usable = A4[0] - 32 * mm - 12
    right, hr = mk("r", alignment=TA_RIGHT), mk("hr", fontName=bold, textColor=colors.white, alignment=TA_RIGHT)
    story = [_header(co, mk, bold, usable), Spacer(1, 5 * mm),
             Paragraph("<b>STOCK PURCHASE</b>", mk("t", fontName=bold, fontSize=13, leading=18, textColor=ACCENT)),
             Paragraph(f"Purchase No: <b>{_esc(pur['no'])}</b> &nbsp;&nbsp; Date: {pur['date'][:16]}", mk("m")),
             Paragraph(f"Supplier: <b>{_esc(party['name'])}</b>", mk("m")), Spacer(1, 3 * mm)]
    rows = [[Paragraph("#", mk("h", fontName=bold, textColor=colors.white)),
             Paragraph("Product", mk("h2", fontName=bold, textColor=colors.white)),
             Paragraph("Qty", hr), Paragraph("Price", hr), Paragraph("Amount", hr)]]
    for i, it in enumerate(d["items"], 1):
        rows.append([Paragraph(str(i), mk("c")), Paragraph(_esc(it["product_name"]), mk("c")),
                     Paragraph(_qty(it["qty"]), right), Paragraph(_m(it["price"]), right),
                     Paragraph(_m(it["qty"] * it["price"]), right)])
    t = Table(rows, colWidths=[10 * mm, usable - 10 * mm - 96 * mm, 30 * mm, 30 * mm, 36 * mm],
              repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f8ff")]),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    tot = Table([[Paragraph("Total", mk("a", fontName=bold)), Paragraph(_m(pur["total"]), right)],
                 [Paragraph("Paid", mk("a")), Paragraph(_m(pur["paid"]), right)],
                 [Paragraph("Balance payable", mk("a", fontName=bold)), Paragraph(_m(d["balance_due"]), right)]],
                colWidths=[45 * mm, 35 * mm], hAlign="RIGHT")
    story += [t, Spacer(1, 4 * mm), tot]
    if pur["note"]:
        story += [Spacer(1, 4 * mm), Paragraph(f"<b>Note:</b> {_esc(pur['note'])}", mk("n"))]
    story += [Spacer(1, 8 * mm), _contact(mk)]
    SimpleDocTemplate(str(out_path), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm,
                      bottomMargin=16 * mm, title=pur["no"], author=co["name"]).build(story)
    return str(out_path)


def build_voucher_pdf(db, voucher_no: str, out_path) -> str:
    d = reports.voucher_detail(db, voucher_no)
    if d is None:
        raise ValueError("Voucher not found")
    reg, bold, mk = _styles()
    v, party, co = d["voucher"], d["party"], d["company"]
    usable = A5[0] - 24 * mm - 12
    is_receipt = v["kind"] == "receipt"
    title = "CASH RECEIPT" if is_receipt else "PAYMENT VOUCHER"
    who = ("Received from" if is_receipt else "Paid to")
    rows = [[Paragraph(f"{who}:", mk("a")), Paragraph(f"<b>{_esc(party['name']) if party else '-'}</b>", mk("a"))],
            [Paragraph("Amount:", mk("a")), Paragraph(f"<b>{_m(v['amount'])}</b>", mk("big", fontName=bold, fontSize=14, leading=18))],
            [Paragraph("Note:", mk("a")), Paragraph(_esc(v["note"]) or "-", mk("a"))]]
    t = Table(rows, colWidths=[32 * mm, usable - 32 * mm])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#d0d5dd")),
                           ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    sig = Table([[Paragraph("Receiver's signature", mk("s")), Paragraph("Authorised signature", mk("s", alignment=TA_RIGHT))]],
                colWidths=[usable / 2, usable / 2])
    sig.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, -1), 0.5, colors.black)]))
    story = [_header(co, mk, bold, usable), Spacer(1, 5 * mm),
             Paragraph(f"<b>{title}</b>", mk("t", fontName=bold, fontSize=14, leading=19, textColor=ACCENT)),
             Paragraph(f"Voucher No: <b>{_esc(v['no'])}</b> &nbsp;&nbsp; Date: {v['date'][:16]}", mk("m")),
             Spacer(1, 4 * mm), t, Spacer(1, 18 * mm), sig, Spacer(1, 4 * mm), _contact(mk)]
    SimpleDocTemplate(str(out_path), pagesize=A5, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm,
                      bottomMargin=12 * mm, title=v["no"], author=co["name"]).build(story)
    return str(out_path)
