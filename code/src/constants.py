# /code/src/constants.py
# +---------------------------------------------------------------------------+
# |                              CONSTANTS                                    |
# +---------------------------------------------------------------------------+

# 🚨
# ⚠️
# 💡

import os
import re
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

DATASET_FILES = [
    "deletion_requests",
    "deletion_rules",
    "evidence_files",
    "output",
    "sample_deletion_requests",
    "sample_output",
    "system_activity",
    "user_audit_log",
    "user_identities",
]

# Miscellaneous
BANNER_PADDING = 4
PEP8_LINE_LEN = 79
SECONDS_IN_MIN = 60
SECONDS_IN_HR = SECONDS_IN_MIN * SECONDS_IN_MIN
SECONDS_TO_MSEC = 1000
MAX_TOKENS = 2048
DATETIME_DURATION = 10
RATE_LIMIT_PAUSE_TIMER = 3
RATE_LIMIT_RETRIES = 4
RATE_LIMIT_STATUS_ERR_CODE = 429
INTERNAL_STATUS_ERR_CODE = 500
DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
PHONE_LEN = 7

DEFAULT_FIELD_NAME = "identifier"
DEFAULT_RULE_CATEGORY = "general_record"

RESOURCE_ID_RE = re.compile(
    r"\b(?:account|search|analytics|support|cache|export|email_delivery|audit_record"
    r"|data_flow|backup|tombstone|legal_hold|marketing)_\d+\b"
)
TRACE_ID_RE = re.compile(r"\b(tr-[\w-]+)\b")
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{6,}\d")
LINK_RE = re.compile(r"linked (\S+) .*? to (\S+@\S+?) and (user_\d+)", re.IGNORECASE)
ABSENT_HINT_RE = re.compile(
    r'rows="?0"?(?!\d)|http_status="?404|NOT_FOUND', re.IGNORECASE
)

# Personal Identifiiable Information (PII)
PII_FIELDS = {
    "name",
    "full_name",
    "email",
    "phone",
    "email_hash",
    "requester_name",
    "requester_email",
    "requester_phone",
    "owner_email",
    "owner_phone",
    "customer_email",
    "display_name",
}

SYSTEM_BY_PREFIX = {  # resource prefix → output system_id
    "account": "account_service",
    "search": "search_service",
    "support": "support_platform",
    "analytics": "analytics_platform",
    "audit_record": "security_service",
    "data_flow": "integration_service",
    "backup": "backup_service",
    "export": "export_service",
    "tombstone": "identity_service",
}


# Case
VALID_KEYPHRASES = (
    "close my account",
    "delete my account",
    "erase my account",
    "remove my account",
    "terminate my account",
    "close my profile",
    "delete my profile",
    "erase my profile",
    "remove my profile",
    "terminate my profile",
    "close my data",
    "delete my data",
    "erase my data",
    "remove my data",
    "terminate my data",
    "delete all my personal details",
)

NON_DELETION_KEYWORDS = (
    "unsubscribe",
    "mailing list",
    "export my data",
    "download my data",
    "change my email",
    "update my phone",
    "reset my password",
)

TARGET_SYSTEMS = {
    "cache": "cache_service",
    "email_delivery": "email_delivery_service",
    "marketing": "marketing_platform",
    "tombstone": "identity_service",
}

# Prompt Instructions
SYSTEM_INSTR_PROMPT = """
You are a consumer behavioral expert and data privacy compliance auditor. 
Your task is to analyze customer messages to determine if they explicitly 
authorize deleting their account, profile, or personal data.

Classification Rules:
- DELETION: The person asks to delete, erase, close, or remove their account or 
personal data (in any language, including indirect phrasing like "close my 
account and remove my details").
- NOT_DELETION: Data access/copy requests, exports, corrections/updates, 
marketing/email opt-outs, unsubscribes, password resets, complaints, or 
questions.
- If a request mixes both, it is DELETION only if deletion is explicitly 
requested.
- If the request is in a language other than English, translate and evaluate 
its intent.

Output Requirement:
Return ONLY the exact boolean value True or False. Do not include markdown 
fences, prose, or explanation.
""".strip()


VALIDITY_PROMPT = """
As a user behavioral expert, analyze this user request to determine if 
they're explicitly requesting to delete, erase, close, or remove their 
account, profile, or personal data. 

Note: 
- If the request is in a language other than English, translate and evaluate 
its intent.
- Requests for data export, downloading data, changing passwords, updating 
emails, or unsubscribing from marketing emails are NOT deletion requests and
 must return False.

Return ONLY the boolean value True or False.

CUSTOMER REQUEST:
"{request_text}"
""".strip()

# Prompt to obtain steps according to the steps agent.
# @TODO - check if needed
STEPS_PROMPT = """ """.strip()
