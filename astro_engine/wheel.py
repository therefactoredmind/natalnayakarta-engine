"""SVG chart wheel. Pure string generation, no dependencies.

Styling: every element has a class (``aw-*``) and all colours are CSS custom properties with
defaults, so the platform restyles the wheel by setting e.g. ``--aw-fire: #e66`` on a parent
element (works for inline SVG) — see docs/ENGINE.md "Wheel styling".
Orientation: Ascendant on the left (9 o'clock), zodiac counter-clockwise, MC up. For charts with
unknown time 0° Aries is on the left and no houses are drawn.
"""
from __future__ import annotations

import math
from html import escape
from typing import Dict, List, Optional

from . import constants as C

VT = "︎"  # text presentation selector: avoid emoji rendering of ♈ etc.

STYLE = """
.aw-root{font-family:var(--aw-font,'DejaVu Sans','Segoe UI Symbol','Noto Sans Symbols','Arial Unicode MS',sans-serif)}
.aw-bg{fill:var(--aw-bg,#ffffff)}
.aw-line{stroke:var(--aw-line,#3a3a4a);fill:none}
.aw-faint{stroke:var(--aw-faint,#c9c9d6);fill:none}
.aw-text{fill:var(--aw-text,#1f1f2e)}
.aw-muted{fill:var(--aw-muted,#77778a)}
.aw-fire{fill:var(--aw-fire,#fde3dc)} .aw-earth{fill:var(--aw-earth,#e6efd9)}
.aw-air{fill:var(--aw-air,#fdf5d6)} .aw-water{fill:var(--aw-water,#dcebf7)}
.aw-glyph-fire{fill:var(--aw-glyph-fire,#c0392b)} .aw-glyph-earth{fill:var(--aw-glyph-earth,#4f7a28)}
.aw-glyph-air{fill:var(--aw-glyph-air,#b7950b)} .aw-glyph-water{fill:var(--aw-glyph-water,#2471a3)}
.aw-planet{fill:var(--aw-planet,#1f1f2e)}
.aw-axis{stroke:var(--aw-axis,#1f1f2e);stroke-width:2}
.aw-asp-conjunction{stroke:var(--aw-asp-conjunction,#8e44ad)}
.aw-asp-opposition{stroke:var(--aw-asp-opposition,#c0392b)}
.aw-asp-square{stroke:var(--aw-asp-square,#e74c3c)}
.aw-asp-trine{stroke:var(--aw-asp-trine,#2e86c1)}
.aw-asp-sextile{stroke:var(--aw-asp-sextile,#27ae60);stroke-dasharray:5 3}
"""


def _spread(lons: List[float], min_sep: float, iters: int = 200) -> List[float]:
    """Displace angles (deg) so neighbours are at least min_sep apart, keeping order and staying close."""
    n = len(lons)
    if n < 2:
        return list(lons)
    min_sep = min(min_sep, 360.0 / n)
    order = sorted(range(n), key=lambda i: lons[i] % 360)
    pos = [lons[i] % 360 for i in order]
    for _ in range(iters):
        moved = False
        for k in range(n):
            gap = pos[k + 1] - pos[k] if k < n - 1 else pos[0] + 360 - pos[-1]
            if gap < min_sep - 1e-6:
                push = (min_sep - gap) / 2
                pos[k] -= push
                if k == n - 1:
                    pos[0] += push
                else:
                    pos[k + 1] += push
                moved = True
        if not moved:
            break
    out = [0.0] * n
    for k, i in enumerate(order):
        out[i] = pos[k] % 360
    return out


