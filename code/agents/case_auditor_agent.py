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
    FINDING_OP_BY_ACTION,
    NON_DELETION_KEYWORDS,
    VALID_KEYPHRASES,
    VALIDITY_FALLBACK_ON_LLM_ERROR,
    VALIDITY_PROMPT,
)
from src.enums import DeletionStatus, StepOperations, StepStates
from src.issues import WARNING, report_issue


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

    @property
    def usage(self):
        return self._model.usage

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

            print(f"ℹ️ Step Count: {self._steps_agent.count()}")

        return self._get_output(deletion_status, steps_json)

    def _check_validity(self) -> bool:
        """Check Validity: Did the user actually ask to delete their data, or
        is the request irrelevant (NOT_APPLICABLE)?"""

        text = self.request_text.lower() if self.request_text else ""
        if any(word in text for word in NON_DELETION_KEYWORDS):
            return False

        if any(phrase in text for phrase in VALID_KEYPHRASES):
            return True

        print("Validity still unknown. Asking model...")
        prompt = VALIDITY_PROMPT.format(request_text=self.request_text)

        response = self._model.get_response(prompt)

        if isinstance(response, bool):
            return response

        if isinstance(response, dict):
            # Error dict or unexpected JSON: apply the deliberate fallback and say so.
            report_issue(
                WARNING,
                f"Case {self.case_id}: LLM could not classify the request. "
                f"Defaulting validity to {VALIDITY_FALLBACK_ON_LLM_ERROR}.",
            )
            return VALIDITY_FALLBACK_ON_LLM_ERROR

        return str(response).strip().lower() in ("true", "yes", "1")

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

        # Scenario 1: No user found initially - attempt fallback to historical logs
        if user_identity.empty:
            print("⚠️ Warning: User unidentified, checking historical logs...")
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

        # Determine final status based on the exact user count
        user_count = len(user_identity)

        if user_count == 0:
            # Scenario 2: Zero users found (even after historical log check)
            # If it's still empty log a warning.
            report_issue(
                WARNING,
                f"⚠️ Case {self.case_id}: User {self.email} completely unknown.",
            )
            return {
                "evidence_files": evidence_files_df,
                "system_activity": system_activity_df,
                "activity_pool": pd.DataFrame(),
                "user_audit_log": user_audit_log_df,
                "user_identities": user_identities_df,
            }

        elif user_count > 1:
            # Scenario 3: Ambiguous results (multiple matching users returned)
            report_issue(
                WARNING,
                f"⚠️ Case {self.case_id}: Multiple users matching {self.email} returned.",
            )
            return {
                "evidence_files": evidence_files_df,
                "system_activity": system_activity_df,
                "activity_pool": pd.DataFrame(),
                "user_audit_log": user_audit_log_df,
                "user_identities": user_identities_df,
            }

        else:
            # Scenario 4: Exactly 1 user found (Success path)
            user_id = user_identity.iloc[0]["user_id"]

            # Accessing directly via column index is faster than .to_dict()
            print(f"😎 User identified as {user_id}")

            # Get user history
            user_audit_log = user_audit_log_df[user_audit_log_df["user_id"] == user_id]
            system_activity = self._filter_system_activity(system_activity_df)

            # Filter out future evidence files
            evidence_files = evidence_files_df[
                evidence_files_df["captured_at"] <= self.audit_at
            ]

            return {
                "evidence_files": evidence_files,
                "system_activity": system_activity,
                "activity_pool": system_activity_df[
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

    def _finalize(self, deletion_status: str, findings: list[ResourceFinding]):
        if deletion_status not in [DeletionStatus.COMPLETE, DeletionStatus.INCOMPLETE]:
            return self._steps_agent.compile()

        for finding in findings:
            if finding.state == StepStates.UNKNOWN:
                report_issue(
                    WARNING,
                    f"Case {self.case_id}: finding {finding.resource_id} has UNKNOWN state.",
                )
                continue

            rule = self._rules_agent.get_rule_by_category(finding.category)
            required_action = rule.get("required_action", StepOperations.DELETE_RECORD)

            is_incomplete = (
                self._rules_agent.evaluate(finding) == DeletionStatus.INCOMPLETE
            )

            if is_incomplete:
                self._steps_agent.add_finding_phase(
                    finding, FINDING_OP_BY_ACTION[required_action]
                )
                self._steps_agent.add_remediation_phase(finding, required_action)
                self._steps_agent.set_verify_incomplete(required_action)
            else:
                # In an INCOMPLETE case every check runs after remediation -> no evidence yet
                self._steps_agent.set_verify_complete(
                    finding, with_evidence=deletion_status == DeletionStatus.COMPLETE
                )

            self._steps_agent.add_verification_phase(finding)

        return self._steps_agent.compile()

    def _get_output(self, deletion_status: str, steps_json: str) -> list:
        parsed_steps = (
            json.loads(steps_json) if isinstance(steps_json, str) else steps_json
        )

        return [self.case_id, deletion_status, parsed_steps]
