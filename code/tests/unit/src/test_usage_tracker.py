# code/tests/unit/src/test_usage_tracker.py

from src.constants import MAX_TOKENS
from src.usage_tracker import ModelUsage, UsageTracker


def test_model_usage_defaults():
    usage = ModelUsage()
    assert (usage.calls, usage.input_tokens, usage.output_tokens) == (0, 0, 0)
    assert usage.total_tokens == 0
    assert usage.least["tokens"] == MAX_TOKENS * 2
    assert usage.most["tokens"] == 0


def test_model_usage_default_dicts_are_not_shared():
    a, b = ModelUsage(), ModelUsage()
    a.least["tokens"] = 1
    assert b.least["tokens"] == MAX_TOKENS * 2


def test_record_accumulates_per_model():
    tracker = UsageTracker()
    tracker.record("m1", 100, 10, "p1", "r1")
    tracker.record("m1", 50, 5, "p2", "r2")
    tracker.record("m2", 7, 3, "p3", "r3")

    m1 = tracker.by_model()["m1"]
    assert (m1.calls, m1.input_tokens, m1.output_tokens) == (2, 150, 15)
    assert m1.total_tokens == 165
    assert m1.response_id == "r2"  # last response seen


def test_record_tracks_least_and_most_expensive_prompts():
    tracker = UsageTracker()
    tracker.record("m", 100, 10, "big", "r-big")
    tracker.record("m", 5, 1, "small", "r-small")
    tracker.record("m", 50, 5, "mid", "r-mid")

    usage = tracker.by_model()["m"]
    assert usage.least == {"response_id": "r-small", "prompt": "small", "tokens": 6}
    assert usage.most == {"response_id": "r-big", "prompt": "big", "tokens": 110}


def test_totals_sum_every_model():
    tracker = UsageTracker()
    tracker.record("m1", 10, 1, "a", "1")
    tracker.record("m2", 20, 2, "b", "2")

    totals = tracker.totals()
    assert (totals.calls, totals.input_tokens, totals.output_tokens) == (2, 30, 3)
    assert totals.total_tokens == 33


def test_by_model_returns_a_copy():
    tracker = UsageTracker()
    tracker.record("m", 1, 1, "p", "r")
    tracker.by_model().clear()
    assert "m" in tracker.by_model()


def test_empty_tracker():
    tracker = UsageTracker()
    assert tracker.by_model() == {}
    assert tracker.totals().calls == 0