def render_wheel(chart: Dict, size: int = 600, aspects: bool = True, title: Optional[str] = None) -> str:
    cx = cy = size / 2
    s = size / 600.0
    R_OUT, R_SIGN, R_PLAN, R_DEG, R_HOUSE_IN, R_ASP = 290 * s, 250 * s, 222 * s, 196 * s, 150 * s, 140 * s
    pts = {p["id"]: p for p in chart["points"]}
    known = bool(chart.get("houses"))
    ref = pts["asc"]["lon"] if known and "asc" in pts else 0.0

    def ang(lon):
        return math.radians(180.0 + (lon - ref))

    def xy(lon, r):
        a = ang(lon)
        return cx + r * math.cos(a), cy - r * math.sin(a)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" class="aw-root" viewBox="0 0 {size} {size}" '
           f'width="{size}" height="{size}" role="img" aria-label="{escape(title or "Натальная карта")}">',
           f"<style>{STYLE}</style>",
           f'<rect class="aw-bg" x="0" y="0" width="{size}" height="{size}"/>']
    # sign ring
    for i, sign in enumerate(C.SIGNS):
        a0, a1 = i * 30.0, (i + 1) * 30.0
        x0, y0 = xy(a0, R_OUT); x1, y1 = xy(a1, R_OUT)
        x2, y2 = xy(a1, R_SIGN); x3, y3 = xy(a0, R_SIGN)
        el = C.SIGN_ELEMENT[sign]
        out.append(f'<path class="aw-{el} aw-sign-sector" data-sign="{sign}" d="M{x0:.2f},{y0:.2f} '
                   f'A{R_OUT:.2f},{R_OUT:.2f} 0 0 0 {x1:.2f},{y1:.2f} L{x2:.2f},{y2:.2f} '
                   f'A{R_SIGN:.2f},{R_SIGN:.2f} 0 0 1 {x3:.2f},{y3:.2f} Z"/>')
        gx, gy = xy(a0 + 15, (R_OUT + R_SIGN) / 2)
        out.append(f'<text class="aw-glyph-{el} aw-sign-glyph" x="{gx:.2f}" y="{gy:.2f}" font-size="{22 * s:.1f}" '
                   f'text-anchor="middle" dominant-baseline="central">{C.SIGN_GLYPH[i]}{VT}<title>{C.SIGNS_RU[i]}</title></text>')
    out.append(f'<circle class="aw-line" cx="{cx}" cy="{cy}" r="{R_OUT:.2f}"/>')
    out.append(f'<circle class="aw-line" cx="{cx}" cy="{cy}" r="{R_SIGN:.2f}"/>')
    out.append(f'<circle class="aw-faint" cx="{cx}" cy="{cy}" r="{R_HOUSE_IN:.2f}"/>')
    # degree ticks
    for d in range(0, 360, 1 if size >= 500 else 5):
        L = (8 if d % 10 == 0 else 5 if d % 5 == 0 else 2.5) * s
        x0, y0 = xy(d, R_SIGN); x1, y1 = xy(d, R_SIGN - L)
        cls = "aw-line" if d % 30 == 0 else "aw-faint"
        out.append(f'<line class="{cls}" x1="{x0:.2f}" y1="{y0:.2f}" x2="{x1:.2f}" y2="{y1:.2f}" stroke-width="{0.8 * s:.2f}"/>')
    # houses
    if known:
        cusps = [h["cusp_lon"] for h in chart["houses"]]
        for i, c in enumerate(cusps):
            axis = i in (0, 3, 6, 9)
            r_end = R_OUT + 6 * s if axis else R_SIGN
            x0, y0 = xy(c, R_HOUSE_IN); x1, y1 = xy(c, r_end)
            out.append(f'<line class="{"aw-axis" if axis else "aw-faint"} aw-cusp" data-house="{i + 1}" x1="{x0:.2f}" '
                       f'y1="{y0:.2f}" x2="{x1:.2f}" y2="{y1:.2f}"/>')
            nxt = cusps[(i + 1) % 12]
            mid = c + ((nxt - c) % 360) / 2
            hx, hy = xy(mid, R_HOUSE_IN + 10 * s)
            out.append(f'<text class="aw-muted aw-house-num" x="{hx:.2f}" y="{hy:.2f}" font-size="{10 * s:.1f}" '
                       f'text-anchor="middle" dominant-baseline="central">{i + 1}</text>')
        for lab, lon in (("ASC", chart["angles"]["asc"]), ("MC", chart["angles"]["mc"]),
                         ("DSC", chart["angles"]["dsc"]), ("IC", chart["angles"]["ic"])):
            lx, ly = xy(lon + 3.5, R_HOUSE_IN + 24 * s)
            out.append(f'<text class="aw-text aw-angle-label" x="{lx:.2f}" y="{ly:.2f}" font-size="{10 * s:.1f}" '
                       f'font-weight="bold" text-anchor="middle" dominant-baseline="central">{lab}</text>')
    # planets (exclude angles)
    body_ids = [p for p in C.PLANETS + C.EXTRA_POINTS if p in pts]
    disp = _spread([pts[p]["lon"] for p in body_ids], 7.0)
    for pid, dl in zip(body_ids, disp):
        p = pts[pid]
        lon = p["lon"]
        x0, y0 = xy(lon, R_SIGN); x1, y1 = xy(lon, R_SIGN - 10 * s)
        out.append(f'<line class="aw-line aw-tick" x1="{x0:.2f}" y1="{y0:.2f}" x2="{x1:.2f}" y2="{y1:.2f}" stroke-width="{1.4 * s:.2f}"/>')
        x2, y2 = xy(dl, R_PLAN + 12 * s)
        out.append(f'<line class="aw-faint aw-leader" x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke-width="{0.8 * s:.2f}"/>')
        gx, gy = xy(dl, R_PLAN)
        tip = f'{p["name_ru"]}: {p["dms"]} {p["sign_ru"]}' + (" ℞" if p["retrograde"] else "")
        out.append(f'<g class="aw-point" data-point="{pid}"><title>{escape(tip)}</title>'
                   f'<text class="aw-planet" x="{gx:.2f}" y="{gy:.2f}" font-size="{19 * s:.1f}" text-anchor="middle" '
                   f'dominant-baseline="central">{C.GLYPH[pid]}{VT}</text>')
        dx, dy = xy(dl, R_DEG)
        deg = int(p["deg_in_sign"])
        label = f'{deg}°' + ("℞" if p["retrograde"] else "")
        out.append(f'<text class="aw-muted aw-deg" x="{dx:.2f}" y="{dy:.2f}" font-size="{9.5 * s:.1f}" text-anchor="middle" '
                   f'dominant-baseline="central">{label}</text></g>')
    # aspects
    if aspects:
        for a in chart.get("aspects", []):
            if a["type"] == "conjunction" or a["a"] not in pts or a["b"] not in pts:
                continue
            if a.get("uncertain"):
                continue
            x0, y0 = xy(pts[a["a"]]["lon"], R_ASP); x1, y1 = xy(pts[a["b"]]["lon"], R_ASP)
            w = max(0.6, 2.2 - 0.25 * a["orb"]) * s
            out.append(f'<line class="aw-asp aw-asp-{a["type"]}" data-a="{a["a"]}" data-b="{a["b"]}" x1="{x0:.2f}" '
                       f'y1="{y0:.2f}" x2="{x1:.2f}" y2="{y1:.2f}" stroke-width="{w:.2f}" opacity="0.85"/>')
    out.append(f'<circle class="aw-faint" cx="{cx}" cy="{cy}" r="{R_ASP:.2f}"/>')
    out.append("</svg>")
    return "\n".join(out)
