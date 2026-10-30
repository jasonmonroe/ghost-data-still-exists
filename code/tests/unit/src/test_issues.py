# code/tests/unit/src/test_issues.py

from src.issues import ERROR, WARNING, get_issues, report_issue, summarize_issues


def test_report_issue_prints_with_icon_and_records(capsys):
    report_issue(ERROR, "boom")
    report_issue(WARNING, "careful")

    out = capsys.readouterr().out
    assert "🚨 Error: boom" in out
    assert "⚠️ Warning: careful" in out
    assert get_issues() == [(ERROR, "boom"), (WARNING, "careful")]


def test_get_issues_returns_a_copy():
    report_issue(WARNING, "x")
    snapshot = get_issues()
    snapshot.clear()
    assert get_issues() == [(WARNING, "x")]


def test_summarize_groups_messages_that_differ_only_by_case_id():
    report_issue(WARNING, "Case case_01: LLM could not classify the request.")
    report_issue(WARNING, "Case case_02: LLM could not classify the request.")
    report_issue(ERROR, "LLM API error code 402")

    assert summarize_issues() == [
        (ERROR, "LLM API error code 402", 1),
        (WARNING, "Case <case>: LLM could not classify the request.", 2),
    ]


def test_summarize_is_empty_without_issues():
    assert summarize_issues() == []
