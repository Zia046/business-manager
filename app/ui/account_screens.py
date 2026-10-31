"""Account Transactions: Cash Book, Balance Sheet, Vouchers."""
from PySide6.QtWidgets import QMessageBox

from ..reports import builders
from .payments_ui import PaymentDialog
from .printing import print_voucher
from .report_window import ReportWindow


def open_cash_book(win):
    ReportWindow(win.db, builders.cash_book_report, "Cash Book", parent=win).exec()


def open_balance_sheet(win):
    ReportWindow(win.db, builders.balance_sheet_report, "Balance Sheet", use_dates=False, parent=win).exec()


def open_vouchers(win):
    def print_selected(rw):
        no = rw.selected_first_cell()
        if not no:
            QMessageBox.information(rw, "Select", "Select a voucher row first.")
            return
        try:
            print_voucher(rw.db, no)
        except Exception as exc:
            QMessageBox.warning(rw, "Print", f"Could not print:\n{exc}")

    def new(mode):
        def run(rw):
            PaymentDialog(rw.db, mode, rw).exec()
            rw.reload()
        return run

    ReportWindow(win.db, builders.vouchers_report, "Vouchers", parent=win,
                 actions=[("Print Selected", print_selected), ("New Receipt", new("receive")),
                          ("New Supplier Payment", new("pay_supplier")),
                          ("New Customer Payment", new("pay_customer"))]).exec()
