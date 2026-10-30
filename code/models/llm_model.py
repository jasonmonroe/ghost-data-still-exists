# code/models/llm_model.py
# +---------------------------------------------------------------------------+
# |                              LLM MODEL                                    |
# +---------------------------------------------------------------------------+

import json
import time

# The Interactions API raises its own error hierarchy, which is NOT a subclass
# of google.genai.errors.APIError, so catch these classes instead.
from google import genai
from google.genai._interactions import APIConnectionError, APIStatusError
from src.constants import (
    GEMINI_API_KEY,
    GEMINI_MODEL_NAME,
    INTERNAL_STATUS_ERR_CODE,
    MAX_TOKENS,
    RATE_LIMIT_PAUSE_TIMER,
    RATE_LIMIT_RETRIES,
    RATE_LIMIT_STATUS_ERR_CODE,
    SYSTEM_INSTR_PROMPT,
)
from src.issues import ERROR, report_issue
from src.usage_tracker import UsageTracker


class LlmModel:
    def __init__(self):
        self._client = genai.Client(api_key=GEMINI_API_KEY)
        self.usage = UsageTracker()

    def get_response(self, prompt: str) -> str | dict | bool:
        """Returns a bool for True/False answers, otherwise parsed JSON or
        raw text. On failure returns {"error": True}; the caller decides the
        fallback."""
        for attempt in range(RATE_LIMIT_RETRIES):
            try:
                response = self._client.interactions.create(
                    system_instruction=SYSTEM_INSTR_PROMPT,
                    model=GEMINI_MODEL_NAME,
                    input=prompt,
                    generation_config={
                        "max_output_tokens": MAX_TOKENS,
                        "temperature": 0.0,
                        "thinking_level": "low",
                    },
                )
                return self._parse_content(self._process_response(response, prompt))

            except (APIStatusError, APIConnectionError) as e:
                # Connection errors and timeouts have no status code: retry them too.
                code = getattr(e, "status_code", INTERNAL_STATUS_ERR_CODE)
                is_retryable = (
                    isinstance(e, APIConnectionError)
                    or code == RATE_LIMIT_STATUS_ERR_CODE
                    or code >= INTERNAL_STATUS_ERR_CODE
                )

                if is_retryable and attempt < RATE_LIMIT_RETRIES - 1:
                    err_label = (
                        "Rate limit"
                        if code == RATE_LIMIT_STATUS_ERR_CODE
                        else f"Server/connection error {code}"
                    )
                    print(
                        f"\n⏸️ {err_label}. Pausing for {RATE_LIMIT_PAUSE_TIMER}s (Attempt {attempt + 1}/{RATE_LIMIT_RETRIES})..."
                    )
                    time.sleep(RATE_LIMIT_PAUSE_TIMER)
                    continue

                report_issue(ERROR, f"LLM API error code {code}: {e}")
                return {"error": True}

        return {"error": True}

    @staticmethod
    def _parse_content(content: str) -> str | dict | bool:
        """'True'/'False' -> bool (not valid JSON, so check first); else JSON; else text."""
        if not content:
            return {"error": True}

        lowered = content.strip().strip("`").strip().lower()
        if lowered in ("true", "false"):
            return lowered == "true"

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return content

    def _process_response(self, response, prompt: str):
        # Interactions API usage fields are total_*; thought tokens are billed as output.
        usage = getattr(response, "usage", None)
        if usage:
            self.usage.record(
                model=getattr(response, "model", None) or GEMINI_MODEL_NAME,
                input_tokens=usage.total_input_tokens or 0,
                output_tokens=(usage.total_output_tokens or 0)
                + (usage.total_thought_tokens or 0),
                prompt=prompt,
                response_id=getattr(response, "id", None),
            )

        content = getattr(response, "output_text", None)
        if isinstance(content, str):
            return content.strip()

        return str(response)
