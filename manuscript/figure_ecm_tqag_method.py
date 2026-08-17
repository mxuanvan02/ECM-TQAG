#!/usr/bin/env python3
"""Render Fig. 1: ECM-TQAG architecture and data pipeline in one schematic.

Design: a single left-to-right flow with explicit inputs and outputs,
large visible arrowheads, and edge labels placed beside (never on) the
arrows. The architecture side is detailed: the returned evidence tuple
tau(y) is drawn as an explicit four-field object, the four contract
operations are listed under the generator call, the five gate
conditions are listed under the gate, and the bundle E_c is shown
feeding the gate as well as the call. Symbols are kept in sync with
the Method section of main.tex.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import (Circle, Ellipse, FancyArrowPatch,
                                FancyBboxPatch, Polygon, Rectangle)

HERE = Path(__file__).resolve().parent

matplotlib.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 6.5,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "mathtext.fontset": "dejavusans",
})

W, H = 7.16, 3.45
fig = plt.figure(figsize=(W, H), facecolor="white")
ax = fig.add_axes((0.002, 0.004, 0.996, 0.992))
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis("off")

INK = "#1F2A30"
MUTED = "#4C5A63"
ARROW = "#5A6B76"
AMBER = "#B07A00"
TEAL = "#147766"
GRAY = "#8A8A8A"
GREEN = "#3E7A2E"

HW, HH = 0.050, 0.120          # main-row sticker half-size
ROW, TOP = 0.56, 0.87          # main row and top row centres


def sticker(cx, cy, fill, edge, hw=HW, hh=HH, dashed=False):
    w, h = 2 * hw, 2 * hh
    ax.add_patch(FancyBboxPatch(
        (cx - hw + 0.004, cy - hh - 0.010), w, h,
        boxstyle="round,pad=0.0,rounding_size=0.016",
        linewidth=0, facecolor="#D9DEE1", zorder=2))
    ax.add_patch(FancyBboxPatch(
        (cx - hw, cy - hh), w, h,
        boxstyle="round,pad=0.0,rounding_size=0.016",
        linewidth=2.2, edgecolor="white", facecolor=fill, zorder=3))
    ax.add_patch(FancyBboxPatch(
        (cx - hw, cy - hh), w, h,
        boxstyle="round,pad=0.0,rounding_size=0.016",
        linewidth=1.0, edgecolor=edge,
        linestyle=(0, (2.2, 1.6)) if dashed else "solid",
        facecolor="none", zorder=4))


def label(cx, cy, text, sub=None):
    ax.text(cx, cy, text, color=INK, fontsize=6.6, fontweight="bold",
            ha="center", va="top", zorder=8)
    if sub:
        ax.text(cx, cy - 0.050, sub, color=MUTED, fontsize=5.6,
                ha="center", va="top", zorder=8)


def edge(x0, y0, x1, y1, text=None, color=ARROW, dashed=False, lw=1.5,
         side="above", curve=None):
    """Arrow with a big head; optional label offset off the line."""
    kw = dict(arrowstyle="-|>", mutation_scale=13, linewidth=lw,
              color=color, shrinkA=0, shrinkB=0, zorder=5)
    if curve is not None:
        kw["connectionstyle"] = f"arc3,rad={curve}"
    if dashed:
        kw["linestyle"] = (0, (3.0, 2.1))
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), **kw))
    if text:
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        if curve is not None:
            my += -0.055 if curve > 0 else 0.055
        elif side == "above":
            my += 0.028
        elif side == "below":
            my -= 0.028
        else:  # right of a vertical arrow
            mx += 0.012
        ha = "left" if side == "right" else "center"
        va = "center" if side == "right" else (
            "bottom" if (side == "above" or (curve or 0) < 0) else "top")
        ax.text(mx, my, text, color=color, fontsize=5.4, ha=ha, va=va,
                zorder=9, bbox=dict(facecolor="white", edgecolor="none",
                                    pad=0.8, alpha=0.9))


def elbow(pts, color=AMBER, lw=1.1, dashed=True):
    """Right-angle connector through the given points, arrow at the end."""
    for (x0, y0), (x1, y1) in zip(pts[:-2], pts[1:-1]):
        ax.plot([x0, x1], [y0, y1], color=color, linewidth=lw,
                linestyle=(0, (3.0, 2.1)) if dashed else "solid",
                zorder=5)
    (x0, y0), (x1, y1) = pts[-2], pts[-1]
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>",
                                 mutation_scale=11, linewidth=lw,
                                 color=color, shrinkA=0, shrinkB=0,
                                 linestyle=(0, (3.0, 2.1)) if dashed
                                 else "solid", zorder=5))


def panel(cx, top, w, h, title):
    ax.add_patch(FancyBboxPatch(
        (cx - w / 2, top - h), w, h,
        boxstyle="round,pad=0.0,rounding_size=0.012",
        linewidth=0.9, edgecolor="#C4CCD1", facecolor="#FCFCFA",
        zorder=4))
    ax.text(cx, top - 0.038, title, color=INK, fontsize=5.8,
            fontweight="bold", ha="center", va="top", zorder=8)


def chip(cx, cy, text):
    ax.text(cx, cy, text, color=INK, fontsize=4.9, ha="center",
            va="center", zorder=8,
            bbox=dict(facecolor="white", edgecolor=GREEN,
                      boxstyle="round,pad=1.8", linewidth=0.8))


# ------------------------------------------------------------- node centres
CORPUS = (0.055, ROW)
EXTRACT = (0.190, ROW)
BUNDLE = (0.325, ROW)
GEN = (0.505, ROW)
TAU = (0.615, ROW)
GATE = (0.720, ROW)
OUT = (0.900, ROW)
PROMPT = (0.505, TOP)
JUDGE = (0.900, TOP)
THW, THH = 0.028, 0.085        # tau card half-size

# ------------------------------------------------------------- icons
# Scanned corpus: page stack.
sticker(*CORPUS, "#EAF3FB", "#2B6CA3")
sx, sy = CORPUS
for off in (0.010, 0.005, 0.0):
    ax.add_patch(Rectangle((sx - 0.026 + off, sy + 0.008 + off), 0.052,
                           0.096, facecolor="white", edgecolor="#2B6CA3",
                           linewidth=0.8, zorder=5))
ax.add_patch(Rectangle((sx - 0.015, sy + 0.074), 0.030, 0.014,
                       facecolor="#9CC4E4", edgecolor="none", zorder=6))
for yy in (0.052, 0.038, 0.024):
    ax.plot([sx - 0.017, sx + 0.017], [sy + yy, sy + yy],
            color="#7FA6C6", linewidth=0.7, zorder=6)

# Extraction: magnifier over text plus a small crop frame.
sticker(*EXTRACT, "#EAF3FB", "#2B6CA3")
ex, ey = EXTRACT
for yy in (-0.066, -0.046, -0.026):
    ax.plot([ex - 0.030, ex + 0.030], [ey + yy, ey + yy],
            color="#7FA6C6", linewidth=0.8, zorder=5)
ax.add_patch(Ellipse((ex - 0.004, ey + 0.028), 0.050, 0.050,
                     facecolor="#FFFFFFB0", edgecolor="#2B6CA3",
                     linewidth=1.3, zorder=6))
ax.plot([ex + 0.015, ex + 0.033], [ey + 0.008, ey - 0.018],
        color="#2B6CA3", linewidth=1.7, solid_capstyle="round", zorder=6)
ax.add_patch(Rectangle((ex + 0.004, ey - 0.086), 0.030, 0.026,
                       facecolor="white", edgecolor="#2B6CA3",
                       linewidth=0.8, zorder=5))
ax.add_patch(Polygon([(ex + 0.004, ey - 0.086), (ex + 0.016, ey - 0.068),
                      (ex + 0.026, ey - 0.086)],
                     facecolor="#7FB89A", edgecolor="none", zorder=6))

# Bundle: three chips T / L / I.
sticker(*BUNDLE, "#E7F4EF", TEAL)
bx, by = BUNDLE
for k, (ch, col) in enumerate((("T", "#2B6CA3"), ("L", "#7A5CA3"),
                               ("I", AMBER))):
    yy = by + 0.062 - k * 0.054
    ax.add_patch(FancyBboxPatch((bx - 0.036, yy - 0.019), 0.072, 0.040,
                                boxstyle="round,pad=0.0,rounding_size=0.010",
                                facecolor="white", edgecolor=col,
                                linewidth=0.9, zorder=5))
    ax.text(bx - 0.022, yy + 0.001, ch, color=col, fontsize=6.2,
            fontweight="bold", ha="center", va="center", zorder=6)
    ax.plot([bx - 0.008, bx + 0.028], [yy + 0.001, yy + 0.001],
            color="#B9C4C9", linewidth=0.8, zorder=6)

# Arm prompt: chat bubble.
sticker(*PROMPT, "#FDEDF0", "#B0486B", hw=0.048, hh=0.100)
px, py = PROMPT
ax.add_patch(FancyBboxPatch((px - 0.033, py - 0.018), 0.066, 0.076,
                            boxstyle="round,pad=0.0,rounding_size=0.014",
                            facecolor="white", edgecolor="#B0486B",
                            linewidth=1.0, zorder=5))
ax.add_patch(Polygon([(px - 0.012, py - 0.018), (px + 0.002, py - 0.018),
                      (px - 0.012, py - 0.042)],
                     facecolor="white", edgecolor="#B0486B",
                     linewidth=1.0, zorder=5))
for yy in (0.034, 0.017, 0.000):
    ax.plot([px - 0.023, px + 0.023], [py + yy, py + yy],
            color="#D797A8", linewidth=0.9, zorder=6)

# Generator call: robot head.
sticker(*GEN, "#FFF3DC", AMBER)
gx0, gy0 = GEN
ax.add_patch(FancyBboxPatch((gx0 - 0.031, gy0 - 0.046), 0.062, 0.076,
                            boxstyle="round,pad=0.0,rounding_size=0.016",
                            facecolor="white", edgecolor=AMBER,
                            linewidth=1.0, zorder=5))
ax.plot([gx0, gx0], [gy0 + 0.030, gy0 + 0.048], color=AMBER,
        linewidth=0.9, zorder=5)
ax.add_patch(Circle((gx0, gy0 + 0.054), 0.006, facecolor="#F2C14E",
                    edgecolor=AMBER, linewidth=0.6, zorder=6))
ax.add_patch(Circle((gx0 - 0.014, gy0 + 0.000), 0.0062, facecolor=INK,
                    edgecolor="none", zorder=6))
ax.add_patch(Circle((gx0 + 0.014, gy0 + 0.000), 0.0062, facecolor=INK,
                    edgecolor="none", zorder=6))
ax.plot([gx0 - 0.011, gx0 + 0.011], [gy0 - 0.024, gy0 - 0.024],
        color=INK, linewidth=1.0, solid_capstyle="round", zorder=6)

# Evidence tuple card: four fields t / q / alpha / h.
sticker(*TAU, "#FFF9EC", AMBER, hw=THW, hh=THH)
tx, ty = TAU
for k, (ch, col) in enumerate((("t", "#7A5CA3"), ("q", "#2B6CA3"),
                               ("$\\alpha$", GREEN), ("h", AMBER))):
    yy = ty + 0.058 - k * 0.039
    ax.add_patch(FancyBboxPatch((tx - 0.021, yy - 0.014), 0.042, 0.030,
                                boxstyle="round,pad=0.0,rounding_size=0.008",
                                facecolor="white", edgecolor=col,
                                linewidth=0.8, zorder=5))
    ax.text(tx, yy + 0.001, ch, color=col, fontsize=5.4,
            fontweight="bold", ha="center", va="center", zorder=6)

# Gate: shield with check.
sticker(*GATE, "#F0EAFB", "#6A4CA3")
gx, gy = GATE
shield = [(gx, gy + 0.066), (gx + 0.033, gy + 0.048), (gx + 0.033, gy - 0.005),
          (gx, gy - 0.060), (gx - 0.033, gy - 0.005), (gx - 0.033, gy + 0.048)]
ax.add_patch(Polygon(shield, facecolor="white", edgecolor="#6A4CA3",
                     linewidth=1.1, zorder=5))
ax.plot([gx - 0.015, gx - 0.004, gx + 0.017],
        [gy + 0.006, gy - 0.015, gy + 0.028],
        color=GREEN, linewidth=1.6, solid_capstyle="round", zorder=6)

# Output: badge with check.
sticker(*OUT, "#EAF6E6", GREEN, hw=0.042, hh=0.105)
ox, oy = OUT
ax.add_patch(Circle((ox, oy + 0.008), 0.027, facecolor="white",
                    edgecolor=GREEN, linewidth=1.1, zorder=5))
ax.plot([ox - 0.012, ox - 0.003, ox + 0.014],
        [oy + 0.008, oy - 0.005, oy + 0.020],
        color=GREEN, linewidth=1.6, solid_capstyle="round", zorder=6)

# Blind judges: two masked heads, dashed sticker.
sticker(*JUDGE, "#F4F4F4", "#777777", hw=0.048, hh=0.100, dashed=True)
jx, jy = JUDGE
for off in (-0.019, 0.019):
    ax.add_patch(Circle((jx + off, jy + 0.016), 0.013, facecolor="white",
                        edgecolor="#666666", linewidth=0.9, zorder=5))
    ax.add_patch(Ellipse((jx + off, jy - 0.026), 0.046, 0.048,
                         facecolor="white", edgecolor="#666666",
                         linewidth=0.9, zorder=5))
ax.add_patch(Rectangle((jx - 0.035, jy + 0.010), 0.070, 0.012,
                       facecolor="#666666", edgecolor="none", zorder=6))

# ------------------------------------------------------------- labels
label(CORPUS[0], CORPUS[1] - HH - 0.042, "Scanned corpus", "input")
label(EXTRACT[0], EXTRACT[1] - HH - 0.042, "OCR, layout, crops")
label(BUNDLE[0], BUNDLE[1] - HH - 0.042, "Bundle $E_c$")
label(OUT[0], OUT[1] - 0.105 - 0.042, "Admission $A$", "output")
# generator and gate labels sit above their stickers so the detail
# connectors below stay clear
ax.text(GEN[0] + 0.040, GEN[1] + HH + 0.012, "Generator call",
        color=INK, fontsize=6.6, fontweight="bold", ha="left",
        va="bottom", zorder=8)
ax.text(GATE[0], GATE[1] + HH + 0.012, "Gate $G$", color=INK,
        fontsize=6.6, fontweight="bold", ha="center", va="bottom",
        zorder=8)
ax.text(TAU[0], TAU[1] + THH + 0.010, "tuple $\\tau(y)$", color=AMBER,
        fontsize=5.6, fontweight="bold", ha="center", va="bottom",
        zorder=8)
# prompt and judge labels sit left of their stickers so the vertical
# arrows never cross text
ax.text(PROMPT[0] - 0.048 - 0.014, PROMPT[1], "Arm prompt $\\pi_a$",
        color=INK, fontsize=6.6, fontweight="bold", ha="right",
        va="center", zorder=8)
ax.text(JUDGE[0] - 0.048 - 0.014, JUDGE[1] + 0.02, "Blind judges",
        color=INK, fontsize=6.6, fontweight="bold", ha="right",
        va="center", zorder=8)
ax.text(JUDGE[0] - 0.048 - 0.014, JUDGE[1] - 0.032, "exploratory",
        color=MUTED, fontsize=5.6, ha="right", va="center", zorder=8)

# ------------------------------------------------------------- detail panels
PT, PH = 0.272, 0.247          # panel top and height
panel(GEN[0], PT, 0.170, PH, "ECM contract (one call)")
for k, line in enumerate((
        "select $q\\sqsubseteq T_c$, $h\\in\\mathit{I}_c$",
        "plan answer $\\alpha$ first",
        "hold $\\tau$ fixed while writing",
        "self-check the schema")):
    ax.text(GEN[0] - 0.073, PT - 0.078 - k * 0.040, line, color=MUTED,
            fontsize=5.2, ha="left", va="top", zorder=8)

panel(GATE[0], PT, 0.190, PH, "gate $G$: all five hold")
ax.text(GATE[0], PT - 0.095,
        "$t=t_c\\,\\cdot\\,q\\sqsubseteq T_c\\,\\cdot\\,"
        "h\\in\\mathit{I}_c$",
        color=INK, fontsize=5.2, ha="center", va="top", zorder=8)
ax.text(GATE[0], PT - 0.140, "$\\sigma(y)\\,\\cdot\\,\\mu(y)$",
        color=INK, fontsize=5.2, ha="center", va="top", zorder=8)
ax.text(GATE[0], PT - 0.192, "each condition recomputed against $E_c$",
        color=MUTED, fontsize=4.9, ha="center", va="top", zorder=8)

# ------------------------------------------------------------- flow arrows
g = HW + 0.006
edge(CORPUS[0] + g, ROW, EXTRACT[0] - g, ROW, "pages")
edge(EXTRACT[0] + g, ROW, BUNDLE[0] - g, ROW, "$T_c,\\,L_c,\\,\\mathit{I}_c$")
edge(BUNDLE[0] + g, ROW, GEN[0] - g, ROW, "$E_c$")
edge(GEN[0] + g, ROW, TAU[0] - THW - 0.004, ROW, "$\\tau(y)$", color=AMBER)
edge(TAU[0] + THW + 0.004, ROW, GATE[0] - g, ROW)
edge(GATE[0] + g, ROW, OUT[0] - 0.048, ROW, "$A(c,a)$")
edge(PROMPT[0], TOP - 0.100 - 0.006, GEN[0], ROW + HH + 0.006, "$\\pi_a$",
     side="right", color="#B0486B")
edge(OUT[0], OUT[1] + 0.111, JUDGE[0], TOP - 0.100 - 0.006,
     "admitted items", side="right", color=GRAY, dashed=True, lw=1.1)

pdf = HERE / "figure_ecm_tqag_method.pdf"
fig.savefig(pdf, format="pdf", dpi=600, facecolor="white")
print(f"wrote {pdf.name}")

if __import__("os").environ.get("ECM_PREVIEW"):
    fig.savefig(HERE / "_prev_m.png", format="png", dpi=220,
                facecolor="white")
    print("wrote _prev_m.png")
