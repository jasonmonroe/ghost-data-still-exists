# Evaluation Report — Ghost Data Still Exists

**Status: DRAFT.** Sections marked `PENDING` need numbers from a real run. As of this draft the pipeline
does not start (`PHONE_RE` is missing from `src/constants.py`, so `agents/evidence_agent.py` fails to import)
and `code/evaluation/main.py` is a stub with no scorer. No accuracy figure below has been measured, and none
should be filled in until the scorer has produced it.

Scoring rule: `dataset/sample_output.csv` is used **only** to score finished output. It is never read to
derive logic, thresholds or labels.

## 1. Case-level deletion-status accuracy

Run: 32 sample cases (`USE_SAMPLE=True`). Compare `deletion_status` per `case_id`.

| Metric | Result |
| --- | --- |
| Overall accuracy | PENDING |
| `COMPLETE` precision / recall | PENDING |
| `INCOMPLETE` precision / recall | PENDING |
| `NOT_APPLICABLE` precision / recall | PENDING |
| Confusion matrix (3×3) | PENDING |

Also report the same table for the full 518-case run's status distribution (no labels available, so
distribution only).

## 2. Step-level and field-level accuracy

Definitions the scorer will use:

- **Step-level:** a predicted step counts as correct when all seven fields match one expected step.
  Precision, recall and F1 over steps per case, then averaged.
- **Field-level:** per field accuracy for `phase`, `system_id`, `resource_id`, `operation`, `state`,
  `evidence_id` over steps matched on `(resource_id, phase)`.
- **Structure:** every `steps_json` parses as a JSON array; each step has exactly the seven required
  fields; `step_no` is `1..n`; operation and state come from the allowed lists.

| Metric | Result |
| --- | --- |
| Step precision / recall / F1 | PENDING |
| `phase` accuracy | PENDING |
| `system_id` accuracy | PENDING |
| `resource_id` accuracy | PENDING |
| `operation` accuracy | PENDING |
| `state` accuracy | PENDING |
| `evidence_id` accuracy | PENDING |
| Rows with valid JSON / valid schema | PENDING |

How the fields are produced (design, from the code):

- `resource_id` / `system_id`: resources come from the case's own workflow events, from evidence chunks that
  contain a user identifier, and from `LINK_RESOURCE_IDENTITY` events. The owner system comes from the
  evidence's own system fields, with `TARGET_SYSTEMS` as a fallback.
- `state`: the newest evidence captured after the resource's last activity decides it. Absence is proven by
  a full snapshot that lists the same resource type without this record, or by `rows=0` / 404 / `NOT_FOUND`.
  Data flows and backups read `enabled` / `restore_allowed` from the evidence.
- PII detection (`REPORT_EXPOSED_PII`): `exposed_fields` is computed from `PERSONAL_INFO_FIELDS` on the proof
  record, with whole-token identifier matching (`user_01` does not match `user_010`).
- `evidence_id`: findings and `COMPLETE`-case verification cite the proving `file_id`; remediation and
  `INCOMPLETE`-case verification use `""`.

## 3. Sequence accuracy

Ordering is enforced in one place, `StepsAgent.compile()`, by sorting every step on:

1. phase: `FINDING` (1) → `REMEDIATION` (2) → `VERIFICATION` (3) (`STEP_AGENT_PHASE_ORDER`);
2. operation priority within the phase (`OP_PRIORITY`):
   - findings: remaining record, exposed PII, active data flow, restore risk;
   - remediation: disable data flow, block restore, delete, redact, anonymize;
   - verification: absent, present, redacted, anonymized, data flow disabled, restore blocked;
3. `system_id`, then `resource_id` ascending.

`step_no` is then assigned `1..n` after sorting. This puts data flows and unsafe restores before any record
change, as the policy requires. Output rows are sorted by `case_id` in `DataHandler.save`.

Known gap: the policy also says downstream copies are processed before their source records "when the
dependency requires it". The current sort has no dependency graph, only the operation order above.

| Metric | Result |
| --- | --- |
| Exact-sequence match per case | PENDING |
| Phase-order violations in output | PENDING (expected 0 by construction; verify) |
| Operation-order violations in output | PENDING (expected 0 by construction; verify) |

## 4. Custom evaluation cases

These cases are designed from `deletion_rules.csv` and the problem statement, not from sample answers. They
are **designed but not yet executed**. Each needs a small fixture (identity row, activity rows, an evidence
file) under the test fixtures before it can be run.

