"""Home-screen icons drawn with Pillow (same look everywhere, testable without Qt)."""
import io

from PIL import Image, ImageDraw

NAVY, WHITE = (20, 40, 110), (255, 255, 255)
S = 4          # supersampling: drawn 4x bigger, then shrunk for smooth edges


def _canvas(size):
    img = Image.new("RGBA", (size * S, size * S), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img), size * S / 100.0      # drawing is done on a 100 x 100 grid


def _fin(img, size):
    return img.resize((size, size), Image.LANCZOS)


def _rr(d, k, box, r, fill=None, outline=None, w=3):
    d.rounded_rectangle([v * k for v in box], r * k, fill=fill, outline=outline, width=int(w * k))


def _poly(d, k, pts, fill):
    d.polygon([(x * k, y * k) for x, y in pts], fill=fill)


def _ell(d, k, box, fill=None, outline=None, w=3):
    d.ellipse([v * k for v in box], fill=fill, outline=outline, width=int(w * k))


def _line(d, k, pts, fill, w):
    d.line([(x * k, y * k) for x, y in pts], fill=fill, width=int(w * k), joint="curve")


def invoice(size=96):
    img, d, k = _canvas(size)
    _rr(d, k, (16, 8, 70, 90), 6, WHITE, NAVY, 4)
    for y in (26, 38, 50, 62):
        _line(d, k, [(26, y), (58 if y < 62 else 46, y)], (70, 120, 200), 4)
    _poly(d, k, [(88, 14), (96, 22), (60, 66), (50, 70), (54, 58)], (37, 99, 235))
    _poly(d, k, [(50, 70), (54, 58), (60, 64)], (250, 190, 90))
    return _fin(img, size)


def cart(size=96):
    img, d, k = _canvas(size)
    g = (46, 140, 50)
    _line(d, k, [(6, 14), (22, 14), (34, 64), (80, 64)], g, 7)
    _poly(d, k, [(26, 26), (92, 26), (84, 54), (34, 54)], (255, 255, 255))
    d.polygon([(26 * k, 26 * k), (92 * k, 26 * k), (84 * k, 54 * k), (34 * k, 54 * k)], outline=g, width=int(5 * k))
    for x in (46, 62, 78):
        _line(d, k, [(x, 30), (x - 2, 50)], g, 3)
    _line(d, k, [(30, 40), (89, 40)], g, 3)
    for x in (42, 72):
        _ell(d, k, (x - 8, 70, x + 8, 86), g)
    return _fin(img, size)


def hand_coins(size=96):
    img, d, k = _canvas(size)
    gold, dark = (250, 200, 60), (190, 130, 20)
    for cx, cy in ((56, 22), (44, 34), (68, 34)):
        _ell(d, k, (cx - 15, cy - 11, cx + 15, cy + 11), gold, dark, 3)
    _ell(d, k, (49, 15, 63, 29), None, dark, 2)
    _rr(d, k, (4, 52, 24, 90), 4, (30, 64, 175))
    _poly(d, k, [(28, 58), (50, 52), (80, 58), (92, 66), (66, 80), (28, 78)], (40, 90, 210))
    _poly(d, k, [(28, 78), (66, 80), (92, 66), (94, 72), (70, 88), (28, 86)], (25, 60, 160))
    return _fin(img, size)


def bars_up(size=96, colors=((20, 40, 130), (20, 40, 130), (20, 40, 130)), arrow=(220, 38, 38)):
    img, d, k = _canvas(size)
    for i, (x, top) in enumerate(((14, 62), (42, 44), (70, 24))):
        _rr(d, k, (x, top, x + 22, 90), 3, colors[i])
    _line(d, k, [(8, 52), (40, 34), (58, 38), (86, 8)], arrow, 7)
    _poly(d, k, [(94, 4), (72, 8), (88, 24)], arrow)
    return _fin(img, size)


def people(size=96):
    img, d, k = _canvas(size)
    b = (30, 90, 200)
    for cx, cy, r, shoulder in ((22, 40, 11, 52), (78, 40, 11, 52), (50, 28, 15, 48)):
        _ell(d, k, (cx - r, cy - r, cx + r, cy + r), b)
        _rr(d, k, (cx - r * 1.7, shoulder + (cy - 28 if cx != 50 else 0) + 6, cx + r * 1.7, 92), 12, b)
    return _fin(img, size)


def clipboard(size=96):
    img, d, k = _canvas(size)
    _rr(d, k, (14, 12, 86, 94), 8, WHITE, NAVY, 5)
    _rr(d, k, (32, 4, 68, 22), 5, NAVY)
    for y in (34, 52, 70):
        _line(d, k, [(24, y), (28, y + 5), (36, y - 5)], (30, 140, 70), 4)
        _line(d, k, [(44, y), (76, y)], (90, 110, 170), 4)
    return _fin(img, size)


