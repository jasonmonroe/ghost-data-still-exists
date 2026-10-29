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

from agents.evidence_agent import ResourceFinding
from src.enums import StepOperations, StepPhrases, StepStates


class StepsAgent:
    def __init__(self):
        self._data = []

        self._verify_op = None
        self._verify_state = None
        self._verify_evidence = None

    def set_verify_complete(self, finding: ResourceFinding):
        self._verify_op = (
            StepOperations.VERIFY_RECORD_ABSENT
            if finding.state == StepStates.ABSENT
            else StepOperations.VERIFY_RECORD_PRESENT
        )
        self._verify_state = finding.state
        self._verify_evidence = finding.evidence_id or ""

    def set_verify_incomplete(self, required_action: str) -> None:
        self._verify_op = (
            StepOperations.VERIFY_RECORD_ABSENT
            if required_action == StepOperations.DELETE_RECORD
            else StepOperations.VERIFY_RECORD_REDACTED
        )

        self._verify_state = (
            StepStates.ABSENT
            if required_action == StepOperations.DELETE_RECORD
            else StepStates.REDACTED
        )

        self._verify_evidence = ""

    def add_finding_phase(self, finding: ResourceFinding) -> None:
        op = (
            StepOperations.REPORT_EXPOSED_PII
            if finding.exposed_fields
            else StepOperations.REPORT_REMAINING_RECORD
        )

        self.add(
            phase=StepPhrases.FINDING,
            system_id=finding.system_id,
            resource_id=finding.resource_id,
            operation=op,
            state=finding.state,
            evidence_id=finding.evidence_id,
        )

    def add_remediation_phase(
        self, finding: ResourceFinding, required_action: str
    ) -> None:
        rem_state = (
            StepStates.ABSENT
            if required_action == "DELETE_RECORD"
            else StepStates.REDACTED
        )

        self.add(
            StepPhrases.REMEDIATION,
            finding.system_id,
            finding.resource_id,
            required_action,
            rem_state,
            "",
        )

    def add_verification_phase(self, finding: ResourceFinding) -> None:
        self.add(
            phase=StepPhrases.VERIFICATION,
            system_id=finding.system_id,
            resource_id=finding.resource_id,
            operation=self._verify_op,
            state=self._verify_state,
            evidence_id=self._verify_evidence,
        )

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

        # If ReportedStatus == COMPLETE include only verification steps
        self._data.append(
            {
                "phase": phase,
                "system_id": system_id,  # system_activity.source_system
                "resource_id": resource_id,  # system_activity.resource_id
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

        # Define strict phase order priority
        phase_order = {
            StepPhrases.FINDING: 1,
            StepPhrases.REMEDIATION: 2,
            StepPhrases.VERIFICATION: 3,
        }

        # Sort items by phase, then system_id, then resource_id
        sorted_data = sorted(
            self._data,
            key=lambda x: (
                phase_order.get(x["phase"], 99),
                x["system_id"],
                x["resource_id"],
            ),
        )

        steps = []
        for idx, item in enumerate(sorted_data, start=1):
            step_item = item.copy()
            step_item["step_no"] = idx
            steps.append(step_item)

        return json.dumps(steps)

    # @depracated
    def compile_old(self) -> str:
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
            step_item = item.copy()

            # Good practice to avoid mutating self._data directly
            step_item["step_no"] = idx
            steps.append(step_item)

        return json.dumps(steps)

    def count(self) -> int:
        return len(self._data)
