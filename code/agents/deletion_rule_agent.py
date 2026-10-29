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
    DEFAULT_REQ_ACTION,
    DEFAULT_RULE_CATEGORY,
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

    # @depracated
    def get_category2(self, resource_id: str) -> str:
        """
        Maps resource prefix to data category from deletion_rules.csv

        Example lookup against rules DataFrame
        Assuming deletion_rules.csv has columns like 'prefix' or 'data_category'
        You can match based on your dataset's specific column structure
        """
        prefix = resource_id.split("_")[0]

        matched_category_rule = self.rules[
            # self.rules["data_category"].str.contains(prefix, case=False, na=False)
            self.rules["data_category"].str.lower().str.startswith(prefix.lower())
        ]

        if not matched_category_rule.empty:
            self.data_category = matched_category_rule.iloc[0]["data_category"]
            return matched_category_rule.iloc[0]["data_category"]

        return DEFAULT_RULE_CATEGORY  # fallback category

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
        """Lookup policy rule based on data category and translate raw CSV actions."""
        matched_category = self.rules[self.rules["data_category"] == category]

        if not matched_category.empty:
            category_rule = matched_category.iloc[0].to_dict()

            self.rule_id = category_rule.get("rule_id")
            self.data_category = category_rule.get("data_category")
            self.condition = category_rule.get("condition")

            # Translate raw CSV action (e.g., "DELETE", "REDACT") to StepOperations enum
            raw_action = category_rule.get("required_action", DEFAULT_REQ_ACTION)
            self.required_action = ACTION_MAPPING.get(
                raw_action, StepOperations.DELETE_RECORD
            )

            # Store the mapped enum back in the returned dict so downstream methods use it
            category_rule["required_action"] = self.required_action

            return category_rule

        return {}

    # @depracated
    def get_rule_by_category_old(self, category: str) -> dict:
        """Lookup policy rule based on data category."""
        matched = self.rules[self.rules["data_category"] == category]

        if not matched.empty:
            category_rule = matched.iloc[0].to_dict()

            self.rule_id = category_rule["rule_id"]
            self.data_category = category_rule["data_category"]
            self.condition = category_rule["condition"]
            self.required_action = category_rule["required_action"]

            return category_rule

        return {}

    def evaluate(self, finding) -> str:
        """
        Determines if a ResourceFinding complies with policy or requires remidiation.
        Returns COMPLETE or INCOMPLETE
        """

        rule = self.get_rule_by_category(finding.category)
        if not rule:
            return DeletionStatus.COMPLETE

        self.required_action = rule.get("required_action")

        # If a record must be ABSENT (deleted) but is still PRESENT
        if (
            finding.state == StepStates.PRESENT
            and self.required_action == DEFAULT_REQ_ACTION
        ):
            return DeletionStatus.INCOMPLETE

        # If a record must be REDACTED/ANONYMIZED but still exposes unredacted PII fields
        if (
            finding.state == StepStates.PRESENT
            and finding.exposed_fields
            and self.required_action
            in (
                StepOperations.REDACT_RECORD,
                StepOperations.ANONYMIZE_RECORD,
            )
        ):
            return DeletionStatus.INCOMPLETE

        return DeletionStatus.COMPLETE
