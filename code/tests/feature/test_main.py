# code/tests/feature/test_main.py
# `python code/main.py` end to end: pipeline -> output.csv -> scorer -> issues.
# Gemini is faked and every written file is redirected to tmp_path.

import re
import runpy

import pandas as pd
import pytest

pytestmark = pytest.mark.slow


def test_main_runs_end_to_end(fake_gemini, outputs, capsys, monkeypatch):
    fake = fake_gemini(["True"])
    monkeypatch.setattr("sys.argv", ["code/main.py"])

    runpy.run_path("code/main.py", run_name="__main__")

    out = re.sub(r"\x1b\[[0-9;]*m", "", capsys.readouterr().out)

    # output.csv (redirected) in the graded format
    saved = pd.read_csv(outputs.output)
    assert list(saved.columns) == ["case_id", "deletion_status", "steps_json"]
    assert len(saved) == 32
    assert saved["case_id"].is_monotonic_increasing

    # banner, scorer, usage, issues, timer — in that order
    for marker in ["GHOST DATA STILL EXISTS", "AUDIT SCORER (SAMPLE MODE)",
                   "MODEL USAGE & TOKEN COST REPORT", "RUN WARNINGS & ERRORS",
                   "Time Taken", "End of Program"]:
        assert marker in out, marker
    assert out.index("AUDIT SCORER") < out.index("RUN WARNINGS")

    assert f"Total Model Calls:     {len(fake.calls)}" in out


def test_main_survives_depleted_credits(fake_gemini, outputs, capsys, monkeypatch):
    """No Gemini credits: every unclear request falls back to 'deletion'."""
    import httpx
    from google.genai._interactions import APIStatusError

    request = httpx.Request("POST", "https://x")
    fake_gemini([APIStatusError("credits", response=httpx.Response(402, request=request), body=None)])
    monkeypatch.setattr("sys.argv", ["code/main.py"])

    runpy.run_path("code/main.py", run_name="__main__")

    out = capsys.readouterr().out
    assert len(pd.read_csv(outputs.output)) == 32
    assert re.search(r"\[ERROR\] x\d+ LLM API error code 402", re.sub(r"\x1b\[[0-9;]*m", "", out))
    assert "Defaulting validity to True" in out
