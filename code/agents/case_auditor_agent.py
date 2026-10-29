# code/agents/case_auditor_agent.py

"""
+---------------------------------------------------------------------------+
|                            CASE AUDITOR AGENT                             |
+---------------------------------------------------------------------------+

Case Auditor Agent

An AI-powered automated auditor that investigates data deletion requests for
518 different cases (dataset/deletion_requests.csv). For every request, your AI
agent must act like a meticulous digital detective.

Audits each case and finalizes the resolution, and returns the solution
"""

# Python Libraries
import json

# Vendor Libraries
import pandas as pd
from agents.deletion_rule_agent import DeletionRuleAgent
from agents.evidence_agent import EvidenceAgent, ResourceFinding

# Local Libraries
from agents.steps_agent import StepsAgent
from models.llm_model import LlmModel
from src.constants import (
    DATE_FORMAT,
    DATETIME_DURATION,
    DEFAULT_REQ_ACTION,
    NON_DELETION_KEYWORDS,
    VALID_KEYPHRASES,
    VALIDITY_PROMPT,
)
from src.enums import DeletionStatus, StepOperations, StepPhrases, StepStates


class CaseAuditorAgent:
    def __init__(self, dataset: dict) -> None:
        self._data = dataset
        self._model = LlmModel()
        self._evidence_agent = EvidenceAgent(
            dataset.get("evidence"),
        )
        self._rules_agent = DeletionRuleAgent(dataset.get("deletion_rules"))

        self.case_id = None
        self.email = None
        self.requested_at = None
        self.reported_status = None
        self.reported_at = None
        self.audit_at = None
        self.request_text = None

    def audit_by_case(self, case_s: pd.Series) -> list:
        self._steps_agent = StepsAgent()

        # main public function
        for col, value in case_s.items():
            if hasattr(self, col):
                setattr(self, col, value)

        if not self._check_validity():
            # Customer request is unknown, not valid or irrelevant.
            deletion_status = DeletionStatus.NOT_APPLICABLE
            steps_json = []
        else:
            # Confirmed, customer wants account deleted
            user_dataset = self._filter_by_user()

            if user_dataset.get("user_identities") is None:
                deletion_status = DeletionStatus.COMPLETE
                evidence_findings = []
            else:
                # With results lets build a prompt and get a response to determine final DeletionStatus
                evidence_findings = self._analyze(user_dataset)
                deletion_status = self._get_deletion_status(evidence_findings)

            # Pass the findings directly into _finalize()
            steps_json = self._finalize(deletion_status, evidence_findings)

            print(f"💡 Step Count: {self._steps_agent.count()}")

        return self._get_output(deletion_status, steps_json)

    def _check_validity(self) -> bool:
        """Check Validity: Did the user actually ask to delete their data, or
        is the request irrelevant (NOT_APPLICABLE)?"""

        text = self.request_text.lower() if self.request_text else ""
        if any(word in text for word in NON_DELETION_KEYWORDS):
            return False

        if any(phrase in text for phrase in VALID_KEYPHRASES):
            return True

        # If keywords or keyphrases can't determine ability use the LLM model
        prompt = VALIDITY_PROMPT.format(request_text=self.request_text)
        print("Validity still unknown.  Asking model...")
        response = self._model.get_response(prompt)

        return response.strip().lower() in ("true", "yes", "1")

    def _analyze(self, user_dataset: dict) -> list[ResourceFinding]:
        """Uncover the Truth: Look past what the company's dashboard claims
        ("Complete!") and check the actual evidence files (such as database
        snapshots, logs, and support tickets) to see if personal data is still
        lingering somewhere it shouldn't be.

        Search global logs (system_activity.csv), evidence files, databases,
        backups, or exports around or before audit_at (2026-09-03T11:30:00Z)
        to see if any residual data or recreation risks exist, comparing
        findings against deletion_rules.csv.
        """

        return self._evidence_agent.search(user_dataset, self._rules_agent)

    def _filter_by_user(self) -> dict:
        """Resolve Identities: Match current and historical names, emails, and
        phone numbers to track down all traces of the user."""

        """
        Look up `email` in user_identities.csv and user_audit_log.csv to find
        all current and historical names, emails, user IDs, or phone numbers
        associated with `person`.
        """

        evidence_files_df = self._data.get("evidence_files")
        user_identities_df = self._data.get("user_identities")
        user_audit_log_df = self._data.get("user_audit_log")
        system_activity_df = self._data.get("system_activity")

        # Find user by current email, then by historical email in the audit log
        email = self.email.strip().lower()
        user_identity = user_identities_df[
            user_identities_df["email"].str.lower() == email
        ]
        if user_identity.empty:
            email_changes = user_audit_log_df[
                user_audit_log_df["field_name"] == "email"
            ]
            historical = email_changes[
                (email_changes["old_value"].str.lower() == email)
                | (email_changes["new_value"].str.lower() == email)
            ]
            user_identity = user_identities_df[
                user_identities_df["user_id"].isin(historical["user_id"])
            ]

        if len(user_identity) != 1:
            # Return the unfiltered datasets
            print(
                f"Warning: Case: {self.case_id} User {self.email} unknown or multiple users returned."
            )

            return {
                "evidence_files": evidence_files_df,
                "system_activity": system_activity_df,
                "activity_pool": pd.DataFrame(),
                "user_audit_log": user_audit_log_df,
                "user_identities": user_identities_df,
            }

        # User identified, now lets perform light filtering on corresponding data
        user_id = user_identity.iloc[0].to_dict()["user_id"]

        # Get user history.  It's possible that this could be empty.
        user_audit_log = user_audit_log_df[user_audit_log_df["user_id"] == user_id]
        system_activity = self._filter_system_activity(system_activity_df)

        # Prove the system activity with the evidence.  Choose which file to
        # cite by getting the target_system captured_at or before audit_date
        # Filter out evidence files to prevent looking at future evidence
        evidence_files = evidence_files_df[
            evidence_files_df["captured_at"] <= self.audit_at
        ]

        # Returning filtered data
        return {
            "evidence_files": evidence_files,
            "system_activity": system_activity,  # this case's workflow window
            "activity_pool": system_activity_df[  # everything <= audit_at (timelines)
                system_activity_df["event_time"] <= self.audit_at
            ],
            "user_audit_log": user_audit_log,
            "user_identities": user_identity,
        }

    def _filter_system_activity(self, system_activity_df: pd.DataFrame) -> pd.DataFrame:
        """
        This case's own workflow events: reported_at +/- DATETIME_DURATION
        minutes, never later than audit_at.
        """

        reported_at = pd.Timestamp(self.reported_at)
        delta = pd.Timedelta(minutes=DATETIME_DURATION)
        earliest = (reported_at - delta).strftime(DATE_FORMAT)
        latest = min((reported_at + delta).strftime(DATE_FORMAT), self.audit_at)

        return system_activity_df[
            system_activity_df["event_time"].between(earliest, latest)
        ]

    def _get_deletion_status(self, evidence_findings: list[ResourceFinding]) -> str:
        """
        ** Evaluate all findings **
        For each case, your program has to output one of three statuses:

        - COMPLETE:
        The data is truly gone (or properly anonymized/retained
        according to strict company policy), and you can prove it with evidence.

        - INCOMPLETE:
        Ghost data still exists, or an active process/backup can
        bring the data back to life.

        - NOT_APPLICABLE:
        The user didn't actually request a deletion."""

        if not evidence_findings:
            return DeletionStatus.COMPLETE

        # If any finding evaluates to INCOMPLETE, the case status is INCOMPLETE
        for finding in evidence_findings:
            status = self._rules_agent.evaluate(finding)
            if status == DeletionStatus.INCOMPLETE:
                return DeletionStatus.INCOMPLETE

        return DeletionStatus.COMPLETE

    # @deprecated
    def _get_deletion_status_old(self, evidence_findings: list) -> str:
        # @TODO - needs work
        """
        ** Evaluate all findings **
        For each case, your program has to output one of three statuses:

        - COMPLETE:
        The data is truly gone (or properly anonymized/retained
        according to strict company policy), and you can prove it with evidence.

        - INCOMPLETE:
        Ghost data still exists, or an active process/backup can
        bring the data back to life.

        - NOT_APPLICABLE:
        The user didn't actually request a deletion."""

        deletion_status = None

        # response_deletion_staus = self._model.get_response(prompt)

        # Determine what the DeletionStatus will be based on response
        # Only return one of three choices

        deletion_status = self._rules_agent.evaluate(evidence_findings)
        print(f"deletion_status={deletion_status}")

        # @TODO - Do additional logic to check rules deletion status

        # With the LLM response and evaluating the deletion rules lets determine
        # the final deletion status

        # if response in [DeletionStatus.COMPLETE, DeletionStatus.INCOMPLETE]:
        # self._rules_agent.apply(evidence_findings)
        #    return response

        return deletion_status

    def _finalize(self, deletion_status: str, findings: list[ResourceFinding]):
        """
        Delivering the Solution
        Your solution must process all the data and generate a final file called
        output.csv.
        For Complete or Incomplete cases, your code must output a structured
        list of steps (steps_json) detailing what findings were made, what
        remediation steps are needed to clean up the ghost data, and what
        verification checks must pass to make sure it stays gone.

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
        """
        if deletion_status not in [DeletionStatus.COMPLETE, DeletionStatus.INCOMPLETE]:
            return self._steps_agent.compile()

        for finding in findings:
            if finding.state == StepStates.UNKNOWN:
                print("⚠️ Warning: Evidence Finding State is `UNKNOWN`")
                continue

            rule = self._rules_agent.get_rule_by_category(finding.category)
            required_action = rule.get("required_action", StepOperations.DELETE_RECORD)

            is_incomplete = (
                self._rules_agent.evaluate(finding) == DeletionStatus.INCOMPLETE
            )

            # FINDING PHASE (If record is present)
            # if finding.state == StepStates.PRESENT:

            # REMEDIATION and VERIFICATION PHASE (Only if incomplete)
            if is_incomplete:
                self._steps_agent.add_finding_phase(finding)
                self._steps_agent.add_remediation_phase(finding, required_action)

                self._steps_agent.set_verify_incomplete(required_action)
                self._steps_agent.add_verification_phase(finding)
            else:
                self._steps_agent.set_verify_complete(finding)
                self._steps_agent.add_verification_phase(finding)

        return self._steps_agent.compile()

    def _get_output(self, deletion_status: str, steps_json: str) -> list:
        parsed_steps = (
            json.loads(steps_json) if isinstance(steps_json, str) else steps_json
        )

        return [self.case_id, deletion_status, parsed_steps]

    ### --- IGNORE BELOW --- ###

    # @depracated - too much complexity in one function
    def _finalize_keep(self, deletion_status: str, findings: list) -> str:

        if deletion_status not in [DeletionStatus.COMPLETE, DeletionStatus.INCOMPLETE]:
            return self._steps_agent.compile()

        for finding in findings:
            rule = self._rules_agent._get_rule_by_category(finding.category)
            required_action = rule.get("required_action", StepOperations.DELETE_RECORD)
            is_incomplete = (
                self._rules_agent.evaluate(finding) == DeletionStatus.INCOMPLETE
            )

            # FINDING PHASE (If record is present)
            if finding.state == StepStates.PRESENT:
                op = (
                    StepOperations.REPORT_EXPOSED_PII
                    if finding.exposed_fields
                    else StepOperations.REPORT_REMAINING_RECORD
                )
                self._steps_agent.add(
                    phase=StepPhrases.FINDING,
                    system_id=finding.system_id,
                    resource_id=finding.resource_id,
                    operation=op,
                    state=finding.state,
                    evidence_id=finding.evidence_id,
                )

            # REMEDIATION PHASE (Only if incomplete)
            if is_incomplete:
                rem_state = (
                    StepStates.ABSENT
                    if required_action == StepOperations.DELETE_RECORD
                    else StepStates.REDACTED
                )
                self._steps_agent.add(
                    phase=StepPhrases.REMEDIATION,
                    system_id=finding.system_id,
                    resource_id=finding.resource_id,
                    operation=required_action,
                    state=rem_state,
                    evidence_id="",
                )

            # VERIFICATION PHASE
            if is_incomplete:
                verify_op = (
                    StepOperations.VERIFY_RECORD_ABSENT
                    if required_action == StepOperations.DELETE_RECORD
                    else StepOperations.VERIFY_RECORD_REDACTED
                )
                verify_state = (
                    StepStates.ABSENT
                    if required_action == StepOperations.DELETE_RECORD
                    else StepStates.REDACTED
                )
                verify_evidence = ""
            else:
                verify_op = (
                    StepOperations.VERIFY_RECORD_ABSENT
                    if finding.state == StepStates.ABSENT
                    else StepOperations.VERIFY_RECORD_PRESENT
                )
                verify_state = finding.state
                verify_evidence = finding.evidence_id or ""

            self._steps_agent.add(
                phase=StepPhrases.VERIFICATION,
                system_id=finding.system_id,
                resource_id=finding.resource_id,
                operation=verify_op,
                state=verify_state,
                evidence_id=verify_evidence,
            )

        return self._steps_agent.compile()

    # @depracated
    def _finalize2(
        self, deletion_status: str, evidence_findings: list[ResourceFinding]
    ) -> str:

        if deletion_status not in [DeletionStatus.COMPLETE, DeletionStatus.INCOMPLETE]:
            return self._steps_agent.compile()

        for finding in evidence_findings:
            rule = self._rules_agent.get_rule_by_category(finding.category)
            required_action = rule.get("required_action", DEFAULT_REQ_ACTION)
            is_incomplete = (
                self._rules_agent.evaluate(finding) == DeletionStatus.INCOMPLETE
            )

            # 1. FINDING PHASE (If record is present)
            if finding.state == "PRESENT":
                op = (
                    "REPORT_EXPOSED_PII"
                    if finding.exposed_fields
                    else "REPORT_REMAINING_RECORD"
                )
                self._steps_agent.add(
                    "FINDING",
                    finding.system_id,
                    finding.resource_id,
                    op,
                    finding.state,
                    finding.evidence_id,
                )

            # 2. REMEDIATION PHASE (Only if incomplete)
            if is_incomplete:
                rem_state = (
                    "ABSENT" if required_action == DEFAULT_REQ_ACTION else "REDACTED"
                )
                self._steps_agent.add(
                    "REMEDIATION",
                    finding.system_id,
                    finding.resource_id,
                    required_action,
                    rem_state,
                    "",
                )

            # 3. VERIFICATION PHASE
            if is_incomplete:
                verify_op = (
                    "VERIFY_RECORD_ABSENT"
                    if required_action == DEFAULT_REQ_ACTION
                    else "VERIFY_RECORD_REDACTED"
                )
                verify_state = (
                    "ABSENT" if required_action == DEFAULT_REQ_ACTION else "REDACTED"
                )
                verify_evidence = ""
            else:
                verify_op = (
                    "VERIFY_RECORD_ABSENT"
                    if finding.state == "ABSENT"
                    else "VERIFY_RECORD_PRESENT"
                )
                verify_state = finding.state
                verify_evidence = finding.evidence_id or ""

            self._steps_agent.add(
                "VERIFICATION",
                finding.system_id,
                finding.resource_id,
                verify_op,
                verify_state,
                verify_evidence,
            )

        return self._steps_agent.compile()

    # @depracated
    def _finalize_old(self, deletion_status: str) -> str:

        # @TODO - Verify data is correct.
        if deletion_status in [DeletionStatus.COMPLETE, DeletionStatus.INCOMPLETE]:
            self._steps_agent.add(
                phase=None,  # StepPhrases.VERIFICATION,
                system_id=None,
                resource_id=None,
                operation=None,  # StepOperations.__
                state=None,  # StepStates._
                evidence_id=None,
            )

        steps_json = self._steps_agent.compile()

        return steps_json
