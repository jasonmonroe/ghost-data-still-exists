# code/tests/unit/agents/test_case_auditor_agent.py

import json

import pandas as pd
import pytest
from agents.case_auditor_agent import CaseAuditorAgent
from src.enums import DeletionStatus as DS
from src.enums import StepStates as St
from src.issues import get_issues


@pytest.fixture
def auditor(dataset, fake_gemini):
    fake_gemini(["True"])
    return CaseAuditorAgent(dataset)


def load_case(auditor, dataset, case_id):
    df = dataset["deletion_requests"]
    case = df[df["case_id"] == case_id].iloc[0]
    for col, value in case.items():
        setattr(auditor, col, value)
    from agents.steps_agent import StepsAgent

    auditor._steps_agent = StepsAgent()
    return case


# --------------------------------------------------------------------------
# Validity
# --------------------------------------------------------------------------
class TestCheckValidity:
    def test_non_deletion_keyword_is_not_applicable(self, auditor):
        auditor.request_text = "Please unsubscribe me from the mailing list."
        assert auditor._check_validity() is False

    def test_deletion_keyphrase_skips_the_model(self, auditor, dataset, fake_gemini):
        fake = fake_gemini(["False"])
        auditor = CaseAuditorAgent(dataset)
        auditor.request_text = "Please DELETE MY ACCOUNT today."
        assert auditor._check_validity() is True
        assert fake.calls == []

    @pytest.mark.parametrize(
        ("reply", "expected"), [("True", True), ("False", False), ("yes", True), ("maybe", False)]
    )
    def test_unclear_requests_ask_the_model(self, dataset, fake_gemini, reply, expected):
        fake = fake_gemini([reply])
        auditor = CaseAuditorAgent(dataset)
        auditor.request_text = "Ich möchte, dass ihr alles über mich vergesst."
        assert auditor._check_validity() is expected
        assert len(fake.calls) == 1

    def test_model_failure_falls_back_to_deletion_with_warning(self, dataset, fake_gemini):
        import httpx
        from google.genai._interactions import APIStatusError

        request = httpx.Request("POST", "https://x")
        fake_gemini([APIStatusError("credits", response=httpx.Response(402, request=request), body=None)])
        auditor = CaseAuditorAgent(dataset)
        auditor.case_id, auditor.request_text = "case_99", "Bitte alles entfernen."
        assert auditor._check_validity() is True
        assert any("Defaulting validity to True" in msg for _, msg in get_issues())

    def test_missing_request_text_does_not_crash(self, auditor):
        auditor.request_text = float("nan")  # empty CSV cell
        assert auditor._check_validity() is True  # unclear -> model -> "True"

    @pytest.mark.xfail(
        strict=True,
        reason="Open design question: NON_DELETION_KEYWORDS are checked before "
        "VALID_KEYPHRASES, so a request that explicitly asks for deletion AND an "
        "opt-out is classified as not a deletion (SYSTEM_INSTR_PROMPT says it is).",
    )
    def test_mixed_request_with_explicit_deletion_is_a_deletion(self, auditor):
        auditor.request_text = "Delete my account and unsubscribe me from emails."
        assert auditor._check_validity() is True


# --------------------------------------------------------------------------
# Identity and activity window
# --------------------------------------------------------------------------
class TestFilterByUser:
    def test_current_email_resolves_one_user(self, auditor, dataset):
        load_case(auditor, dataset, "case_01")
        data = auditor._filter_by_user()
        assert list(data["user_identities"]["user_id"]) == ["user_01"]
        assert (data["evidence_files"]["captured_at"] <= auditor.audit_at).all()
        assert (data["activity_pool"]["event_time"] <= auditor.audit_at).all()

    def test_historical_email_resolves_through_audit_log(self, auditor, dataset):
        load_case(auditor, dataset, "case_10")  # request uses a past email
        data = auditor._filter_by_user()
        assert len(data["user_identities"]) == 1
        assert auditor.email.lower() not in set(dataset["user_identities"]["email"].str.lower())

    def test_email_lookup_is_case_insensitive(self, auditor, dataset):
        load_case(auditor, dataset, "case_01")
        auditor.email = "  AMINA.ELMASRI@GMAIL.COM "
        assert list(auditor._filter_by_user()["user_identities"]["user_id"]) == ["user_01"]

    def test_unknown_email_audits_nobody(self, auditor, dataset):
        load_case(auditor, dataset, "case_01")
        auditor.email = "nobody@nowhere.invalid"
        assert auditor._filter_by_user()["user_identities"] is None
        assert "completely unknown" in get_issues()[0][1]

    def test_ambiguous_email_audits_nobody(self, auditor, dataset, monkeypatch):
        load_case(auditor, dataset, "case_01")
        ids = dataset["user_identities"]
        dup = ids[ids["user_id"] == "user_01"].assign(user_id="user_dup")
        monkeypatch.setitem(auditor._data, "user_identities", pd.concat([ids, dup]))
        assert auditor._filter_by_user()["user_identities"] is None
        assert "Multiple users" in get_issues()[0][1]


