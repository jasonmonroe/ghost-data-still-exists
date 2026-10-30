# code/tests/unit/agents/test_deletion_rule_agent.py

import agents.deletion_rule_agent as rule_module
import pytest
from agents.deletion_rule_agent import DeletionRuleAgent
from src.constants import DEFAULT_RULE_CATEGORY
from src.enums import DeletionStatus as DS
from src.enums import StepOperations as Op
from src.enums import StepStates as St


@pytest.fixture
def agent(rules_df):
    return DeletionRuleAgent(rules_df)


class TestStartupValidation:
    def test_valid_mapping_constructs(self, rules_df):
        DeletionRuleAgent(rules_df)

    def test_typo_in_category_mapping_fails_fast(self, rules_df, monkeypatch):
        bad = {"export": "EXPORT_RECORD"}  # not in deletion_rules.csv
        monkeypatch.setattr(rule_module, "CATEGORY_BY_PREFIX", bad)
        with pytest.raises(ValueError, match="EXPORT_RECORD"):
            DeletionRuleAgent(rules_df)

    def test_process_categories_are_exempt(self, rules_df, monkeypatch):
        monkeypatch.setattr(rule_module, "CATEGORY_BY_PREFIX", {"data_flow": "DATA_FLOW"})
        DeletionRuleAgent(rules_df)  # DATA_FLOW has no CSV row, but is allowed


class TestGetCategory:
    @pytest.mark.parametrize(
        ("resource_id", "category"),
        [
            ("account_001", "USER_PROFILE"),
            ("audit_record_265", "SECURITY_AUDIT_LOG"),
            ("email_delivery_8297", "EMAIL_DELIVERY_LOG"),
            ("data_flow_9846", "DATA_FLOW"),
            ("backup_3870", "BACKUP_ARCHIVE"),
            ("support_001", "SUPPORT_MESSAGE"),
            ("legal_hold_12", "LEGAL_HOLD_RECORD"),
        ],
    )
    def test_maps_prefix_to_rules_category(self, agent, resource_id, category):
        assert agent.get_category(resource_id) == category

    def test_unknown_prefix_falls_back(self, agent):
        assert agent.get_category("mystery_42") == DEFAULT_RULE_CATEGORY


class TestGetRuleByCategory:
    def test_data_flow_is_a_process_without_csv_row(self, agent):
        assert agent.get_rule_by_category("DATA_FLOW")["required_action"] == Op.DISABLE_DATA_FLOW

    def test_backup_restore_path_must_be_blocked(self, agent):
        assert agent.get_rule_by_category("BACKUP_ARCHIVE")["required_action"] == Op.BLOCK_RESTORE

    @pytest.mark.parametrize(
        ("category", "action"),
        [
            ("USER_PROFILE", Op.DELETE_RECORD),
            ("SUPPORT_MESSAGE", Op.REDACT_RECORD),
            ("ANALYTICS_PROFILE", Op.ANONYMIZE_RECORD),
            ("SECURITY_AUDIT_LOG", Op.VERIFY_RECORD_PRESENT),  # RETAIN
        ],
    )
    def test_csv_actions_are_translated(self, agent, category, action):
        rule = agent.get_rule_by_category(category)
        assert rule["required_action"] == action
        assert rule["rule_id"].startswith("rule_")

    def test_unknown_category_has_no_rule(self, agent):
        assert agent.get_rule_by_category("NOPE") == {}


class TestEvaluate:
    @pytest.mark.parametrize(
        ("category", "state", "exposed", "expected"),
        [
            # DELETE rule
            ("USER_PROFILE", St.PRESENT, (), DS.INCOMPLETE),
            ("USER_PROFILE", St.ABSENT, (), DS.COMPLETE),
            # REDACT / ANONYMIZE: only a violation while PII is still exposed
            ("SUPPORT_MESSAGE", St.PRESENT, ("email",), DS.INCOMPLETE),
            ("SUPPORT_MESSAGE", St.PRESENT, (), DS.COMPLETE),
            ("SUPPORT_MESSAGE", St.REDACTED, (), DS.COMPLETE),
            ("ANALYTICS_PROFILE", St.PRESENT, ("name",), DS.INCOMPLETE),
            ("ANALYTICS_PROFILE", St.ANONYMIZED, (), DS.COMPLETE),
            # Processes
            ("BACKUP_ARCHIVE", St.ACTIVE, (), DS.INCOMPLETE),
            ("BACKUP_ARCHIVE", St.BLOCKED, (), DS.COMPLETE),
            ("DATA_FLOW", St.ACTIVE, (), DS.INCOMPLETE),
            ("DATA_FLOW", St.DISABLED, (), DS.COMPLETE),
            # RETAIN: a retained record that is present is compliant
            ("SECURITY_AUDIT_LOG", St.PRESENT, (), DS.COMPLETE),
            # ACTIVE only means something for processes
            ("USER_PROFILE", St.ACTIVE, (), DS.COMPLETE),
            # No rule -> nothing to violate
            ("NOPE", St.PRESENT, (), DS.COMPLETE),
        ],
    )
    def test_status_matrix(self, agent, make_finding, category, state, exposed, expected):
        finding = make_finding(category=category, state=state, exposed_fields=frozenset(exposed))
        assert agent.evaluate(finding) == expected
