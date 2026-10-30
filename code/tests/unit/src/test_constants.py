# code/tests/unit/src/test_constants.py
# Contract tests for the mapping tables: these catch the "typo silently
# returns COMPLETE" class of bug (the CATEGORY_BY_PREFIX lesson).

import pytest
from src import constants as C
from src.enums import DeletionStatus, StepOperations, StepPhases, StepStates

REMEDIATIONS = {
    StepOperations.DELETE_RECORD,
    StepOperations.REDACT_RECORD,
    StepOperations.ANONYMIZE_RECORD,
    StepOperations.DISABLE_DATA_FLOW,
    StepOperations.BLOCK_RESTORE,
}


def test_every_mapped_category_exists_in_rules_or_is_a_process(rules_df):
    known = set(rules_df["data_category"]) | C.PROCESS_CATEGORIES
    missing = {p: c for p, c in C.CATEGORY_BY_PREFIX.items() if c not in known}
    assert missing == {}


def test_resource_id_regex_recognizes_every_mapped_prefix():
    for prefix in C.CATEGORY_BY_PREFIX:
        assert C.RESOURCE_ID_RE.fullmatch(f"{prefix}_123"), prefix


def test_every_csv_action_is_mapped(rules_df):
    assert set(rules_df["required_action"]) <= set(C.ACTION_MAPPING)


@pytest.mark.parametrize(
    "table", ["VERIFY_OP_MAPPING", "VERIFY_STATE_MAPPING", "FINDING_OP_BY_ACTION"]
)
def test_every_remediation_has_an_entry(table):
    assert set(getattr(C, table)) == REMEDIATIONS


def test_every_operation_has_a_sort_priority():
    assert set(C.OP_PRIORITY) == set(StepOperations)


def test_every_official_state_has_a_verification():
    official = set(StepStates) - {StepStates.UNKNOWN, StepStates.ACTIVE}
    assert set(C.VERIFY_OP_BY_STATE) == official


def test_phase_order_is_finding_remediation_verification():
    order = C.STEP_AGENT_PHASE_ORDER
    assert order[StepPhases.FINDING] < order[StepPhases.REMEDIATION]
    assert order[StepPhases.REMEDIATION] < order[StepPhases.VERIFICATION]


def test_process_flags_cover_backups_and_data_flows():
    assert set(C.PROCESS_FLAGS) == {"backup", "data_flow"}


def test_use_sample_is_a_bool():
    assert isinstance(C.USE_SAMPLE, bool)


def test_enums_compare_equal_to_their_strings():
    # StrEnum: values serialize to plain strings in steps_json
    assert DeletionStatus.COMPLETE == "COMPLETE"
    assert f"{StepOperations.DELETE_RECORD}" == "DELETE_RECORD"
    assert StepStates("BLOCKED") is StepStates.BLOCKED


def test_prompts_ask_for_a_bare_boolean():
    assert "{request_text}" in C.VALIDITY_PROMPT
    assert "True or False" in C.SYSTEM_INSTR_PROMPT
