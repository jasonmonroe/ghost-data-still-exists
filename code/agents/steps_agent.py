# code/agent/steps_agent.py

"""
+-----------------------------------------------------------------------------+
|                                   STEPS AGENT                               |
+-----------------------------------------------------------------------------+

Ordered JSON array of findings, remediation actions, and verification checks
Takes data such as phase, operation, state, meaning maps it with a matrix
and outputs the correct value.

The grader parses `steps_json` as JSON. JSON object-key order and whitespace
are ignored; array order is not.
"""

import json

from agents.evidence_agent import ResourceFinding
from src.constants import (
    DEFAULT_SORT_PRIORITY,
    OP_PRIORITY,
    STEP_AGENT_PHASE_ORDER,
    VERIFY_OP_BY_STATE,
    VERIFY_OP_MAPPING,
    VERIFY_STATE_MAPPING,
)
from src.enums import StepOperations, StepPhases, StepStates
from src.utils import normalize_resource


class StepsAgent:
    def __init__(self):
        self._data = []

        self._verify_op = None
        self._verify_state = None
        self._verify_evidence = None

    def set_verify_complete(
        self, finding: ResourceFinding, with_evidence: bool = True
    ) -> None:
        """Verification proving the current, compliant state."""
        self._verify_op = VERIFY_OP_BY_STATE.get(
            finding.state, StepOperations.VERIFY_RECORD_PRESENT
        )
        self._verify_state = finding.state
        self._verify_evidence = (finding.evidence_id or "") if with_evidence else ""

    def set_verify_incomplete(self, required_action: str) -> None:
        self._verify_op = VERIFY_OP_MAPPING.get(
            required_action, StepOperations.VERIFY_RECORD_ABSENT
        )
        self._verify_state = VERIFY_STATE_MAPPING.get(
            required_action, StepStates.ABSENT
        )
        self._verify_evidence = ""

    def add_finding_phase(
        self, finding: ResourceFinding, operation: StepOperations
    ) -> None:
        """The caller decides the finding operation; this only records it."""
        self._add(
            phase=StepPhases.FINDING,
            system_id=finding.system_id,
            resource_id=finding.resource_id,
            operation=operation,
            state=finding.state,
            evidence_id=finding.evidence_id,
        )

    def add_remediation_phase(
        self, finding: ResourceFinding, required_action: str
    ) -> None:

        # Map required action to its target state
        remediation_state = VERIFY_STATE_MAPPING.get(required_action, StepStates.ABSENT)

        self._add(
            StepPhases.REMEDIATION,
            finding.system_id,
            finding.resource_id,
            required_action,
            remediation_state,
            "",
        )

    def add_verification_phase(self, finding: ResourceFinding) -> None:
        self._add(
            phase=StepPhases.VERIFICATION,
            system_id=finding.system_id,
            resource_id=finding.resource_id,
            operation=self._verify_op,
            state=self._verify_state,
            evidence_id=self._verify_evidence,
        )

    def _add(
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
                "resource_id": normalize_resource(resource_id),
                "operation": operation,
                "state": state,
                "evidence_id": evidence_id if evidence_id is not None else "",
            }
        )

    def compile(self) -> str:
        """
        Compiles all added steps in their exact insertion order, enforces
        consecutive numbering, and returns the final JSON string for steps_json.
        Returns '[]' if no steps exist (e.g. for NOT_APPLICABLE cases).
        """
        if not self._data:
            return json.dumps([])

        sorted_data = sorted(
            self._data,
            key=lambda step: (
                STEP_AGENT_PHASE_ORDER.get(step["phase"], DEFAULT_SORT_PRIORITY),
                OP_PRIORITY.get(step["operation"], DEFAULT_SORT_PRIORITY),
                step["system_id"],
                step["resource_id"],
            ),
        )

        steps = []
        for idx, item in enumerate(sorted_data, start=1):
            step_item = item.copy()
            step_item["step_no"] = idx
            steps.append(step_item)

        """
        steps = []
        for idx, item in enumerate(self._data, start=1):
            step_item = item.copy()
            step_item["step_no"] = idx
            steps.append(step_item)
        """

        return json.dumps(steps)

    def count(self) -> int:
        return len(self._data)
