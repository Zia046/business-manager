"""Repair job slip given to the customer (token receipt)."""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..config import SOFTWARE_CONTACT_LINE
from .invoice_pdf import _esc, _fonts


def build_repair_slip(db, repair_id: int, out_path, width_mm: int = 80) -> str:
    r = db.one("SELECT * FROM repairs WHERE id=?", (repair_id,))
    co = db.one("SELECT * FROM company WHERE id=1")
    reg, bold = _fonts()
    margin = 3 * mm
    usable = width_mm * mm - 2 * margin - 12
    s = ParagraphStyle("s", fontName=reg, fontSize=8, leading=10.5)
    c = ParagraphStyle("c", parent=s, alignment=TA_CENTER)
    h = ParagraphStyle("h", parent=c, fontName=bold, fontSize=11, leading=14)
    rows = [("Job No", r["no"]), ("Date", r["date"][:16]), ("Customer", r["customer_name"]),
            ("Phone", r["phone"] or "-"), ("Device", r["device"]), ("IMEI", r["imei"] or "-"),
            ("Problem", r["problem"] or "-"), ("Estimate", f"{r['estimate']:,.0f}"),
            ("Advance paid", f"{r['received']:,.0f}")]
    table = Table([[Paragraph(f"<b>{_esc(a)}</b>", s), Paragraph(_esc(str(b)), s)] for a, b in rows],
                  colWidths=[usable * 0.32, usable * 0.68])
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.grey),
                               ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
    story = [Paragraph(_esc(co["name"]).upper(), h), Paragraph(_esc(f"{co['address']}  Mobile: {co['phone']}"), c),
             Spacer(1, 2 * mm), Paragraph("REPAIR JOB SLIP", h), Spacer(1, 2 * mm), table, Spacer(1, 3 * mm),
             Paragraph("Please bring this slip when you collect the phone. The shop is not responsible for "
                       "data or for phones not collected within 30 days.", c), Spacer(1, 2 * mm),
             Paragraph(_esc(SOFTWARE_CONTACT_LINE), ParagraphStyle("sw", parent=c, fontSize=6, textColor=colors.grey))]
    height = sum(f.wrap(usable, 10000)[1] for f in story) + 2 * margin + 14 * mm
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(out_path), pagesize=(width_mm * mm, max(height, 60 * mm)), leftMargin=margin,
                      rightMargin=margin, topMargin=margin, bottomMargin=margin, title=r["no"]).build(story)
    return str(out_path)
