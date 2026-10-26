# /code/src/data_handler.py

# Data handler for the application


import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import scikit-learn as sklearn
import scipy as sp
import statsmodels as sm

# Local Libraries
from src.constants import (
    DATASET_FILES, 
    DATASET_PATH, 
    EVIDENCE_PATH, 
    SAMPLE_DEL_REQUEST_FILE, 
    SAMPLE_OUTPUT_FILE, 
    USE_SAMPLE,
    )

class DataHandler:
    def __init__(self, use_sample: bool):
        
        self.deletion_requests = None
        self.deletion_rules = None
        self.evidence_files = None
        self.output = None
        self.system_activity = None
        self.user_audit_log = None
        self.user_identities = None
        
        self.evidence = self._load_evidence()

    def load_data(self, use_sample: bool):
         
        for csv_file in DATASET_FILES:
            if getattr(self, csv_file):
                filepath = f"{DATASET_PATH}{csv_file}.csv"
                setattr(self, csv_file, pd.read_csv(filepath))

        # Override output if using sample
        if use_sample:
            self.output = DATASET_PATH / f"{SAMPLE_OUTPUT_FILE}.csv"
            self.deletion_requests = DATASET_PATH / f"{SAMPLE_DEL_REQUEST_FILE}.csv"
     

    def _load_evidence(self):
        # Just load the filenames
        self.evidence = []

        # Map each evidence subdirectory name to its sorted file paths.
        return {
            sub_dir.name: sorted(
                p for p in sub_dir.iterdir()
                if p.is_file() and not p.name.startswith(".")
            )
            for sub_dir in sorted(EVIDENCE_PATH.iterdir())
            if sub_dir.is_dir()
        }

        """
        for sub_dir in EVIDENCE_PATH:
            dir_name = str(sub_dir.stem).lower()
            self.evidence[dir_name] = {}

            # Get all file paths in the sub directory
            sub_dir_files = [f for f in sub_dir.iterdir() if f.is_file()]
            for sub_dir_files in sub_dir.iterdir():
                for sub_dir_file in sub_dir_files:
                    # read data
                    sub_dir_filepath =  None
                    self.evidence[dir_name][sub_dir_file.name] = None
        """

    def save(self, output_csv):
        # Save output csv file to dataset output file.
        
    