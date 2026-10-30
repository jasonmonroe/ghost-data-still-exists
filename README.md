# Ghost Data Still Exists

A deletion-audit agent built for **HackerRank Orchestrate (October 2026)**.

When a customer asks a company to delete their data, the deletion workflow can report **Complete** while
copies still sit in database replicas, logs, support attachments, exports, search indexes, analytics
records, archives, or backups. Sync and restore processes can even recreate data that was already deleted.

For every request in `dataset/deletion_requests.csv`, this agent:

1. decides whether the request text actually authorizes deletion (`NOT_APPLICABLE` if not);
2. resolves the person's current **and historical** identifiers (email, email hash, phone, user ID);
3. reconstructs what is really true at the case's `audit_at` time from the evidence files, treating
   workflow statuses and activity results as claims, not proof;
4. applies `deletion_rules.csv` (delete / redact / anonymize / retain / account tombstone); and
5. returns `COMPLETE` or `INCOMPLETE` plus an ordered `steps_json` of findings, remediation and
   verification checks.

The full challenge contract is in [`problem_statement.md`](./problem_statement.md); AI-agent working rules
are in [`AGENTS.md`](./AGENTS.md) and [`CLAUDE.md`](./CLAUDE.md).

> **Project status:** the full pipeline runs end to end on the 32 sample cases (87.5% status accuracy). The
> live LLM path is not yet verified and the 518-case run has not been produced. See [Status](#status).

---

## Approach

**Code decides, the LLM perceives.** Identity resolution, record matching, rule evaluation, status and step
ordering are deterministic Python. The LLM (Gemini) is used only where judgement is unavoidable, currently
classifying request intent (multilingual) when keyword lists don't settle it.

| Stage | Component | What it does |
| --- | --- | --- |
| Validity | `CaseAuditorAgent._check_validity` | Keyword lists first; LLM only for requests neither list covers. |
| Identity | `CaseAuditorAgent._filter_by_user` | Maps the request email (current or historical) to one `user_id`; filters audit log, activity and evidence by `audit_at`. |
| Evidence | `EvidenceAgent` | Builds search terms, matches resources to the user record-by-record, and proves each resource's state (`PRESENT` / `ABSENT` / `ACTIVE` / `DISABLED` / `BLOCKED`) with a cited `file_id`. |
| Policy | `DeletionRuleAgent` | Maps a resource to its data category, looks up the required action, and decides whether the finding violates policy. |
| Steps | `StepsAgent` | Collects findings, remediation and verification, sorts them and numbers them `1..n`. |

Key design points:

- **Claims vs proof.** `system_activity.csv` and `reported_status` are claims. State comes from evidence
  captured at or before `audit_at`; later evidence is ignored.
- **Search terms** are the user ID, all emails (lowercased), all email hashes (stored and
  `sha256(email.lower())`) and phones as digits. Names and timestamps are never used because they are decoys.
- **Record-level matching.** A resource belongs to the user only if it appears with a user identifier in the
  same SQL row, JSON record, text line or log `trace_id` group, or through a `LINK_RESOURCE_IDENTITY` event.
- **Absence proof.** A full snapshot that lists other records of the same type but not this one proves
  absence; so does a lookup with `rows=0`, HTTP 404 or `NOT_FOUND`. Logs alone cannot prove absence.
- **Processes are not records.** Active data flows → `DISABLE_DATA_FLOW`; restorable backups →
  `BLOCK_RESTORE`.
- **Startup fail-safe.** The category mapping is validated against `deletion_rules.csv` when the agent
  starts, so a typo cannot silently turn a violation into `COMPLETE`.
- **Deterministic output.** Rows sorted by `case_id`; steps ordered FINDING → REMEDIATION → VERIFICATION,
  then by operation order, `system_id`, `resource_id`.

---

## Project structure

```text
.
├── AGENTS.md                  # rules for AI coding agents (logging, contract)
├── CLAUDE.md                  # project conventions + current status for Claude Code
├── README.md                  # this file
├── problem_statement.md       # full challenge contract
├── requirements.txt
├── .env.example               # copy to .env and fill in
├── log.txt                    # AI session transcript (submitted as chat_transcript)
├── output.csv                 # final predictions (generated, repo root)
├── dataset/                   # participant data (not included in code.zip)
│   ├── deletion_requests.csv          518 evaluation requests
│   ├── sample_deletion_requests.csv   32 public sample requests
│   ├── sample_output.csv              correct sample answers (scoring only)
│   ├── user_identities.csv            current identity snapshot
│   ├── user_audit_log.csv             historical identity changes
│   ├── system_activity.csv            global activity stream (claims)
│   ├── deletion_rules.csv             required treatment per data category
│   ├── evidence_files.csv             manifest of evidence files
│   ├── output.csv                     blank output template
│   └── evidence/                      databases, documents, images, logs, records
└── code/                      # imports are rooted here: `from agents.… import …`
    ├── main.py                        entry point
    ├── pipelines/run_case_audit_pipeline.py   loops cases through the auditor
    ├── agents/
    │   ├── case_auditor_agent.py      per-case orchestration
    │   ├── evidence_agent.py          resources, state, proof → ResourceFinding
    │   ├── deletion_rule_agent.py     category lookup + policy evaluation
    │   └── steps_agent.py             ordered steps_json
    ├── models/llm_model.py            Gemini client, retries, usage recording
    ├── src/
    │   ├── constants.py               config, regexes, mappings, prompts
    │   ├── enums.py                   statuses, phases, operations, states
    │   ├── data_handler.py            loads CSVs, evidence paths, saves output
    │   ├── usage_tracker.py           per-model token usage (least/most expensive prompts)
    │   ├── issues.py                  collects run warnings/errors for the evaluation summary
    │   └── utils.py                   helpers
    ├── evaluation/
    │   ├── main.py                    scorer, usage report writer, warnings summary
    │   ├── evaluation_report.md       written by hand from the scorer output
    │   └── usage_report.md            regenerated from the usage tracker on production runs only
    └── tests/{unit,feature}/          mirrors the source tree
```

Never import as `from code.…`: `code` is a standard-library module and shadows the folder.

---

## Setup

Requirements: Python 3.14, a Gemini API key, and the Tesseract OCR binary (used by `pytesseract` to read
screenshots; install with e.g. `brew install tesseract` or `apt install tesseract-ocr`).

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # then fill in the values below
```

| Variable | Purpose |
| --- | --- |
| `GEMINI_API_KEY` | API key for the LLM calls. Read from the environment only, never committed. |
| `GEMINI_MODEL_NAME` | Model used for intent classification. |
| `GEMINI_API_ENDPOINT` | API endpoint. |
| `USE_SAMPLE` | `True` runs the 32 sample requests; `False` runs all 518. |
| `INPUT_PRICE_PER_MTOK`, `OUTPUT_PRICE_PER_MTOK` | Optional USD per 1M tokens; enables the cost estimate in `usage_report.md`. |
| `APP_NAME`, `LOG_LEVEL` | Display name and log verbosity. |

## Run

From the repository root (the dataset path is `./dataset/`):

```bash
source .venv/bin/activate
python code/main.py
```

With `USE_SAMPLE=False` this processes all 518 requests. The pipeline writes the root-level `output.csv`
(`case_id,deletion_status,steps_json`, sorted by `case_id`), then automatically:

1. scores it against `dataset/sample_output.csv` (sample mode) or prints the status distribution only
   (full mode, which has no labels);
2. prints the token usage, including the **least and most expensive prompts** from the usage tracker;
3. in full mode only (`USE_SAMPLE=False`), rewrites `code/evaluation/usage_report.md` from the tracker's
   real counts (sample runs print usage to the console and leave the report untouched); and
4. prints every warning and error collected during the run, grouped by message.

Unclear requests are classified by the LLM. If it fails (outage, rate limit, no credits), the request is
treated as a deletion request and a warning is recorded (`VALIDITY_FALLBACK_ON_LLM_ERROR` in
`src/constants.py`), so a broken key shows up in the summary instead of silently skipping cases.

## Tests

```bash
pytest -q
```

The unit and feature test files are currently stubs.

---

## Output format

```text
case_id,deletion_status,steps_json
```

`deletion_status` is `COMPLETE`, `INCOMPLETE` or `NOT_APPLICABLE` (with `steps_json=[]`). Each step has
`step_no`, `phase`, `system_id`, `resource_id`, `operation`, `state` and `evidence_id`.

| Phase | Operations |
| --- | --- |
| FINDING | `REPORT_REMAINING_RECORD`, `REPORT_EXPOSED_PII`, `REPORT_ACTIVE_DATA_FLOW`, `REPORT_RESTORE_RISK` |
| REMEDIATION | `DISABLE_DATA_FLOW`, `BLOCK_RESTORE`, `DELETE_RECORD`, `REDACT_RECORD`, `ANONYMIZE_RECORD` |
| VERIFICATION | `VERIFY_RECORD_ABSENT`, `VERIFY_RECORD_PRESENT`, `VERIFY_RECORD_REDACTED`, `VERIFY_RECORD_ANONYMIZED`, `VERIFY_DATA_FLOW_DISABLED`, `VERIFY_RESTORE_BLOCKED` |

Findings and verification steps for a `COMPLETE` case cite the evidence that proves the state. Remediation
steps and the verification steps of an `INCOMPLETE` case describe future work and use an empty
`evidence_id`.

---

## Status

**Working:** the full pipeline runs end to end on the 32 samples: validity check, identity resolution through
current and historical emails, record-level evidence matching, per-resource state proof, rule-driven steps,
deterministic ordering, scoring, usage report and a warnings summary.

**Latest sample run** (LLM calls failed with `402 credits depleted`, so the 28 ambiguous requests used the
fallback; see `code/evaluation/evaluation_report.md`):

| Metric | Result |
| --- | --- |
| Status accuracy | 87.50% (28/32) |
| Step precision / recall / F1 (strict) | 0.66 / 0.62 / 0.63 |
| Field accuracy (paired steps) | system_id 100%, operation 90.3%, state 90.3%, evidence_id 94.4% |
| Exact sequence match | 15.6% |
| Phase-order violations | 0 |

**Open:**

- the live LLM path and the real token counts are unverified until the Gemini account has credits;
- exact step sequences match in only 5 of 32 cases;
- the final 518-case run has not been produced;
- `usage_report.md` and `evaluation_report.md` must be refreshed from that final run;
- unit and feature tests are stubs.

The detailed, prioritized list lives in [`CLAUDE.md`](./CLAUDE.md).

---

## Evaluation and reports

`code/evaluation/` is where the scorer and the two required reports live:

- `evaluation_report.md`: case-level status accuracy, step- and field-level accuracy, sequence accuracy,
  at least three custom evaluation cases, failures found and improvements made.
- `usage_report.md`: for the final full-dataset run, model providers and names, call counts, input and
  output tokens, total and per-request tokens, and estimated total and per-request cost. Token counts come
  from each API response through `src/usage_tracker.py`, not from estimates.

`dataset/sample_output.csv` is used only to score finished output, never to derive logic.

---

## Submission

| Item | Description |
| --- | --- |
| `code.zip` | Runnable solution, prompts, configuration, this `README.md` and the evaluation reports |
| `output.csv` | One row for each of the 518 requests |
| `chat_transcript` | The root `log.txt` |
| AI interview | Explanation of architecture, investigation approach, remediation planning and evaluation |

Submit at: https://www.hackerrank.com/contests/hackerrank-orchestrate-october26/challenges/ghost-data-still-exists

Package from the repository root without the dataset:

```bash
zip -r code.zip README.md code -x "*/__pycache__/*" "*/.venv/*" "*/.git/*" "*/.DS_Store"
```

Do not include `dataset/`, virtual environments, caches, nested archives, `.env`, API keys, credentials or
real personal data. Remove scratch files (`log copy*.txt`, `*_old.txt`, `dataset/evidence/_orig/`) before
packaging.

---

## Author

**Jason Monroe** — jason@jasonmonroe.com, Monroe Labs Co.

## License

Copyright © 2011-2026 Monroe Labs Co. All rights reserved.

No open-source license has been chosen and no `LICENSE` file exists in this repository. The dataset and the
challenge statement belong to HackerRank and are provided for the Orchestrate challenge only. All persons and
records in the dataset are fictional.
