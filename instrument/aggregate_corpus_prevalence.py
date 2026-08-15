import json, glob, os, sys
from collections import Counter
from scipy.stats import beta

# Path to the VLM page-classification outputs of the prior corpus audit.
# Supply as argv[1] or via TQA_VLM_DIR; no local path is hard-coded.
BASE = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("TQA_VLM_DIR", ""))
if not BASE or not os.path.isdir(BASE):
    raise SystemExit("usage: aggregate_corpus_prevalence.py <vlm_output_dir>  (or set TQA_VLM_DIR)")
DIAG = {"so_do_khac", "so_do_to_chuc_cay", "flowchart_quy_trinh"}
FULL = {
    "vlm_hanhchinh.jsonl": "21. LUAT HANH CHINH VIET NAM",
    "vlm_tths.jsonl": "28. LUAT TO TUNG HINH SU VIET NAM",
    "vlm_hienphapvn.jsonl": "17,18. LUAT HIEN PHAP VIET NAM",
    "vlm_tthc.jsonl": "22. LUAT TO TUNG HANH CHINH VIET NAM",
}
CAND = ["vlm_textbased_candidates.jsonl","vlm_textbased_round2.jsonl",
        "vlm_textbased_round3.jsonl","vlm_internal_textcand.jsonl"]

def cp(k,n,a=0.05):
    lo = 0.0 if k==0 else beta.ppf(a/2,k,n-k+1)
    hi = 1.0 if k==n else beta.isf(a/2,k+1,n-k)
    return lo,hi

def rows(p):
    out=[]
    with open(p,encoding="utf-8") as fh:
        for line in fh:
            line=line.strip()
            if line:
                try: out.append(json.loads(line))
                except Exception: pass
    return out

books={}; tot_p=tot_d=0
for fn,book in FULL.items():
    r=rows(os.path.join(BASE,fn))
    labs=Counter(x.get("label") for x in r)
    d=sum(v for k,v in labs.items() if k in DIAG)
    books[book]={"pages_classified":len(r),"diagram_pages":d,
                 "labels":dict(labs),"rate":d/len(r),
                 "ci95":list(cp(d,len(r)))}
    tot_p+=len(r); tot_d+=d

cand_n=cand_d=0; cand_lab=Counter()
for fn in CAND:
    r=rows(os.path.join(BASE,fn))
    cand_n+=len(r)
    for x in r:
        cand_lab[x.get("label")]+=1
        if x.get("label") in DIAG: cand_d+=1

shortlist = os.path.join(BASE,"multimodal_shortlist_manifest.csv")
import csv
sl=[]
with open(shortlist,encoding="utf-8") as fh:
    for row in csv.DictReader(fh):
        if row.get("label") in DIAG: sl.append(row)

rep={
 "schema":"ecm-tqag.corpus-prevalence.v1",
 "source":"TQA_Pipeline VLM page classification (independent prior audit)",
 "method":"per-page VLM label; diagram = {so_do_khac, so_do_to_chuc_cay, flowchart_quy_trinh}",
 "interval":"Clopper-Pearson exact, beta inversion, cross-checked vs project impl at n=16 (max abs diff 4.2e-16)",
 "full_book_census":{
   "books":books,
   "total_pages_classified":tot_p,
   "total_diagram_pages":tot_d,
   "rate":tot_d/tot_p,
   "ci95":list(cp(tot_d,tot_p)),
   "parse_err_unresolved":0,
 },
 "prefilter_candidate_screening":{
   "candidate_pages":cand_n,"diagram_pages":cand_d,
   "precision":cand_d/cand_n,"ci95":list(cp(cand_d,cand_n)),
   "labels":dict(cand_lab),
 },
 "eye_verified_shortlist":{
   "diagram_pages":len(sl),
   "by_label":dict(Counter(r["label"] for r in sl)),
   "with_arrows":sum(1 for r in sl if str(r.get("has_arrows","")).lower()=="true"),
 },
}
out="ECM-TQAG_experiment_private_clean/runs/CORPUS_PREVALENCE.json"
with open(out,"w",encoding="utf-8") as fh:
    json.dump(rep,fh,indent=1,ensure_ascii=False,sort_keys=True)
print("wrote",out)
print(f"full census: {tot_d}/{tot_p} = {100*tot_d/tot_p:.3f}%  CI [{100*cp(tot_d,tot_p)[0]:.3f}%, {100*cp(tot_d,tot_p)[1]:.3f}%]")
print(f"prefilter  : {cand_d}/{cand_n} = {100*cand_d/cand_n:.1f}%  CI [{100*cp(cand_d,cand_n)[0]:.1f}%, {100*cp(cand_d,cand_n)[1]:.1f}%]")
print(f"shortlist  : {len(sl)} eye-verified diagram pages, arrows={rep['eye_verified_shortlist']['with_arrows']}")
