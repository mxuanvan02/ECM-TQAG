"""Exact Clopper-Pearson via beta inversion (no factorials -> no overflow at n=2167).

Cross-checked against the project's own exact implementation at a small n where
that implementation does not overflow, to prove the two agree.
"""
import sys
from pathlib import Path
from scipy.stats import beta

ROOT = Path("ECM-TQAG_experiment_private_clean")
sys.path.insert(0, str(ROOT))


def cp(k, n, alpha=0.05):
    lo = 0.0 if k == 0 else beta.ppf(alpha / 2, k, n - k + 1)
    hi = 1.0 if k == n else beta.isf(alpha / 2, k + 1, n - k)
    return lo, hi


# --- validation: agree with the project's exact implementation at small n ---
from ecm_tqag.stats.intervals import clopper_pearson

print("=== cross-check vs project implementation (small n) ===")
ok = True
for k, n in [(0, 16), (1, 16), (4, 30), (6, 16), (12, 16)]:
    mine = cp(k, n)
    theirs = clopper_pearson(k, n)
    d = max(abs(mine[0] - theirs["lower"]), abs(mine[1] - theirs["upper"]))
    flag = "OK" if d < 1e-9 else "MISMATCH"
    if d >= 1e-9:
        ok = False
    print(f"  {k}/{n}: mine=[{mine[0]:.6f},{mine[1]:.6f}] theirs=[{theirs['lower']:.6f},{theirs['upper']:.6f}] max_absdiff={d:.2e} {flag}")
print("  cross-check passed:", ok)

print()
print("=== corpus-scale diagram prevalence (full page-by-page VLM census) ===")
for label, k, n in [
    ("all 4 fully-classified books", 4, 2167),
    ("21. HANH CHINH", 0, 464),
    ("28. TTHS", 1, 575),
    ("17,18. HIEN PHAP VN", 2, 677),
    ("22. TTHC", 1, 451),
]:
    lo, hi = cp(k, n)
    print(f"  {label:32s} {k:2d}/{n:5d} = {100*k/n:6.3f}%  95% CP CI [{100*lo:.3f}%, {100*hi:.3f}%]")

print()
print("=== prefilter precision (vector-rich candidate screening) ===")
lo, hi = cp(31, 437)
print(f"  diagram pages among screened candidates 31/437 = {100*31/437:.1f}%  95% CP CI [{100*lo:.1f}%, {100*hi:.1f}%]")