def profit(size=96):
    img, d, k = _canvas(size)
    g = (46, 150, 60)
    for x, top in ((8, 62), (26, 46), (44, 30)):
        _rr(d, k, (x, top, x + 14, 90), 2, g)
    _line(d, k, [(6, 44), (30, 26), (46, 30), (66, 8)], g, 6)
    _poly(d, k, [(76, 2), (56, 6), (72, 22)], g)
    for i, y in enumerate((82, 70, 58)):
        _ell(d, k, (62, y - 6, 92, y + 6), (250, 200, 60), (190, 130, 20), 2)
    return _fin(img, size)


def gauge(size=96):
    img, d, k = _canvas(size)
    d.pieslice([8 * k, 14 * k, 92 * k, 98 * k], 180, 240, fill=(34, 160, 90))
    d.pieslice([8 * k, 14 * k, 92 * k, 98 * k], 240, 300, fill=(250, 190, 40))
    d.pieslice([8 * k, 14 * k, 92 * k, 98 * k], 300, 360, fill=(220, 60, 60))
    _ell(d, k, (24, 30, 76, 82), (235, 240, 255))
    _line(d, k, [(50, 62), (68, 38)], NAVY, 6)
    _ell(d, k, (44, 56, 56, 68), NAVY)
    _rr(d, k, (14, 84, 86, 94), 4, NAVY)
    return _fin(img, size)


HOME_ICONS = {"sale_invoice": invoice, "stock_purchase": cart, "cash_received": hand_coins,
              "stock_position": bars_up, "outstanding": people, "sale_summary": clipboard,
              "profit_loss": profit, "dashboard": gauge}


def arrow_circle(color, size=40):
    """White-on-colour round button with a '>' for the right side of each home button."""
    img, d, k = _canvas(size)
    _ell(d, k, (2, 2, 98, 98), color)
    _line(d, k, [(40, 25), (62, 50), (40, 75)], WHITE, 11)
    return _fin(img, size)


# ---- small round icons for the numbers row ----
def _badge(color, symbol, size=48):
    img, d, k = _canvas(size)
    _ell(d, k, (0, 0, 100, 100), color)
    w = WHITE
    if symbol == "cart":
        _line(d, k, [(20, 28), (30, 28), (38, 62), (72, 62)], w, 6)
        _poly(d, k, [(34, 36), (78, 36), (72, 54), (39, 54)], w)
        for x in (44, 66):
            _ell(d, k, (x - 5, 68, x + 5, 78), w)
    elif symbol == "wallet":
        _rr(d, k, (20, 30, 80, 72), 8, w)
        _rr(d, k, (52, 44, 82, 58), 6, color)
        _ell(d, k, (60, 47, 68, 55), w)
    elif symbol == "people":
        for cx, cy, r in ((28, 38, 7), (72, 38, 7)):
            _ell(d, k, (cx - r, cy - r, cx + r, cy + r), w)
            _rr(d, k, (cx - 12, 48, cx + 12, 74), 8, w)
        _ell(d, k, (39, 24, 61, 46), w)
        _rr(d, k, (32, 50, 68, 78), 10, w)
    elif symbol == "box":
        _poly(d, k, [(50, 20), (78, 34), (50, 48), (22, 34)], w)
        _poly(d, k, [(22, 38), (48, 52), (48, 80), (22, 66)], w)
        _poly(d, k, [(78, 38), (52, 52), (52, 80), (78, 66)], w)
    elif symbol == "phone":
        _rr(d, k, (32, 18, 68, 82), 7, w)
        _rr(d, k, (37, 26, 63, 68), 2, color)
        _ell(d, k, (46, 71, 54, 79), color)
    elif symbol == "warn":
        _poly(d, k, [(50, 18), (82, 76), (18, 76)], w)
        _line(d, k, [(50, 38), (50, 58)], color, 7)
        _ell(d, k, (46, 62, 54, 70), color)
    elif symbol == "cloud":
        for x0, y0, x1, y1 in ((22, 44, 50, 72), (38, 28, 68, 64), (56, 42, 82, 72)):
            _ell(d, k, (x0, y0, x1, y1), w)
        _rr(d, k, (36, 56, 70, 72), 4, w)
        _poly(d, k, [(50, 50), (62, 62), (38, 62)], color)
    return _fin(img, size)


BADGES = {"today_sales": ((46, 170, 70), "cart"), "cash": ((37, 99, 235), "wallet"),
          "receivable": ((147, 70, 220), "people"), "low_stock": ((250, 140, 40), "box"),
          "phones_in_stock": ((60, 160, 60), "phone"), "qist_overdue": ((150, 50, 200), "warn"),
          "last_backup": ((40, 150, 230), "cloud")}


def png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def home_icon_png(key: str, size=96) -> bytes:
    return png(HOME_ICONS[key](size))


def badge_png(key: str, size=48) -> bytes:
    color, sym = BADGES[key]
    return png(_badge(color, sym, size))


def arrow_png(color, size=40) -> bytes:
    return png(arrow_circle(color, size))
