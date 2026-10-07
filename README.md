# AI Whispers

**How many AI handoffs does a fact survive?**

Live page: https://eshwarpotturi.github.io/ai-whispers/

It is the game of Chinese whispers, played by AI. A short business document is passed through six AI rewriting steps (summary, client email, newsletter bullets, news paragraph, morning briefing, client update). After every step we check each original fact: is it intact, distorted or missing?

## What we found

| Measure | Result |
|---|---|
| Facts intact after six handoffs | 38% |
| Facts distorted | 33% |
| Facts missing | 28% |
| Caveats gone completely | 76% |
| Intact when the final message is written straight from the original | 80% |
| Intact when every step is told "keep every figure, caveat and condition" | 88% |

- **Caveats die first.** "Unaudited figures", "funded by the manufacturer" and "margin of error" were dropped in about three out of four chains.
- **Decisions survive but get bent.** A SELL rating almost never disappeared, but "we rate it SELL" often became "analysts have downgraded it".
- **Meaning changes, not only detail.** "Has not yet renewed its contract" became "will not be renewing" and then "the loss of a key customer".
- **No model was safe.** The best kept 56% of facts (GPT-5.1), the worst 17% (Gemini 2.5 Pro). A flagship model was not automatically safer.
- **The fix is cheap.** One extra sentence in each step took the result from 38% to 88% without making the messages longer.

## Why it matters

Teams are chaining AI steps: research note to summary to client email to sales update. Each step looks fine by itself, and nobody compares the last message with the first. A client can receive a sentence the analyst never wrote. This experiment shows which facts break, at which step, and what to do about it.

## What to do with it

1. **Lock the fragile lines.** Pass caveats, conditions and "not yet" statements as fixed text that no step may rewrite.
2. **Keep the source in reach.** Let each step see the original, not only the previous step's output.
3. **Tell each step what must survive**, then test your own chain the way this page does.

## How it works

| Item | Detail |
|---|---|
| Documents | 3 invented notes (analyst note, drug trial summary, customer survey), 9 to 11 checkable facts each |
| Fact types | number, decision, uncertainty, caveat |
| Handoffs | 6, each a fresh call that sees only the previous step's text |
| Models | GPT-4.1 mini, GPT-5.1, Claude Haiku 4.5, Claude Sonnet 4.5, Gemini 2.5 Flash, Gemini 2.5 Pro |
| Conditions | plain chain (54 chains), guarded chain with one extra instruction (36), direct rewrite from the original (54) |
| Calls | 594 rewriting calls, 414 scoring calls |
| Scoring | GPT-4.1 marks each fact intact, distorted or missing after every step |
| Cross-check | a plain text search for the original's key figures, with no AI judge |

The two measures agree. Key figures found in the final message: 55% for the plain chain, 97% for the guarded chain, 89% for the direct rewrite.

## Files

| File | What it is |
|---|---|
| `index.html` | The page |
| `data.js` | Aggregated results used by the page |
| `results.json` | Every raw output and every judge verdict |
| `whispers.py` | Runs the experiment (resumable) |
| `build_data.py` | Turns `results.json` into `data.js` |

## Run it yourself

```bash
# put your LLM Foundry token in ../.env (one line), then run until it prints ALL DONE
python3 whispers.py
python3 build_data.py
```

To test your own document, add it to `DOCS` in `whispers.py` with its list of facts. To test your own pipeline, edit `HOPS`.

## Questions you may ask

**Isn't loss expected when you shorten text?** Yes, some. That is why the direct rewrite exists: the same 100-word client update, written straight from the original, kept 80% of facts. The chain ended at the same length and kept 38%.

**Is the AI judge reliable?** It is one model's reading, so we added a text search for key figures that uses no AI. Both give the same ordering of conditions and the same best and worst model. "Distorted" includes facts that were only partly kept.

**Is the model ranking final?** No. Each model has nine chains. The ends of the ranking are clear; the middle is a tie.

**Has this been done before?** The idea of an AI "telephone game" exists. [Perez et al. (2024)](https://arxiv.org/abs/2407.04503) ran long chains and measured tone, toxicity and length, not facts. We found no fact-by-fact measurement on business documents across current vendors, though we did not survey the whole literature.

**Is this real client data?** No. The companies, the drug and the survey are invented.

## Limits

- Small sample: three runs per document and model.
- One pipeline design. Other steps and prompts will lose different things.
- Models were called with default settings through an enterprise gateway in October 2026.

A personal experiment, not an official product.
