"""AI Whispers: how many AI handoffs does a fact survive?

Passes a short business document through a chain of AI rewriting steps and
scores, after every step, which of the original facts are intact, distorted,
missing, and what was invented. Resumable: run repeatedly until it prints ALL DONE.
Token is read from ../.env (never stored in results).
"""
import json, os, re, sys, time, threading, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

BASE = "https://llmfoundry.straivedemo.com"
TOKEN = re.sub(r"^[A-Za-z_]+=", "", open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")).read().strip())
OUT = "results.json"
BUDGET = float(os.environ.get("BUDGET", 112))
THREADS = int(os.environ.get("THREADS", 5))

MODELS = {
    "GPT-4.1 mini":      {"vendor": "OpenAI",    "tier": "small",    "path": "/openai/v1/chat/completions", "id": "gpt-4.1-mini"},
    "GPT-5.1":           {"vendor": "OpenAI",    "tier": "flagship", "path": "/openai/v1/chat/completions", "id": "gpt-5.1"},
    "Claude Haiku 4.5":  {"vendor": "Anthropic", "tier": "small",    "path": "/anthropic/v1/messages", "id": "claude-haiku-4-5"},
    "Claude Sonnet 4.5": {"vendor": "Anthropic", "tier": "flagship", "path": "/anthropic/v1/messages", "id": "claude-sonnet-4-5"},
    "Gemini 2.5 Flash":  {"vendor": "Google",    "tier": "small",    "path": "/gemini/v1beta/openai/chat/completions", "id": "gemini-2.5-flash"},
    "Gemini 2.5 Pro":    {"vendor": "Google",    "tier": "flagship", "path": "/gemini/v1beta/openai/chat/completions", "id": "gemini-2.5-pro"},
}
JUDGE = {"path": "/openai/v1/chat/completions", "id": "gpt-4.1"}

DOCS = {
 "analyst": {"title": "Analyst note on a company", "text":
  "Northgate Precision Industries reported full-year revenue of $1.9 billion, down 6%. Operating margin fell to 4.1% from 7.8%. Net debt stands at 4.6 times EBITDA. Free cash flow was negative $85 million and the dividend has been suspended. Its largest customer, which accounts for 28% of revenue, has not yet renewed its contract. Management guides to revenue flat to down 3% next year. We rate the stock SELL with a 12-month price target of $14, against a current price of $19. Our view could change if the contract is renewed, which we think has roughly a 50% chance. This note is based on unaudited preliminary figures.",
  "facts": [["Revenue $1.9 billion, down 6%", "number"], ["Operating margin 4.1%, down from 7.8%", "number"], ["Net debt 4.6 times EBITDA", "number"],
            ["Free cash flow negative $85 million", "number"], ["Dividend suspended", "decision"],
            ["Largest customer (28% of revenue) has not yet renewed its contract (still undecided)", "uncertainty"],
            ["Guidance: revenue flat to down 3% next year", "number"], ["Rating is SELL", "decision"], ["Price target $14 versus current price $19", "number"],
            ["View could change if the contract is renewed, roughly a 50% chance", "uncertainty"], ["Figures are unaudited and preliminary", "caveat"]]},
 "trial": {"title": "Summary of a drug trial", "text":
  "A phase 2 trial of Zentrolimab in 212 adults with moderate asthma found a 31% reduction in severe attacks over 24 weeks compared with placebo. The result was statistically significant (p = 0.03). Lung function did not improve. Serious side effects occurred in 9% of the treatment group against 4% on placebo, including two cases of liver inflammation. The benefit was seen only in patients with high eosinophil counts; there was no effect in other patients. The trial was funded by the manufacturer. The authors say a larger phase 3 trial is needed before the drug can be recommended, and that the study was too short to assess long-term safety.",
  "facts": [["Phase 2 trial in 212 adults with moderate asthma", "number"], ["31% reduction in severe attacks over 24 weeks versus placebo", "number"],
            ["Statistically significant, p = 0.03", "number"], ["Lung function did not improve", "uncertainty"],
            ["Serious side effects 9% on treatment versus 4% on placebo", "number"], ["Two cases of liver inflammation", "number"],
            ["Benefit only in patients with high eosinophil counts; no effect in others", "uncertainty"], ["Trial funded by the manufacturer", "caveat"],
            ["Larger phase 3 trial needed before the drug can be recommended", "decision"], ["Study too short to assess long-term safety", "caveat"]]},
 "survey": {"title": "Findings from a customer survey", "text":
  "An online survey of 1,480 UK adults in September found that 62% would consider switching their main bank for a better mobile app. Among under-35s the figure was 78%. However, only 18% of respondents had actually switched banks in the past five years. Fees remained the top stated reason for switching (41%), ahead of app quality (27%). The margin of error is plus or minus 3 percentage points. The sample was drawn from an online panel and under-represents people over 65. The survey was commissioned by a mobile banking software vendor. We recommend treating the results as a signal of interest, not a forecast of switching.",
  "facts": [["Online survey of 1,480 UK adults", "number"], ["62% would consider switching main bank for a better mobile app", "number"], ["78% among under-35s", "number"],
            ["Only 18% actually switched banks in the past five years", "uncertainty"], ["Fees are the top reason (41%), ahead of app quality (27%)", "number"],
            ["Margin of error plus or minus 3 percentage points", "caveat"], ["Online panel under-represents people over 65", "caveat"],
            ["Commissioned by a mobile banking software vendor", "caveat"], ["Recommendation: treat as a signal of interest, not a forecast of switching", "decision"]]},
}
HOPS = [["Manager summary", "Summarise this note for a busy senior manager in at most 80 words."],
        ["Client email", "Using only the summary below, write a 150-word email to a client explaining the findings."],
        ["Newsletter bullets", "Turn the email below into 3 short bullet points for an internal newsletter."],
        ["News paragraph", "Using only the bullet points below, write a short news paragraph of about 100 words."],
        ["Morning briefing", "Summarise the paragraph below in at most 60 words for a morning briefing."],
        ["Client update", "Using only the briefing below, write a 100-word update that an account manager can send to a client."]]
DIRECT = "Using only the note below, write a 100-word update that an account manager can send to a client."
GUARD = " Keep every figure, caveat and condition from the text exactly as stated, and do not add anything that is not in it."
REPS = {"chain": 3, "guarded": 2, "direct": 3}

def call(path, mid, prompt, temperature=None, as_json=False):
    body = {"model": mid, "messages": [{"role": "user", "content": prompt}]}
    if as_json: body["response_format"] = {"type": "json_object"}
    if "anthropic" in path: body["max_tokens"] = 1200
    if temperature is not None: body["temperature"] = temperature
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers={"Authorization": f"Bearer {TOKEN}:ai-whispers",
        "Content-Type": "application/json", "anthropic-version": "2023-06-01", "Cache-Control": "no-cache"})
    resp = json.load(urllib.request.urlopen(req, timeout=55))
    txt = resp["content"][0]["text"] if "content" in resp else resp["choices"][0]["message"]["content"]
    if not txt or not txt.strip(): raise ValueError("empty reply")
    return txt.strip()

