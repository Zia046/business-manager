"""Send a PDF straight to a Windows printer (no PDF viewer), using Qt's PDF renderer + printer support."""


def list_printers() -> list[str]:
    try:
        from PySide6.QtPrintSupport import QPrinterInfo
        return list(QPrinterInfo.availablePrinterNames())
    except Exception:
        return []


def direct_print(pdf_path, printer_name=None, dpi=300):
    """Prints every page of the PDF at the PDF's own paper size (A4, A5 or an 80mm/58mm roll).
    printer_name None = Windows default printer. Raises RuntimeError when it cannot print."""
    from PySide6.QtCore import QMarginsF, QSize, QSizeF
    from PySide6.QtGui import QPageLayout, QPageSize, QPainter
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtPrintSupport import QPrinter, QPrinterInfo

    doc = QPdfDocument()
    doc.load(str(pdf_path))
    if doc.pageCount() < 1:
        raise RuntimeError("Could not read the bill PDF")
    name = printer_name or QPrinterInfo.defaultPrinterName()
    if not name or name not in QPrinterInfo.availablePrinterNames():
        raise RuntimeError(f"Printer '{name or 'default'}' was not found. Check Utilities > Printer Settings.")
    printer = QPrinter(QPrinterInfo.printerInfo(name), QPrinter.HighResolution)
    try:
        printer.setResolution(dpi)
    except Exception:
        pass
    painter = QPainter()
    for i in range(doc.pageCount()):
        pts = doc.pagePointSize(i)                               # page size in points (1/72 inch)
        mm = QSizeF(pts.width() * 25.4 / 72, pts.height() * 25.4 / 72)
        layout = QPageLayout(QPageSize(mm, QPageSize.Millimeter), QPageLayout.Portrait,
                             QMarginsF(0, 0, 0, 0), QPageLayout.Millimeter)
        printer.setPageLayout(layout)
        if i == 0:
            if not painter.begin(printer):
                raise RuntimeError("The printer could not be started")
        else:
            printer.newPage()
        rect = printer.pageLayout().paintRectPixels(printer.resolution())
        image = doc.render(i, QSize(rect.width(), rect.height()))
        painter.drawImage(0, 0, image)
    painter.end()
