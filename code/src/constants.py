# /code/src/constants.py

import os
from pathlib import Path

# Constants for the application

APP_NAME = os.getenv("APP_NAME")
MODEL_NAME = os.getenv("MODEL_NAME")
MODEL_API_KEY = os.getenv("MODEL_API_KEY")
MODEL_API_URL = os.getenv("MODEL_API_URL")
USE_SAMPLE = os.getenv("USE_SAMPLE", "True")

# Data paths
DATASET_PATH = Path("./dataset/")
EVIDENCE_PATH = DATASET_PATH / "evidence"

DEL_REQUEST_FILE = "deletion_requests"
SAMPLE_DEL_REQUEST_FILE = "sample_deletion_requests"
SAMPLE_OUTPUT_FILE = "sample_output"
OUTPUT_FILE = "output"

DATASET_FILES = [
    DEL_REQUEST_FILE,
    "deletion_rules",
    "evidence_files",
    "system_activity",
    "user_audit_log",
    "user_identities",
    OUTPUT_FILE,
]

# Miscellaneous
BANNER_PADDING = 4
SECONDS_IN_MIN = 60
SECONDS_IN_HR = SECONDS_IN_MIN * SECONDS_IN_MIN
SECONDS_TO_MSEC = 1000
PEP8_LINE_LEN = 79