| # | Scenario | Edge case exercised | Expected outcome |
| --- | --- | --- | --- |
| C1 | Deletion request; account is gone but a `data_flow` is still `enabled` and an export of the user still exists | Active data flow must be disabled **before** the dependent record is deleted | `INCOMPLETE`; findings: active data flow, remaining export; remediation order: `DISABLE_DATA_FLOW`, then `DELETE_RECORD`; verification: `VERIFY_DATA_FLOW_DISABLED`, `VERIFY_RECORD_ABSENT`; remediation/verification `evidence_id` empty |
| C2 | Deletion request; all copies deleted; a security audit record inside its retention period and an account tombstone with only `user_id` remain | Retained records must stay and must not be deleted | `COMPLETE`; only `VERIFY_RECORD_PRESENT` steps citing proof evidence; no `DELETE_RECORD` |
| C3 | Request text is a data export / marketing opt-out request, though other fields look like a deletion case | Non-deletion intent | `NOT_APPLICABLE`, `steps_json=[]` |
| C4 | Request email is a historical email found only in `user_audit_log`; the resource appears in evidence by old email hash | Historical identity resolution | Resolved to the same `user_id`; resource found; state proven from evidence at or before `audit_at` |
| C5 | A backup archive with `restore_allowed=true` holds the user's data | Restore risk | `INCOMPLETE`; `REPORT_RESTORE_RISK`, `BLOCK_RESTORE`, `VERIFY_RESTORE_BLOCKED` |
| C6 | A later evidence file (captured after `audit_at`) shows the record present | Future evidence must be ignored | Status computed from evidence at or before `audit_at` only |

Results: PENDING.

## 5. Failures found and improvements made

Bugs found during development and what changed. Each was found by reading or running the code; none was
found by an automated test, because the tests are still stubs.

| Failure | Impact | Fix |
| --- | --- | --- |
| `CATEGORY_BY_PREFIX` defined twice in `constants.py`; the second overrode the first and used names missing from `deletion_rules.csv` (`EXPORT_RECORD`, `IDENTITY_TOMBSTONE`) and dropped `account`/`email_delivery` | An unknown category finds no rule and silently returns `COMPLETE`; startup crashed on the validator | One mapping aligned to the rules file (`USER_EXPORT`, `ACCOUNT_TOMBSTONE`, …) |
| Silent `COMPLETE` on unmapped categories | A violation could be hidden by a typo | `DeletionRuleAgent.__init__` validates every mapped category against the rules file and raises, except process categories (`DATA_FLOW`, `BACKUP_ARCHIVE`) |
| Finding operation chosen from `exposed_fields` rather than the rule action | A DELETE record reported as `REPORT_EXPOSED_PII` | `FINDING_OP_BY_ACTION` maps rule action to finding operation |
| Data flows and backups treated as records with hardcoded attributes | Wrong remediation operations | `PROCESS_CATEGORIES` / `PROCESS_FLAGS`; state read from evidence; `DISABLE_DATA_FLOW` and `BLOCK_RESTORE` |
| `exposed_fields` built as a tuple containing a set | Not a `frozenset`, so the frozen dataclass could not hash it | `frozenset(...)` around the exposed-field set |
| Substring matching in exposed-field detection | `user_01` matched `user_010` | Shared whole-token matchers `_term_in_text` / `_phones_in` used by both `_mentions_user` and `_get_exposed` |
| Search terms computed inside `_filter` as a side effect | `_get_exposed` / `_mentions_user` raised or used empty terms if called first | Terms built once in `search()` |
| Repeated inline logic in `_get_search_terms` | Hard to reason about and to test | `normalizers` dict plus one `values_for` helper |
| `StepsAgent` reused across cases | Steps could leak between cases | A new `StepsAgent` per case |
| UNKNOWN-state findings produced steps | Steps without proof | Findings in `UNKNOWN` state are dropped in `EvidenceAgent.search` |

Open failures at the time of writing (to fix, then re-measure):

- `PHONE_RE` missing from `src/constants.py`; the program fails at import.
- `LlmModel.get_response` runs `json.loads` on a bare `True`/`False`, so validity silently becomes `False`.
- `_filter_by_user` returns all identities when no unique user matches, and `audit_by_case` then audits the
  wrong user.
- `DataHandler.save` writes `dataset/output.csv`; the contract needs repo-root `output.csv`.
- RETAIN semantics: a required-retained record that has gone ABSENT is not flagged.
- Workflow-window noise: the same resource appears for different users.
- No scorer, no automated tests.

## 6. How to reproduce

```bash
source .venv/bin/activate
USE_SAMPLE=True python code/main.py      # then run the scorer once it exists
```
