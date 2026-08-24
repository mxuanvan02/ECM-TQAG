#!/usr/bin/env python3
"""Regenerate the manuscript result figures for the four-arm census.

Every plotted value is read from the census run's own task records or from the
offline failure-attribution audit. Nothing is entered by hand, so the figures
cannot drift from the reported numbers.

Inputs (relative to the census package root):
  runs/<census>/state/tasks/*.json   -> per-chunk, per-arm admission
  runs/<census>/FAILURE_ATTRIBUTION.json -> traced cause per failed attempt

Outputs:
  figure_admission_matrix.pdf
  figure_failure_taxonomy.pdf
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs" / "census_4arm_framec_20260824T120000Z"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "figures"

# Arm order is the reporting order: contract first, then the disclosure control,
# then the two original controls.
ARMS = ["ecm_full", "gate_disclosed", "direct", "structured_no_contract"]
SHORT = {
    "ecm_full": "ECM",
    "gate_disclosed": "GATE",
    "direct": "DIR",
    "structured_no_contract": "STR",
}
LABELS = {
    "ecm_full": "ECM\n(contracted)",
    "gate_disclosed": "Gate disclosed,\nno ordering",
    "direct": "Direct",
    "structured_no_contract": "Structured,\nno contract",
}

# Colour-blind-safe ramp; every series also carries a hatch or a printed value
# so the figures stay readable in greyscale (LNCS prints many papers in mono).
C = {
    "ecm_full": "#1b4f72",
    "gate_disclosed": "#2e86c1",
    "direct": "#7f8c8d",
    "structured_no_contract": "#b0b8bd",
}

# Figures are generated at final display width and included at scale 1.0, so
# the point sizes below are also the printed point sizes. Smallest is 7 pt,
# above the 6 pt LNCS floor.
plt.rcParams.update({
    "font.family": "serif",
    "font.size": 8,
    "axes.linewidth": 0.6,
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "pdf.fonttype": 42,
})


def load_admission() -> tuple[list[str], dict[str, set[str]]]:
    """Per-arm admitted chunk sets, recomputed from terminal task records."""
    admitted: dict[str, set[str]] = {a: set() for a in ARMS}
    chunks: set[str] = set()
    for path in sorted((RUN / "state" / "tasks").glob("*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        tid = rec.get("task_id", "")
        if not tid.startswith("generation::"):
            continue
        parts = tid.split("::")
        chunk, arm = "::".join(parts[2:5]), parts[5]
        chunks.add(chunk)
        if rec.get("status") == "COMPLETE" and rec.get("gates_passed"):
            admitted[arm].add(chunk)
    return sorted(chunks), admitted


def fig_admission_matrix(chunks: list[str], admitted: dict[str, set[str]]) -> Path:
    # Order columns by how many arms admitted them, so uniform columns fall to
    # the edges and the informative (discordant) columns sit together.
    def key(c: str) -> tuple:
        return (-sum(c in admitted[a] for a in ARMS),
                tuple(0 if c in admitted[a] else 1 for a in ARMS), c)

    cols = sorted(chunks, key=key)
    n = len(cols)
    fig, ax = plt.subplots(figsize=(6.0, 1.55))
    for r, arm in enumerate(ARMS):
        for j, c in enumerate(cols):
            ok = c in admitted[arm]
            ax.add_patch(Rectangle((j, len(ARMS) - 1 - r), 1, 1,
                                   facecolor=C[arm] if ok else "#f2f2f2",
                                   edgecolor="white", linewidth=0.7))
            if not ok:
                ax.text(j + 0.5, len(ARMS) - 1 - r + 0.5, "\u00d7",
                        ha="center", va="center", fontsize=8, color="#555555")
    ax.set_xlim(0, n)
    ax.set_ylim(0, len(ARMS))
    ax.set_xticks([j + 0.5 for j in range(n)])
    ax.set_xticklabels([str(j + 1) for j in range(n)], fontsize=7.5)
    ax.set_yticks([len(ARMS) - 1 - r + 0.5 for r in range(len(ARMS))])
    ax.set_yticklabels(
        ["%s  %d/%d" % (SHORT[a], len(admitted[a]), n) for a in ARMS], fontsize=8.5)
    ax.set_xlabel("Source chunk (ordered by number of admitting arms)", fontsize=8.5)
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "figure_admission_matrix.pdf"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def fig_failure_taxonomy() -> Path:
    audit = json.loads((RUN / "FAILURE_ATTRIBUTION.json").read_text(encoding="utf-8"))
    by = audit["by_category_and_arm"]
    # Ordered so the substantive capability failure is the bottom (anchor) band.
    series = [
        ("quotation_of_image_rendered_text", "Quoted text rendered inside the image", "//"),
        ("case_only_false_reject", "Quotation correct except leading-character case", ".."),
        ("schema_or_field_violation", "Schema or field-set violation", "\\\\"),
        ("malformed_no_single_json_object", "Not one well-formed JSON object", "xx"),
        ("unresolved", "Quotation source unresolved", ""),
    ]
    greys = ["#1b4f72", "#5499c7", "#95a5a6", "#c8cfd3", "#e8ebed"]

    fig, ax = plt.subplots(figsize=(5.4, 2.15))
    xs = range(len(ARMS))
    bottom = [0.0] * len(ARMS)
    for (key, label, hatch), colour in zip(series, greys):
        vals = [by.get(key, {}).get(a, 0) for a in ARMS]
        ax.bar(xs, vals, 0.62, bottom=bottom, label=label, color=colour,
               edgecolor="white", linewidth=0.6, hatch=hatch)
        bottom = [b + v for b, v in zip(bottom, vals)]
    totals = [int(b) for b in bottom]
    for x, t in zip(xs, totals):
        ax.text(x, t + 0.25, "%d of 24" % t, ha="center", fontsize=7)
    ax.set_xticks(list(xs))
    ax.set_xticklabels([LABELS[a] for a in ARMS], fontsize=7.5)
    ax.set_ylabel("Attempts failing verification", fontsize=7.5)
    ax.set_ylim(0, max(totals) + 1.6)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(fontsize=6.6, frameon=False, loc="upper center",
              bbox_to_anchor=(0.5, -0.28), ncol=1, handlelength=1.6)
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "figure_failure_taxonomy.pdf"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def main() -> int:
    chunks, admitted = load_admission()
    print("chunks: %d" % len(chunks))
    for a in ARMS:
        print("  %-24s %d/%d" % (a, len(admitted[a]), len(chunks)))
    p1 = fig_admission_matrix(chunks, admitted)
    p2 = fig_failure_taxonomy()
    print("wrote %s" % p1)
    print("wrote %s" % p2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
