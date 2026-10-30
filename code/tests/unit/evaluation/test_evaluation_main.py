# code/tests/unit/evaluation/test_evaluation_main.py
# (Unique basename on purpose: pytest's default import mode needs it.)

import json
import re

import evaluation.main as E
import pandas as pd
import pytest
from src.issues import ERROR, WARNING, report_issue
from src.usage_tracker import UsageTracker

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def plain(capsys) -> str:
    return ANSI.sub("", capsys.readouterr().out)


def step(phase="VERIFICATION", resource="account_1", op="VERIFY_RECORD_ABSENT",
         state="ABSENT", evidence="evidence_1", system="account_service", no=1):
    return {"step_no": no, "phase": phase, "system_id": system, "resource_id": resource,
            "operation": op, "state": state, "evidence_id": evidence}


def frame(rows):
    return pd.DataFrame(
        [(c, s, json.dumps(steps)) for c, s, steps in rows],
        columns=["case_id", "deletion_status", "steps_json"],
    )


@pytest.fixture
def tracker():
    t = UsageTracker()
    t.record("gemini-test", 180, 2, "short prompt", "resp_small")
    t.record("gemini-test", 400, 20, "long prompt", "resp_big")
    return t


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
class TestParseSteps:
    def test_json_array(self):
        assert E.parse_steps('[{"a": 1}]') == [{"a": 1}]

    @pytest.mark.parametrize("raw", ["not json", None, float("nan"), '{"a": 1}'])
    def test_anything_else_is_empty(self, raw):
        assert E.parse_steps(raw) == []


def test_step_key_ignores_case_whitespace_and_step_no():
    a = step(no=1)
    b = {**step(no=7), "phase": " verification ", "state": "absent", "resource_id": " account_1 "}
    assert E.step_key(a) == E.step_key(b)


@pytest.mark.parametrize(
    ("tp", "n_pred", "n_true", "expected"),
    [
        (0, 0, 0, (1.0, 1.0, 1.0)),  # both empty: NOT_APPLICABLE match
        (2, 4, 2, (0.5, 1.0, 2 / 3)),
        (0, 3, 0, (0.0, 0.0, 0.0)),
        (0, 0, 3, (0.0, 0.0, 0.0)),
    ],
)
def test_prf(tp, n_pred, n_true, expected):
    assert E.prf(tp, n_pred, n_true) == pytest.approx(expected)


def test_pair_steps_is_one_to_one_on_phase_and_resource():
    preds = [step(), step(), step(resource="search_1")]
    trues = [step(), step(phase="FINDING")]
    pairs = E.pair_steps(preds, trues)
    assert len(pairs) == 1
    assert pairs[0] == (step(), step())


class TestEstimateCost:
    def test_none_without_prices(self, monkeypatch):
        monkeypatch.setattr(E, "INPUT_PRICE_PER_MTOK", None)
        assert E.estimate_cost(1_000, 1_000) is None

    def test_per_million_tokens(self, monkeypatch):
        monkeypatch.setattr(E, "INPUT_PRICE_PER_MTOK", "0.10")
        monkeypatch.setattr(E, "OUTPUT_PRICE_PER_MTOK", "0.40")
        assert E.estimate_cost(1_000_000, 500_000) == pytest.approx(0.30)


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------
def test_report_token_usage_prints_totals_and_extremes(tracker, capsys):
    E.report_token_usage(tracker)
    out = plain(capsys)
    assert "Total Model Calls:     2" in out
    assert "Total Tokens:          602" in out
    assert "resp_small" in out and "resp_big" in out


def test_report_token_usage_without_calls(capsys):
    E.report_token_usage(UsageTracker())
    assert "No external LLM model calls recorded" in plain(capsys)


def test_write_usage_report(tracker, outputs, monkeypatch):
    monkeypatch.setattr(E, "INPUT_PRICE_PER_MTOK", "1")
    monkeypatch.setattr(E, "OUTPUT_PRICE_PER_MTOK", "2")
    E.write_usage_report(tracker, request_count=32)

    text = outputs.usage_report.read_text()
    assert "**32 requests**" in text
    assert "| gemini-test | 2 | 580 | 22 | 602 |" in text
    assert "Total tokens per request (total ÷ requests): 18.81" in text
    assert "Estimated total cost: $0.000624" in text
    assert "resp_small" in text and "long prompt" in text


def test_write_usage_report_without_calls_or_prices(outputs, monkeypatch):
    monkeypatch.setattr(E, "INPUT_PRICE_PER_MTOK", None)
    E.write_usage_report(UsageTracker(), request_count=0)
    text = outputs.usage_report.read_text()
    assert "No model calls were recorded" in text
    assert "price not configured" in text


