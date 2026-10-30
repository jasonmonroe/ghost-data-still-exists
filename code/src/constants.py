# /code/src/constants.py
# +---------------------------------------------------------------------------+
# |                              CONSTANTS                                    |
# +---------------------------------------------------------------------------+
# 🚨 ⚠️ 💡
import os
import re
from pathlib import Path

from src.enums import StepOperations, StepPhases, StepStates

# ============================================================================
# ENVIRONMENT & APP SETTINGS
# ============================================================================

APP_NAME = os.getenv("APP_NAME", "Ghost Data Still Exists")
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_API_ENDPOINT = os.getenv("GEMINI_API_ENDPOINT")
# Parsed once here; every module imports this bool (never re-parse the env var).
# Optional USD price per 1M tokens, used only for the cost estimate in usage_report.md.
# Left unset, the report says "price not configured" instead of guessing.
INPUT_PRICE_PER_MTOK = os.getenv("INPUT_PRICE_PER_MTOK")
OUTPUT_PRICE_PER_MTOK = os.getenv("OUTPUT_PRICE_PER_MTOK")
USE_SAMPLE = os.getenv("USE_SAMPLE", "True").strip().lower() in (
    "true",
    "1",
    "t",
    "yes",
)


# ============================================================================
# FILE PATHS & DIRECTORIES
# ============================================================================

DATASET_PATH = Path("./dataset/")
OUTPUT_FILE = "output.csv"
OUTPUT_FILEPATH = Path(".") / OUTPUT_FILE  # repo root, per the submission contract

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


# ============================================================================
# NUMERIC LIMITS, TIMEVALS & DEFAULTS
# ============================================================================

BANNER_PADDING = 4
PEP8_LINE_LEN = 79
SECONDS_IN_MIN = 60
SECONDS_IN_HR = SECONDS_IN_MIN * SECONDS_IN_MIN
SECONDS_TO_MSEC = 1000
MAX_TOKENS = 2048
DATETIME_DURATION = 10
WORKFLOW_SOURCE_SYSTEM = "deletion_worker"
RATE_LIMIT_PAUSE_TIMER = 3
RATE_LIMIT_RETRIES = 4
RATE_LIMIT_STATUS_ERR_CODE = 429
INTERNAL_STATUS_ERR_CODE = 500
DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
PHONE_LEN = 7

OUTPUT_COLUMNS = ["case_id", "deletion_status", "steps_json"]
DEFAULT_RULE_CATEGORY = "general_record"

# If the LLM cannot classify a request (outage, rate limit, bad output), treat
# it as a deletion request. Missing real leftover data is the failure this audit
# exists to prevent; a false NOT_APPLICABLE would hide it.
VALIDITY_FALLBACK_ON_LLM_ERROR = True

# Fallback sort priority for unknown or unmapped phases/operations
DEFAULT_SORT_PRIORITY = 99

PROCESS_FLAGS = {
    "backup": ("restore_allowed", 4, StepStates.ACTIVE, StepStates.BLOCKED),
    "data_flow": ("enabled", 4, StepStates.ACTIVE, StepStates.DISABLED),
}
PROCESS_CATEGORIES = {"BACKUP_ARCHIVE", "DATA_FLOW"}

# ============================================================================
# REGULAR EXPRESSION PATTERNS
# ============================================================================
ABSENT_HINT_RE = re.compile(
    r'rows="?0"?(?!\d)|http_status="?404|NOT_FOUND', re.IGNORECASE
)
LINK_RE = re.compile(
    r"linked (\S+) .*? to ([\w.-]+@[\w.-]+) and (user_\d+)", re.IGNORECASE
)
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{6,}\d")
PROCESS_TABLE_STATE_RE = re.compile(
    r"\|\s*(ACTIVE|BLOCKED|DISABLED)\s*\|", re.IGNORECASE
)
RESOURCE_ID_RE = re.compile(
    r"\b(?:account|search|analytics|support|cache|export|email_delivery|audit_record"
    r"|data_flow|backup|tombstone|legal_hold|marketing)_\d+\b"
)
SQL_VALUE_RE = re.compile(r"'((?:[^']|'')*)'|(NULL)|(-?\d+(?:\.\d+)?)")
TRACE_ID_RE = re.compile(r"\b(tr-[\w-]+)\b")

# ============================================================================
# MAPPINGS & DICTIONARIES
# ============================================================================
CATEGORY_BY_PREFIX = {
    "account": "USER_PROFILE",
    "analytics": "ANALYTICS_PROFILE",
    "audit_record": "SECURITY_AUDIT_LOG",
    "backup": "BACKUP_ARCHIVE",
    "cache": "CACHE_ENTRY",
    "data_flow": "DATA_FLOW",
    "email_delivery": "EMAIL_DELIVERY_LOG",
    "export": "USER_EXPORT",
    "legal_hold": "LEGAL_HOLD_RECORD",
    "marketing": "MARKETING_PROFILE",
    "search": "SEARCH_INDEX_ENTRY",
    "support": "SUPPORT_MESSAGE",
    "tombstone": "ACCOUNT_TOMBSTONE",
}

