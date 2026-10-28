# code/agent/steps_agent.py

"""
+-----------------------------------------------------------------------------+
|                                   STEPS AGENT                               |
+-----------------------------------------------------------------------------+


| `steps_json` | Ordered JSON array of findings, remediation actions, and verification checks |

The final file must contain exactly 518 data rows, sorted by `case_id`.

Each object in `steps_json` must contain:

```json
{
  "step_no": 1,
  "phase": "FINDING",
  "system_id": "account_service",
  "resource_id": "account_005",
  "operation": "REPORT_REMAINING_RECORD",
  "state": "PRESENT",
  "evidence_id": "evidence_01"
}
```

`phase` must be `FINDING`, `REMEDIATION`, or `VERIFICATION`. Step numbers start at `1` and increase consecutively. Array order is significant.

For `COMPLETE`, include only verification steps proving the current state. For `INCOMPLETE`, include findings, the complete remediation plan, and the checks that must pass afterward. For `NOT_APPLICABLE`, use an empty JSON array (`[]`) because no deletion or deletion verification is authorized.

A non-deletion row therefore has this form:

```csv
case_000,NOT_APPLICABLE,[]
```

The grader parses `steps_json` as JSON. JSON object-key order and whitespace are ignored; array order is not.

## Allowed Operations

| Phase | Operation | State | Meaning |
| --- | --- | --- | --- |
| `FINDING` | `REPORT_REMAINING_RECORD` | `PRESENT` | A record that should have been deleted still exists. |
| `FINDING` | `REPORT_EXPOSED_PII` | `PRESENT` | A record may remain, but it still contains identifiers that should have been redacted or anonymized. |
| `FINDING` | `REPORT_ACTIVE_DATA_FLOW` | `ACTIVE` | An active process can copy or recreate the user's data. |
| `FINDING` | `REPORT_RESTORE_RISK` | `ACTIVE` | A backup or restore path can bring deleted data back. |
| `REMEDIATION` | `DISABLE_DATA_FLOW` | `DISABLED` | Stop the process that can copy or recreate the data. |
| `REMEDIATION` | `BLOCK_RESTORE` | `BLOCKED` | Prevent the affected backup from restoring the user's data. |
| `REMEDIATION` | `DELETE_RECORD` | `ABSENT` | Remove the entire record. |
| `REMEDIATION` | `REDACT_RECORD` | `REDACTED` | Keep the record but remove the identifying fields required by policy. |
| `REMEDIATION` | `ANONYMIZE_RECORD` | `ANONYMIZED` | Keep the record after irreversibly unlinking it from the user. |
| `VERIFICATION` | `VERIFY_RECORD_ABSENT` | `ABSENT` | Confirm that a record no longer exists. |
| `VERIFICATION` | `VERIFY_RECORD_PRESENT` | `PRESENT` | Confirm that a policy-required retained record still exists. |
| `VERIFICATION` | `VERIFY_RECORD_REDACTED` | `REDACTED` | Confirm that required identifying fields have been removed. |
| `VERIFICATION` | `VERIFY_RECORD_ANONYMIZED` | `ANONYMIZED` | Confirm that the record can no longer be linked to the user. |
| `VERIFICATION` | `VERIFY_DATA_FLOW_DISABLED` | `DISABLED` | Confirm that the relevant data flow is inactive. |
| `VERIFICATION` | `VERIFY_RESTORE_BLOCKED` | `BLOCKED` | Confirm that the affected data cannot be restored. |
"""

import json


class StepsAgent:
    def __init__(self):
        self._data = []

    def add(
        self,
        phase: str,
        system_id: str,
        resource_id: str,
        operation: str,
        state: str,
        evidence_id: str,
    ) -> None:
        """Helper to append individual step components."""
        self._data.append(
            {
                "phase": phase,
                "system_id": system_id,
                "resource_id": resource_id,
                "operation": operation,
                "state": state,
                "evidence_id": evidence_id if evidence_id is not None else "",
            }
        )

    def compile(self) -> str:
        """
        Compiles all added steps, enforces consecutive numbering starting and
        retrus the final JSON string for steps_json.
        Returns '[]' if no steps exist (e.g. for NOT_APPLICABLE cases).
        """

        if not self._data:
            return json.dumps([])

        steps = []
        for idx, item in enumerate(self._data, start=1):
            # Create a copy or update the dictionary directly to include step_no
            step_item = (
                item.copy()
            )  # Good practice to avoid mutating self._data directly
            step_item["step_no"] = idx
            steps.append(step_item)

        return json.dumps(steps)
