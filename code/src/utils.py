# /code/src/utils.py

# Utils for the application

# Python Libraries
import time
import uuid

# Vendor Libraries
import pandas as pd

# Local Libraries
from src.constants import (
    BANNER_PADDING,
    PEP8_LINE_LEN,
    SECONDS_IN_HR,
    SECONDS_IN_MIN,
    SECONDS_TO_MSEC,
)


def banner(title: str) -> None:
    banner_length = PEP8_LINE_LEN - BANNER_PADDING
    top_btm = f"+{'-' * banner_length}+"

    # Calculate padding for centering the title within the banner width
    total_padding = (
        banner_length - len(title) - BANNER_PADDING
    )  # Subtract 2 for the spaces framing the title
    pad_left = max(0, total_padding // 2) - 2
    pad_right = max(0, total_padding - pad_left) - 2

    print(top_btm)
    print(f"| {' ' * pad_left}👻{title.upper()}👻{' ' * pad_right} |")
    print(top_btm)
    print()


def format_time(duration: float) -> str:
    hrs = 0
    mins = 0
    secs = 0
    msec = 0

    if duration > SECONDS_IN_HR:
        hrs = duration // SECONDS_IN_HR
        duration = duration % SECONDS_IN_HR
    if duration > SECONDS_IN_MIN:
        mins = duration // SECONDS_IN_MIN
        duration = duration % SECONDS_IN_MIN

    duration_ms = duration * SECONDS_TO_MSEC
    msec = f"{duration_ms:.3f}"

    return f"{hrs}h {mins}m {secs}s {msec}ms"


def get_date():
    return time.strftime("%Y-%m-%d")


def get_progress_bar(idx: int, total: int) -> str:
    """
    Displays progress of claim analysis.

    :param idx:
    :param total:
    :return:
    """
    print()

    i_empty, i_full = "☑️ ", "✅️ "
    completion_pct = ((idx + 1) / total) * 100

    graphic = ""
    for i in range(total):
        graphic += i_full if i <= idx else i_empty

    return graphic + f"\t{idx} / {total}\t{completion_pct:.1f}%"


def get_run_id() -> str:
    return str(uuid.uuid4()).upper()[0:6]


def get_time() -> float:
    return time.time()


def start_timer() -> float:
    return get_time()


def stop_timer(start_time: float) -> float:
    return get_time() - start_time


def show_time(time_taken: float) -> None:
    print(f"\n⏱ Time Taken: {format_time(time_taken)}")


def prefix_of(resource_id: str) -> str:
    """Return the record-type prefix of a resource id: 'audit_record_265' -> 'audit_record'."""
    return resource_id.rsplit("_", 1)[0]


def clean_str(value) -> str:
    """Return a stripped string; None and NaN (empty pandas cells) become ""."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()