def judge(doc, text):
    d = DOCS[doc]
    p = ("You are checking whether a rewritten text is faithful to an original note.\n\nORIGINAL NOTE:\n" + d["text"] + "\n\nREWRITTEN TEXT:\n" + text
         + "\n\nFor each numbered fact from the original, classify how the rewritten text treats it:\n"
         "- \"intact\": present and correct (rounding like 'about 30%' for 31% still counts as intact)\n"
         "- \"distorted\": present but changed in meaning, e.g. a different number, an uncertainty stated as certain, a condition dropped, a status changed, or made so vague the specific fact is lost\n"
         "- \"missing\": not there at all\nFACTS:\n" + "\n".join(f"{i+1}. {f[0]}" for i, f in enumerate(d["facts"]))
         + "\n\nThen list factual claims in the rewritten text that are NOT supported by the original (new facts, causes, plans, numbers, events). "
         "Ignore greetings, sign-offs, offers of help and generic filler.\n"
         f"Reply with JSON only: {{\"facts\": [exactly {len(d['facts'])} strings], \"invented\": [strings]}}")
    n = len(d["facts"])
    for temp in (0, 0.4, 0.7):
        raw = call(JUDGE["path"], JUDGE["id"], p + " No comments inside the JSON.", temperature=temp, as_json=True)
        j = json.loads(re.search(r"\{.*\}", re.sub(r"//[^\n]*", "", raw), re.S).group(0))
        items = j.get("facts", [])
        if isinstance(items, dict): items = list(items.values())
        f = []
        for x in items:
            if isinstance(x, dict): x = x.get("status") or x.get("classification") or next(iter(x.values()), "")
            x = re.sub(r"[^a-z]", "", str(x).lower())
            f.append(next((k for k in ("intact", "distorted", "missing") if x.startswith(k)), x))
        if len(f) == n and all(x in ("intact", "distorted", "missing") for x in f): break
    else:
        print("JUDGE RAW", raw[:300].replace("\n", " "), flush=True); raise ValueError("bad judge output")
    return {"facts": f, "invented": [str(x) for x in j.get("invented", [])]}

