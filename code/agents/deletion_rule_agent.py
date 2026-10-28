# code/agents/delition_rule_agent.py
# +---------------------------------------------------------------------------+
# |                            DELETION RULE AGENT                            |
# +---------------------------------------------------------------------------+

"""
## Rules

- Resolve the user’s current and historical identifiers.
- Determine the resource state at `audit_at` using the available evidence.
Reported workflow statuses and operation results are claims.
- Apply `deletion_rules.csv` to every relevant record, including account
tombstones, active data flows, and restore risks.
- Order steps by phase: findings, remediation, then verification. Within each
phase, follow the operation order in the table above, followed by `system_id`
and `resource_id` in ascending order.
- Findings and verification steps for `COMPLETE` cases must cite a `file_id`,
`activity_id`, or `audit_id`. Proposed remediation and future verification steps
for `INCOMPLETE` cases use an empty `evidence_id`.
"""

import pandas as pd


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
        # TBD

    def apply(self):
        # TBD
        return None

    # Should we use LLM
