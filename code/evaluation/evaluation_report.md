# Evaluation Report — Ghost Data Still Exists

**Status: sample run measured; full 518-case run and live-LLM run pending.** All numbers below come from one
run of `python code/main.py` on the 32 sample cases (`USE_SAMPLE=True`), scored by `code/evaluation/main.py`.

**Important caveat:** in that run every one of the 28 requests that needed the LLM hit the validity fallback
(`VALIDITY_FALLBACK_ON_LLM_ERROR = True`, treat as deletion) because the Gemini account returned
`402 prepayment credits are depleted`. The numbers therefore measure the evidence/rules/steps pipeline plus
the fallback, not the LLM classifier. The 32 samples contain no `NOT_APPLICABLE` cases, so that class is not
exercised. Re-run after billing is restored and update this file.

Scoring rule: `dataset/sample_output.csv` is used **only** to score finished output. It is never read to
derive logic, thresholds, or labels. The output is written to the repository root (`./output.csv`).

## 1. Case-level deletion-status accuracy

Run: 32 sample cases. Compare `deletion_status` per `case_id`.

| Metric | Result |
| --- | --- |
| Overall accuracy | 87.50% (28/32) |
| `COMPLETE` precision / recall / F1 | 0.75 / 0.90 / 0.82 (support 10) |
| `INCOMPLETE` precision / recall / F1 | 0.95 / 0.86 / 0.90 (support 22) |
| `NOT_APPLICABLE` | no cases in the samples |

Confusion matrix (rows = expected, columns = predicted):

| | pred COMPLETE | pred INCOMPLETE |
| --- | --- | --- |
| **true COMPLETE** | 9 | 1 |
| **true INCOMPLETE** | 3 | 19 |

Misses: `case_03` (predicted INCOMPLETE, expected COMPLETE) and `case_07`, `case_10`, `case_12` (predicted
COMPLETE, expected INCOMPLETE). The scorer averages only over labels that have cases, so an absent class does
not drag the macro average down.

For the full 518-case run there are no labels, so the scorer prints the status distribution only.

## 2. Step-level and field-level accuracy

Definitions used by the scorer (`code/evaluation/main.py`):

- **Step-level (strict, one-to-one):** a predicted step is correct only if `phase`, `system_id`,
  `resource_id`, `operation`, `state` and `evidence_id` all equal one expected step, and each expected step can
  be matched by at most one prediction. Precision, recall and F1 are computed per case, then averaged.
  (`step_no` is the position and is covered by the sequence check.) Two empty step lists count as a perfect
  match.
- **Field-level:** predicted and expected steps are paired one-to-one on `(phase, resource_id)`; accuracy is
  then reported per remaining field.
- **Structure and schema:** every `steps_json` parses as a JSON array, each step has exactly the seven
  required fields, and `step_no` runs `1..n`.

| Metric | Result |
| --- | --- |
| Step precision (strict) | 0.6622 |
| Step recall (strict) | 0.6163 |
| Step F1 (strict) | 0.6268 |
| Steps predicted / expected | 180 / 193 |
| Paired steps (by phase + resource_id) | 144 |
| `system_id` accuracy (paired) | 100.00% |
| `operation` accuracy (paired) | 90.28% |
| `state` accuracy (paired) | 90.28% |
| `evidence_id` accuracy (paired) | 94.44% |
| Rows with valid JSON / valid schema | 32 / 32 |

`phase` and `resource_id` are the pairing keys, so they are not scored separately. Because 144 of 193
expected steps were paired, about 49 expected steps have no prediction with the same phase and resource, which
is the main source of the low strict recall.

How the fields are produced (design, from the code):

- `resource_id` / `system_id`: resources come from the case's own workflow events, from evidence chunks that
  contain a user identifier, and from `LINK_RESOURCE_IDENTITY` events. The owner system comes from the
  evidence's own system fields, with `TARGET_SYSTEMS` as a fallback.
- `state`: the newest evidence captured after the resource's last activity decides it. Absence is proven by a
  full snapshot that lists the same resource type without this record, or by `rows=0` / 404 / `NOT_FOUND`.
  Data flows and backups read `enabled` / `restore_allowed` from the evidence.
- PII detection (`REPORT_EXPOSED_PII`): `exposed_fields` is computed from `PERSONAL_INFO_FIELDS` on the proof
  record, with whole-token identifier matching (`user_01` does not match `user_010`).
- `evidence_id`: findings and `COMPLETE`-case verification cite the proving `file_id`; remediation and
  `INCOMPLETE`-case verification use `""`.

## 3. Sequence accuracy

Ordering is enforced in `StepsAgent.compile()`, by sorting every step on:

1. phase: `FINDING` (1) → `REMEDIATION` (2) → `VERIFICATION` (3) (`STEP_AGENT_PHASE_ORDER`);
2. operation priority within the phase (`OP_PRIORITY`):
   - findings: remaining record, exposed PII, active data flow, restore risk;
   - remediation: disable data flow, block restore, delete, redact, anonymize;
   - verification: absent, present, redacted, anonymized, data flow disabled, restore blocked;
3. `system_id`, then `resource_id` ascending.

`step_no` is assigned `1..n` after sorting. This places data flows and unsafe restores before record changes.
Output rows are sorted by `case_id` in `DataHandler.save`. Known gap: there is no dependency graph for
"process downstream copies before their source records".

| Metric | Result |
| --- | --- |
| Exact-sequence match per case (full step list equal to expected) | 15.62% (5/32) |
| Phase-order violations in output | 0 |
| Operation-order violations in output | not measured by the scorer |

