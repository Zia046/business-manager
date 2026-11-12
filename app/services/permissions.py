"""What a staff account may open. The owner may open everything.

Staff can sell, take recoveries, handle customers and returns, and look things up, but cannot see
purchase prices, profit, accounts, other people's logins, backups or the reset option."""

STAFF_ALLOWED = {
    "sale_invoice", "cash_received", "sale_return", "customers", "products", "imei_search", "invoice_print",
    "sale_summary", "outstanding", "customer_transactions", "about", "change_password", "price_list",
    "labels", "qist", "qist_due", "repairs", "dashboard", "low_stock", "license",
}


def can_open(role: str, key: str) -> bool:
    return role == "owner" or key in STAFF_ALLOWED
