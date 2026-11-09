"""Qt-free helpers for responsive layouts (testable): how many columns fit in a given width."""


def columns_for(width: int, min_item: int, spacing: int = 14, max_cols: int = 4, allowed=None) -> int:
    """Largest number of columns (at most max_cols) so that every item is still at least min_item wide.
    `allowed` limits the choices, e.g. (4, 2, 1) so that 8 buttons never leave one lonely button in a row."""
    fit = max(1, min(max_cols, (int(width) + spacing) // (min_item + spacing)))
    if allowed:
        fit = max([c for c in allowed if c <= fit] or [min(allowed)])
    return fit