STEP_AGENT_PHASE_ORDER = {
    StepPhases.FINDING: 1,
    StepPhases.REMEDIATION: 2,
    StepPhases.VERIFICATION: 3,
}

ACTION_MAPPING = {
    "DELETE": StepOperations.DELETE_RECORD,
    "REDACT": StepOperations.REDACT_RECORD,
    "ANONYMIZE": StepOperations.ANONYMIZE_RECORD,
    "RETAIN": StepOperations.VERIFY_RECORD_PRESENT,
}

VERIFY_OP_MAPPING = {
    StepOperations.DELETE_RECORD: StepOperations.VERIFY_RECORD_ABSENT,
    StepOperations.REDACT_RECORD: StepOperations.VERIFY_RECORD_REDACTED,
    StepOperations.ANONYMIZE_RECORD: StepOperations.VERIFY_RECORD_ANONYMIZED,
    StepOperations.DISABLE_DATA_FLOW: StepOperations.VERIFY_DATA_FLOW_DISABLED,
    StepOperations.BLOCK_RESTORE: StepOperations.VERIFY_RESTORE_BLOCKED,
}

VERIFY_STATE_MAPPING = {
    StepOperations.DELETE_RECORD: StepStates.ABSENT,
    StepOperations.REDACT_RECORD: StepStates.REDACTED,
    StepOperations.ANONYMIZE_RECORD: StepStates.ANONYMIZED,
    StepOperations.DISABLE_DATA_FLOW: StepStates.DISABLED,
    StepOperations.BLOCK_RESTORE: StepStates.BLOCKED,
}

VERIFY_OP_BY_STATE = {
    StepStates.ABSENT: StepOperations.VERIFY_RECORD_ABSENT,
    StepStates.PRESENT: StepOperations.VERIFY_RECORD_PRESENT,
    StepStates.REDACTED: StepOperations.VERIFY_RECORD_REDACTED,
    StepStates.ANONYMIZED: StepOperations.VERIFY_RECORD_ANONYMIZED,
    StepStates.BLOCKED: StepOperations.VERIFY_RESTORE_BLOCKED,
    StepStates.DISABLED: StepOperations.VERIFY_DATA_FLOW_DISABLED,
}
FINDING_OP_BY_ACTION = {
    StepOperations.DELETE_RECORD: StepOperations.REPORT_REMAINING_RECORD,
    StepOperations.REDACT_RECORD: StepOperations.REPORT_EXPOSED_PII,
    StepOperations.ANONYMIZE_RECORD: StepOperations.REPORT_EXPOSED_PII,
    StepOperations.BLOCK_RESTORE: StepOperations.REPORT_RESTORE_RISK,
    StepOperations.DISABLE_DATA_FLOW: StepOperations.REPORT_ACTIVE_DATA_FLOW,
}

OP_PRIORITY = {
    # Findings
    StepOperations.REPORT_REMAINING_RECORD: 1,
    StepOperations.REPORT_EXPOSED_PII: 2,
    StepOperations.REPORT_ACTIVE_DATA_FLOW: 3,
    StepOperations.REPORT_RESTORE_RISK: 4,
    # Remediations
    StepOperations.DISABLE_DATA_FLOW: 1,
    StepOperations.BLOCK_RESTORE: 2,
    StepOperations.DELETE_RECORD: 3,
    StepOperations.REDACT_RECORD: 4,
    StepOperations.ANONYMIZE_RECORD: 5,
    # Verifications
    StepOperations.VERIFY_RECORD_ABSENT: 1,
    StepOperations.VERIFY_RECORD_PRESENT: 2,
    StepOperations.VERIFY_RECORD_REDACTED: 3,
    StepOperations.VERIFY_RECORD_ANONYMIZED: 4,
    StepOperations.VERIFY_DATA_FLOW_DISABLED: 5,
    StepOperations.VERIFY_RESTORE_BLOCKED: 6,
}

TARGET_SYSTEMS = {
    "cache": "cache_service",
    "email_delivery": "email_delivery_service",
    "marketing": "marketing_platform",
    "tombstone": "identity_service",
}


# ============================================================================
# DOMAIN-SPECIFIC SETS & KEYWORD TUPLES
# ============================================================================

PERSONAL_INFO_FIELDS = {
    "customer_email",
    "display_name",
    "email",
    "email_hash",
    "full_name",
    "name",
    "owner_email",
    "owner_phone",
    "phone",
    "requester_email",
    "requester_name",
    "requester_phone",
}

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


# ============================================================================
# LLM PROMPTS & TEMPLATES
# ============================================================================

SYSTEM_INSTR_PROMPT = """
You are a consumer behavioral expert and data privacy compliance auditor. Your 
task is to analyze customer messages to determine if they explicitly authorize 
deleting their account, profile, or personal data.

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
Return ONLY the exact boolean value True or False.
Do not include markdown fences, prose, or explanation.
""".strip()

VALIDITY_PROMPT = """
As a user behavioral expert, analyze this user request to determine if they're 
explicitly requesting to delete, erase, close, or remove their account, profile, 
or personal data.

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
