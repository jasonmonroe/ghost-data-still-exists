# code/agents/case_auditor_agent.py

"""
Case Auditor Agent

An AI-powered automated auditor that investigates data deletion requests for
518 different cases (dataset/deletion_requests.csv). For every request, your AI
agent must act like a meticulous digital detective.

Audits each case and finalizes the resolution, and returns the solution
"""


class CaseAuditorAgent:
    def __init__(self) -> None:
        # It's empty right now
        pass

    def get_case_by_id(case_id: str):
        # main public function
        pass

    def _check_validity(self):
        """Check Validity: Did the user actually ask to delete their data, or
        is the request irrelevant (NOT_APPLICABLE)?"""

    def _analyze(self):
        """Uncover the Truth: Look past what the company's dashboard claims
        ("Complete!") and check the actual evidence files (such as database
        snapshots, logs, and support tickets) to see if personal data is still
        lingering somewhere it shouldn't be."""

    def _resolve_identities(self):
        """Resolve Identities: Match current and historical names, emails, and
        phone numbers to track down all traces of the user."""

    def _determine_outcome(self):
        """For each case, your program has to output one of three statuses:
        - COMPLETE: The data is truly gone (or properly anonymized/retained
        according to strict company policy), and you can prove it with evidence.

        - INCOMPLETE: Ghost data still exists, or an active process/backup can
        bring the data back to life.

        - NOT_APPLICABLE: The user didn't actually request a deletion."""

    def _finalize(self):
        """Delivering the Solution
        Your solution must process all the data and generate a final file called
        output.csv.
        For Complete or Incomplete cases, your code must output a structured
        list of steps (steps_json) detailing what findings were made, what
        remediation steps are needed to clean up the ghost data, and what
        verification checks must pass to make sure it stays gone."""

    def _get_output(self):
        return []
