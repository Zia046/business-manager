"""All Reports-menu screens, Outstanding, Sale Summary, and Invoice Print (view/edit/cancel)."""
from PySide6.QtWidgets import QMessageBox

from ..reports import builders as B
from ..services import reminders, trading
from ..services.common import BusinessError, is_owner
from .printing import print_invoice
from .report_window import ReportWindow
from .sale_invoice import SaleInvoiceDialog
from .whatsapp import send_whatsapp


def _simple(builder, title, use_dates=True, filter_kind=None):
    return lambda win: ReportWindow(win.db, builder, title, use_dates=use_dates, filter_kind=filter_kind,
                                    parent=win).exec()


def open_invoice_print(win):
    def invoice_id(rw):
        no = rw.selected_first_cell()
        if not no:
            QMessageBox.information(rw, "Select", "Select an invoice row first.")
            return None
        return rw.db.scalar("SELECT id FROM invoices WHERE no=?", (no,), None)

    def do_print(size):
        def run(rw):
            iid = invoice_id(rw)
            if iid:
                try:
                    print_invoice(rw.db, iid, size)
                except Exception as exc:
                    QMessageBox.warning(rw, "Print", f"Could not print:\n{exc}")
        return run

    def edit(rw):
        iid = invoice_id(rw)
        if not iid:
            return
        if rw.db.scalar("SELECT status FROM invoices WHERE id=?", (iid,), "") == "cancelled":
            QMessageBox.information(rw, "Cancelled", "A cancelled invoice cannot be edited.")
            return
        try:
            SaleInvoiceDialog(rw.db, rw, invoice_id=iid).exec()
        except BusinessError as exc:
            QMessageBox.warning(rw, "Edit", str(exc))
        rw.reload()

    def cancel(rw):
        iid = invoice_id(rw)
        if not iid:
            return
        no = rw.selected_first_cell()
        if QMessageBox.question(rw, "Cancel invoice", f"Cancel invoice {no}?\n\nStock will be returned and the "
                                "customer's account and cash book will be corrected.") != QMessageBox.Yes:
            return
        try:
            trading.cancel_invoice(rw.db, iid)
        except BusinessError as exc:
            QMessageBox.warning(rw, "Cancel", str(exc))
        rw.reload()

    actions = [("Print A4", do_print("A4")), ("Print Thermal", do_print("Thermal")), ("View / Edit", edit)]
    if is_owner():
        actions.append(("Cancel Invoice", cancel))          # staff cannot cancel bills
    ReportWindow(win.db, B.invoice_list_report, "Invoice Print", parent=win, actions=actions).exec()


def _party_by_cell(rw, sql):
    value = rw.selected_first_cell()
    if not value:
        QMessageBox.information(rw, "Select", "Select a row first.")
        return None
    return rw.db.scalar(sql, (value,), None)


def open_outstanding(win):
    def remind(rw):
        pid = _party_by_cell(rw, "SELECT id FROM parties WHERE id=? AND kind='customer'")
        if pid:
            phone, text = reminders.balance_message(rw.db, pid)
            send_whatsapp(rw, phone, text)
    ReportWindow(win.db, B.outstanding_report, "Outstanding / Baqayajat", use_dates=False, parent=win,
                 actions=[("WhatsApp Reminder", remind)]).exec()


def open_qist_due(win):
    def remind(rw):
        pid = _party_by_cell(rw, "SELECT party_id FROM installment_plans WHERE no=?")
        if pid:
            phone, text = reminders.qist_message(rw.db, pid)
            send_whatsapp(rw, phone, text)
    ReportWindow(win.db, B.qist_due_report, "Qist Due List", use_dates=False, parent=win,
                 actions=[("WhatsApp Reminder", remind)]).exec()


SCREENS = {
    "customer_transactions": _simple(B.customer_transactions_report, "Customer Transactions", filter_kind="customer"),
    "cash_received_report": _simple(B.cash_received_report, "Cash Received"),
    "profit_loss": _simple(B.profit_loss_report, "Profit & Loss"),
    "invoice_wise": _simple(B.invoice_wise_report, "Invoice Wise Sale Summary"),
    "low_stock": _simple(B.low_stock_report, "Low Stock", use_dates=False),
    "stock_position": _simple(B.stock_position_report, "Stock Position", use_dates=False),
    "product_ledger": _simple(B.product_ledger_report, "Products Ledger", filter_kind="product"),
    "all_balances": _simple(B.all_customer_balance_report, "All Customer Balance", use_dates=False),
    "products_report": _simple(B.products_report, "Products", use_dates=False),
    "outstanding": open_outstanding,
    "qist_due": open_qist_due,
    "price_list": _simple(B.price_list_report, "Price List", use_dates=False),
    "sale_summary": _simple(B.sale_summary_report, "Sale Summary"),
    "invoice_print": open_invoice_print,
    "imei_search": _simple(B.imei_search_report, "IMEI Search / History", use_dates=False, filter_kind="imei"),
    "daily_closing": _simple(B.daily_closing_report, "Daily Closing"),
    "audit_log": _simple(B.audit_log_report, "Audit Log"),
}
