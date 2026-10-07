"""Turn results.json (raw chains) into data.js for the page, and print the headline numbers."""
import json, re, statistics as st, sys
from collections import defaultdict

src = open("whispers.py").read()
ns = {}
exec(src.split("def call(")[0].replace('TOKEN = re.sub', 'TOKEN = "" or re.sub').replace(
    'open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")).read().strip()', '""'), ns)
MODELS, DOCS, HOPS = ns["MODELS"], ns["DOCS"], ns["HOPS"]
state = json.load(open("results.json"))
runs = [v for v in state.values() if v["steps"]]

def complete(r):
    n = 1 if r["cond"] == "direct" else len(HOPS)
    return len(r["steps"]) == n and "judge" in r["steps"][-1] and (r["cond"] != "chain" or all("judge" in s for s in r["steps"]))
runs = [r for r in runs if complete(r)]

def share(judges, status):
    tot = sum(len(j["facts"]) for j in judges)
    return round(100 * sum(j["facts"].count(status) for j in judges) / tot, 1) if tot else None

out = {"models": {m: {"vendor": v["vendor"], "tier": v["tier"]} for m, v in MODELS.items()},
       "docs": {k: {"title": d["title"], "text": d["text"], "facts": d["facts"]} for k, d in DOCS.items()},
       "hops": [h[0] for h in HOPS], "hop_prompts": [h[1] for h in HOPS]}

chain = [r for r in runs if r["cond"] == "chain"]
# decay curve: % intact / distorted / missing per hop, per model and overall
def curve(rs):
    return [{s: share([r["steps"][h]["judge"] for r in rs], s) for s in ("intact", "distorted", "missing")} for h in range(len(HOPS))]
out["curve_all"] = curve(chain)
out["curve_model"] = {m: curve([r for r in chain if r["model"] == m]) for m in MODELS if any(r["model"] == m for r in chain)}
out["curve_doc"] = {d: curve([r for r in chain if r["doc"] == d]) for d in DOCS}

# survival by fact type at each hop
bytype = defaultdict(lambda: [defaultdict(int) for _ in HOPS])
for r in chain:
    for h, s in enumerate(r["steps"]):
        for (fact, typ), status in zip(DOCS[r["doc"]]["facts"], s["judge"]["facts"]):
            bytype[typ][h][status] += 1
out["by_type"] = {t: [{k: round(100 * c[k] / sum(c.values()), 1) for k in ("intact", "distorted", "missing")} for c in hops] for t, hops in bytype.items()}

# per individual fact at final hop
perfact = {}
for d in DOCS:
    rs = [r for r in chain if r["doc"] == d]
    perfact[d] = [{k: sum(r["steps"][-1]["judge"]["facts"][i] == k for r in rs) for k in ("intact", "distorted", "missing")} for i in range(len(DOCS[d]["facts"]))]
out["per_fact_final"] = perfact

# model table
def final_stats(rs):
    js = [r["steps"][-1]["judge"] for r in rs]
    return {"n": len(rs), "intact": share(js, "intact"), "distorted": share(js, "distorted"), "missing": share(js, "missing"),
            "invented": round(st.mean(len(j["invented"]) for j in js), 2) if js else None}
out["model_final"] = {m: final_stats([r for r in chain if r["model"] == m]) for m in MODELS}
out["cond_final"] = {c: final_stats([r for r in runs if r["cond"] == c]) for c in ("chain", "guarded", "direct")}
out["cond_model_final"] = {c: {m: final_stats([r for r in runs if r["cond"] == c and r["model"] == m]) for m in MODELS} for c in ("chain", "guarded", "direct")}
out["invented_by_hop"] = [round(st.mean(len(r["steps"][h]["judge"]["invented"]) for r in chain), 2) for h in range(len(HOPS))] if chain else []

# full chains for the replay (rep 0 of every doc x model)
out["replay"] = {f'{r["doc"]}|{r["model"]}': [{"text": s["text"], "facts": s["judge"]["facts"], "invented": s["judge"]["invented"]} for s in r["steps"]]
                 for r in chain if r["rep"] == 0}
out["counts"] = {"chains": len(chain), "guarded": sum(r["cond"] == "guarded" for r in runs), "direct": sum(r["cond"] == "direct" for r in runs),
                 "rewrite_calls": sum(len(r["steps"]) for r in runs), "judge_calls": sum("judge" in s for r in runs for s in r["steps"])}
# judge-free cross-check: are the original's key figures still literally in the text?
TOK = {"analyst": ["1.9", "6%", "4.1%", "7.8%", "4.6", "85", "28%", "3%", "$14", "$19", "50%"],
       "trial": ["212", "31%", "24", "0.03", "9%", "4%", "two", "phase 2", "phase 3"],
       "survey": ["1,480", "62%", "78%", "18%", "41%", "27%", "3", "65"]}
def kf(r, h=-1):
    t = r["steps"][h]["text"].lower().replace("1480", "1,480")
    return 100 * sum(k in t for k in TOK[r["doc"]]) / len(TOK[r["doc"]])
out["keyfig_cond"] = {c: round(st.mean(kf(r) for r in runs if r["cond"] == c), 1) for c in ("chain", "guarded", "direct")}
out["keyfig_hop"] = [round(st.mean(kf(r, h) for r in chain), 1) for h in range(len(HOPS))]
out["keyfig_model"] = {m: round(st.mean(kf(r) for r in chain if r["model"] == m), 1) for m in MODELS}
out["words_final"] = {c: round(st.mean(len(r["steps"][-1]["text"].split()) for r in runs if r["cond"] == c)) for c in ("chain", "guarded", "direct")}
print("keyfig", out["keyfig_cond"], out["keyfig_hop"], out["keyfig_model"], out["words_final"])
open("data.js", "w").write("window.DATA = " + json.dumps(out, ensure_ascii=False) + ";\n")

print("counts", out["counts"])
print("overall by hop:", [(c["intact"], c["distorted"], c["missing"]) for c in out["curve_all"]])
print("by type final:", {t: v[-1] for t, v in out["by_type"].items()})
for m, v in out["model_final"].items(): print(f"{m:18}", v)
print("conditions:", out["cond_final"])
print("invented by hop:", out["invented_by_hop"])
if "--facts" in sys.argv:
    for d in DOCS:
        for (f, t), c in zip(DOCS[d]["facts"], perfact[d]): print(f"  [{d}] {t:11} {c}  {f}")
