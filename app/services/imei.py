"""IMEI rules for mobile phones.

* digits only, at least 10 and at most 100 digits
* single-IMEI phone: one number; double-IMEI phone: two different numbers
* a number can never exist twice in the stock (checked against IMEI 1 and IMEI 2 of every phone)
"""
import re

from .common import BusinessError

MIN_LEN, MAX_LEN = 10, 100
MODES = ("single", "double")


def clean(text, label="IMEI") -> str:
    t = (text or "").strip()
    if not t:
        raise BusinessError(f"{label} is required")
    if not re.fullmatch(r"[0-9]+", t):
        raise BusinessError(f"{label} must contain numbers only")
    if not (MIN_LEN <= len(t) <= MAX_LEN):
        raise BusinessError(f"{label} must be between {MIN_LEN} and {MAX_LEN} digits (you typed {len(t)})")
    return t


def unit(imei1, imei2, mode):
    """Validate the number(s) of ONE phone. Returns (imei1, imei2 or None)."""
    if mode not in MODES:
        raise BusinessError("Select whether the phone has a single or double IMEI")
    first = clean(imei1, "IMEI 1" if mode == "double" else "IMEI")
    if mode == "double":
        second = clean(imei2, "IMEI 2")
        if first == second:
            raise BusinessError("IMEI 1 and IMEI 2 cannot be the same")
        return first, second
    if (imei2 or "").strip():
        raise BusinessError("This phone has a single IMEI - leave IMEI 2 empty")
    return first, None


def as_unit(raw, mode):
    """Accepts 'imei', ('imei1','imei2') or {'imei1':..,'imei2':..} and validates it."""
    if isinstance(raw, dict):
        return unit(raw.get("imei1"), raw.get("imei2"), mode)
    if isinstance(raw, (tuple, list)):
        return unit(raw[0], raw[1] if len(raw) > 1 else None, mode)
    return unit(raw, None, mode)


def parse_lines(text, mode):
    """Text box -> list of (imei1, imei2). One phone per line; double phones: two numbers per line
    separated by space, comma or tab. Raises BusinessError naming the bad line."""
    units, seen = [], set()
    for n, line in enumerate((text or "").splitlines(), 1):
        if not line.strip():
            continue
        parts = [p for p in re.split(r"[\s,;]+", line.strip()) if p]
        want = 2 if mode == "double" else 1
        if len(parts) != want:
            raise BusinessError(f"Line {n}: type {'two IMEI numbers' if want == 2 else 'one IMEI number'} "
                                f"for each phone")
        try:
            u = unit(parts[0], parts[1] if want == 2 else None, mode)
        except BusinessError as exc:
            raise BusinessError(f"Line {n}: {exc}")
        for x in u:
            if x and x in seen:
                raise BusinessError(f"Line {n}: IMEI {x} is typed twice")
            if x:
                seen.add(x)
        units.append(u)
    return units
