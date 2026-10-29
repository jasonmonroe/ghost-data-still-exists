# /code/main.py

"""
This project (Ghost Data Still Exists) is an audit challenge that simulates a
major real-world data privacy problem: When a user asks a company to delete
their personal data, companies often think they’ve erased everything, but
"ghost data" is usually left behind.
To picture how this works and what your AI agent needs to do, break it down
into four simple parts:

1. The Real-World Problem
Imagine an online shopping company called Northstar Shop. When a customer
requests to delete their account, the company's main software dashboard happily
reports: "Deletion Complete!"
Weeks later, that same customer tries to sign up again, but the system blocks
them saying, "This email is already registered."
How can the email still be registered if the account was supposedly deleted?
The reality is that user data gets copied all over the place—into backup
archives, customer support logs, analytics databases, export files, search
indexes, or secondary replicas. Furthermore, active background synchronization
processes can sometimes recreate or re-import data that was already deleted
from the primary database.

2. The Goal of the Project
Your task is to build an AI-powered automated auditor that investigates data
deletion requests for 518 different cases (dataset/deletion_requests.csv). For
every request, your AI agent must act like a meticulous digital detective:

- Check Validity: Did the user actually ask to delete their data, or is the
request irrelevant (NOT_APPLICABLE)?

- Uncover the Truth: Look past what the company's dashboard claims ("Complete!")
and check the actual evidence files (such as database snapshots, logs, and
support tickets) to see if personal data is still lingering somewhere it
shouldn't be.

- Resolve Identities: Match current and historical names, emails, and phone
numbers to track down all traces of the user.

3. Deciding the DeletionStatus
For each case, your program has to output one of three statuses:

- COMPLETE: The data is truly gone (or properly anonymized/retained according
to strict company policy), and you can prove it with evidence.

- INCOMPLETE: Ghost data still exists, or an active process/backup can bring
the data back to life.

- NOT_APPLICABLE: The user didn't actually request a deletion.

4. Delivering the Solution
Your solution must process all the data and generate a final file called
output.csv.
For Complete or Incomplete cases, your code must output a structured list of
steps (steps_json) detailing what findings were made, what remediation steps are
 needed to clean up the ghost data, and what verification checks must pass to
 make sure it stays gone.

__author__ = "Jason Monroe (jason@jasonmonroe.com)"
__copyright__ = "Copyright © 2011-2026 Monroe Labs Co."
__date__ = "2026-10-25"
__version__ = "1.0.0"

"""

from dotenv import load_dotenv
from src.constants import APP_NAME

# Python Libraries

load_dotenv("../.env")

# Python Libraries

import warnings

# Local Libraries
from evaluation.main import main as run_evaluation_pipeline
from pipelines.run_case_audit_pipeline import run_case_audit_pipeline
from src.data_handler import DataHandler
from src.utils import banner, get_run_id, show_time, start_timer, stop_timer


def main():
    warnings.filterwarnings("ignore")

    # Calling main pipeline from code evaluation
    run_evaluation_pipeline()

    # Get Dataset
    data_handle = DataHandler()
    dataset = data_handle.__dict__

    # Running pipelines
    output_csv = run_case_audit_pipeline(dataset)

    if len(output_csv) == 0:
        print("⚠️ Warning: No output data returned.")
        return

    # Override dataset/output.csv
    data_handle.save(output_csv)


if __name__ == "__main__":
    # Run ID
    run_id = get_run_id()
    print(f"Run ID: {run_id}")

    banner(APP_NAME.replace("_", " ").upper())

    # Start Time
    start_time = start_timer()
    main()
    time_taken = stop_timer(start_time)

    # Print Time Taken
    show_time(time_taken)
    print(f"----- End of Program {run_id} -----\n")
