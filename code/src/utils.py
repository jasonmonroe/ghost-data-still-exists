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
    """Seconds -> 'Xh Ym Zs N.NNNms', e.g. 3725.5 -> '1h 2m 5s 500.000ms'."""
    hrs, remainder = divmod(duration, SECONDS_IN_HR)
    mins, remainder = divmod(remainder, SECONDS_IN_MIN)
    secs, fraction = divmod(remainder, 1)

    msec = f"{fraction * SECONDS_TO_MSEC:.3f}"

    return f"{int(hrs)}h {int(mins)}m {int(secs)}s {msec}ms"


def get_progress_bar(done: int, total: int) -> str:
    """
    Progress of the case audit.
    :param done: number of cases finished so far (1-based: 1 after the first case)
    :param total: total number of cases
    :return: one ✅ per finished case, ☑️ for the rest, then 'done / total  pct%'
    """
    print()

    i_empty, i_full = "☑️ ", "✅️ "
    completion_pct = (done / total) * 100

    graphic = "".join(i_full if i < done else i_empty for i in range(total))

    return graphic + f"\t{done} / {total}\t{completion_pct:.1f}%"


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


def normalize_resource(value) -> str:
    """Normalize resource IDs, treating None, 'None', 'null', and empty strings uniformly."""
    cleaned = clean_str(value)
    if cleaned.lower() in ("none", "null", ""):
        return ""
    return cleaned
