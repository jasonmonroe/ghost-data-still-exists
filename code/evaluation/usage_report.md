# Usage Report — Ghost Data Still Exists

**Status: DRAFT.** This report must describe the **final full-dataset run (518 requests)** that produced
`output.csv`. That run has not happened yet, so every number below is `PENDING`. Do not estimate these
values by hand: they come from `src/usage_tracker.py`, which records each API response's own `usage` field.

## 1. Model information

| Provider | Model | Used for |
| --- | --- | --- |
| Google (Gemini, Interactions API via `google-genai`) | value of `GEMINI_MODEL_NAME` in `.env` (record the exact name here after the final run) | Classifying whether `request_text` authorizes deletion, only for requests that neither keyword list in `constants.py` settles |

Everything else is deterministic Python with no model call: identity resolution, evidence matching,
state proof, rule evaluation, status and step ordering. The solution is **not** zero-cost: it makes
Gemini calls, so the cost section must be filled with real prices.

Settings: temperature `0.0`, `thinking_level` `low`, `max_output_tokens` = `MAX_TOKENS` (2048),
retries on 429 and 5xx up to `RATE_LIMIT_RETRIES`.

Development/coding assistance (Claude Code) is logged in `log.txt` and is not part of this run's cost.

## 2. Execution stats (final run)

| Metric | Value |
| --- | --- |
| Requests processed | 518 (expected) |
| Requests that needed a model call | PENDING |
| Total model calls (including retries) | PENDING |
| Input tokens | PENDING |
| Output tokens | PENDING |
| Total tokens | PENDING |
| Average tokens per request (total ÷ 518) | PENDING |
| Average tokens per model call | PENDING |
| Smallest / largest call (tokens) | PENDING (`UsageTracker` keeps `least` / `most`) |

Per-model table (one row per model name the API reports back):

| Model | Calls | Input tokens | Output tokens | Total tokens |
| --- | --- | --- | --- | --- |
| PENDING | PENDING | PENDING | PENDING | PENDING |
| **Overall** | PENDING | PENDING | PENDING | PENDING |

## 3. Cost breakdown

Formula: `cost = input_tokens × input_price + output_tokens × output_price`, with the provider's published
per-token prices for the model above on the date of the run (record the date and the prices used).

| Metric | Value |
| --- | --- |
| Input price used | PENDING |
| Output price used | PENDING |
| Estimated total cost | PENDING |
| Estimated cost per request (÷ 518) | PENDING |

## 4. Cost-control notes

- Keyword lists (`VALID_KEYPHRASES`, `NON_DELETION_KEYWORDS`) are checked first, so clear requests make no
  model call.
- Known gaps: there is no response cache yet, although the design calls for caching every LLM call, so
  repeated identical request texts are billed again. Add a cache and re-measure.
- `LlmModel.get_response` currently parses a bare `True`/`False` with `json.loads`, which fails and returns
  an error dict. Until fixed, calls may be billed while the answer is discarded, so fix this before the
  final run or the token totals will not match useful work.

## 5. How the numbers are produced

`LlmModel._process_response` calls `UsageTracker.record(model, input_tokens, output_tokens, prompt)` for each
response. `UsageTracker.by_model()` and `.totals()` hold the per-model and overall counts. A small step still
needs to be written to dump those totals into this file after the final run.
