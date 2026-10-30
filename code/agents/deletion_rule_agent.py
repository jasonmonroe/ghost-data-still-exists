# code/agents/deletion_rule_agent.py

"""
+-----------------------------------------------------------------------------+
|                              DELETION RULE AGENT                            |
+-----------------------------------------------------------------------------+

Policy expert—its job is to look at a discovered resource category,
cross-reference deletion_rules.csv, and determine: "Does this violate policy?
If so, what remediation and verification steps are legally required?"

- Resolve the user’s current and historical identifiers.
- Determine the resource state at `audit_at` using the available evidence.
  Reported workflow statuses and operation results are claims.

- Apply `deletion_rules.csv` to every relevant record, including account
  tombstones, active data flows, and restore risks.

- Order steps by phase: findings, remediation, then verification. Within each
  phase, follow the operation order in the table above, followed by `system_id`
  and `resource_id` in ascending order.

- Findings and verification steps for `COMPLETE` cases must cite a `file_id`,
  `activity_id`, or `audit_id`. Proposed remediation and future verification
  steps for `INCOMPLETE` cases use an empty `evidence_id`.
"""

# Vendor Libraries
import pandas as pd

# Local Libraries
from src.constants import (
    ACTION_MAPPING,
    CATEGORY_BY_PREFIX,
    DEFAULT_RULE_CATEGORY,
    PROCESS_CATEGORIES,
)
from src.enums import DeletionStatus, StepOperations, StepStates


class DeletionRuleAgent:
    def __init__(self, deletion_rules: pd.DataFrame):
        """
        A deletion is complete only when:

        - every relevant copy has received the treatment required by `deletion_rules.csv`;
        - no active sync, import, or restore path can recreate the data;
        - retained records contain only the identifiers permitted by the rules; and
        - records that must be retained remain available.
        """

        self.rules = deletion_rules

        self.rule_id = None
        self.data_category = None
        self.condition = None
        self.required_action = None

        # Startup fail-safe: Crash immediately on typo rather than returning silent COMPLETE
        valid_categories = set(self.rules["data_category"].unique())
        for prefix, cat in CATEGORY_BY_PREFIX.items():
            if cat not in PROCESS_CATEGORIES and cat not in valid_categories:
                raise ValueError(
                    f"🚨 Startup Error: Mapped category '{cat}' for prefix '{prefix}' "
                    f"does not exist in deletion_rules.csv!"
                )

    def get_category(self, resource_id: str) -> str:
        """Maps resource ID prefix cleanly to data category using explicit mapping."""
        parts = resource_id.split("_")

        # Check two-word prefixes first (e.g., audit_record, data_flow, email_delivery)
        if len(parts) >= 3:
            two_part_prefix = f"{parts[0]}_{parts[1]}"
            if two_part_prefix in CATEGORY_BY_PREFIX:
                self.data_category = CATEGORY_BY_PREFIX[two_part_prefix]
                return self.data_category

        single_prefix = parts[0]
        if single_prefix in CATEGORY_BY_PREFIX:
            self.data_category = CATEGORY_BY_PREFIX[single_prefix]
            return self.data_category

        return DEFAULT_RULE_CATEGORY

    def get_rule_by_category(self, category: str) -> dict:
        """Lookup policy rule for a category and translate the raw CSV action."""
        # Processes first: DATA_FLOW has no CSV row; BACKUP_ARCHIVE's RETAIN
        # covers the archive, not its restore path.
        if category == "DATA_FLOW":
            return {
                "data_category": category,
                "required_action": StepOperations.DISABLE_DATA_FLOW,
            }
        if category == "BACKUP_ARCHIVE":
            return {
                "data_category": category,
                "required_action": StepOperations.BLOCK_RESTORE,
            }

        matched = self.rules[self.rules["data_category"] == category]
        if matched.empty:
            return {}

        rule = matched.iloc[0].to_dict()
        rule["required_action"] = ACTION_MAPPING.get(
            rule.get("required_action", ""), StepOperations.DELETE_RECORD
        )
        return rule

    def evaluate(self, finding) -> str:
        """
        Determines if a ResourceFinding complies with policy or requires remediation.
        Returns COMPLETE or INCOMPLETE
        """
        rule = self.get_rule_by_category(finding.category)
        if not rule:
            return DeletionStatus.COMPLETE

        required_action = rule.get("required_action")
        self.required_action = required_action

        # 1. Process violations: Data flow or backup restore risk is ACTIVE
        if finding.state == StepStates.ACTIVE and required_action in (
            StepOperations.DISABLE_DATA_FLOW,
            StepOperations.BLOCK_RESTORE,
        ):
            return DeletionStatus.INCOMPLETE

        # 2. Record deletion violations: Record must be ABSENT but is PRESENT
        if (
            finding.state == StepStates.PRESENT
            and required_action == StepOperations.DELETE_RECORD
        ):
            return DeletionStatus.INCOMPLETE

        # 3. Redaction / Anonymization violations: Record is PRESENT with unredacted PII
        if (
            finding.state == StepStates.PRESENT
            and finding.exposed_fields
            and required_action
            in (
                StepOperations.REDACT_RECORD,
                StepOperations.ANONYMIZE_RECORD,
            )
        ):
            return DeletionStatus.INCOMPLETE

        return DeletionStatus.COMPLETE
