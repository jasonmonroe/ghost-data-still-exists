# CLAUDE.md — Ghost Data Still Exists (hackathon mode)

@AGENTS.md

Instructions for Claude Code working in this repo. Read fully before acting.

**`AGENTS.md` (imported above) is the source of truth** for session logging (append every turn to
`log.txt` in the repo root), the output contract and the submission rules. Follow it exactly.
This file adds project-specific conventions; if anything here conflicts with `AGENTS.md`, `AGENTS.md` wins.

## What this project is

HackerRank Orchestrate (Oct 2026) challenge, worked as if the hackathon is still running.
An AI-assisted deletion-audit agent: for each request in `dataset/deletion_requests.csv`, decide
`COMPLETE` / `INCOMPLETE` / `NOT_APPLICABLE` and emit ordered `steps_json` (findings →
remediation → verification). Full contract: `problem_statement.md`.

## Working with Jason (read this)

- Jason is a senior PHP/Laravel engineer (15 yrs) building production Python skills. Bridge new
  Python concepts to their Laravel/PHP equivalent in one line when it helps.
- **Tutor, not ghostwriter.** Prefer small, reviewable diffs. Explain *why* for any non-obvious change.
  He must be able to explain every committed line (AI interview / job interviews).
- **Plan before code** on anything larger than one function. Wait for approval before multi-file edits.
- **Run after every change.** Never hand back code that hasn't been executed. Show the command and result.
- Don't rewrite whole files unless asked; show/modify only the relevant sections.
- Be direct and candid; no filler.
- Answer questions and review; always ask before writing code since Jason's coding style isn't as advanced as
  Claudes.

## Run / test

```bash
source .venv/bin/activate            # Python 3.14
python code/main.py                  # full pipeline (USE_SAMPLE=True → 32 sample cases)
pytest -q                            # all tests (currently stubs, see status)
```

Config comes from `.env` (copy `.env.example`): `GEMINI_API_KEY`, `GEMINI_MODEL_NAME`,
`GEMINI_API_ENDPOINT`, `USE_SAMPLE` (`True` → `sample_deletion_requests.csv`), `APP_NAME`, `LOG_LEVEL`.
Run from the repo root (dataset path is `./dataset/`). `main.py` calls `load_dotenv()` before importing
the app, so constants see the env vars.

Imports are rooted at `code/` (e.g. `from agents.evidence_agent import EvidenceAgent`,
`from src.constants import DATASET_PATH`). **Never** `from code.…` — `code` is a stdlib module and
shadows the folder.

## Layout

```
code/
  main.py                                entry: evaluation stub → audit pipeline → DataHandler.save
  pipelines/run_case_audit_pipeline.py   loops cases → CaseAuditorAgent.audit_by_case → output rows
  agents/case_auditor_agent.py           per case: validity → identity → evidence → status → steps
  agents/evidence_agent.py               per case: user's resources + state + proof (ResourceFinding)
  agents/deletion_rule_agent.py          category lookup + rule action + evaluate(finding) → COMPLETE/INCOMPLETE
  agents/steps_agent.py                  new instance per case; collects steps, compile() sorts + numbers
  models/llm_model.py                    Gemini client (Interactions API), retries, usage recording
  src/data_handler.py                    loads CSVs, USE_SAMPLE swap, saves output
  src/constants.py, src/enums.py         config, regexes, category/op/state mappings, prompts
  src/usage_tracker.py, src/utils.py     token usage per model (for usage_report), helpers
  evaluation/main.py                     STUB — scorer / report generation goes here
  tests/unit/…, tests/feature/…          mirror the source tree; files named test_<module>.py (stubs)
```

Per-case flow (`CaseAuditorAgent.audit_by_case`): `_check_validity` (keyword lists in constants, LLM only
when neither list matches) → `_filter_by_user` (current or historical email → one user) →
`EvidenceAgent.search` → `DeletionRuleAgent.evaluate` per finding → `_finalize` builds steps via
`StepsAgent` → `[case_id, status, steps]`.

