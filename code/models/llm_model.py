# code/models/llm_model.py
# +---------------------------------------------------------------------------+
# |                              LLM MODEL                                    |
# +---------------------------------------------------------------------------+

import json
import time

from google import genai
from google.genai.errors import APIError
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
from src.usage_tracker import UsageTracker


class LlmModel:
    def __init__(self):
        self._client = genai.Client(api_key=GEMINI_API_KEY)
        self.usage = UsageTracker()

    def get_response(self, prompt: str) -> str | dict | bool:
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
                content = self._process_response(response, prompt)
                return json.loads(content) if content else {}

            except APIError as e:
                code = getattr(e, "code", INTERNAL_STATUS_ERR_CODE)
                is_retryable = (
                    code == RATE_LIMIT_STATUS_ERR_CODE
                    or code >= INTERNAL_STATUS_ERR_CODE
                )

                if is_retryable and attempt < RATE_LIMIT_RETRIES - 1:
                    err_label = (
                        "Rate limit"
                        if code == RATE_LIMIT_STATUS_ERR_CODE
                        else f"Server error {code}"
                    )
                    print(
                        f"\n⏸️ {err_label}. Pausing for {RATE_LIMIT_PAUSE_TIMER}s (Attempt {attempt + 1}/{RATE_LIMIT_RETRIES})..."
                    )
                    time.sleep(RATE_LIMIT_PAUSE_TIMER)
                    continue

                print(f"\n🚨 API Error Code {code}: {e}")
                return {"error": True}

            except (json.JSONDecodeError, TypeError) as e:
                print(f"\n🚨 Failed to parse LLM response JSON: {e}")
                return {"error": True}

        return {"error": True}

    def _process_response(self, response, prompt: str):
        print(response)
        self.usage.response_id = response.id
        if getattr(response, "usage", None):
            self.usage.record(
                model=response.model or GEMINI_MODEL_NAME,
                input_tokens=response.usage.prompt_tokens or 0,
                output_tokens=response.usage.completion_tokens or 0,
                prompt=prompt,
            )

        content = getattr(response, "output_text", None)
        if isinstance(content, str):
            return content.strip()

        return str(response)
