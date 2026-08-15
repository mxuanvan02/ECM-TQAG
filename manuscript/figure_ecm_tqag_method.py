#!/usr/bin/env python3
"""Render Fig. 1: the ECM-TQAG evidence-contracted generation pipeline.

The figure visualises the method of Section II: a per-chunk conditioning
bundle E_c, an arm-specific prompt pi_a as the sole varying quantity, one
contracted generation call, a deterministic gate G that verifies the returned
evidence tuple against E_c without repair, and blind dual judging that yields
the derived endpoint V(c,a).

Symbols must stay synchronised with the Method section of main.tex.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

HERE = Path(__file__).resolve().parent

matplotlib.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 7.0,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "mathtext.fontset": "dejavusans",
})

W, H = 7.16, 1.56
fig = plt.figure(figsize=(W, H), facecolor="white")
ax = fig.add_axes((0.004, 0.005, 0.992, 0.99))
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis("off")

INK = "#14252D"
MUTED = "#4C5F68"
TEAL = "#147766"
AMBER = "#A26A00"
BLUE = "#176082"
PALE_TEAL = "#EBF6F2"
PALE_AMBER = "#FFF7E2"
PALE_BLUE = "#EAF3F8"
WHITE = "#FFFFFF"

# Five stages across one band, leaving a lower strip for the verification loop.
BOX_Y, BOX_H = 0.395, 0.585
BOX_W = 0.1845
GAP = (1.0 - 0.012 * 2 - 5 * BOX_W) / 4
XS = [0.012 + i * (BOX_W + GAP) for i in range(5)]


def box(x, badge, badge_color, title, lines, edge, fill):
    ax.add_patch(FancyBboxPatch(
        (x, BOX_Y), BOX_W, BOX_H,
        boxstyle="round,pad=0.004,rounding_size=0.013",
        linewidth=1.2, edgecolor=edge, facecolor=fill, zorder=3,
    ))
    by = BOX_Y + BOX_H - 0.088
    ax.add_patch(FancyBboxPatch(
        (x + 0.011, by), 0.027, 0.072,
        boxstyle="round,pad=0.002,rounding_size=0.006",
        linewidth=0, facecolor=badge_color, zorder=4,
    ))
    ax.text(x + 0.0245, by + 0.036, badge, color=WHITE, fontsize=5.7,
            fontweight="bold", ha="center", va="center", zorder=5)
    ax.text(x + 0.047, by + 0.036, title, color=INK, fontsize=6.7,
            fontweight="bold", ha="left", va="center", zorder=5)
    ax.text(x + 0.014, BOX_Y + BOX_H - 0.150, "\n".join(lines), color=MUTED,
            fontsize=5.2, ha="left", va="top", linespacing=1.42, zorder=5)


def harrow(i, color):
    """Plain connector between consecutive stages.

    Stage transitions carry no text: the inter-box gap is far too narrow for a
    legible horizontal label, and rotated labels collided with the box borders.
    The transition semantics are stated in the box bodies instead.
    """
    x0 = XS[i] + BOX_W
    x1 = XS[i + 1]
    y = BOX_Y + BOX_H / 2
    ax.add_patch(FancyArrowPatch(
        (x0 + 0.004, y), (x1 - 0.004, y), arrowstyle="-|>",
        mutation_scale=8.0, linewidth=1.2, color=color,
        shrinkA=0, shrinkB=0, zorder=6,
    ))


box(XS[0], "A", TEAL, "Source chunk $c$",
    ["conditioning bundle",
     "$E_c=(T_c,\\,L_c,\\,\\mathcal{I}_c)$:",
     "recognised text $T_c$,",
     "structure $L_c$, hash-bound",
     "image census $\\mathcal{I}_c$"],
    TEAL, PALE_TEAL)

box(XS[1], "B", TEAL, "Arm prompt $\\pi_a$",
    ["the only quantity that",
     "varies across arms:",
     "ECM contract, direct,",
     "structured no-contract;",
     "$g$, schema, decoding fixed"],
    TEAL, PALE_TEAL)

box(XS[2], "C", AMBER, "Contracted call",
    ["$y=g(\\pi_a,E_c)$, one call:",
     "select quote $q$, image $h$;",
     "plan answer $\\alpha$ first;",
     "hold $\\tau=(t,q,\\alpha,h)$ fixed;",
     "self-check necessity"],
    AMBER, PALE_AMBER)

box(XS[3], "D", AMBER, "Gate $G(y,E_c)$",
    ["verify, never repair:",
     "$q$ verbatim in $T_c$,",
     "$h\\in\\mathcal{I}_c$, type $t$ and",
     "schema exact, MCQ option",
     "equals $\\alpha$"],
    AMBER, PALE_AMBER)

box(XS[4], "E", BLUE, "Blind dual judging",
    ["two masked families,",
     "seven-field object,",
     "no provenance violation",
     "and $\\min(s_1,s_2,s_3)\\geq 3$",
     "$\\Rightarrow$ endpoint $V(c,a)=1$"],
    BLUE, PALE_BLUE)

harrow(0, TEAL)
harrow(1, TEAL)
harrow(2, AMBER)
harrow(3, BLUE)

# Verification loop: the tuple returned in C is checked by D against the
# bundle from A. Drawn as a closed path in the strip below the stages.
LOOP_Y = 0.115
xD = XS[3] + BOX_W / 2
xA = XS[0] + BOX_W / 2
for xx, yy in ((xD, BOX_Y),):
    ax.plot([xx, xx], [yy - 0.004, LOOP_Y], color=AMBER, linewidth=1.1,
            linestyle=(0, (3.6, 2.2)), zorder=5)
ax.plot([xA, xD], [LOOP_Y, LOOP_Y], color=AMBER, linewidth=1.1,
        linestyle=(0, (3.6, 2.2)), zorder=5)
ax.add_patch(FancyArrowPatch(
    (xA, LOOP_Y), (xA, BOX_Y - 0.006), arrowstyle="-|>", mutation_scale=8.0,
    linewidth=1.1, color=AMBER, shrinkA=0, shrinkB=0, zorder=6,
))
ax.text((xA + xD) / 2, LOOP_Y - 0.012,
        "returned tuple $\\tau(y)$ verified against $E_c$; "
        "failure is a terminal outcome retained in the ITT denominator",
        color=AMBER, fontsize=5.0, fontweight="bold", ha="center", va="top",
        bbox=dict(facecolor="white", edgecolor="none", pad=1.0), zorder=7)

pdf = HERE / "figure_ecm_tqag_method.pdf"
fig.savefig(pdf, format="pdf", dpi=600, facecolor="white")
print(f"wrote {pdf.name}")

if __import__("os").environ.get("ECM_PREVIEW"):
    fig.savefig(HERE / "_prev_m.png", format="png", dpi=210, facecolor="white")
    print("wrote _prev_m.png")
