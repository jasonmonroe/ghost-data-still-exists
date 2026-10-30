# /code/src/data_handler.py
# +---------------------------------------------------------------------------+
# |                              DATA HANDLER                                 |
# +---------------------------------------------------------------------------+
# Data handler for the application

# Python Libraries
import json

# Vendor Libraries
import pandas as pd

# Local Libraries
from src.constants import (
    DATASET_FILES,
    DATASET_PATH,
    OUTPUT_COLUMNS,
    OUTPUT_FILEPATH,
    USE_SAMPLE,
)


class DataHandler:
    def __init__(self):
        self.deletion_requests = None
        self.deletion_rules = None
        self.evidence = None
        self.evidence_files = None
        self.output = None
        self.sample_deletion_requests = None
        self.sample_output = None
        self.system_activity = None
        self.user_audit_log = None
        self.user_identities = None

        self._load_data()
        self._load_evidence()

    def _load_data(self):
        for csv_filename in DATASET_FILES:
            if hasattr(self, csv_filename):
                filepath = DATASET_PATH / f"{csv_filename}.csv"
                setattr(
                    self,
                    csv_filename,
                    pd.read_csv(filepath),
                )

        # Override output if using sample
        if USE_SAMPLE:
            self.output = self.sample_output
            self.deletion_requests = self.sample_deletion_requests

            print(f"ℹ️ Using sample data.\n {len(self.deletion_requests)} rows.")

    def _load_evidence(self):
        """Evidence paths come from evidence_files.csv; files are read lazily."""
        paths = self.evidence_files["file_path"]
        self.evidence = {
            "records": [
                DATASET_PATH / p for p in paths if p.startswith("evidence/records/")
            ]
        }

    def save(self, output_csv: list) -> None:
        # Save output csv file to dataset output file.
        print("Saving data to output.csv.")

        output_df = pd.DataFrame(output_csv, columns=OUTPUT_COLUMNS)
        output_df["steps_json"] = output_df["steps_json"].apply(json.dumps)

        output_df.sort_values("case_id").to_csv(OUTPUT_FILEPATH, index=False)
