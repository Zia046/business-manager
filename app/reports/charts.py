"""Charts and the analog clock as pictures (Pillow only), so they look the same everywhere and can be tested."""
import io
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BLUE, GREEN, RED = (27, 110, 243), (34, 160, 90), (214, 69, 65)
INK, MUTED, GRID, PAPER = (31, 41, 55), (107, 114, 128), (225, 231, 240), (255, 255, 255)
_FONTS = ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
          "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
_BOLD = ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


def font(size, bold=False):
    for p in (_BOLD if bold else _FONTS):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    try:
        return ImageFont.load_default(size)
    except TypeError:                                    # very old Pillow
        return ImageFont.load_default()


def short(v: float) -> str:
    """1,250,000 -> 1.25M ; 45,500 -> 45.5k ; 800 -> 800"""
    a = abs(v)
    if a >= 1e6:
        s = f"{a / 1e6:.2f}".rstrip("0").rstrip(".") + "M"
    elif a >= 1e4:
        s = f"{a / 1e3:.1f}".rstrip("0").rstrip(".") + "k"
    else:
        s = f"{a:,.0f}"
    return ("-" if v < 0 else "") + s


def _nice_max(v):
    """Top of the scale: 4 equal steps, each a round number (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8 x 10^n)."""
    if v <= 0:
        return 1
    step = v / 4
    exp = 10 ** math.floor(math.log10(step))
    for m in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if step <= m * exp:
            return 4 * m * exp
    return 40 * exp


def bar_chart(series, title, size=(560, 300), color=BLUE, signed=False, scale=2) -> Image.Image:
    """series: [(label, value)]. signed=True colours gains green and losses red around a zero line."""
    W, H = size[0] * scale, size[1] * scale
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    f_t, f_s, f_v = font(15 * scale, True), font(10 * scale), font(10 * scale, True)
    d.text((14 * scale, 10 * scale), title, fill=INK, font=f_t)
    left, right, top, bottom = 46 * scale, 12 * scale, 44 * scale, 30 * scale
    x0, x1, y0, y1 = left, W - right, top, H - bottom
    vals = [v for _, v in series]
    if signed and any(v < 0 for v in vals):          # symmetric scale, so zero is always a grid line
        hi = _nice_max(max(abs(v) for v in vals))
        lo = -hi
    else:
        hi, lo = _nice_max(max([v for v in vals if v > 0] + [0])), 0
    span = (hi - lo) or 1

    def y_of(v):
        return y1 - (v - lo) / span * (y1 - y0)

    for i in range(5):                                           # grid + y labels
        v = lo + span * i / 4
        y = y_of(v)
        d.line([(x0, y), (x1, y)], fill=GRID, width=scale)
        label = short(v)
        d.text((x0 - 6 * scale - d.textlength(label, font=f_s), y - 6 * scale), label, fill=MUTED, font=f_s)
    n = max(len(series), 1)
    slot = (x1 - x0) / n
    bw = slot * 0.62
    zero = y_of(0)
    if signed:
        d.line([(x0, zero), (x1, zero)], fill=MUTED, width=scale)
    widest = max([d.textlength(lbl, font=f_s) for lbl, _ in series] + [1])
    every = max(1, math.ceil((widest + 6 * scale) / slot))        # show every n-th label when they would collide
    crowded = max([d.textlength(short(v), font=f_v) for _, v in series] + [1]) > slot - 2 * scale
    if crowded:                                                   # smaller numbers, every other one a little higher
        f_v = font(8 * scale, True)
    for i, (label, v) in enumerate(series):
        cx = x0 + slot * (i + 0.5)
        col = (GREEN if v >= 0 else RED) if signed else color
        ya, yb = sorted((y_of(v), zero))
        if v != 0:
            if abs(yb - ya) < 2 * scale:
                ya = yb - 2 * scale
            d.rounded_rectangle([cx - bw / 2, ya, cx + bw / 2, yb], radius=3 * scale, fill=col)
        if v:
            txt = short(v)
            tw = d.textlength(txt, font=f_v)
            lift = 10 * scale if crowded and i % 2 else 0
            ty = ya - 13 * scale - lift if v > 0 else yb + 2 * scale + lift
            d.text((min(max(cx - tw / 2, 2 * scale), W - tw - 2 * scale), ty), txt, fill=INK, font=f_v)
        if (len(series) - 1 - i) % every == 0:                    # always keep the newest period labelled
            lw = d.textlength(label, font=f_s)
            d.text((min(max(cx - lw / 2, 2 * scale), W - lw - 2 * scale), y1 + 8 * scale), label, fill=MUTED,
                   font=f_s)
    return img.resize(size, Image.LANCZOS)


def clock_image(hour, minute, second, size=180) -> Image.Image:
    """Round analog clock."""
    s = 4
    N = size * s
    img = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = N / 2
    d.ellipse([4, 4, N - 4, N - 4], fill=PAPER, outline=BLUE, width=6 * s)
    f = font(int(N * 0.11), True)
    for h in range(1, 13):
        a = math.radians(h * 30 - 90)
        tx, ty = c + math.cos(a) * N * 0.36, c + math.sin(a) * N * 0.36
        w = d.textlength(str(h), font=f)
        d.text((tx - w / 2, ty - N * 0.065), str(h), fill=INK, font=f)
    for m in range(60):
        a = math.radians(m * 6 - 90)
        r1 = N * (0.455 if m % 5 else 0.43)
        d.line([(c + math.cos(a) * r1, c + math.sin(a) * r1), (c + math.cos(a) * N * 0.47, c + math.sin(a) * N * 0.47)],
               fill=MUTED, width=2 * s if m % 5 == 0 else s)

    def hand(angle_deg, length, width, color):
        a = math.radians(angle_deg - 90)
        d.line([(c - math.cos(a) * N * 0.05, c - math.sin(a) * N * 0.05),
                (c + math.cos(a) * N * length, c + math.sin(a) * N * length)], fill=color, width=width)
    hand((hour % 12 + minute / 60) * 30, 0.25, 5 * s, INK)
    hand((minute + second / 60) * 6, 0.35, 3 * s, BLUE)
    hand(second * 6, 0.40, s, RED)
    d.ellipse([c - 5 * s, c - 5 * s, c + 5 * s, c + 5 * s], fill=RED)
    return img.resize((size, size), Image.LANCZOS)


def to_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()
