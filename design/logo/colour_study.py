"""Concept B in the app's own palette (from frontend/src/index.css)."""
import re
from pathlib import Path

HERE = Path(__file__).parent
INK, PAPER, ICE, FROST, INK3 = "#101317", "#f7f8f9", "#5e8ca8", "#9aafbd", "#6b7480"
D_INK, D_TEXT, D_ICE, D_MUTED = "#101317", "#e9edf1", "#7aa6c2", "#aab3bd"


def paths(name):
    s = (HERE / "concepts" / name).read_text(encoding="utf-8")
    w, h = map(float, re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', s).groups())
    return re.findall(r"<path[^>]*/>", s), w, h


def fill(p, c):
    return p.replace("<path", f'<path fill="{c}"', 1)


LOCK, LW, LH = paths("b-lockup.svg")   # n, i, tittle, l, a-ring, a-stem, by Meyora
SYM, _, _ = paths("b-symbol.svg")      # stem, crescent


def lockup(x, y, s, word, moon, sub):
    cols = [word, word, moon, word, word, word, sub]
    body = "".join(fill(p, c) for p, c in zip(LOCK, cols))
    return f'<g transform="translate({x} {y}) scale({s})">{body}</g>'


def tile(x, y, size, bg, stem, moon, radius=0.22, small=False):
    r = size * radius
    t = f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="{r:.1f}" fill="{bg}"/>'
    if small:  # small-size cut: the crescent alone, big
        s = size / 256 * 1.75
        cx, cy = 117, 80
        inner = fill(SYM[1], moon)
        return t + f'<g transform="translate({x + size/2 - cx*s:.2f} {y + size/2 - cy*s:.2f}) scale({s:.4f})">{inner}</g>'
    s = size / 256 * 0.78
    off = size * 0.11
    inner = fill(SYM[0], stem) + fill(SYM[1], moon)
    return t + f'<g transform="translate({x + off:.2f} {y + off:.2f}) scale({s:.4f})">{inner}</g>'


def label(x, y, text, c="#6b7480", size=15, weight=500):
    return f'<text x="{x}" y="{y}" font-family="Inter, Segoe UI, sans-serif" font-size="{size}" font-weight="{weight}" fill="{c}">{text}</text>'


W, H = 1600, 1060
out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
       f'<rect width="{W}" height="{H}" fill="#eceff2"/>',
       label(60, 70, "Nila by Meyora · concept B in the app palette", INK, 30, 700),
       label(60, 102, "Graphite ink #101317 · Ice #5e8ca8 (dark mode #7aa6c2) · Paper #f7f8f9 · the same tokens the app already uses")]
# light + dark lockups
out.append(f'<rect x="60" y="136" width="720" height="380" rx="24" fill="{PAPER}"/>')
out.append(lockup(60 + (720 - LW * 1.05) / 2, 136 + 28, 1.05, INK, ICE, INK3))
out.append(label(84, 500, "Light: ink letters, ice crescent", INK3, 14))
out.append(f'<rect x="820" y="136" width="720" height="380" rx="24" fill="{D_INK}"/>')
out.append(lockup(820 + (720 - LW * 1.05) / 2, 136 + 28, 1.05, D_TEXT, D_ICE, D_MUTED))
out.append(label(844, 500, "Dark: paper letters, bright ice crescent", D_MUTED, 14))
# one-colour versions
out.append(f'<rect x="60" y="540" width="720" height="220" rx="24" fill="{ICE}"/>')
out.append(lockup(60 + (720 - LW * 0.62) / 2, 540 + 14, 0.62, "#ffffff", "#ffffff", "#ffffff"))
out.append(label(84, 742, "Reversed, one colour on ice", "#e9f0f5", 14))
out.append(f'<rect x="820" y="540" width="720" height="220" rx="24" fill="#ffffff"/>')
out.append(lockup(820 + (720 - LW * 0.62) / 2, 540 + 14, 0.62, ICE, ICE, ICE))
out.append(label(844, 742, "One colour ice (print, stamps, embroidery)", INK3, 14))
# app icons + favicons
out.append(f'<rect x="60" y="784" width="1480" height="236" rx="24" fill="{PAPER}"/>')
x = 100
for bg, stem, moon, name in [(INK, D_TEXT, D_ICE, "App icon · ink"), (ICE, "#ffffff", "#ffffff", "App icon · ice"),
                              ("#ffffff", INK, ICE, "App icon · paper")]:
    out.append(tile(x, 816, 150, bg, stem, moon))
    out.append(label(x, 996, name, INK3, 13))
    x += 200
x += 40
out.append(label(x, 836, "Favicon (small-size cut: crescent only)", INK3, 13))
for size in (64, 32, 16):
    out.append(tile(x, 870 + (64 - size), size, INK, D_TEXT, D_ICE, small=True))
    out.append(label(x, 960, f"{size}px", INK3, 12))
    x += size + 36
x += 30
for size in (64, 32, 16):
    out.append(tile(x, 870 + (64 - size), size, ICE, "#fff", "#ffffff", small=True))
    out.append(label(x, 960, f"{size}px", INK3, 12))
    x += size + 36
out.append("</svg>")
(HERE / "concept-b-colour.svg").write_text("\n".join(out), encoding="utf-8")
print("ok")
