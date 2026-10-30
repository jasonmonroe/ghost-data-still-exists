# code/tests/unit/agents/test_steps_agent.py

import json

import pytest
from agents.steps_agent import StepsAgent
from src.enums import StepOperations as Op
from src.enums import StepStates as St


def compiled(agent: StepsAgent) -> list[dict]:
    return json.loads(agent.compile())


def test_empty_agent_compiles_to_empty_array():
    agent = StepsAgent()
    assert agent.compile() == "[]"
    assert agent.count() == 0


def test_incomplete_record_gets_finding_remediation_and_future_verification(make_finding):
    finding = make_finding(state=St.PRESENT, evidence_id="evidence_54")
    agent = StepsAgent()
    agent.add_finding_phase(finding, Op.REPORT_REMAINING_RECORD)
    agent.add_remediation_phase(finding, Op.DELETE_RECORD)
    agent.set_verify_incomplete(Op.DELETE_RECORD)
    agent.add_verification_phase(finding)

    steps = compiled(agent)
    assert [(s["phase"], s["operation"], s["state"], s["evidence_id"]) for s in steps] == [
        ("FINDING", "REPORT_REMAINING_RECORD", "PRESENT", "evidence_54"),
        ("REMEDIATION", "DELETE_RECORD", "ABSENT", ""),
        ("VERIFICATION", "VERIFY_RECORD_ABSENT", "ABSENT", ""),
    ]
    assert [s["step_no"] for s in steps] == [1, 2, 3]


@pytest.mark.parametrize(
    ("action", "op", "state"),
    [
        (Op.DELETE_RECORD, Op.VERIFY_RECORD_ABSENT, St.ABSENT),
        (Op.REDACT_RECORD, Op.VERIFY_RECORD_REDACTED, St.REDACTED),
        (Op.ANONYMIZE_RECORD, Op.VERIFY_RECORD_ANONYMIZED, St.ANONYMIZED),
        (Op.DISABLE_DATA_FLOW, Op.VERIFY_DATA_FLOW_DISABLED, St.DISABLED),
        (Op.BLOCK_RESTORE, Op.VERIFY_RESTORE_BLOCKED, St.BLOCKED),
    ],
)
def test_future_verification_matches_the_remediation(make_finding, action, op, state):
    agent = StepsAgent()
    agent.set_verify_incomplete(action)
    agent.add_verification_phase(make_finding())
    (step,) = compiled(agent)
    assert (step["operation"], step["state"], step["evidence_id"]) == (op, state, "")


@pytest.mark.parametrize(
    ("state", "op"),
    [
        (St.ABSENT, Op.VERIFY_RECORD_ABSENT),
        (St.PRESENT, Op.VERIFY_RECORD_PRESENT),
        (St.REDACTED, Op.VERIFY_RECORD_REDACTED),
        (St.ANONYMIZED, Op.VERIFY_RECORD_ANONYMIZED),
        (St.BLOCKED, Op.VERIFY_RESTORE_BLOCKED),
        (St.DISABLED, Op.VERIFY_DATA_FLOW_DISABLED),
    ],
)
def test_complete_verification_proves_current_state_with_evidence(make_finding, state, op):
    agent = StepsAgent()
    finding = make_finding(state=state, evidence_id="evidence_92")
    agent.set_verify_complete(finding)
    agent.add_verification_phase(finding)
    (step,) = compiled(agent)
    assert (step["operation"], step["state"], step["evidence_id"]) == (op, state, "evidence_92")


def test_complete_style_check_inside_incomplete_case_has_no_evidence(make_finding):
    agent = StepsAgent()
    finding = make_finding(state=St.ABSENT, evidence_id="evidence_50")
    agent.set_verify_complete(finding, with_evidence=False)
    agent.add_verification_phase(finding)
    assert compiled(agent)[0]["evidence_id"] == ""


def test_missing_evidence_becomes_empty_string(make_finding):
    agent = StepsAgent()
    finding = make_finding(evidence_id=None)
    agent.set_verify_complete(finding)
    agent.add_verification_phase(finding)
    agent.add_finding_phase(finding, Op.REPORT_REMAINING_RECORD)
    assert all(s["evidence_id"] == "" for s in compiled(agent))


def test_resource_ids_are_normalized(make_finding):
    agent = StepsAgent()
    agent.add_finding_phase(make_finding(resource_id=" account_001 "), Op.REPORT_REMAINING_RECORD)
    assert compiled(agent)[0]["resource_id"] == "account_001"


def test_compile_orders_phase_then_operation_then_system_then_resource(make_finding):
    agent = StepsAgent()
    rec = make_finding(system_id="search_service", resource_id="search_2", state=St.PRESENT)
    rec_b = make_finding(system_id="account_service", resource_id="account_9", state=St.PRESENT)
    flow = make_finding(system_id="integration_service", resource_id="data_flow_1", state=St.ACTIVE)

    # Added deliberately out of order
    agent.set_verify_incomplete(Op.DELETE_RECORD)
    agent.add_verification_phase(rec)
    agent.add_remediation_phase(rec, Op.DELETE_RECORD)
    agent.add_remediation_phase(flow, Op.DISABLE_DATA_FLOW)
    agent.add_finding_phase(flow, Op.REPORT_ACTIVE_DATA_FLOW)
    agent.add_finding_phase(rec, Op.REPORT_REMAINING_RECORD)
    agent.add_finding_phase(rec_b, Op.REPORT_REMAINING_RECORD)

    steps = compiled(agent)
    assert [(s["phase"], s["resource_id"]) for s in steps] == [
        ("FINDING", "account_9"),  # same op: account_service < search_service
        ("FINDING", "search_2"),
        ("FINDING", "data_flow_1"),  # REPORT_ACTIVE_DATA_FLOW after REPORT_REMAINING_RECORD
        ("REMEDIATION", "data_flow_1"),  # disable flows before deleting records
        ("REMEDIATION", "search_2"),
        ("VERIFICATION", "search_2"),
    ]
    assert [s["step_no"] for s in steps] == list(range(1, 7))


def test_count_tracks_added_steps(make_finding):
    agent = StepsAgent()
    agent.add_finding_phase(make_finding(), Op.REPORT_REMAINING_RECORD)
    agent.add_remediation_phase(make_finding(), Op.DELETE_RECORD)
    assert agent.count() == 2


def test_compile_does_not_mutate_stored_steps(make_finding):
    agent = StepsAgent()
    agent.add_finding_phase(make_finding(), Op.REPORT_REMAINING_RECORD)
    agent.compile()
    assert "step_no" not in agent._data[0]