The exact-sequence rate is low mainly because it requires every step of the case to match, so a single
missing or extra step fails the case. It is the weakest metric and the first place to debug.

## 3b. Warnings and errors during the run

The evaluation prints every warning and error collected by `src/issues.py` during the run, grouped by message.
For the run above:

| Level | Count | Message |
| --- | --- | --- |
| ERROR | 28 | LLM API error code 402: prepayment credits are depleted |
| WARNING | 28 | Case `<case>`: LLM could not classify the request. Defaulting validity to True. |

No evidence-file, OCR or JSON-decoding errors were reported.

## 4. Custom evaluation cases

These cases are designed from `deletion_rules.csv` and the problem specification. Each exercises specific edge cases under test fixtures.

| # | Scenario | Edge case exercised | Expected outcome |
| --- | --- | --- | --- |
| C1 | Deletion request; account is gone but a `data_flow` is still `enabled` and an export of the user still exists | Active data flow must be disabled **before** the dependent record is deleted | `INCOMPLETE`; findings: active data flow, remaining export; remediation order: `DISABLE_DATA_FLOW`, then `DELETE_RECORD`; verification: `VERIFY_DATA_FLOW_DISABLED`, `VERIFY_RECORD_ABSENT`; remediation/verification `evidence_id` empty |
| C2 | Deletion request; all copies deleted; a security audit record inside its retention period and an account tombstone with only `user_id` remain | Retained records must stay and must not be deleted | `COMPLETE`; only `VERIFY_RECORD_PRESENT` steps citing proof evidence; no `DELETE_RECORD` |
| C3 | Request text is a data export / marketing opt-out request, though other fields look like a deletion case | Non-deletion intent | `NOT_APPLICABLE`, `steps_json=[]` |
| C4 | Request email is a historical email found only in `user_audit_log`; the resource appears in evidence by old email hash | Historical identity resolution | Resolved to the same `user_id`; resource found; state proven from evidence at or before `audit_at` |
| C5 | A backup archive with `restore_allowed=true` holds the user's data | Restore risk | `INCOMPLETE`; `REPORT_RESTORE_RISK`, `BLOCK_RESTORE`, `VERIFY_RESTORE_BLOCKED` |
| C6 | A later evidence file (captured after `audit_at`) shows the record present | Future evidence must be ignored | Status computed from evidence at or before `audit_at` only |

Results: not yet executed (fixtures still to be built).

## 5. Failures found and improvements made

Summary of key fixes and refactorings applied during development:

| Failure | Impact | Fix |
| --- | --- | --- |
| `CATEGORY_BY_PREFIX` mismatch with `deletion_rules.csv` | Unmapped categories caused silent `COMPLETE` status defaults | Consolidated `CATEGORY_BY_PREFIX` dictionary matching rule categories (`USER_EXPORT`, `ACCOUNT_TOMBSTONE`, etc.) |
| Silent `COMPLETE` on unmapped categories | Mismatched categories bypassed evaluation | Added startup assertion in `DeletionRuleAgent.__init__` validating categories against rule files |
| Finding operation misassignment | DELETE actions mapped to `REPORT_EXPOSED_PII` | Corrected `FINDING_OP_BY_ACTION` mapping to emit `REPORT_REMAINING_RECORD` |
| Process resource handling | Data flows and backups defaulted to record-level steps | Extended `StepsAgent` and `_finalize()` with `DISABLE_DATA_FLOW` and `BLOCK_RESTORE` mappings |
| Output CSV location mismatch | Files written to `dataset/output.csv`, overwriting the blank template | `OUTPUT_FILEPATH` now points at the repo root `./output.csv` |
| `json.loads("True")` in the LLM wrapper | Every validity answer parsed as an error and became `NOT_APPLICABLE` | `_parse_content` returns a bool for `True`/`False`; failures use an explicit, logged fallback |
| Wrong exception classes | The Interactions API errors were never caught or retried | Catch `APIStatusError` / `APIConnectionError`; retry 429, 5xx and connection errors |
| Wrong usage field names | `prompt_tokens`/`completion_tokens` do not exist; usage would be zero or raise | Use `total_input_tokens`, `total_output_tokens`, `total_thought_tokens` (checked in SDK types) |
| `UsageTracker` least/most logic always true | Least/most prompts overwritten on every call | Compare against the stored token count; fixed the `response_id` key |
| Lenient step metric | Matched on `(resource_id, phase)` only, so wrong operations counted as correct | Strict one-to-one matching on six fields plus per-field accuracy |
| `USE_SAMPLE` parsed two ways | Pipeline could run 518 cases while scoring against 32 | Parsed once as a bool in `constants.py` |
| Warnings only printed inline | Easy to miss in a 500-line run | `src/issues.py` collects them; the evaluation prints a grouped summary |
| One long scorer function | Hard to read and to change the metrics | Split the scorer into small helpers (`parse_steps`, `pair_steps`, `prf`, `print_distribution`) |

## 6. How to reproduce

```bash
source .venv/bin/activate
USE_SAMPLE=True python code/main.py      # writes ./output.csv, then scores it, then prints usage and issues
```

`usage_report.md` is regenerated from the usage tracker only at the end of a production run
(`USE_SAMPLE=False`); sample runs print usage to the console and leave the file untouched. The report
therefore always reflects the most recent full 518-case run. Optional `INPUT_PRICE_PER_MTOK` / `OUTPUT_PRICE_PER_MTOK` in `.env` turn on the
cost estimate. 