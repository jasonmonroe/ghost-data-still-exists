# /code/src/enums.py

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
