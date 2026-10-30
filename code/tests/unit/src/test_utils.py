# code/tests/unit/src/test_utils.py

import math
import re

import pytest
from src import utils
from src.utils import (
    banner,
    clean_str,
    format_time,
    get_progress_bar,
    get_run_id,
    normalize_resource,
    prefix_of,
    show_time,
    start_timer,
    stop_timer,
)


class TestFormatTime:
    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [
            (0, "0h 0m 0s 0.000ms"),
            (13.054086, "0h 0m 13s 54.086ms"),
            (60, "0h 1m 0s 0.000ms"),
            (3600, "1h 0m 0s 0.000ms"),
            (3725.5, "1h 2m 5s 500.000ms"),
        ],
    )
    def test_splits_into_hours_minutes_seconds_and_ms(self, seconds, expected):
        assert format_time(seconds) == expected

    def test_show_time_prints_formatted_duration(self, capsys):
        show_time(61)
        assert "⏱ Time Taken: 0h 1m 1s 0.000ms" in capsys.readouterr().out


class TestProgressBar:
    def test_first_of_three(self):
        bar = get_progress_bar(1, 3)
        assert bar.count("✅") == 1
        assert bar.endswith("\t1 / 3\t33.3%")

    def test_last_case_is_exactly_100_percent(self):
        bar = get_progress_bar(32, 32)
        assert bar.count("✅") == 32
        assert bar.endswith("\t32 / 32\t100.0%")


def test_banner_wraps_uppercased_title(capsys):
    banner("ghost data")
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("+") and lines[0].endswith("+")
    assert "👻GHOST DATA👻" in lines[1]
    assert lines[2] == lines[0]


def test_run_id_is_six_uppercase_hex_chars():
    run_id = get_run_id()
    assert re.fullmatch(r"[0-9A-F]{6}", run_id)


def test_timer_measures_elapsed_time(monkeypatch):
    clock = iter([100.0, 102.5])
    monkeypatch.setattr(utils, "get_time", lambda: next(clock))
    start = start_timer()
    assert stop_timer(start) == pytest.approx(2.5)


@pytest.mark.parametrize(
    ("resource_id", "prefix"),
    [
        ("account_001", "account"),
        ("audit_record_265", "audit_record"),
        ("email_delivery_8297", "email_delivery"),
        ("data_flow_9846", "data_flow"),
    ],
)
def test_prefix_of(resource_id, prefix):
    assert prefix_of(resource_id) == prefix


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        (float("nan"), ""),
        ("  a@b.com ", "a@b.com"),
        (42, "42"),
        ("", ""),
    ],
)
def test_clean_str(value, expected):
    assert clean_str(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        ("None", ""),
        ("null", ""),
        ("  NULL ", ""),
        (math.nan, ""),
        (" account_001 ", "account_001"),
    ],
)
def test_normalize_resource(value, expected):
    assert normalize_resource(value) == expected