## Core design decisions (keep these)

1. **Claims vs proof.** `system_activity.csv` and `reported_status` are claims. State comes from
   evidence files captured `<= audit_at`. Cite evidence `file_id`s, not `activity_id`s.
2. **Identity first.** Resolve the request email via `user_identities` **or** historical values in
   `user_audit_log`. Search terms = user_id, all emails (lowercased), all email hashes
   (stored + `sha256(email.lower())`), phones as digits. **Never names or timestamps** (decoys).
3. **Record-level matching.** A resource belongs to the user only if it co-occurs with a user
   identifier in the same SQL row / JSON record / text line / **log trace_id group**, or via
   `LINK_RESOURCE_IDENTITY` activity, or the case's own workflow events (`reported_at ± 10 min`).
4. **Absence proof.** Newest evidence captured after the record's last activity decides state.
   A full snapshot (SQL/JSON) that lists other records of the same type but not this one ⇒ ABSENT.
   A lookup with `rows=0` / 404 / NOT_FOUND ⇒ ABSENT. Logs alone can't prove absence by omission.
5. **Owner system** comes from the evidence's own `system`/`data_store` fields per resource prefix
   (`account` → `account_service`), not from the last `target_system` in activity.
6. **Code decides, LLM perceives.** Deterministic code owns identity, matching, rules, status,
   step generation and ordering. LLM only for: request-intent classification (multilingual),
   extracting facts from images/PDFs, and ambiguous rule conditions. Cache every LLM call.
7. **Parse each evidence file once** (cache by path); filter parsed records per case.
8. `ResourceFinding` (frozen dataclass: `system_id`, `resource_id`, `category`, `state`, `evidence_id`,
   `exposed_fields: frozenset`, `timeline`) is the contract between EvidenceAgent and DeletionRuleAgent.
   Findings with `UNKNOWN` state are dropped in `EvidenceAgent.search`.
9. **Category mapping is single-sourced.** `CATEGORY_BY_PREFIX` (one dict, in `constants.py`) must use
   category names that exist in `deletion_rules.csv`. `DeletionRuleAgent.__init__` raises at startup if a
   mapped category is missing from the rules file (except `PROCESS_CATEGORIES`: `DATA_FLOW`,
   `BACKUP_ARCHIVE`). An unmapped category silently becomes COMPLETE, so never weaken that check.
10. **Processes are not records.** `DATA_FLOW` has no CSV rule → `DISABLE_DATA_FLOW`; `BACKUP_ARCHIVE`
    → `BLOCK_RESTORE` (its CSV RETAIN covers the archive, not its restore path). State comes from the
    evidence (`PROCESS_FLAGS`: `enabled`, `restore_allowed`; ACTIVE vs DISABLED/BLOCKED).
11. **Finding op follows the rule action** (`FINDING_OP_BY_ACTION`): DELETE → `REPORT_REMAINING_RECORD`,
    REDACT/ANONYMIZE → `REPORT_EXPOSED_PII`, BLOCK_RESTORE → `REPORT_RESTORE_RISK`,
    DISABLE_DATA_FLOW → `REPORT_ACTIVE_DATA_FLOW`. `exposed_fields` (from `PERSONAL_INFO_FIELDS`) decides
    whether a REDACT/ANONYMIZE record is a violation.
12. **Status rule:** a case is INCOMPLETE if any finding violates its rule; no findings → COMPLETE;
    invalid/non-deletion request → NOT_APPLICABLE with `[]`. In an INCOMPLETE case every verification
    step is future work (empty `evidence_id`); in a COMPLETE case verification cites the proof file.

## Hard rules

- **Do not read `dataset/sample_output.csv` to derive logic.** It is only for scoring finished output
  (evaluation report). Reason from inputs.
- No hardcoded labels, case-specific shortcuts, or resource-number patterns (e.g. `account_001 ↔ user_01`).
- Deterministic output: sorted rows, stable step ordering, `json.dumps(..., sort_keys=True)`.
  Final file goes to repo-root `output.csv` (AGENTS.md §6.3).
