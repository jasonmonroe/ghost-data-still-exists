# code/pipelines/run_case_audit_pipeline.py


from agents.case_auditor_agent import CaseAuditorAgent
from src.utils import get_progress_bar


def run_case_audit_pipeline(dataset: dict):
    print("\n--- 🏃 Running Case Audit Pipeline 🏃 ---")
    output_csv = []

    auditor = CaseAuditorAgent()

    cases = []
    row_count = len(cases)

    # Analyze each case
    for _ in cases:
        row_idx = 0

        output = None
        output_csv = output_csv.append(output)

        print(get_progress_bar(row_idx, row_count))

    # Return the output csv data
    return output_csv
