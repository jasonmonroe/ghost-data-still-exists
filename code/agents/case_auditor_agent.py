# code/agents/case_auditor_agent.py

"""
Case Auditor Agent

An AI-powered automated auditor that investigates data deletion requests for
518 different cases (dataset/deletion_requests.csv). For every request, your AI
agent must act like a meticulous digital detective.

Audits each case and finalizes the resolution, and returns the solution
"""

# Python Libraries
import json

# Vendor Libraries
from code.agents.steps_agent import StepsAgent

import pandas as pd

# Local Libraries
from agents.deletion_rule_agent import DeletionRuleAgent
from agents.evidence_agent import EvidenceAgent
from models.llm_model import LlmModel
from src.constants import (
    DATETIME_DURATION,
    NON_DELETION_KEYWORDS,
    VALID_KEYPHRASES,
    VALIDITY_PROMPT,
)
from src.enums import DeletionStatus, ReportedStatus
from src.prompt_builder import PromptBuilder


class CaseAuditorAgent:
    def __init__(self, dataset: dict) -> None:
        self._data = dataset
        self._model = LlmModel()
        self._evidence_agent = EvidenceAgent(
            dataset.get("evidence"),  # @TODO - may not need
        )
        self._rules_agent = DeletionRuleAgent(dataset.get("deletion_rules"))
        self._steps_agent = StepsAgent()

        self.case_id = None
        self.email = None
        self.requested_at = None
        self.reported_status = None
        self.reported_at = None
        self.audit_at = None
        self.request_text = None

    def audit_by_case(self, case_s: pd.Series) -> list:
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

            if user_dataset.get("user_identity") is None:
                deletion_status = DeletionStatus.COMPLETE
                evidence_dataset = {}
            else:
                evidence_dataset = self._analyze(user_dataset)
                user_evidence_dataset = user_dataset
                user_evidence_dataset["evidence"] = evidence_dataset

                # user_evidence_dataset = {**user_dataset, **evidence_dataset}

                # With results lets build a prompt and get a response to determine final DeletionStatus
                builder = PromptBuilder(user_evidence_dataset, case_s)
                deletion_status = self._get_deletion_status(builder.prompt)

            # @TODO - Apply Rules here?
            results = self._rules_agent.apply()
            steps_json = self._finalize(deletion_status)

        # Build Prompt

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
        prompt = VALIDITY_PROMPT.format(text=self.response_text)
        print("Validity still unknown.  Asking model...")
        response = self._model.get_response(prompt)
        return response.strip().lower() in ("true", "yes", "1")

    def _analevyze(self, user_dataset: dict) -> dict:
        """Uncover the Truth: Look past what the company's dashboard claims
        ("Complete!") and check the actual evidence files (such as database
        snapshots, logs, and support tickets) to see if personal data is still
        lingering somewhere it shouldn't be."""

        # Search global logs (system_activity.csv), evidence files, databases,
        # backups, or exports around or before audit_at (2026-09-03T11:30:00Z)
        # to see if any residual data or recreation risks exist, comparing
        # findings against deletion_rules.csv.

        evidence_dataset = self._evidence_agent.search(user_dataset)

        return evidence_dataset

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

        # Find user by email
        user_identity = user_identities_df[
            user_identities_df["email"].str.lower() == self.email.lower()
        ]

        if len(user_identity) != 0:
            # Return the unfiltered datasets
            print(
                f"Warning: Case: {self.case_id} User {self.email} unknown or multiple users returned."
            )

            return {
                "evidence_files": evidence_files_df,
                "system_activity": system_activity_df,
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

        # @TODO - might be over filtering
        # if target_system:
        #    origin_text = target_system.split("_")[0]
        #    # Find all rows where the origin column contains system_activity.target_system
        #    evidence_files = evidence_files[
        #        evidence_files["origin"].str.contains(origin_text, na=False)
        #    ]

        # Returning filtered data
        return {
            "evidence_files": evidence_files,
            "system_activity": system_activity,
            "user_audit_log": user_audit_log,
            "user_identities": user_identity,
        }

    def _filter_system_activity(self, system_activity_df: pd.DataFrame) -> pd.DataFrame:

        def _delta(op: str) -> str:
            reported_at = pd.Timestamp(self.reported_at)
            delta = pd.Timedelta(minutes=DATETIME_DURATION)
            expr = (f"{reported_at} {op} {delta}").strftime("%Y-%m-%dT%H:%M:%SZ")

            return eval(expr)

        # Filter system activity by timestamp
        # Only consider activity events.event_time occuring on or BEFORE
        # user_identities.audit_at
        system_activity_df = system_activity_df[
            system_activity_df["event_time"].between(
                self.requested_at, self.reported_at
            )
        ]

        # Narrow the window further if reported status complete
        # Use +- 10 minutes for all activities around this datetime
        # target_system = None
        if self.reported_status == ReportedStatus.COMPLETE:
            earliest_activity = _delta("-")
            latest_activity = _delta("+")

            # pd_timestamp = pd.Timestamp(self.reported_at)

            # earliest_activity = (
            #    pd_timestamp - pd.Timedelta(minutes=DATETIME_DURATION)
            # ).strftime("%Y-%m-%dT%H:%M:%SZ")

            # latest_activity = (
            #    pd_timestamp + pd.Timedelta(minutes=DATETIME_DURATION)
            # ).strftime("%Y-%m-%dT%H:%M:%SZ")

            system_activity_df = system_activity_df[
                system_activity_df["event_time"].between(
                    earliest_activity, latest_activity
                )
            ]

            # if len(system_activity) == 1:
            # target_system = system_activity.iloc[0]["target_system"]

            return system_activity_df

    def _get_deletion_status(self, prompt: str) -> str:
        """For each case, your program has to output one of three statuses:

        - COMPLETE:
        The data is truly gone (or properly anonymized/retained
        according to strict company policy), and you can prove it with evidence.

        - INCOMPLETE:
        Ghost data still exists, or an active process/backup can
        bring the data back to life.

        - NOT_APPLICABLE:
        The user didn't actually request a deletion."""

        response = self._model.get_response(prompt)

        # Determine what the DeletionStatus will be based on response
        # Only return one of three choices

        if response in [DeletionStatus.COMPLETE, DeletionStatus.INCOMPLETE]:
            return response

        return DeletionStatus.NOT_APPLICABLE

    def _finalize(self, deletion_status: str) -> dict:
        """Delivering the Solution
        Your solution must process all the data and generate a final file called
        output.csv.
        For Complete or Incomplete cases, your code must output a structured
        list of steps (steps_json) detailing what findings were made, what
        remediation steps are needed to clean up the ghost data, and what
        verification checks must pass to make sure it stays gone."""

        # Format the result into the exact steps_json array structure
        """
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

        steps_json = {}

        if deletion_status in [DeletionStatus.COMPLETE, DeletionStatus.INCOMPLETE]:
            steps_json = self._steps_agent.generate()

        return steps_json

    def _get_output(self, deletion_status: str, steps_json: list) -> list:
        return [self.case_id, deletion_status, json.load(steps_json)]
