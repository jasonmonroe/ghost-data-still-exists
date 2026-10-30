# code/tests/feature/pipelines/test_run_case_audit_pipeline.py
# Runs the real pipeline over the 32 sample cases (Gemini faked) and checks
# the output contract from problem_statement.md. Slow: ~15 s.

import collections
import json

import pandas as pd
import pytest
from src.constants import OP_PRIORITY, STEP_AGENT_PHASE_ORDER
from src.enums import DeletionStatus as DS

pytestmark = pytest.mark.slow

STEP_KEYS = {"step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"}

# problem_statement.md "Allowed Operations": operation -> (phase, state)
ALLOWED = {
    "REPORT_REMAINING_RECORD": ("FINDING", "PRESENT"),
    "REPORT_EXPOSED_PII": ("FINDING", "PRESENT"),
    "REPORT_ACTIVE_DATA_FLOW": ("FINDING", "ACTIVE"),
    "REPORT_RESTORE_RISK": ("FINDING", "ACTIVE"),
    "DISABLE_DATA_FLOW": ("REMEDIATION", "DISABLED"),
    "BLOCK_RESTORE": ("REMEDIATION", "BLOCKED"),
    "DELETE_RECORD": ("REMEDIATION", "ABSENT"),
    "REDACT_RECORD": ("REMEDIATION", "REDACTED"),
    "ANONYMIZE_RECORD": ("REMEDIATION", "ANONYMIZED"),
    "VERIFY_RECORD_ABSENT": ("VERIFICATION", "ABSENT"),
    "VERIFY_RECORD_PRESENT": ("VERIFICATION", "PRESENT"),
    "VERIFY_RECORD_REDACTED": ("VERIFICATION", "REDACTED"),
    "VERIFY_RECORD_ANONYMIZED": ("VERIFICATION", "ANONYMIZED"),
    "VERIFY_DATA_FLOW_DISABLED": ("VERIFICATION", "DISABLED"),
    "VERIFY_RESTORE_BLOCKED": ("VERIFICATION", "BLOCKED"),
}


@pytest.fixture(scope="module")
def run(dataset):
    """Run the pipeline once for this module, with Gemini replying 'True'."""
    import types

    import models.llm_model as llm_model
    from conftest import FakeInteractions
    from pipelines.run_case_audit_pipeline import run_case_audit_pipeline

    fake = FakeInteractions(["True"])
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(llm_model.genai, "Client", lambda **kw: types.SimpleNamespace(interactions=fake))
        rows, usage = run_case_audit_pipeline(dataset)
    return types.SimpleNamespace(rows=rows, usage=usage, fake=fake, dataset=dataset)


def test_one_row_per_request_in_order(run):
    assert [r[0] for r in run.rows] == list(run.dataset["deletion_requests"]["case_id"])


def test_statuses_are_from_the_allowed_set(run):
    assert {r[1] for r in run.rows} <= {DS.COMPLETE, DS.INCOMPLETE, DS.NOT_APPLICABLE}


def test_every_step_has_exactly_the_seven_fields(run):
    for case_id, _, steps in run.rows:
        for s in steps:
            assert set(s) == STEP_KEYS, (case_id, s)


def test_step_numbers_are_consecutive_from_one(run):
    for case_id, _, steps in run.rows:
        assert [s["step_no"] for s in steps] == list(range(1, len(steps) + 1)), case_id


def test_operation_phase_and_state_combinations_are_allowed(run):
    for case_id, _, steps in run.rows:
        for s in steps:
            assert ALLOWED[s["operation"]] == (s["phase"], s["state"]), (case_id, s)


def test_steps_are_ordered_by_phase_operation_system_resource(run):
    def key(s):
        return (STEP_AGENT_PHASE_ORDER[s["phase"]], OP_PRIORITY[s["operation"]],
                s["system_id"], s["resource_id"])

    for case_id, _, steps in run.rows:
        assert [key(s) for s in steps] == sorted(key(s) for s in steps), case_id


def test_complete_cases_only_verify_and_cite_proof(run):
    for case_id, status, steps in run.rows:
        if status == DS.COMPLETE:
            assert {s["phase"] for s in steps} <= {"VERIFICATION"}, case_id
            assert all(s["evidence_id"] for s in steps), case_id


def test_incomplete_cases_report_fix_and_reverify(run):
    for case_id, status, steps in run.rows:
        if status == DS.INCOMPLETE:
            phases = collections.Counter(s["phase"] for s in steps)
            assert phases["FINDING"] and phases["REMEDIATION"] and phases["VERIFICATION"], case_id
            for s in steps:
                if s["phase"] == "FINDING":
                    assert s["evidence_id"], (case_id, s)
                else:  # proposed fixes and future checks have no proof yet
                    assert s["evidence_id"] == "", (case_id, s)


def test_not_applicable_cases_have_no_steps(run):
    assert all(steps == [] for _, status, steps in run.rows if status == DS.NOT_APPLICABLE)


def test_model_is_only_asked_when_keywords_cannot_decide(run):
    calls = len(run.fake.calls)
    assert 0 < calls < len(run.rows)
    assert run.usage.totals().calls == calls


def test_status_accuracy_does_not_regress(run):
    """Scoring only (sample_output.csv is never used to derive logic)."""
    truth = pd.read_csv("dataset/sample_output.csv").set_index("case_id")["deletion_status"]
    correct = sum(truth[c] == s for c, s, _ in run.rows)
    assert correct / len(run.rows) >= 0.85, f"{correct}/{len(run.rows)}"


def test_rows_serialize_to_valid_json(run):
    for _, _, steps in run.rows:
        assert json.loads(json.dumps(steps)) == steps
