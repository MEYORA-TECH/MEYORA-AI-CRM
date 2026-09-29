"""Generate the three Nila concept marks (black, paths only)."""
import math
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

OUT = Path(__file__).parent / "concepts"
F = lambda v: f"{v:.2f}".rstrip("0").rstrip(".")


def svg(w, h, body):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {F(w)} {F(h)}">\n{body}\n</svg>\n'


def path(d, evenodd=False):
    return f'<path{" fill-rule=\"evenodd\"" if evenodd else ""} d="{d}"/>'


def rect(x, y, w, h):
    return f"M{F(x)} {F(y)}H{F(x + w)}V{F(y + h)}H{F(x)}Z"


def circle(cx, cy, r):
    return f"M{F(cx - r)} {F(cy)}A{F(r)} {F(r)} 0 1 0 {F(cx + r)} {F(cy)}A{F(r)} {F(r)} 0 1 0 {F(cx - r)} {F(cy)}Z"


def _sweep(a_from, a_to, a_via):
    two = 2 * math.pi
    fwd = (a_to - a_from) % two
    via = (a_via - a_from) % two
    if via < fwd:
        return 1, fwd
    return 0, two - fwd


def crescent(cx, cy, r, ang_deg, d, r2):
    """Disc (cx,cy,r) minus a disc of radius r2 offset by d toward ang_deg (screen degrees)."""
    a = math.radians(ang_deg)
    ex, ey = cx + d * math.cos(a), cy + d * math.sin(a)
    # circle intersection
    x = (d * d - r2 * r2 + r * r) / (2 * d)
    h = math.sqrt(r * r - x * x)
    mx, my = cx + x * math.cos(a), cy + x * math.sin(a)
    p1 = (mx + h * -math.sin(a), my + h * math.cos(a))
    p2 = (mx - h * -math.sin(a), my - h * math.cos(a))
    ang = lambda p, c: math.atan2(p[1] - c[1], p[0] - c[0])
    s1, dl1 = _sweep(ang(p1, (cx, cy)), ang(p2, (cx, cy)), a + math.pi)
    s2, dl2 = _sweep(ang(p2, (ex, ey)), ang(p1, (ex, ey)), a + math.pi)
    return (f"M{F(p1[0])} {F(p1[1])}A{F(r)} {F(r)} 0 {int(dl1 > math.pi)} {s1} {F(p2[0])} {F(p2[1])}"
            f"A{F(r2)} {F(r2)} 0 {int(dl2 > math.pi)} {s2} {F(p1[0])} {F(p1[1])}Z")


# ---- custom geometric "nila" (baseline 200, x-height 120, stem 26) ----
BASE, XH, ST = 200, 120, 26
TOP = BASE - XH


def letter_n(x0, moon=False):
    r, ri = XH / 2, XH / 2 - ST
    cy = TOP + r
    arch = (f"M{F(x0)} {F(cy)}A{F(r)} {F(r)} 0 0 1 {F(x0 + 2 * r)} {F(cy)}V{BASE}H{F(x0 + 2 * r - ST)}V{F(cy)}"
            f"A{F(ri)} {F(ri)} 0 0 0 {F(x0 + ST)} {F(cy)}Z")
    parts = [path(rect(x0, TOP, ST, XH) + arch)]
    if moon:
        parts.append(path(circle(x0 + r, BASE - 30, 17)))
    return parts, x0 + 2 * r


def letter_i(x0, tittle="dot"):
    parts = [path(rect(x0, TOP, ST, XH))]
    cx = x0 + ST / 2
    if tittle == "dot":
        parts.append(path(circle(cx, TOP - 34, 15)))
    else:
        parts.append(path(crescent(cx + 1, TOP - 38, 25, -45, 12, 19)))
    return parts, x0 + ST


def letter_l(x0):
    return [path(rect(x0, 30, ST, BASE - 30))], x0 + ST


def letter_a(x0):
    r, ri = XH / 2, XH / 2 - ST
    cx, cy = x0 + r, TOP + r
    ring = circle(cx, cy, r) + circle(cx, cy, ri)
    return [path(ring, evenodd=True), path(rect(x0 + 2 * r - ST, TOP, ST, XH))], x0 + 2 * r


def wordmark(x0, n_moon=False, tittle="dot", gap=24):
    parts = []
    p, x = letter_n(x0, n_moon); parts += p
    p, x = letter_i(x + gap, tittle); parts += p
    p, x = letter_l(x + gap); parts += p
    p, x = letter_a(x + gap - 2); parts += p
    return parts, x


# ---- "by Meyora" — Bahnschrift outlines as a concept-stage stand-in (final: Exo 2, OFL) ----
FONT = TTFont(r"C:\Windows\Fonts\bahnschrift.ttf")
GS, CMAP = FONT.getGlyphSet(), FONT.getBestCmap()
UPM = FONT["head"].unitsPerEm


def text_path(s, x, baseline, size, tracking=0.04):
    sc = size / UPM
    pen = SVGPathPen(GS)
    for ch in s:
        g = CMAP[ord(ch)]
        GS[g].draw(TransformPen(pen, (sc, 0, 0, -sc, x, baseline)))
        x += GS[g].width * sc + tracking * size
    return pen.getCommands(), x


def text_width(s, size, tracking=0.04):
    return sum(GS[CMAP[ord(c)]].width for c in s) * size / UPM + tracking * size * len(s)


def endorse(right_x, baseline=252, size=38):
    s = "by Meyora"
    d, _ = text_path(s, right_x - text_width(s, size) + 0.04 * size, baseline, size)
    return path(d)


def write(name, w, h, parts):
    (OUT / name).write_text(svg(w, h, "\n".join(parts)), encoding="utf-8")


# A — Moonrise n: the n is an arch, the full moon rises inside it
R, RI, CY = 100, 64, 128
a = (f"M28 226V{CY}A{R} {R} 0 0 1 228 {CY}V226H192V{CY}A{RI} {RI} 0 0 0 64 {CY}V226Z")
write("a-symbol.svg", 256, 256, [path(a), path(circle(128, 176, 34))])
parts, x = wordmark(0, n_moon=True)
write("a-lockup.svg", x, 256, parts + [endorse(x)])

# B — Insight tittle: the dot of the i is a crescent moon
write("b-symbol.svg", 256, 256, [path(rect(102, 136, 52, 96)), path(crescent(126, 70, 54, -45, 24, 42))])
parts, x = wordmark(0, tittle="moon")
write("b-lockup.svg", x, 256, parts + [endorse(x)])

# C — Reflection: a half moon over the rows it lights (records / pipeline)
c = [path(f"M40 128A88 88 0 0 1 216 128Z"), path(rect(40, 148, 176, 26)), path(rect(84, 194, 88, 26))]
write("c-symbol.svg", 256, 256, c)
wm, wx = wordmark(0)
sc = 256 / 256
off = 256 + 36
g = "\n".join(c) + f'\n<g transform="translate({off} 0)">' + "\n".join(wm) + "</g>"
write("c-lockup.svg", off + wx, 256, [g, f'<g transform="translate({off} 0)">{endorse(wx)}</g>'])
print("ok")