def test_activity_window_is_reported_at_plus_minus_10_minutes_capped_at_audit(auditor):
    auditor.reported_at = "2026-09-01T10:00:00Z"
    auditor.audit_at = "2026-09-01T10:05:00Z"
    events = pd.DataFrame(
        {
            "event_time": [
                "2026-09-01T09:49:59Z",  # too early
                "2026-09-01T09:50:00Z",
                "2026-09-01T10:05:00Z",
                "2026-09-01T10:05:01Z",  # after audit_at
            ]
        }
    )
    kept = auditor._filter_system_activity(events)["event_time"].tolist()
    assert kept == ["2026-09-01T09:50:00Z", "2026-09-01T10:05:00Z"]


# --------------------------------------------------------------------------
# Status and steps
# --------------------------------------------------------------------------
def test_status_is_complete_without_findings(auditor):
    assert auditor._get_deletion_status([]) == DS.COMPLETE


def test_any_violation_makes_the_case_incomplete(auditor, make_finding):
    ok = make_finding(state=St.ABSENT)
    bad = make_finding(resource_id="search_1", category="SEARCH_INDEX_ENTRY", state=St.PRESENT)
    assert auditor._get_deletion_status([ok]) == DS.COMPLETE
    assert auditor._get_deletion_status([ok, bad]) == DS.INCOMPLETE


def test_finalize_not_applicable_has_no_steps(auditor):
    from agents.steps_agent import StepsAgent

    auditor._steps_agent = StepsAgent()
    assert auditor._finalize(DS.NOT_APPLICABLE, []) == "[]"


def test_finalize_complete_case_cites_evidence(auditor, make_finding):
    from agents.steps_agent import StepsAgent

    auditor._steps_agent = StepsAgent()
    steps = json.loads(auditor._finalize(DS.COMPLETE, [make_finding(evidence_id="evidence_54")]))
    assert steps == [
        {
            "phase": "VERIFICATION",
            "system_id": "account_service",
            "resource_id": "account_001",
            "operation": "VERIFY_RECORD_ABSENT",
            "state": "ABSENT",
            "evidence_id": "evidence_54",
            "step_no": 1,
        }
    ]


def test_finalize_incomplete_case(auditor, make_finding):
    from agents.steps_agent import StepsAgent

    auditor._steps_agent = StepsAgent()
    gone = make_finding(evidence_id="evidence_54")
    backup = make_finding(
        system_id="backup_service",
        resource_id="backup_3870",
        category="BACKUP_ARCHIVE",
        state=St.ACTIVE,
        evidence_id="evidence_03",
    )
    unknown = make_finding(resource_id="email_delivery_1", category="EMAIL_DELIVERY_LOG", state=St.UNKNOWN)

    steps = json.loads(auditor._finalize(DS.INCOMPLETE, [gone, backup, unknown]))
    assert [(s["phase"], s["operation"], s["state"], s["evidence_id"]) for s in steps] == [
        ("FINDING", "REPORT_RESTORE_RISK", "ACTIVE", "evidence_03"),
        ("REMEDIATION", "BLOCK_RESTORE", "BLOCKED", ""),
        ("VERIFICATION", "VERIFY_RECORD_ABSENT", "ABSENT", ""),  # no evidence yet
        ("VERIFICATION", "VERIFY_RESTORE_BLOCKED", "BLOCKED", ""),
    ]
    assert "UNKNOWN state" in get_issues()[0][1]


def test_get_output_parses_steps_json(auditor):
    auditor.case_id = "case_77"
    assert auditor._get_output(DS.COMPLETE, '[{"step_no": 1}]') == ["case_77", DS.COMPLETE, [{"step_no": 1}]]
    assert auditor._get_output(DS.NOT_APPLICABLE, []) == ["case_77", DS.NOT_APPLICABLE, []]


def test_usage_property_exposes_the_model_tracker(auditor):
    assert auditor.usage is auditor._model.usage


# --------------------------------------------------------------------------
# audit_by_case (one case end to end)
# --------------------------------------------------------------------------
def test_audit_non_deletion_request(auditor, dataset):
    case = dataset["deletion_requests"].iloc[0].copy()
    case["request_text"] = "Please export my data and unsubscribe me."
    case_id, status, steps = auditor.audit_by_case(case)
    assert (case_id, status, steps) == (case["case_id"], DS.NOT_APPLICABLE, [])


def test_audit_unknown_user_is_complete_with_no_steps(auditor, dataset):
    case = dataset["deletion_requests"].iloc[0].copy()
    case["email"] = "nobody@nowhere.invalid"
    _, status, steps = auditor.audit_by_case(case)
    assert (status, steps) == (DS.COMPLETE, [])


def test_audit_case_01_proves_the_account_is_gone(auditor, dataset):
    case = dataset["deletion_requests"].iloc[0]
    case_id, status, steps = auditor.audit_by_case(case)
    assert (case_id, status) == ("case_01", DS.COMPLETE)
    assert {"resource_id": "account_001", "state": "ABSENT"}.items() <= steps[0].items()
