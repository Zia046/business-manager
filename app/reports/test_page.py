"""Small test receipt for Printer Settings."""
from pathlib import Path

from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from ..config import DEVELOPER_NAME, DEVELOPER_PHONE
from .invoice_pdf import _fonts


def build_test_receipt(data_dir, width_mm: int = 80) -> str:
    reg, bold = _fonts()
    c = ParagraphStyle("c", fontName=reg, fontSize=9, leading=12, alignment=TA_CENTER)
    b = ParagraphStyle("b", parent=c, fontName=bold, fontSize=12, leading=16)
    story = [Paragraph("PRINTER TEST", b), Spacer(1, 2 * mm),
             Paragraph(f"Paper width: {width_mm} mm", c),
             Paragraph("If you can read this clearly,<br/>the printer is set up correctly.", c),
             Spacer(1, 2 * mm), Paragraph("0123456789  ABCDEFGHIJ  abcdefghij", c), Spacer(1, 3 * mm),
             Paragraph(f"{DEVELOPER_NAME}  {DEVELOPER_PHONE}", c)]
    margin = 3 * mm
    h = sum(f.wrap(width_mm * mm - 2 * margin - 12, 10000)[1] for f in story) + 2 * margin + 12 * mm
    out = Path(data_dir) / "invoices" / "printer_test.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(out), pagesize=(width_mm * mm, max(h, 40 * mm)), leftMargin=margin, rightMargin=margin,
                      topMargin=margin, bottomMargin=margin).build(story)
    return str(out)
