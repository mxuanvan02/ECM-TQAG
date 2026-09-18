"""Reconstruct Fig.1 cell classes from released records only, to test whether
the figure's DATA is recoverable without the unpublished run tree."""
import json
from collections import Counter

rows = json.load(open("records/admission_decisions.json"))["rows"]
rows = rows.values() if isinstance(rows, dict) else rows

cell = Counter()
per_arm = {}
for r in rows:
    arm = r["arm"]
    if r["admitted"]:
        cls = "filled"
    elif r["provenance_admitted"]:
        cls = "dotted"      # passed 5 provenance, failed a division-of-labour cond
    else:
        cls = "cross"       # failed a provenance condition
    cell[cls] += 1
    per_arm.setdefault(arm, Counter())[cls] += 1

print("Fig.1 legend classes recovered from records/admission_decisions.json:")
for k in ("filled", "dotted", "cross"):
    print(f"  {k:8s} {cell[k]:4d}")
print("  total   ", sum(cell.values()), "(expect 300 = 5 arms x 60 chunks)")
print()
print("per-arm 'filled' (= admitted all eight):")
for arm, c in sorted(per_arm.items()):
    print(f"  {arm:28s} filled={c['filled']:3d} dotted={c['dotted']:3d} cross={c['cross']:3d}")
print()
print("paper Fig.1 alt text claims: ECM 24, DISC 10, PROV 11, DIR 6, STR 6 filled")
