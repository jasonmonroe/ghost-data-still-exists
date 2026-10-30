# code/tests/unit/models/test_llm_model.py
# The Gemini client is replaced by FakeInteractions (see conftest.py), so
# these tests never hit the network or spend credits.

import httpx
import pytest
from google.genai._interactions import APIConnectionError, APIStatusError
from models.llm_model import LlmModel
from src.issues import get_issues

REQUEST = httpx.Request("POST", "https://generativelanguage.googleapis.com")


def status_error(code: int, message: str = "boom") -> APIStatusError:
    return APIStatusError(message, response=httpx.Response(code, request=REQUEST), body=None)


def connection_error() -> APIConnectionError:
    return APIConnectionError(request=REQUEST)


class TestParseContent:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("True", True),
            ("false", False),
            ("  TRUE \n", True),
            ("`True`", True),
            ('{"a": 1}', {"a": 1}),
            ("[1, 2]", [1, 2]),
            ("Yes, the user wants deletion", "Yes, the user wants deletion"),
        ],
    )
    def test_bools_then_json_then_text(self, raw, expected):
        assert LlmModel._parse_content(raw) == expected

    @pytest.mark.parametrize("raw", ["", None])
    def test_empty_reply_is_an_error(self, raw):
        assert LlmModel._parse_content(raw) == {"error": True}


class TestGetResponse:
    def test_returns_parsed_bool_and_sends_the_prompt(self, fake_gemini):
        fake = fake_gemini(["True"])
        assert LlmModel().get_response("is this a deletion?") is True
        (call,) = fake.calls
        assert call["input"] == "is this a deletion?"
        assert call["generation_config"]["temperature"] == 0.0

    def test_records_token_usage_including_thought_tokens(self, fake_gemini):
        fake_gemini(["True"])
        model = LlmModel()
        model.get_response("p")
        usage = model.usage.by_model()["fake-model"]
        assert (usage.calls, usage.input_tokens, usage.output_tokens) == (1, 100, 10)
        assert usage.most["response_id"] == "resp_1"
        assert usage.most["prompt"] == "p"

    @pytest.mark.parametrize("error", [status_error(429), status_error(503), connection_error()])
    def test_retries_transient_errors_then_succeeds(self, fake_gemini, error):
        fake = fake_gemini([error, "false"])
        assert LlmModel().get_response("p") is False
        assert len(fake.calls) == 2
        assert get_issues() == []

    def test_non_retryable_error_returns_error_immediately(self, fake_gemini):
        fake = fake_gemini([status_error(402, "credits depleted")])
        assert LlmModel().get_response("p") == {"error": True}
        assert len(fake.calls) == 1
        level, message = get_issues()[0]
        assert level == "ERROR" and "402" in message

    def test_gives_up_after_max_retries(self, fake_gemini):
        from src.constants import RATE_LIMIT_RETRIES

        fake = fake_gemini([status_error(429)])
        assert LlmModel().get_response("p") == {"error": True}
        assert len(fake.calls) == RATE_LIMIT_RETRIES

    def test_response_without_usage_or_text_is_handled(self, fake_gemini, monkeypatch):
        import types

        import models.llm_model as llm_module

        class Bare:
            def create(self, **kw):
                return types.SimpleNamespace(id="r", usage=None, output_text=None)

        monkeypatch.setattr(
            llm_module.genai, "Client", lambda **kw: types.SimpleNamespace(interactions=Bare())
        )
        model = LlmModel()
        # No output_text: falls back to str(response), which is neither bool nor JSON
        assert isinstance(model.get_response("p"), str)
        assert model.usage.by_model() == {}
