# /code/src/data_handler.py

# Data handler for the application


import pandas as pd

# Local Libraries
from src.constants import (
    DATASET_FILES,
    DATASET_PATH,
    EVIDENCE_PATH,
    OUTPUT_FILE,
    SAMPLE_DEL_REQUEST_FILE,
    SAMPLE_OUTPUT_FILE,
    USE_SAMPLE,
)


class DataHandler:
    def __init__(self):

        self.deletion_requests = None
        self.deletion_rules = None
        self.evidence_files = None
        self.output = None
        self.system_activity = None
        self.user_audit_log = None
        self.user_identities = None

        self.load_data()

        self.evidence = self._load_evidence()

    def load_data(self):

        for csv_filename in DATASET_FILES:
            if hasattr(self, csv_filename):
                filepath = DATASET_PATH / f"{csv_filename}.csv"
                setattr(self, csv_filename, pd.read_csv(filepath))

        # Override output if using sample
        if USE_SAMPLE in [True, "True"]:
            print("ℹ️ Using sample data")
            self.output = DATASET_PATH / f"{SAMPLE_OUTPUT_FILE}.csv"
            self.deletion_requests = DATASET_PATH / f"{SAMPLE_DEL_REQUEST_FILE}.csv"

    def _load_evidence(self) -> dict:
        # Just load the filenames do not read until ready for reading
        self.evidence = {}

        # Map each evidence subdirectory name to its sorted file paths.
        return {
            sub_dir.name: sorted(
                p
                for p in sub_dir.iterdir()
                if p.is_file() and not p.name.startswith(".")
            )
            for sub_dir in sorted(EVIDENCE_PATH.iterdir())
            if sub_dir.is_dir()
        }

    def save(self, output_csv) -> None:
        # Save output csv file to dataset output file.
        print(f"Saving data to {OUTPUT_FILE}.")
        output_df = pd.DataFrame(output_csv)
        output_df.to_csv(OUTPUT_FILE, index=False)