- Step order: FINDING → REMEDIATION → VERIFICATION; within a phase by operation order in
  `problem_statement.md`, then `system_id`, then `resource_id`; `step_no` 1..n.
- Secrets only from env vars / `.env` (`GEMINI_API_KEY`). Never log or print the key. Never name an app key `ANTHROPIC_API_KEY`
  (it hijacks Claude Code billing).
- Keep scratch files (`log copy*.txt`, `*_old.txt`, `dataset/evidence/_orig/`) out of `code.zip`;
  only `log.txt` is the transcript. Never include `dataset/`, `.venv`, or `.env`.
- No `eval()`. Read CSVs with `dtype=str` where IDs/phones matter.

## Current status / next steps (updated 2026-10-29)

### Blocker right now
- `python code/main.py` fails at import: `evidence_agent.py` imports `PHONE_RE` from `src.constants`,
  but it is no longer defined there (`PHONE_LEN` is). Restore the regex before anything else runs.
  (Also needs `pip install -r requirements.txt` — `google-genai` was missing from the venv.)

### Done (by reading code; re-verify with a run once the blocker is fixed)
- `CATEGORY_BY_PREFIX` aligned with `deletion_rules.csv` + startup validator; `legal_hold`, `tombstone`,
  `email_delivery` mapped; `SYSTEM_BY_PREFIX` replaced by evidence-derived owner system
  (`_build_system_by_prefix`, `TARGET_SYSTEMS` fallback).
- Finding op from rule action; process (data flow / backup) state read from evidence; field-level
  `exposed_fields`; shared token-boundary matchers `_term_in_text` / `_phones_in`; search terms built once
  per case in `search()`; `StepsAgent` created per case and sorts by phase → op priority → system → resource.

### Fix next (priority order)
1. Restore `PHONE_RE`; run all 32 samples; record status counts. Score against `sample_output.csv`
   only after output is produced (never to derive logic).
2. **Real LLM path is untested and likely wrong:** `LlmModel.get_response` does `json.loads(content)` on a
   bare `True`/`False` → JSONDecodeError → `{"error": True}` → validity silently False. Also a debug
   `print(response)` in `_process_response`; verify Interactions API usage field names
   (`prompt_tokens`/`completion_tokens` vs `total_input_tokens`/…) and `response.model` on one real response.
   Design says cache every LLM call — there is no cache yet.
3. `_filter_by_user` fallback (no unique user) returns ALL identities, and `audit_by_case` only checks
   `user_identities is None`, so a non-unique/unknown email audits the wrong user via `.iloc[0]`.
4. `DataHandler.save` writes `dataset/output.csv` and `json.dumps` without `sort_keys`; contract wants
   repo-root `output.csv`. `DataHandler._load_evidence` only collects `evidence/records/` paths — confirm
   that is all `EvidenceAgent` needs (it reads via `evidence_files.csv`).
5. **Open question — RETAIN semantics** (`LEGAL_HOLD_RECORD`, `SECURITY_AUDIT_LOG`, `ACCOUNT_TOMBSTONE`):
   `evaluate()` never flags a retained record that has gone ABSENT, and verification mirrors the observed
   state. Decide how "required retained records remain available" is enforced.
6. Workflow-window noise: same records appear for different users (`account_9335` in cases 13/18/20).
7. Evaluation: `code/evaluation/main.py` is a stub; no scorer yet. Then `evaluation/evaluation_report.md`
   (accuracy, ≥3 custom cases, failures/improvements), `evaluation/usage_report.md` from `UsageTracker`,
   full 518 run, README with setup/run instructions.
8. Tests are stubs; `pytest` fails at collection (`tests/unit/src/test_utils.py` IndentationError; no
   pytest `pythonpath = code`). Jason deferred tests — don't touch them unless asked.

### Way of working
- Jason writes the code in his own style; Claude explains logic, gives hints (hint ladder), runs the
  code and reviews. Ignore methods marked `@deprecated`.
