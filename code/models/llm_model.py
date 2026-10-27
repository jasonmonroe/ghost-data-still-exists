# 🚨
# ⚠️
# 💡


# models/llm_model.py
# +---------------------------------------------------------------------------+
# |                              LLM MODEL                                    |
# +---------------------------------------------------------------------------+


import json
import re
import time

from openai import InternalServerError, OpenAI, RateLimitError
from openai.types.chat import ChatCompletion
from src.constants import (
    MAX_TOKENS,
    MODEL_API_KEY,
    MODEL_API_URL,
    MODEL_NAME,
    RATE_LIMIT_PAUSE_TIMER,
    RATE_LIMIT_RETRIES,
    SYSTEM_INSTR_PROMPT,
)
from src.usage_tracker import UsageTracker


class LlmModel:
    def __init__(self):
        self._client = self._load()
        self.usage = UsageTracker()

    def _load(self):
        return OpenAI(
            base_url=MODEL_API_URL,
            api_key=MODEL_API_KEY,
            timeout=120,  # ⏱️ Kill the connection if it hangs over 120 seconds
            max_retries=RATE_LIMIT_RETRIES,  # 🔄 Automatically back off and retry 3 times natively
        )

    def get_response(self, prompt: str) -> dict:

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
                    top_p=1.0,
                    timeout=90.0,
                )

                if getattr(response, "usage", None):
                    self.usage.record(
                        model=response.model or MODEL_NAME,
                        input_tokens=response.usage.prompt_tokens or 0,
                        output_tokens=response.usage.completion_tokens or 0,
                    )

                return self._filter_response(response)

            except InternalServerError as e:
                print(f"🚨 Server error encountered (503/5xx): {e} 🚨")
                return {}  # Return safe empty list so downstream code doesn't crash on None

            except RateLimitError:
                if attempt >= RATE_LIMIT_RETRIES - 1:
                    print(
                        "\n🚨 Request has exceeded the maximum amount of retries! Returning {error: True}. 🚨"
                    )

                    return {"error": True}

                attempt = self._handle_rate_limit_error(attempt)

                attempt += 1

            except Exception as e:
                print(f"\n🚨 Unexpected API error occurred: {e} 🚨")
                return {}

    def _handle_rate_limit_error(self, attempt: int) -> int:
        print(f"\n🚨 Rate limit / Quota exceeded (429) on attempt: {attempt} 🚨")

        body = e.body[0] if isinstance(e.body, list) else e.body
        error_message = body.get("error", {}).get("message", [])
        print(f"\n🚨 {error_message} 🚨")

        # You can parse the retry delay or default to a safe pause
        delay_time = self._parse_delay_time(error_message)
        # log_chat_transcript("RATE LIMIT ERROR", error_message)
        print(f"\n⏸️  Pausing for {delay_time} seconds ...")

        time.sleep(delay_time)

        return attempt

    def _parse_delay_time(self, error_message: str) -> int | float:
        # Let's attempt to use the vendor's response delay time suggestion instead of our own.
        err = error_message.lower()
        anchor_str = "please retry in "
        end_char = "s"  # Safely skips the decimal point

        if anchor_str not in err or end_char not in err:
            return RATE_LIMIT_PAUSE_TIMER

        # Anchor string has been found!
        # Cherry pick their delay time by getting the start and end string positions. Then remove the `s` for seconds and convert to a float.
        start_pos = err.find(anchor_str) + len(anchor_str)
        end_pos = err.find(end_char, start_pos)

        delay_time_str = err[start_pos:end_pos]
        delay_time = float(delay_time_str.replace("s", ""))

        # Just in case the vendor's delay time is long we will override it.
        if delay_time > (RATE_LIMIT_PAUSE_TIMER * 2):
            return RATE_LIMIT_PAUSE_TIMER

        return delay_time

    def _filter_response(self, response: ChatCompletion) -> dict:
        content_str = ""
        try:
            if hasattr(response, "choices") and response.choices:
                choice = response.choices[0]
                content_str = choice.message.content or ""
            elif hasattr(response, "content"):
                content_str = response.content or ""
            elif isinstance(response, str):
                content_str = response
            else:
                content_str = str(response)

            if not content_str or not content_str.strip():
                return {}

            cleaned_str = content_str.strip()

            # 1. Strip markdown code fence markers if present
            cleaned_str = re.sub(
                r"^```(?:json)?\s*", "", cleaned_str, flags=re.MULTILINE
            )
            cleaned_str = re.sub(
                r"\s*```$", "", cleaned_str, flags=re.MULTILINE
            ).strip()

            # 2. Extract strictly from the FIRST '{' to the LAST '}' (Greedy search)
            start_idx = cleaned_str.find("{")
            end_idx = cleaned_str.rfind("}")

            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                cleaned_str = cleaned_str[start_idx : end_idx + 1]
            elif start_idx != -1:
                # Auto-repair if the output was cut off before the closing brace
                cleaned_str = cleaned_str[start_idx:]
                if not cleaned_str.endswith("}"):
                    cleaned_str += "\n}"

            # 3. Parse JSON safely
            content = json.loads(cleaned_str.strip())
            return content

        except (AttributeError, IndexError, json.JSONDecodeError) as e:
            print(f"🚨 Error occurred while parsing response: {e} 🚨")
            print(f" `repr(content_str)` was: {content_str!r}")
            return {}