lock = threading.Lock()
state = json.load(open(OUT)) if os.path.exists(OUT) else {}
def save():
    with lock:
        tmp = OUT + ".tmp"; json.dump(state, open(tmp, "w"), indent=1); os.replace(tmp, OUT)

jobs = [(c, d, m, r) for c in ("chain", "direct", "guarded") for r in range(REPS[c]) for d in DOCS for m in MODELS]
T0 = time.time()
def nhops(c): return 1 if c == "direct" else len(HOPS)
def is_done(key, c):
    s = state.get(key, {}).get("steps", [])
    if len(s) < nhops(c): return False
    need = s if c == "chain" else s[-1:]
    return all("judge" in x for x in need)

def work(job):
    c, d, m, r = job
    key = f"{c}|{d}|{m}|{r}"
    with lock: st = state.setdefault(key, {"cond": c, "doc": d, "model": m, "rep": r, "steps": []})
    fails = 0
    while not is_done(key, c) and time.time() - T0 < BUDGET and fails < 3:
        try:
            steps = st["steps"]
            pending = [x for x in (steps if c == "chain" else steps[-1:] if len(steps) == nhops(c) else []) if "judge" not in x]
            if pending:
                pending[0]["judge"] = judge(d, pending[0]["text"])
            else:
                prev = steps[-1]["text"] if steps else DOCS[d]["text"]
                instr = DIRECT if c == "direct" else HOPS[len(steps)][1] + (GUARD if c == "guarded" else "")
                txt = call(MODELS[m]["path"], MODELS[m]["id"], instr + " Reply with the text only.\n\n" + prev)
                steps.append({"hop": len(steps) + 1, "text": txt})
            save()
        except urllib.error.HTTPError as e:
            fails += 1; print("HTTP", e.code, key, flush=True); time.sleep(12 if e.code == 429 else 3)
        except Exception as e:
            fails += 1; print("ERR", str(e)[:70], key, flush=True); time.sleep(2)

todo = [j for j in jobs if not is_done(f"{j[0]}|{j[1]}|{j[2]}|{j[3]}", j[0])]
if "--status" not in sys.argv:
    with ThreadPoolExecutor(THREADS) as ex: list(ex.map(work, todo))
left = [j for j in jobs if not is_done(f"{j[0]}|{j[1]}|{j[2]}|{j[3]}", j[0])]
print(f"chains done {len(jobs) - len(left)}/{len(jobs)}" + ("  ALL DONE" if not left else ""))
