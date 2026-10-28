# /code/src/enums.py
# +---------------------------------------------------------------------------+
# |                               ENUMERATIONS                                |
# +---------------------------------------------------------------------------+

# Enums for the application
from enum import Enum


class DeletionStatus(Enum):
    #  The data is truly gone (or properly anonymized/retained according to strict company policy), and you can prove it with evidence.
    COMPLETE = "COMPLETE"

    # Ghost data still exists, or an active process/backup can bring the data back to life.
    INCOMPLETE = "INCOMPLETE"

    # The user didn't actually request a deletion.
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ReportedStatus(Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIALLY_COMPLETE"
    NOT_STARTED = "NOT_STARTED"


class StepPhrases(Enum):
    FINDING = "FINDING"
    REMEDIATION = "REMEDIATION"
    VERIFICATION = "VERIFICATION"


class StepOperations(Enum):
    REPORT_REMAINING_RECORD = "REPORT_REMAINING_RECORD"
    REPORT_EXPOSED_PII = "REPORT_EXPOSED_PII"
    REPORT_ACTIVE_DATA_FLOW = "REPORT_ACTIVE_DATA_FLOW"
    REPORT_RESTORE_RISK = "REPORT_RESTORE_RISK"
    DISABLE_DATA_FLOW = "DISABLE_DATA_FLOW"
    BLOCK_RESTORE = "BLOCK_RESTORE"
    DELETE_RECORD = "DELETE_RECORD"
    REDACT_RECORD = "REDACT_RECORD"
    ANONYMIZE_RECORD = "ANONYMIZE_RECORD"
    VERIFY_RECORD_ABSENT = "VERIFY_RECORD_ABSENT"
    VERIFY_RECORD_PRESENT = "VERIFY_RECORD_PRESENT"
    VERIFY_RECORD_REDACTED = "VERIFY_RECORD_REDACTED"
    VERIFY_RECORD_ANONYMIZED = "VERIFY_RECORD_ANONYMIZED"
    VERIFY_DATA_FLOW_DISABLED = "VERIFY_DATA_FLOW_DISABLED"
    VERIFY_RESTORE_BLOCKED = "VERIFY_RESTORE_BLOCKED"


class StepStates(Enum):
    PRESENT = "PRESENT"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    ABSENT = "ABSENT"
    REDACTED = "REDACTED"
    ANONYMIZED = "ANONYMIZED"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"  # non-official
