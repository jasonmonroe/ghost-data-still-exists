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
import pandas as pd

# Local Libraries
from agents.evidence_agent import EvidenceAgent
from models.llm_model import LlmModel
from src.constants import NON_DELETION_KEYWORDS, VALID_KEYPHRASES, VALIDITY_PROMPT
from src.enums import DeletionStatus
from src.prompt_builder import PromptBuilder


class CaseAuditorAgent:
    def __init__(self, dataset: dict) -> None:
        self._data = dataset
        self._model = LlmModel()
        self._agent = EvidenceAgent(
            dataset.get("evidence"),
            # dataset.get("evidence_files"),
            # dataset.get("system_activity"),
        )
        self._bulder = None

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
            evidence_dataset = self._analyze(user_dataset)
            user_evidence_dataset = {**user_dataset, **evidence_dataset}

            # With results lets build a prompt and get a response to determine final DeletionStatus
            builder = PromptBuilder(user_evidence_dataset)
            deletion_status = self._get_deletion_status(builder.prompt)

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

    def _analyze(self, user_dataset: dict) -> dict:
        """Uncover the Truth: Look past what the company's dashboard claims
        ("Complete!") and check the actual evidence files (such as database
        snapshots, logs, and support tickets) to see if personal data is still
        lingering somewhere it shouldn't be."""

        if user_dataset.get("user_identity") is None:
            deletion_status = DeletionStatus.COMPLETE
            evidence_dataset = {}
            # steps_json = ["User not found"]
        else:
            # Search global logs (system_activity.csv), evidence files, databases,
            # backups, or exports around or before audit_at (2026-09-03T11:30:00Z)
            # to see if any residual data or recreation risks exist, comparing
            # findings against deletion_rules.csv.
            self._agent = EvidenceAgent(
                self._data.get("evidence"),
                self._data.get("evidence_files"),
            )
            evidence_dataset = self._agent.search(
                user_dataset,
                # self._data.get("system_activity"),
            )

            # Set deletion status to None to be determined later
            deletion_status = None

            # steps_json = []

        # Return activity dataset to build final prompt
        return {
            "deletion_status": deletion_status,
            "evidence_dataset": evidence_dataset,
            # "steps_json": steps_json,
        }

    def _filter_by_user(self) -> dict:
        """Resolve Identities: Match current and historical names, emails, and
        phone numbers to track down all traces of the user."""

        """
        Look up `email` in user_identities.csv and user_audit_log.csv to find
        all current and historical names, emails, user IDs, or phone numbers
        associated with `person`.
        """
        user_identities_df = self._data.get("user_identities")
        user_identity = user_identities_df[user_identities_df["email"] == self.email]

        # Filter by user
        if len(user_identity) == 1:
            user_identity = user_identity.iloc[0].to_dict()
            user_id = user_identity["user_id"]
            user_audit_log_df = self._data.get("user_audit_log")
            user_audit_log = user_audit_log_df[user_audit_log_df["user_id"] == user_id]

            # Filter system activity by timestamp
            system_activity_df = self._data.get("system_activity")

            # Only consider activity events.event_time occuring on or BEFORE user_identities.audit_at
            system_activity = system_activity_df[
                system_activity_df["event_time"] <= self.audit_at
            ]

            # Filter out evidence files to prevent looking at future evidence
            evidence_files_df = self._data.get("evidence_files")
            evidence_files = evidence_files_df[
                evidence_files_df["captured_at"] <= self.audit_at
            ]

        else:
            print(
                f"Warning: Case: {self.case_id} User {self.email} unknown or multiple users returned."
            )

            evidence_files = None
            system_activity = None
            user_audit_log = None
            user_identity = None

        return {
            "evidence_files": evidence_files,
            "system_activity": system_activity,
            "user_audit_log": user_audit_log,
            "user_identities": user_identity,
        }

    def _get_deletion_status(self, prompt: str) -> str:
        """For each case, your program has to output one of three statuses:
        - COMPLETE: The data is truly gone (or properly anonymized/retained
        according to strict company policy), and you can prove it with evidence.

        - INCOMPLETE: Ghost data still exists, or an active process/backup can
        bring the data back to life.

        - NOT_APPLICABLE: The user didn't actually request a deletion."""

        response = self._model.get_response(prompt)

        # Determine what the DeletionStatus will be based on response
        # Only return one of three choices

        if response in [DeletionStatus.COMPLETE, DeletionStatus.INCOMPLETE]:
            return response

        return DeletionStatus.NOT_APPLICABLE

    def _finalize(self, deletion_status: str):
        """Delivering the Solution
        Your solution must process all the data and generate a final file called
        output.csv.
        For Complete or Incomplete cases, your code must output a structured
        list of steps (steps_json) detailing what findings were made, what
        remediation steps are needed to clean up the ghost data, and what
        verification checks must pass to make sure it stays gone."""

        # Format the result into the exact steps_json array structure

        steps_json = {}

        if deletion_status in [DeletionStatus.COMPLETE, DeletionStatus.INCOMPLETE]:
            # Build steps
            pass

        return steps_json

    def _get_output(self, deletion_status: str, steps_json: list) -> list:
        return [self.case_id, deletion_status, json.load(steps_json)]
