"""Final Nila by Meyora masters (concept B, approved: light logo + paper app icon)."""
import math
from pathlib import Path

import build_concepts as bc

OUT = Path(__file__).parent / "final"
INK, ICE, INK3, PAPER = "#101317", "#5e8ca8", "#6b7480", "#f7f8f9"
D_TEXT, D_ICE, D_MUTED = "#e9edf1", "#7aa6c2", "#aab3bd"
F = bc.F


def svg(w, h, title, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {F(w)} {F(h)}">\n<title>{title}</title>\n'
            f"{body}\n</svg>\n")


def fill(p, c):
    return p.replace("<path", f'<path fill="{c}"', 1)


def write(name, w, h, title, parts):
    (OUT / name).write_text(svg(w, h, title, "\n".join(parts)), encoding="utf-8")


def crescent_bbox(cx, cy, r, ang, d, r2):
    a = math.radians(ang)
    ex, ey = cx + d * math.cos(a), cy + d * math.sin(a)
    pts = [(cx + r * math.cos(t / 720 * 2 * math.pi), cy + r * math.sin(t / 720 * 2 * math.pi)) for t in range(720)]
    pts = [p for p in pts if math.hypot(p[0] - ex, p[1] - ey) >= r2]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


# Symbol: the crescent-dotted i
STEM = bc.path(bc.rect(102, 136, 52, 96))
MOON = bc.path(bc.crescent(126, 70, 54, -45, 24, 42))
write("nila-symbol.svg", 256, 256, "Nila", [STEM, MOON])
write("nila-symbol-colour.svg", 256, 256, "Nila", [fill(STEM, INK), fill(MOON, ICE)])

# Small-size cut: the crescent alone, centred on its own bounding box, slightly above centre
R = 104
k = R / 54
x0, y0, x1, y1 = crescent_bbox(0, 0, R, -45, 24 * k, 42 * k)
cx, cy = 128 - (x0 + x1) / 2, 124 - (y0 + y1) / 2
SMALL = bc.path(bc.crescent(cx, cy, R, -45, 24 * k, 42 * k))
write("nila-symbol-small.svg", 256, 256, "Nila", [SMALL])
write("nila-symbol-small-colour.svg", 256, 256, "Nila", [fill(SMALL, ICE)])

# Wordmark and lockup
WM, WX = bc.wordmark(0, tittle="moon")
ENDORSE = bc.endorse(WX)


def colour(parts, word, moon):
    return [fill(p, moon if i == 2 else word) for i, p in enumerate(parts)]


write("nila-wordmark.svg", WX, 256, "Nila", colour(WM, INK, ICE))
write("nila-wordmark-dark.svg", WX, 256, "Nila", colour(WM, D_TEXT, D_ICE))
write("nila-lockup.svg", WX, 256, "Nila by Meyora", colour(WM, INK, ICE) + [fill(ENDORSE, INK3)])
write("nila-lockup-dark.svg", WX, 256, "Nila by Meyora", colour(WM, D_TEXT, D_ICE) + [fill(ENDORSE, D_MUTED)])
write("nila-lockup-black.svg", WX, 256, "Nila by Meyora", WM + [ENDORSE])
print("final ok", F(WX))
