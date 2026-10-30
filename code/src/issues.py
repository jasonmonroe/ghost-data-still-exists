# /code/src/issues.py
# +---------------------------------------------------------------------------+
# |                              RUN ISSUES                                   |
# +---------------------------------------------------------------------------+
# Collects warnings and errors raised while a run is in progress so the
# evaluation can list them at the end. Laravel parallel: a tiny Log::channel
# that also keeps an in-memory copy for the final report.

import re

WARNING = "WARNING"
ERROR = "ERROR"

_issues: list[tuple[str, str]] = []


def report_issue(level: str, message: str) -> None:
    """Print the issue now (with its icon) and remember it for the summary."""
    icon = "🚨" if level == ERROR else "⚠️"
    print(f"{icon} {level.title()}: {message}")
    _issues.append((level, message))


def get_issues() -> list[tuple[str, str]]:
    return list(_issues)


def summarize_issues() -> list[tuple[str, str, int]]:
    """(level, message, count) with case ids collapsed so repeats group together."""
    counts: dict[tuple[str, str], int] = {}
    for level, message in _issues:
        key = (level, re.sub(r"\bcase_\w+\b", "<case>", message))
        counts[key] = counts.get(key, 0) + 1
    return [(lvl, msg, n) for (lvl, msg), n in sorted(counts.items())]
