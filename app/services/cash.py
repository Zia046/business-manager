"""Cash in Hand correction (owner only, with the owner's password).

The cash book is never rewritten: the difference is posted as one 'Cash adjustment' line, so the old
entries stay as they were and the change is visible in the Cash Book and in the Audit Log."""
from . import reports
from .auth import verify_password
from .common import BusinessError, current_login, is_owner, log_audit, now, post_cash, r2


def set_cash_in_hand(db, new_amount, password: str, note: str = "") -> float:
    """Make Cash in Hand equal `new_amount`. Returns the difference that was posted (can be negative)."""
    if not is_owner():
        raise BusinessError("Only the owner can change Cash in Hand")
    try:
        new_amount = r2(float(new_amount))
    except (TypeError, ValueError):
        raise BusinessError("Enter the cash amount as a number")
    if new_amount < 0:
        raise BusinessError("Cash in Hand cannot be negative")
    user = db.one("SELECT * FROM users WHERE login_id=? AND role='owner' AND active=1", (current_login(),))
    if not user or not verify_password(password or "", user["pass_hash"]):
        raise BusinessError("Wrong password")
    old = reports.cash_in_hand(db)
    diff = r2(new_amount - old)
    if diff == 0:
        return 0.0
    with db.transaction() as c:
        post_cash(c, now(), "in" if diff > 0 else "out", abs(diff), "cash_adjust", 0, None,
                  (note or "").strip() or f"Cash in Hand set to {new_amount:,.2f}")
    log_audit(db, "Cash in Hand changed", f"{old:,.2f} -> {new_amount:,.2f}  ({diff:+,.2f})  {(note or '').strip()}")
    return diff
