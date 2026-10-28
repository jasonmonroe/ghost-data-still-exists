# code/agents/delition_rule_agent.py

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

import pandas as pd
from src.enums import DeletionStatus, StepStates


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

    def get_category(self, resource_id: str) -> str:
        """Maps resource prefix to data category from deletion_rules.csv"""
        prefix = resource_id.split("_")[0]

        # Example lookup against rules DataFrame
        # Assuming deletion_rules.csv has columns like 'prefix' or 'data_category'
        # You can match based on your dataset's specific column structure
        match = self.rules[
            self.rules["data_category"].str.contains(prefix, case=False, na=False)
        ]

        if not match.empty:
            self.data_category = match.iloc[0]["data_category"]
            return match.iloc[0]["data_category"]

        return "general_record"  # fallback category

    def _get_category_rule(self, category: str) -> dict:
        """Lookup policy rule based on data category."""
        matched = self.rules[self.rules["data_category"] == category]

        if not matched.empty:
            return matched.iloc[0].to_dict

        return {}

    def evaluate(self, finding) -> str:
        """
        Determines if a ResourceFinding complies with policy or requires remidiation.
        Returns COMPLETE or INCOMPLETE
        """

        # If a record taht should have been deleted (ABSENT required)
        if finding.state == StepStates.PRESENT:
            rule = self._get_category_rule(finding.category)
            self.required_action = rule.get("required_action", None)

            if self.required_action and self.required_action == "DELETE_RECORD":
                return DeletionStatus.INCOMPLETE

        return DeletionStatus.COMPLETE
