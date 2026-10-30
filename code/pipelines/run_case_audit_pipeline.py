# code/pipelines/run_case_audit_pipeline.py


# Local Libraries
from agents.case_auditor_agent import CaseAuditorAgent
from src.utils import get_progress_bar


def run_case_audit_pipeline(dataset: dict):
    print("\n--- 🏃 Running Case Audit Pipeline 🏃 ---")
    output_csv = []

    cases_df = dataset.get("deletion_requests")
    row_count = len(cases_df)
    auditor = CaseAuditorAgent(dataset)

    # Analyze each case for deletion requests
    """
    {
        "case_id": "case_01",
        "email": "amina.elmasri@gmail.com",
        "requested_at": "2026-08-18T09:14:00Z",
        "reported_status": "COMPLETE",
        "reported_at": "2026-08-20T16:42:00Z",
        "audit_at": "2026-09-03T11:30:00Z",
        "request_text": "Hi, I haven’t used this account in years and would like it closed. Please remove the profile and the personal details attached to it."
        }
    """

    for index, case_df in cases_df.iterrows():
        output = auditor.audit_by_case(case_df)
        output_csv.append(output)

        print(f"Case ID: {case_df['case_id']}" + get_progress_bar(index + 1, row_count))

    # Return the output csv data
    return output_csv
