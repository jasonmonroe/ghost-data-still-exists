# code/models/llm_model.py
# +---------------------------------------------------------------------------+
# |                              LLM MODEL                                    |
# +---------------------------------------------------------------------------+
# https://ai.google.dev/gemini-api/docs/models

import json
import time

from google import genai
from google.genai.errors import APIError  # Or general Exception
from src.constants import (
    INTERNAL_STATUS_ERR_CODE,
    MAX_TOKENS,
    MODEL_NAME,
    RATE_LIMIT_PAUSE_TIMER,
    RATE_LIMIT_RETRIES,
    RATE_LIMIT_STATUS_ERR_CODE,
    SYSTEM_INSTR_PROMPT,
)
from src.usage_tracker import UsageTracker


class LlmModel:
    def __init__(self):

        self._client = genai.Client()
        self.usage = UsageTracker()

    def get_response(self, prompt: str) -> str | dict:
        attempt = 0
        while attempt < RATE_LIMIT_RETRIES:
            try:
                response = self._client.interactions.create(
                    system_instruction=SYSTEM_INSTR_PROMPT,
                    model=MODEL_NAME,
                    input=prompt,
                    tools=[{"type": "google_search"}],
                    generation_config={
                        "max_output_tokens": MAX_TOKENS,
                        "temperature": 0.0,
                        "thinking_level": "low",
                    },
                )
                # Process and format response
                content = self._process_response(response, prompt)

                return json.loads(content) if content else {}

            except APIError as e:
                if (
                    attempt >= RATE_LIMIT_RETRIES - 1
                    and e.code == RATE_LIMIT_STATUS_ERR_CODE
                ):
                    print("\n🚨 Max retries reached for rate limit. 🚨")
                    return {"error": True}

                if e.code == RATE_LIMIT_STATUS_ERR_CODE:
                    print(
                        f"\n⏸️ Rate limit hit. Pausing for {RATE_LIMIT_PAUSE_TIMER}s..."
                    )
                    time.sleep(RATE_LIMIT_PAUSE_TIMER)
                    attempt += 1

                elif e.code >= INTERNAL_STATUS_ERR_CODE:
                    print(f"\n🚨 Google server error {e.code}: Temporary Issue")
                else:
                    print(f"🚨 API Error Code! {e}")

                return {"error": True}

    def _process_response(self, response, prompt: str):
        print(f"response datatype: {type(response)}")
        print(json.dumps(response))

        # Track token usage for your usage_report.md
        # @TODO - find out if Gemini has a usage attr
        self.usage.response_id = response.id
        if getattr(response, "usage", None):
            self.usage.record(
                model=response.model or MODEL_NAME,
                input_tokens=response.usage.prompt_tokens or 0,
                output_tokens=response.usage.completion_tokens or 0,
                prompt=prompt,
            )
        else:
            print()

        # Send content of response back to source
        content = response.output_text

        if isinstance(content, str):
            return content.strip()

        print("⚠️ Warning: Response did not extract content.")
        return response

    """
    # @depracated
    def get_response_openai(self, prompt: str) -> dict:
        attempt = 0
        while attempt < RATE_LIMIT_RETRIES:
            try:
                response = self._client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=[
                        {"role": "system", "content": SYSTEM_INSTR_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.0,
                    max_completion_tokens=MAX_TOKENS,
                    response_format={"type": "json_object"},
                )

                # Track token usage for your usage_report.md
                if getattr(response, "usage", None):
                    self.usage.record(
                        model=response.model or MODEL_NAME,
                        input_tokens=response.usage.prompt_tokens or 0,
                        output_tokens=response.usage.completion_tokens or 0,
                    )

                content = response.choices[0].message.content
                return json.loads(content) if content else {}

            except RateLimitError:
                if attempt >= RATE_LIMIT_RETRIES - 1:
                    print("\n🚨 Max retries reached for rate limit. 🚨")
                    return {"error": True}

                print(f"\n⏸️ Rate limit hit. Pausing for {RATE_LIMIT_PAUSE_TIMER}s...")
                time.sleep(RATE_LIMIT_PAUSE_TIMER)
                attempt += 1

            except (InternalServerError, Exception) as e:
                print(f"\n🚨 API error encountered: {e} 🚨")
                return {}

        return {}
    """
