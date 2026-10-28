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

## Run / test

```bash
source .venv/bin/activate            # Python 3.14
python code/main.py                  # full pipeline (USE_SAMPLE=True → 32 sample cases)
pytest -q                            # all tests
pytest code/tests/unit -q            # fast, run on every save
pytest -m "not slow"                 # skip OCR / full-pipeline tests
```

Imports are rooted at `code/` (e.g. `from agents.evidence_agent import EvidenceAgent`,
`from src.constants import DATASET_PATH`). **Never** `from code.…` — `code` is a stdlib module and
shadows the folder.

## Layout

```
code/
  main.py                          entry point
  pipelines/run_case_audit_pipeline.py   loops cases → auditor → output rows
  agents/case_auditor_agent.py     per case: validity → identity → evidence → rules → steps
  agents/evidence_agent.py         per case: user's resources + state + proof (ResourceFinding)
  agents/deletion_rule_agent.py    TODO: findings × deletion_rules → required action
  agents/steps_agent.py            TODO: actions → ordered steps_json
  src/data_handler.py              loads CSVs + evidence paths
  src/constants.py, src/enums.py   config, allowed statuses/operations/states
  tests/unit/…, tests/feature/…    mirror the source tree; files named test_<module>.py
```

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
8. `ResourceFinding` (frozen dataclass) is the contract between EvidenceAgent and DeletionRuleAgent.

## Hard rules

- **Do not read `dataset/sample_output.csv` to derive logic.** It is only for scoring finished output
  (evaluation report). Reason from inputs.
- No hardcoded labels, case-specific shortcuts, or resource-number patterns (e.g. `account_001 ↔ user_01`).
- Deterministic output: sorted rows, stable step ordering, `json.dumps(..., sort_keys=True)`.
- Step order: FINDING → REMEDIATION → VERIFICATION; within a phase by operation order in
  `problem_statement.md`, then `system_id`, then `resource_id`; `step_no` 1..n.
- Secrets only from env vars / `.env` (`MODEL_API_KEY`). Never name an app key `ANTHROPIC_API_KEY`
  (it hijacks Claude Code billing).
- No `eval()`. Read CSVs with `dtype=str` where IDs/phones matter.

## Current status / next steps

- EvidenceAgent works on sample cases: case_01, case_02 → `account_00x` ABSENT `evidence_54`;
  case_05 → `account_005` PRESENT `evidence_54` (failover replica copy).
- Known issue: workflow window adds noise (case_01 also returns `cache_7537`, UNKNOWN). Try limiting
  to deletion-type events and measure across all 32 samples.
- TODO in `ResourceFinding`: `category` (prefix → data_category), `exposed_fields`, `attributes`
  (`enabled`, `restore_allowed`, `retention_until`).
- Then: DeletionRuleAgent → StepsAgent → wire `_get_output` (currently `json.load` on a list),
  remove `sys.exit(0)` in the pipeline loop, evaluation + usage reports.