def test_report_run_issues(capsys):
    E.report_run_issues()
    assert "None." in plain(capsys)

    report_issue(WARNING, "Case case_01: x")
    report_issue(WARNING, "Case case_02: x")
    report_issue(ERROR, "boom")
    capsys.readouterr()
    E.report_run_issues()
    out = plain(capsys)
    assert "[ERROR] x1 boom" in out
    assert "[WARNING] x2 Case <case>: x" in out


def test_print_distribution(capsys):
    E.print_distribution(frame([("c1", "COMPLETE", []), ("c2", "COMPLETE", []), ("c3", "NOT_APPLICABLE", [])]))
    out = plain(capsys)
    assert "COMPLETE: 2" in out and "NOT_APPLICABLE: 1" in out and "Total rows: 3" in out


# --------------------------------------------------------------------------
# Scorer
# --------------------------------------------------------------------------
def test_perfect_predictions_score_100_percent(capsys):
    truth = frame([("c1", "COMPLETE", [step()]), ("c2", "NOT_APPLICABLE", [])])
    E.evaluate_predictions(truth.copy(), truth)
    out = plain(capsys)
    assert "Overall Accuracy: 100.00% (2/2 cases)" in out
    assert "Step F1 (strict):        1.0000" in out
    assert "Exact Sequence Match:   100.00%" in out
    assert "Phase Order Violations: 0" in out


def test_wrong_operation_counts_as_a_miss_and_a_field_error(capsys):
    truth = frame([("c1", "INCOMPLETE", [step(op="VERIFY_RECORD_ABSENT")])])
    pred = frame([("c1", "COMPLETE", [step(op="VERIFY_RECORD_PRESENT")])])
    E.evaluate_predictions(pred, truth)
    out = plain(capsys)
    assert "Overall Accuracy: 0.00% (0/1 cases)" in out
    assert "Step Precision (strict): 0.0000" in out
    assert re.search(r"operation\s+0\.00%", out)
    assert re.search(r"system_id\s+100\.00%", out)


def test_phase_order_violation_is_counted(capsys):
    truth = frame([("c1", "INCOMPLETE", [])])
    pred = frame([("c1", "INCOMPLETE", [step(phase="VERIFICATION"), step(phase="FINDING")])])
    E.evaluate_predictions(pred, truth)
    assert "Phase Order Violations: 1" in plain(capsys)


def test_missing_column_and_no_overlap(capsys):
    pred = frame([("x1", "COMPLETE", [])]).drop(columns=["steps_json"])
    E.evaluate_predictions(pred, frame([("c1", "COMPLETE", [])]))
    out = plain(capsys)
    assert "Expected column 'steps_json' missing" in out
    assert "No matching case_ids" in out


def test_diagnose_missing_steps(capsys):
    missing = E.diagnose_missing_steps([step(), step(resource="search_1")], [step()])
    assert [m["normalized_key"] for m in missing] == [("verification", "search_1")]
    assert "Total unmatched expected steps: 1" in plain(capsys)


def test_inspect_resource_id_differences(capsys):
    E.inspect_resource_id_differences(
        [step(resource="account_1"), step(phase="FINDING", resource="search-9")],
        [step(resource="account_1"), step(resource="tmp_search_9_copy")],
    )
    out = plain(capsys)
    assert "Phases in expected but NEVER predicted: {'FINDING'}" in out
    assert "Expected: 'search-9'" in out
    assert "Possible predicted matches: ['tmp_search_9_copy']" in out


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def test_run_project_evaluation_without_output_file(capsys):
    E.run_project_evaluation()
    assert "Generated output missing" in plain(capsys)


def test_run_project_evaluation_sample_mode(outputs, tracker, capsys):
    truth = pd.read_csv(E.REFERENCE_OUTPUT_PATH)
    truth.to_csv(outputs.output, index=False)  # perfect predictions
    E.run_project_evaluation(tracker, request_count=32)
    out = plain(capsys)
    assert "SAMPLE MODE" in out and "100.00% (32/32 cases)" in out
    assert "RUN WARNINGS & ERRORS" in out


def test_run_project_evaluation_production_mode(outputs, monkeypatch, capsys):
    monkeypatch.setattr(E, "REFERENCE_OUTPUT_PATH", None)
    frame([("c1", "COMPLETE", [])]).to_csv(outputs.output, index=False)
    E.run_project_evaluation()
    assert "PRODUCTION MODE: distribution only" in plain(capsys)


@pytest.mark.xfail(
    strict=True,
    reason="Open TODO (documented in README/CLAUDE.md): usage_report.md must only be "
    "written on production runs (USE_SAMPLE=False); sample runs still overwrite it.",
)
def test_sample_run_does_not_write_usage_report(outputs, tracker, monkeypatch):
    monkeypatch.setattr(E, "USE_SAMPLE", True)
    pd.read_csv(E.REFERENCE_OUTPUT_PATH).to_csv(outputs.output, index=False)
    E.run_project_evaluation(tracker, request_count=32)
    assert not outputs.usage_report.exists()
