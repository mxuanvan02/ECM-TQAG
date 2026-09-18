#!/usr/bin/env python3
"""Regenerate the manuscript result figures for the reported census.

Every plotted cell is recomputed from the published decision records, so the
figure cannot drift from the reported numbers and no unpublished run tree is
needed. The conventions are carried over unchanged from the frame-C figure
builder: colour-blind-safe ramp, a printed count on every row, Type-42 fonts.

WHAT IS PLOTTED, AND WHY IT IS A2 AND NOT A
  The primary endpoint is admission: the five provenance conditions AND G6/G7/G8.
  The provenance-only quantity A_P is reported too, but it separates the arms
  poorly at this frame size, so the matrix that carries the paper's claim is the
  A2 matrix.

Input (repo layout, relative to the experiment root, i.e. one level above this
script's directory):
  records/admission_decisions.json

  When this script ships inside the submission package, set ECM_RECORDS to
  the absolute path of that file in a clone of branch experiments/census-5arm.
  Each row carries: chunk_id, arm, admitted (all eight conditions),
  provenance_admitted (the five provenance conditions), failed_conditions.
  That is sufficient for both figures: the three cell states of Fig. 1 follow
  from admitted / provenance_admitted, and the per-gate rejection counts of
  Fig. 2 follow from failed_conditions.

Outputs (written next to main.tex by default, or to argv[1]):
  figure_admission.pdf
  figure_conditions.pdf
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

HERE = Path(__file__).resolve().parent
# Repo layout: experiments/census_5arm_framef/{figures/,records/}, so records/
# sits one level above this script's directory. When the script is shipped
# inside the submission package instead, point ECM_RECORDS at the file in a
# clone of branch experiments/census-5arm.
_CANDIDATES = [
    Path(os.environ["ECM_RECORDS"]) if os.environ.get("ECM_RECORDS") else None,
    HERE.parent / "records" / "admission_decisions.json",
    Path.cwd() / "records" / "admission_decisions.json",
]
RECORDS = next((p for p in _CANDIDATES if p and p.exists()), _CANDIDATES[1])
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent

G6 = "g6_answer_not_in_quote"

# Reporting order: the contract first, then its length-matched disclosure control,
# then the provenance-only arm, then the two unconstrained controls.
ARMS = ["ecm_v2", "ecm_v2_disclosed", "ecm_full", "direct", "structured_no_contract"]
SHORT = {
    "ecm_v2": "ECM",
    "ecm_v2_disclosed": "DISC",
    "ecm_full": "PROV",
    "direct": "DIR",
    "structured_no_contract": "STR",
}
LABELS = {
    "ecm_v2": "ECM\n(full contract)",
    "ecm_v2_disclosed": "Gates disclosed,\nno ordering",
    "ecm_full": "PROV\n(provenance only)",
    "direct": "Direct",
    "structured_no_contract": "Structured,\nno contract",
}
C = {
    "ecm_v2": "#1b4f72",
    "ecm_v2_disclosed": "#2e86c1",
    "ecm_full": "#5499c7",
    "direct": "#7f8c8d",
    "structured_no_contract": "#b0b8bd",
}

plt.rcParams.update({
    "font.family": "serif",
    "font.size": 8,
    "axes.linewidth": 0.6,
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "pdf.fonttype": 42,
})


def load_rows() -> list[dict]:
    """Read the published decision records."""
    blob = json.loads(RECORDS.read_text(encoding="utf-8"))
    rows = blob["rows"]
    return list(rows.values()) if isinstance(rows, dict) else list(rows)


def load_v1_admission(rows) -> tuple[list[str], dict[str, set[str]]]:
    """Per-arm provenance-admitted chunk sets (the five provenance conditions)."""
    admitted: dict[str, set[str]] = {a: set() for a in ARMS}
    chunks: set[str] = set()
    for rec in rows:
        arm = rec.get("arm")
        if arm not in admitted:
            continue
        chunk = rec["chunk_id"]
        chunks.add(chunk)
        if rec.get("provenance_admitted"):
            admitted[arm].add(chunk)
    return sorted(chunks), admitted


def load_a2(rows) -> tuple[dict[str, set[str]], dict[str, dict[str, int]]]:
    """A2 pass sets and per-gate failure counts, from the same records."""
    a2: dict[str, set[str]] = {a: set() for a in ARMS}
    failures: dict[str, dict[str, int]] = {a: {} for a in ARMS}
    for rec in rows:
        arm = rec.get("arm")
        if arm not in a2:
            continue
        chunk = rec["chunk_id"]
        if rec.get("admitted"):
            a2[arm].add(chunk)
        for gate in rec.get("failed_conditions") or []:
            failures[arm][gate] = failures[arm].get(gate, 0) + 1
    return a2, failures


def fig_admission_matrix(chunks: list[str], a2: dict[str, set[str]],
                  v1: dict[str, set[str]]) -> Path:
    """A2 per chunk and arm. Three states, because two failure modes differ.

    A cell is filled when A2 holds; marked with a middle dot when the item was
    provenance-admitted but failed a division-of-labour condition; and marked
    with a cross when provenance admission itself failed.
    """
    def key(c: str) -> tuple:
        return (-sum(c in a2[a] for a in ARMS),
                tuple(0 if c in a2[a] else 1 for a in ARMS), c)

    cols = sorted(chunks, key=key)
    n = len(cols)
    fig, ax = plt.subplots(figsize=(6.6, 1.45))
    for r, arm in enumerate(ARMS):
        y = len(ARMS) - 1 - r
        for j, c in enumerate(cols):
            passed = c in a2[arm]
            v1_ok = c in v1[arm]
            face = C[arm] if passed else ("#e4e7e9" if v1_ok else "#f7f7f7")
            ax.add_patch(Rectangle((j, y), 1, 1, facecolor=face,
                                   edgecolor="white", linewidth=0.35))
            if not passed:
                mark = "\u00b7" if v1_ok else "\u00d7"
                # 8pt, not 5.5: the figure is embedded at \textwidth, a scale of
                # 0.787, and 5.5pt measured 4.34pt on the built page -- below the
                # 6pt legibility floor that the TikZ geometry gate (G5) enforces.
                # 8pt renders at 6.29pt. Cells are ~7.3pt wide, so the glyph still
                # fits without touching its neighbours.
                size = 9 if v1_ok else 8.0
                ax.text(j + 0.5, y + 0.5, mark, ha="center", va="center",
                        fontsize=size, color="#555555")
    ax.set_xlim(0, n)
    ax.set_ylim(0, len(ARMS))
    ax.set_xticks([0.5, n - 0.5])
    # 8pt, not 7.5: at the 0.787 embedding scale 7.5pt measured 5.90pt on the
    # built page, under the 6pt floor. Every font in this figure must be at
    # least 6.0/0.787 = 7.63pt standalone.
    ax.set_xticklabels(["1", str(n)], fontsize=8)
    ax.set_yticks([len(ARMS) - 1 - r + 0.5 for r in range(len(ARMS))])
    ax.set_yticklabels(
        ["%s  %d/%d" % (SHORT[a], len(a2[a]), n) for a in ARMS], fontsize=8)
    ax.set_xlabel("Source chunk (ordered by number of admitting arms)",
                  fontsize=8.5)
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "figure_admission.pdf"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def fig_condition_structure(a2: dict[str, set[str]],
                       failures: dict[str, dict[str, int]]) -> Path:
    """Which gate rejects, per arm. G6 is the load-bearing gate, so it is first."""
    series = [
        (G6, "$G_6$: answer lies inside the quotation", "//"),
        ("g7_answer_meets_figure", "$G_7$: answer absent from figure lettering", ".."),
        ("g8_description_meets_figure", "$G_8$: description absent from lettering", "\\\\"),
    ]
    greys = ["#1b4f72", "#7f9db5", "#c8cfd3"]

    fig, ax = plt.subplots(figsize=(5.4, 2.25))
    xs = range(len(ARMS))
    bottom = [0.0] * len(ARMS)
    for (key, label, hatch), colour in zip(series, greys):
        vals = [failures[a].get(key, 0) for a in ARMS]
        ax.bar(xs, vals, 0.62, bottom=bottom, label=label, color=colour,
               edgecolor="white", linewidth=0.6, hatch=hatch)
        bottom = [b + v for b, v in zip(bottom, vals)]
    for x, arm in zip(xs, ARMS):
        ax.text(x, bottom[x] + 0.6, "admitted %d/60" % len(a2[arm]),
                ha="center", fontsize=7)
    ax.set_xticks(list(xs))
    ax.set_xticklabels([LABELS[a] for a in ARMS], fontsize=7)
    ax.set_ylabel("Gate rejections among provenance-admitted items", fontsize=7.5)
    ax.set_ylim(0, max(bottom) + 4.0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(fontsize=6.6, frameon=False, loc="upper center",
              bbox_to_anchor=(0.5, -0.30), ncol=1, handlelength=1.6)
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "figure_conditions.pdf"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def main() -> int:
    if not RECORDS.exists():
        sys.stderr.write(
            "missing input: %s\n"
            "expected records/admission_decisions.json one level above\n"
            "figures/ (repo layout) or in the working directory, or set\n"
            "ECM_RECORDS to its path; see branch experiments/census-5arm\n" % RECORDS)
        return 1
    rows = load_rows()
    chunks, v1 = load_v1_admission(rows)
    a2, failures = load_a2(rows)
    print("records: %s" % RECORDS)
    print("chunks: %d  rows: %d" % (len(chunks), len(rows)))
    for a in ARMS:
        print("  %-24s A_P=%2d/%d  A2=%2d/%d  gate failures=%s"
              % (a, len(v1[a]), len(chunks), len(a2[a]), len(chunks), failures[a]))
    p1 = fig_admission_matrix(chunks, a2, v1)
    p2 = fig_condition_structure(a2, failures)
    print("wrote %s" % p1)
    print("wrote %s" % p2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
